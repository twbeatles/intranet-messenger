# -*- coding: utf-8 -*-
"""Room access-control and key-version boundary tests (AUTH-01/02/04/05/07/08/10 + MSG-01).

Uses real Flask test clients (separate A/B/C sessions), socketio.test_client
and the real SQLite DB. Production visibility is cross-checked between HTTP /
Socket observations and DB snapshots; the independent oracle is the expected
values stated in each test.
"""
from __future__ import annotations

import os

from app.models import get_db
from app.models.messages import can_user_see_message, create_message
from app.models.rooms import get_room_member_key_version
from app.services.runtime_paths import get_upload_folder
from tests.test_feature_risk_review_plan import (
    _create_room,
    _create_socket_client,
    _first_event,
    _login,
    _register,
)


def _user_id(client, username: str) -> int:
    # /api/users excludes the caller, so this is for looking up other users.
    users = client.get("/api/users").json
    return next(u["id"] for u in users if u["username"] == username)


def _self_id(client) -> int:
    me = client.get("/api/me").json
    assert me.get("logged_in") is True
    return int(me["user"]["id"])


def _room_key_version(room_id: int) -> int:
    cur = get_db().cursor()
    cur.execute("SELECT COALESCE(key_version, 1) AS kv FROM rooms WHERE id = ?", (room_id,))
    return int(cur.fetchone()["kv"])


def _message_ids(client, room_id: int) -> list[int]:
    resp = client.get(f"/api/rooms/{room_id}/messages")
    assert resp.status_code == 200
    return [m["id"] for m in resp.json["messages"]]


def test_auth01_invitee_sees_zero_preinvite_messages(app):
    """AUTH-01: M1 invisible before invite, only M2 allowed after (HTTP+search+DB)."""
    owner = app.test_client()
    invitee = app.test_client()
    _register(owner, "bnd_owner")
    _register(owner, "bnd_invitee")
    _login(owner, "bnd_owner")
    owner_id = _self_id(owner)
    invitee_id = _user_id(owner, "bnd_invitee")
    room_id = _create_room(owner, name="bnd-auth01-room")

    m1 = create_message(room_id, owner_id, "bnd-auth01-secret-before", "text", encrypted=False)
    assert m1 and m1["id"]

    # Before invite: a non-member gets 403 on history, i.e. zero exposure.
    _login(invitee, "bnd_invitee")
    assert invitee.get(f"/api/rooms/{room_id}/messages").status_code == 403

    invite = owner.post(f"/api/rooms/{room_id}/members", json={"user_id": invitee_id})
    assert invite.status_code == 200
    assert get_room_member_key_version(room_id, invitee_id) == _room_key_version(room_id)

    visible = _message_ids(invitee, room_id)
    assert m1["id"] not in visible
    assert can_user_see_message(room_id, invitee_id, int(m1["id"])) is False

    m2 = create_message(room_id, owner_id, "bnd-auth01-after-invite", "text", encrypted=False)
    visible_after = _message_ids(invitee, room_id)
    assert m2["id"] in visible_after
    assert can_user_see_message(room_id, invitee_id, int(m2["id"])) is True

    # Search oracle: pre-invite text yields nothing, post-invite text is found.
    search_old = invitee.get("/api/search", query_string={"q": "bnd-auth01-secret-before"})
    assert search_old.status_code == 200
    assert [m["id"] for m in search_old.json] == []
    search_new = invitee.get("/api/search", query_string={"q": "bnd-auth01-after-invite"})
    assert search_new.status_code == 200
    assert m2["id"] in [m["id"] for m in search_new.json]


def test_auth02_kicked_member_loses_new_messages_and_files(app):
    """AUTH-02: after kick, M3/F3 exposure is zero (HTTP + file URL + DB)."""
    owner = app.test_client()
    member = app.test_client()
    _register(owner, "bnd_k_owner")
    _register(owner, "bnd_k_member")
    _login(owner, "bnd_k_owner")
    owner_id = _self_id(owner)
    member_id = _user_id(owner, "bnd_k_member")
    room_id = _create_room(owner, members=[member_id], name="bnd-auth02-room")
    _login(member, "bnd_k_member")
    assert _message_ids(member, room_id) == []

    kick = owner.delete(f"/api/rooms/{room_id}/members/{member_id}")
    assert kick.status_code == 200

    m3 = create_message(room_id, owner_id, "bnd-auth02-after-kick", "text", encrypted=False)
    assert m3 and m3["id"]

    upload_folder = get_upload_folder()
    stored = "bnd-auth02-f3.bin"
    with open(os.path.join(upload_folder, stored), "wb") as fh:
        fh.write(b"bnd-auth02-bytes")
    f3 = create_message(room_id, owner_id, "bnd-auth02-file", "file",
                        file_path=stored, file_name=stored)
    assert f3 and f3["id"]

    # A kicked user is no longer a member: history/files 403, direct URL 403.
    assert member.get(f"/api/rooms/{room_id}/messages").status_code == 403
    assert member.get(f"/api/rooms/{room_id}/files").status_code == 403
    assert member.get(f"/uploads/{stored}").status_code == 403
    assert can_user_see_message(room_id, member_id, int(m3["id"])) is False
    assert can_user_see_message(room_id, member_id, int(f3["id"])) is False


def test_auth04_invalid_invite_rolls_back_without_version_bump(app):
    """AUTH-04: inviting a nonexistent user is 400 with version/membership unchanged."""
    owner = app.test_client()
    _register(owner, "bnd_rb_owner")
    _login(owner, "bnd_rb_owner")
    room_id = _create_room(owner, name="bnd-auth04-room")
    before = _room_key_version(room_id)

    resp = owner.post(f"/api/rooms/{room_id}/members", json={"user_id": 999999999})
    assert resp.status_code == 400
    assert _room_key_version(room_id) == before

    cur = get_db().cursor()
    cur.execute("SELECT COUNT(*) AS cnt FROM room_members WHERE room_id = ?", (room_id,))
    assert cur.fetchone()["cnt"] == 1


def test_auth05_logged_out_session_is_denied(app):
    """AUTH-05: a logged-out session is denied message reads."""
    owner = app.test_client()
    _register(owner, "bnd_lo_owner")
    _login(owner, "bnd_lo_owner")
    room_id = _create_room(owner, name="bnd-auth05-room")

    assert owner.post("/api/logout").status_code == 200
    # /api/me returns 200 + logged_in False after logout (verified server behavior).
    assert owner.get("/api/me").json.get("logged_in") is False
    assert owner.get(f"/api/rooms/{room_id}/messages").status_code == 401


def test_auth07_10_outsider_and_crossroom_isolation(app):
    """AUTH-07/10: non-members get nothing; room1 auth grants no room2 rights."""
    owner = app.test_client()
    outsider = app.test_client()
    _register(owner, "bnd_x_owner")
    _register(owner, "bnd_x_outsider")
    _register(owner, "bnd_x_r2member")
    _login(owner, "bnd_x_owner")
    owner_id = _self_id(owner)
    r2member_id = _user_id(owner, "bnd_x_r2member")

    room1 = _create_room(owner, name="bnd-x-room1")
    room2 = _create_room(owner, members=[r2member_id], name="bnd-x-room2")
    m1 = create_message(room1, owner_id, "bnd-x-room1-secret", "text", encrypted=False)
    m2 = create_message(room2, owner_id, "bnd-x-room2-secret", "text", encrypted=False)

    _login(outsider, "bnd_x_outsider")
    assert outsider.get(f"/api/rooms/{room1}/messages").status_code == 403
    assert outsider.get(f"/api/rooms/{room1}/files").status_code == 403
    assert outsider.get(f"/api/messages/{m1['id']}/reactions").status_code == 403
    assert outsider.post(f"/api/messages/{m1['id']}/reactions",
                         json={"emoji": "👍"}).status_code == 403
    search = outsider.get("/api/search", query_string={"q": "bnd-x-room1-secret"})
    assert search.status_code == 200
    assert search.json == []

    # A room2 member sees room2 only; room1 resources stay 403.
    r2 = app.test_client()
    _login(r2, "bnd_x_r2member")
    assert r2.get(f"/api/rooms/{room1}/messages").status_code == 403
    assert m2["id"] in _message_ids(r2, room2)
    assert can_user_see_message(room1, r2member_id, int(m1["id"])) is False


def test_auth08_token_binding_rejects_wrong_user_room_type(app):
    """AUTH-08: token binding (user/room/type) mismatches are rejected; valid use is once."""
    import app.upload_tokens as upload_tokens

    token = upload_tokens.issue_upload_token(
        user_id=11, room_id=21, file_path="b.bin", file_name="b.bin",
        file_type="file", file_size=3,
    )
    assert upload_tokens.get_upload_token_failure_reason(token, 999, 21, "file")
    assert upload_tokens.get_upload_token_failure_reason(token, 11, 999, "file")
    assert upload_tokens.get_upload_token_failure_reason(token, 11, 21, "image")
    assert upload_tokens.consume_upload_token(token, 999, 21, "file") is None
    assert upload_tokens.consume_upload_token(token, 11, 999, "file") is None

    ok = upload_tokens.consume_upload_token(token, 11, 21, "file")
    assert ok is not None and ok["file_name"] == "b.bin"
    assert upload_tokens.consume_upload_token(token, 11, 21, "file") is None


def test_msg01_socket_member_receives_outsider_blocked(app):
    """MSG-01: members receive new_message; outsider socket sends fail with no DB row."""
    owner = app.test_client()
    member = app.test_client()
    outsider = app.test_client()
    _register(owner, "bnd_s_owner")
    _register(owner, "bnd_s_member")
    _register(owner, "bnd_s_outsider")
    _login(owner, "bnd_s_owner")
    member_id = _user_id(owner, "bnd_s_member")
    room_id = _create_room(owner, members=[member_id], name="bnd-socket-room")
    _login(member, "bnd_s_member")
    _login(outsider, "bnd_s_outsider")

    sc_owner = _create_socket_client(app, owner)
    sc_member = _create_socket_client(app, member)
    sc_out = _create_socket_client(app, outsider)
    try:
        sc_owner.get_received()
        sc_member.get_received()
        sc_out.get_received()
        sc_owner.emit("send_message", {"room_id": room_id, "content": "bnd-socket-hello",
                                      "type": "text", "encrypted": False})
        got = _first_event(sc_member.get_received(), "new_message")
        assert got and got["content"] == "bnd-socket-hello"

        before = get_db().cursor().execute(
            "SELECT COUNT(*) AS cnt FROM messages WHERE room_id = ?",
            (room_id,)).fetchone()["cnt"]
        sc_out.emit("send_message", {"room_id": room_id, "content": "bnd-socket-intrude",
                                    "type": "text", "encrypted": False})
        errs = [e for e in sc_out.get_received() if e.get("name") == "error"]
        assert errs
        after = get_db().cursor().execute(
            "SELECT COUNT(*) AS cnt FROM messages WHERE room_id = ?",
            (room_id,)).fetchone()["cnt"]
        assert after == before  # the intruding message records zero rows
    finally:
        sc_owner.disconnect()
        sc_member.disconnect()
        sc_out.disconnect()
