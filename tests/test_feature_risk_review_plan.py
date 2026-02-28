# -*- coding: utf-8 -*-

import json
import os
import tempfile
import time

import jwt
import pytest
from jwt.utils import base64url_encode


def _register(client, username: str, password: str = "Password123!", nickname: str | None = None):
    r = client.post(
        "/api/register",
        json={"username": username, "password": password, "nickname": nickname or username},
    )
    assert r.status_code == 200
    assert r.json.get("success") is True


def _login(client, username: str, password: str = "Password123!"):
    r = client.post("/api/login", json={"username": username, "password": password})
    assert r.status_code == 200
    assert r.json.get("success") is True


def _create_room(client, members=None, name="room"):
    r = client.post("/api/rooms", json={"name": name, "members": members or []})
    assert r.status_code == 200
    assert r.json.get("success") is True
    return r.json["room_id"]


def _create_socket_client(app, flask_client):
    from app import socketio

    sc = socketio.test_client(app, flask_test_client=flask_client)
    assert sc.is_connected()
    return sc


def _first_event(received, name):
    for evt in received:
        if evt.get("name") == name:
            args = evt.get("args") or []
            return args[0] if args else {}
    return None


def _oct_jwk(secret: bytes, kid: str):
    return {
        "kty": "oct",
        "kid": kid,
        "alg": "HS256",
        "use": "sig",
        "k": base64url_encode(secret).decode("ascii"),
    }


def _write_jwks_file(jwks: dict) -> str:
    fd, path = tempfile.mkstemp(prefix="oidc-jwks-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(jwks, f)
    return "file:///" + path.replace("\\", "/")


def test_advanced_search_rejects_invalid_limit_and_offset(client):
    _register(client, "adv_search_user")
    _login(client, "adv_search_user")

    r1 = client.post("/api/search/advanced", json={"query": "hello", "limit": "abc"})
    assert r1.status_code == 400
    assert r1.json.get("code") == "invalid_limit"

    r2 = client.post("/api/search/advanced", json={"query": "hello", "offset": "x"})
    assert r2.status_code == 400
    assert r2.json.get("code") == "invalid_offset"


def test_leave_room_is_idempotent_with_flags(client):
    _register(client, "leave_flag_user")
    _login(client, "leave_flag_user")
    room_id = _create_room(client, name="leave-flag-room")

    first = client.post(f"/api/rooms/{room_id}/leave")
    assert first.status_code == 200
    assert first.json == {"success": True, "left": True, "already_left": False}

    second = client.post(f"/api/rooms/{room_id}/leave")
    assert second.status_code == 200
    assert second.json == {"success": True, "left": False, "already_left": True}


def test_socket_room_members_updated_denies_non_member(app):
    c1 = app.test_client()
    c2 = app.test_client()
    c3 = app.test_client()

    _register(c1, "rm_owner")
    _register(c1, "rm_member")
    _register(c1, "rm_outsider")
    _login(c1, "rm_owner")

    users = c1.get("/api/users").json
    member_id = next(u["id"] for u in users if u["username"] == "rm_member")
    room_id = _create_room(c1, members=[member_id], name="rm-room")

    _login(c2, "rm_member")
    _login(c3, "rm_outsider")

    sc3 = _create_socket_client(app, c3)
    try:
        sc3.emit("room_members_updated", {"room_id": room_id})
        received = sc3.get_received()
        assert _first_event(received, "room_members_updated") is None
        assert _first_event(received, "error") is not None
    finally:
        sc3.disconnect()


def test_socket_reaction_updated_ignores_client_payload(app):
    c1 = app.test_client()
    c2 = app.test_client()

    _register(c1, "rx_owner")
    _register(c1, "rx_member")
    _login(c1, "rx_owner")
    users = c1.get("/api/users").json
    member_id = next(u["id"] for u in users if u["username"] == "rx_member")
    room_id = _create_room(c1, members=[member_id], name="rx-room")
    _login(c2, "rx_member")

    sc1 = _create_socket_client(app, c1)
    sc2 = _create_socket_client(app, c2)
    try:
        sc1.emit("send_message", {"room_id": room_id, "content": "hello", "type": "text", "encrypted": False})
        m_evt = _first_event(sc1.get_received(), "new_message")
        assert m_evt and m_evt.get("id")
        message_id = m_evt["id"]

        api_reaction = c2.post(f"/api/messages/{message_id}/reactions", json={"emoji": "👍"})
        assert api_reaction.status_code == 200
        canonical = api_reaction.json.get("reactions")
        assert isinstance(canonical, list)

        sc1.get_received()
        sc2.emit(
            "reaction_updated",
            {
                "room_id": room_id,
                "message_id": message_id,
                "reactions": [{"emoji": "X", "count": 999, "user_ids": [999]}],
            },
        )
        rx_evt = _first_event(sc1.get_received(), "reaction_updated")
        assert rx_evt is not None
        assert rx_evt.get("room_id") == room_id
        assert rx_evt.get("message_id") == message_id
        assert rx_evt.get("reactions") == canonical
    finally:
        sc1.disconnect()
        sc2.disconnect()


def test_socket_poll_updated_ignores_client_payload(app):
    c1 = app.test_client()
    c2 = app.test_client()

    _register(c1, "poll_owner2")
    _register(c1, "poll_member2")
    _login(c1, "poll_owner2")
    users = c1.get("/api/users").json
    member_id = next(u["id"] for u in users if u["username"] == "poll_member2")
    room_id = _create_room(c1, members=[member_id], name="poll-room2")
    _login(c2, "poll_member2")

    poll_resp = c1.post(f"/api/rooms/{room_id}/polls", json={"question": "Q?", "options": ["A", "B"]})
    assert poll_resp.status_code == 200
    poll_id = poll_resp.json["poll"]["id"]
    option_id = poll_resp.json["poll"]["options"][0]["id"]

    vote = c2.post(f"/api/polls/{poll_id}/vote", json={"option_id": option_id})
    assert vote.status_code == 200
    canonical = dict(vote.json["poll"])
    canonical.pop("my_votes", None)

    sc1 = _create_socket_client(app, c1)
    sc2 = _create_socket_client(app, c2)
    try:
        sc1.get_received()
        sc2.emit("poll_updated", {"room_id": room_id, "poll_id": poll_id, "poll": {"id": poll_id, "question": "FAKE"}})
        evt = _first_event(sc1.get_received(), "poll_updated")
        assert evt is not None
        assert evt.get("room_id") == room_id
        assert evt["poll"]["id"] == poll_id
        assert evt["poll"] == canonical
        assert "my_votes" not in evt["poll"]
    finally:
        sc1.disconnect()
        sc2.disconnect()


def test_socket_profile_updated_ignores_client_payload(app):
    c1 = app.test_client()
    c2 = app.test_client()

    _register(c1, "profile_observer")
    _register(c1, "profile_actor")
    _login(c1, "profile_observer")
    _login(c2, "profile_actor")

    update = c2.put("/api/profile", json={"nickname": "RealName", "status_message": "hello"})
    assert update.status_code == 200

    sc1 = _create_socket_client(app, c1)
    sc2 = _create_socket_client(app, c2)
    try:
        sc1.get_received()
        sc2.emit("profile_updated", {"nickname": "FORGED", "profile_image": "/profiles/fake.png"})
        evt = _first_event(sc1.get_received(), "user_profile_updated")
        assert evt is not None
        assert evt.get("nickname") == "RealName"
    finally:
        sc1.disconnect()
        sc2.disconnect()


def test_pin_updated_socket_does_not_create_system_message_and_is_rate_limited(app):
    app.config["SOCKET_PIN_UPDATED_PER_MINUTE"] = 1
    c1 = app.test_client()
    c2 = app.test_client()

    _register(c1, "pin_rate_owner")
    _register(c1, "pin_rate_member")
    _login(c1, "pin_rate_owner")
    users = c1.get("/api/users").json
    member_id = next(u["id"] for u in users if u["username"] == "pin_rate_member")
    room_id = _create_room(c1, members=[member_id], name="pin-rate-room")
    _login(c2, "pin_rate_member")

    from app.models import get_db

    with app.app_context():
        cur = get_db().cursor()
        cur.execute("SELECT COUNT(*) FROM messages WHERE room_id = ? AND message_type = 'system'", (room_id,))
        before_count = cur.fetchone()[0]

    sc1 = _create_socket_client(app, c1)
    sc2 = _create_socket_client(app, c2)
    try:
        sc1.get_received()
        sc2.emit("pin_updated", {"room_id": room_id})
        first_evt = _first_event(sc1.get_received(), "pin_updated")
        assert first_evt is not None
        assert first_evt.get("room_id") == room_id

        sc2.emit("pin_updated", {"room_id": room_id})
        errs = [evt for evt in sc2.get_received() if evt.get("name") == "error"]
        assert errs
    finally:
        sc1.disconnect()
        sc2.disconnect()

    with app.app_context():
        cur = get_db().cursor()
        cur.execute("SELECT COUNT(*) FROM messages WHERE room_id = ? AND message_type = 'system'", (room_id,))
        after_count = cur.fetchone()[0]
    assert before_count == after_count


def test_pin_api_emits_new_message_and_pin_updated(app):
    c1 = app.test_client()
    c2 = app.test_client()

    _register(c1, "pin_owner_emit")
    _register(c1, "pin_member_emit")
    _login(c1, "pin_owner_emit")
    users = c1.get("/api/users").json
    member_id = next(u["id"] for u in users if u["username"] == "pin_member_emit")
    room_id = _create_room(c1, members=[member_id], name="pin-emit-room")
    _login(c2, "pin_member_emit")

    sc1 = _create_socket_client(app, c1)
    sc2 = _create_socket_client(app, c2)
    try:
        sc1.emit("send_message", {"room_id": room_id, "content": "for pin", "type": "text", "encrypted": False})
        msg_evt = _first_event(sc1.get_received(), "new_message")
        assert msg_evt and msg_evt.get("id")
        message_id = msg_evt["id"]

        sc2.get_received()
        create_resp = c1.post(f"/api/rooms/{room_id}/pins", json={"message_id": message_id})
        assert create_resp.status_code == 200
        pin_id = create_resp.json.get("pin_id")
        assert isinstance(pin_id, int)

        after_create = sc2.get_received()
        assert _first_event(after_create, "pin_updated") is not None
        sys_msg = _first_event(after_create, "new_message")
        assert sys_msg is not None
        assert sys_msg.get("message_type") == "system"

        sc2.get_received()
        delete_resp = c1.delete(f"/api/rooms/{room_id}/pins/{pin_id}")
        assert delete_resp.status_code == 200

        after_delete = sc2.get_received()
        assert _first_event(after_delete, "pin_updated") is not None
        sys_msg2 = _first_event(after_delete, "new_message")
        assert sys_msg2 is not None
        assert sys_msg2.get("message_type") == "system"
    finally:
        sc1.disconnect()
        sc2.disconnect()


def test_uploads_traversal_encoded_path_blocked(app):
    c = app.test_client()
    _register(c, "up_trv_user")
    _login(c, "up_trv_user")

    r = c.get("/uploads/profiles/%2e%2e/%2e%2e/secret.txt")
    assert r.status_code in (400, 403, 404)


def test_oidc_exchange_success_with_valid_id_token_and_nonce(app, monkeypatch):
    import app.oidc as oidc

    app.config.update(
        {
            "OIDC_ISSUER_URL": "https://issuer.example",
            "OIDC_CLIENT_ID": "client-123",
            "OIDC_CLIENT_SECRET": "secret-123",
            "OIDC_JWKS_CACHE_SECONDS": 0,
        }
    )

    kid = "k1"
    secret = b"oidc-secret-success-0123456789012345"
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "sub-1",
            "iss": "https://issuer.example",
            "aud": "client-123",
            "exp": now + 300,
            "nonce": "nonce-1",
            "name": "OIDC User",
            "email": "oidc@example.com",
        },
        secret,
        algorithm="HS256",
        headers={"kid": kid},
    )
    jwks = {"keys": [_oct_jwk(secret, kid)]}
    jwks_url = _write_jwks_file(jwks)

    def fake_fetch_json(url, timeout=10):
        if url.endswith("/.well-known/openid-configuration"):
            return {
                "authorization_endpoint": "https://issuer.example/auth",
                "token_endpoint": "https://issuer.example/token",
                "userinfo_endpoint": "https://issuer.example/userinfo",
                "jwks_uri": jwks_url,
            }
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(oidc, "_fetch_json", fake_fetch_json)
    monkeypatch.setattr(oidc, "_post_form", lambda *args, **kwargs: {"id_token": token})

    claims = oidc.exchange_code_for_userinfo(app, code="abc", redirect_uri="https://app/cb", expected_nonce="nonce-1")
    assert claims["sub"] == "sub-1"
    assert claims["email"] == "oidc@example.com"


def test_oidc_exchange_rejects_nonce_mismatch(app, monkeypatch):
    import app.oidc as oidc

    app.config.update(
        {
            "OIDC_ISSUER_URL": "https://issuer.example",
            "OIDC_CLIENT_ID": "client-123",
            "OIDC_CLIENT_SECRET": "secret-123",
            "OIDC_JWKS_CACHE_SECONDS": 0,
        }
    )

    kid = "k2"
    secret = b"oidc-secret-nonce-01234567890123456"
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "sub-2",
            "iss": "https://issuer.example",
            "aud": "client-123",
            "exp": now + 300,
            "nonce": "nonce-real",
        },
        secret,
        algorithm="HS256",
        headers={"kid": kid},
    )
    jwks = {"keys": [_oct_jwk(secret, kid)]}
    jwks_url = _write_jwks_file(jwks)

    def fake_fetch_json(url, timeout=10):
        if url.endswith("/.well-known/openid-configuration"):
            return {
                "authorization_endpoint": "https://issuer.example/auth",
                "token_endpoint": "https://issuer.example/token",
                "userinfo_endpoint": "https://issuer.example/userinfo",
                "jwks_uri": jwks_url,
            }
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(oidc, "_fetch_json", fake_fetch_json)
    monkeypatch.setattr(oidc, "_post_form", lambda *args, **kwargs: {"id_token": token})

    with pytest.raises(RuntimeError):
        oidc.exchange_code_for_userinfo(app, code="abc", redirect_uri="https://app/cb", expected_nonce="nonce-wrong")


def test_oidc_exchange_rejects_missing_id_token(app, monkeypatch):
    import app.oidc as oidc

    app.config.update(
        {
            "OIDC_ISSUER_URL": "https://issuer.example",
            "OIDC_CLIENT_ID": "client-123",
            "OIDC_CLIENT_SECRET": "secret-123",
            "OIDC_JWKS_CACHE_SECONDS": 0,
        }
    )

    monkeypatch.setattr(
        oidc,
        "_fetch_json",
        lambda url, timeout=10: {
            "authorization_endpoint": "https://issuer.example/auth",
            "token_endpoint": "https://issuer.example/token",
            "userinfo_endpoint": "https://issuer.example/userinfo",
            "jwks_uri": "https://issuer.example/jwks",
        },
    )
    monkeypatch.setattr(oidc, "_post_form", lambda *args, **kwargs: {"access_token": "token-only"})

    with pytest.raises(RuntimeError):
        oidc.exchange_code_for_userinfo(app, code="abc", redirect_uri="https://app/cb", expected_nonce="nonce-1")


def test_oidc_exchange_rejects_invalid_signature(app, monkeypatch):
    import app.oidc as oidc

    app.config.update(
        {
            "OIDC_ISSUER_URL": "https://issuer.example",
            "OIDC_CLIENT_ID": "client-123",
            "OIDC_CLIENT_SECRET": "secret-123",
            "OIDC_JWKS_CACHE_SECONDS": 0,
        }
    )

    kid = "k3"
    sign_secret = b"oidc-secret-sign-01234567890123456"
    verify_secret = b"oidc-secret-verify-012345678901234"
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "sub-3",
            "iss": "https://issuer.example",
            "aud": "client-123",
            "exp": now + 300,
            "nonce": "nonce-3",
        },
        sign_secret,
        algorithm="HS256",
        headers={"kid": kid},
    )
    jwks = {"keys": [_oct_jwk(verify_secret, kid)]}
    jwks_url = _write_jwks_file(jwks)

    def fake_fetch_json(url, timeout=10):
        if url.endswith("/.well-known/openid-configuration"):
            return {
                "authorization_endpoint": "https://issuer.example/auth",
                "token_endpoint": "https://issuer.example/token",
                "userinfo_endpoint": "https://issuer.example/userinfo",
                "jwks_uri": jwks_url,
            }
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(oidc, "_fetch_json", fake_fetch_json)
    monkeypatch.setattr(oidc, "_post_form", lambda *args, **kwargs: {"id_token": token})

    with pytest.raises(Exception):
        oidc.exchange_code_for_userinfo(app, code="abc", redirect_uri="https://app/cb", expected_nonce="nonce-3")

