# -*- coding: utf-8 -*-

from __future__ import annotations

import concurrent.futures
from pathlib import Path

import pytest

from app.models import get_db, get_room_member_key_version, invite_members_with_key_rotation, rotate_room_key
from app.models.messages import can_user_see_message, create_message
from tests.test_feature_risk_review_plan import (
    _create_room,
    _create_socket_client,
    _first_event,
    _login,
    _register,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _user_id(client, username: str) -> int:
    users = client.get("/api/users").json
    return next(user["id"] for user in users if user["username"] == username)


def _room_key_version(room_id: int) -> int:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(key_version, 1) AS key_version FROM rooms WHERE id = ?", (room_id,))
    row = cur.fetchone()
    return int(row["key_version"] if row else 1)


def test_concurrent_invites_assign_consistent_joined_key_version(app):
    owner_a = app.test_client()
    owner_b = app.test_client()
    member_a = app.test_client()
    member_b = app.test_client()

    _register(owner_a, "audit_owner")
    _register(owner_a, "audit_mem_a")
    _register(owner_a, "audit_mem_b")
    _login(owner_a, "audit_owner")
    room_id = _create_room(owner_a, name="audit-concurrent-room")
    member_a_id = _user_id(owner_a, "audit_mem_a")
    member_b_id = _user_id(owner_a, "audit_mem_b")

    sc_owner = _create_socket_client(app, owner_a)
    try:
        sc_owner.emit("send_message", {"room_id": room_id, "content": "pre-invite", "type": "text", "encrypted": False})
        pre_msg = _first_event(sc_owner.get_received(), "new_message")
        assert pre_msg and pre_msg["id"]
    finally:
        sc_owner.disconnect()

    _login(owner_b, "audit_owner")

    def invite(user_id: int):
        client = owner_a if user_id == member_a_id else owner_b
        return client.post(f"/api/rooms/{room_id}/members", json={"user_id": user_id})

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(invite, member_a_id), executor.submit(invite, member_b_id)]
        results = [future.result() for future in concurrent.futures.as_completed(futures)]

    assert all(response.status_code == 200 for response in results)

    current_version = _room_key_version(room_id)
    assert current_version >= 3
    assert get_room_member_key_version(room_id, member_a_id) >= 2
    assert get_room_member_key_version(room_id, member_b_id) >= 2

    _login(member_a, "audit_mem_a")
    _login(member_b, "audit_mem_b")
    assert member_a.get(f"/api/rooms/{room_id}/messages").json["messages"] == []
    assert member_b.get(f"/api/rooms/{room_id}/messages").json["messages"] == []


def test_invite_skips_rotation_when_candidates_already_members(app):
    owner = app.test_client()
    member = app.test_client()

    _register(owner, "audit_skip_owner")
    _register(owner, "audit_skip_member")
    _login(owner, "audit_skip_owner")
    member_id = _user_id(owner, "audit_skip_member")
    room_id = _create_room(owner, members=[member_id], name="audit-skip-room")
    before_version = _room_key_version(room_id)

    _login(member, "audit_skip_member")
    duplicate = owner.post(f"/api/rooms/{room_id}/members", json={"user_id": member_id})
    assert duplicate.status_code == 400
    assert _room_key_version(room_id) == before_version


def test_invite_rotate_rolls_back_when_member_insert_fails(app, monkeypatch):
    import app.models.rooms as rooms_model

    owner = app.test_client()
    _register(owner, "audit_rb_owner")
    _register(owner, "audit_rb_member")
    _login(owner, "audit_rb_owner")
    room_id = _create_room(owner, name="audit-rollback-room")
    member_id = _user_id(owner, "audit_rb_member")
    before_version = _room_key_version(room_id)

    original_add = rooms_model.add_room_member

    def fail_add_when_in_transaction(room_id, user_id, joined_key_version=None, conn=None):
        if conn is not None:
            return False
        return original_add(room_id, user_id, joined_key_version=joined_key_version, conn=conn)

    monkeypatch.setattr(rooms_model, "add_room_member", fail_add_when_in_transaction)

    rotation, added, error_code = invite_members_with_key_rotation(room_id, [member_id])
    assert rotation is None
    assert added == []
    assert error_code == "add_failed"
    assert _room_key_version(room_id) == before_version


def test_rotate_room_key_supports_shared_connection_transaction(app):
    owner = app.test_client()
    _register(owner, "audit_rotate_owner")
    _login(owner, "audit_rotate_owner")
    room_id = _create_room(owner, name="audit-rotate-room")
    before_version = _room_key_version(room_id)

    conn = get_db()
    conn.execute("BEGIN IMMEDIATE")
    rotation = rotate_room_key(room_id, conn=conn)
    assert rotation is not None
    assert rotation["key_version"] == before_version + 1
    conn.rollback()

    assert _room_key_version(room_id) == before_version


def test_can_user_see_message_respects_joined_key_version(app):
    owner = app.test_client()
    member = app.test_client()

    _register(owner, "audit_vis_owner")
    _register(owner, "audit_vis_member")
    _login(owner, "audit_vis_owner")
    owner_id = owner.get("/api/me").json["user"]["id"]
    member_id = _user_id(owner, "audit_vis_member")
    room_id = _create_room(owner, name="audit-vis-room")

    old_msg = create_message(room_id, owner_id, "before invite", "text", encrypted=False)
    assert old_msg and old_msg["id"]

    invite = owner.post(f"/api/rooms/{room_id}/members", json={"user_id": member_id})
    assert invite.status_code == 200

    _login(member, "audit_vis_member")
    assert can_user_see_message(room_id, member_id, int(old_msg["id"])) is False

    new_msg = create_message(room_id, owner_id, "after invite", "text", encrypted=False)
    assert new_msg and new_msg["id"]
    assert can_user_see_message(room_id, member_id, int(new_msg["id"])) is True


def test_room_members_updated_socket_relay_is_rate_limited(app):
    app.config["SOCKET_ROOM_MEMBERS_UPDATED_PER_MINUTE"] = 1
    c1 = app.test_client()
    c2 = app.test_client()

    _register(c1, "audit_rm_owner")
    _register(c1, "audit_rm_member")
    _login(c1, "audit_rm_owner")
    users = c1.get("/api/users").json
    member_id = next(u["id"] for u in users if u["username"] == "audit_rm_member")
    room_id = _create_room(c1, members=[member_id], name="audit-rm-room")
    _login(c2, "audit_rm_member")

    sc1 = _create_socket_client(app, c1)
    sc2 = _create_socket_client(app, c2)
    try:
        sc1.get_received()
        sc2.emit("room_members_updated", {"room_id": room_id})
        assert _first_event(sc1.get_received(), "room_members_updated") is not None

        sc2.emit("room_members_updated", {"room_id": room_id})
        errs = [evt for evt in sc2.get_received() if evt.get("name") == "error"]
        assert errs
    finally:
        sc1.disconnect()
        sc2.disconnect()


def test_upload_token_single_use_under_thread_race(monkeypatch):
    import app.upload_tokens as upload_tokens

    monkeypatch.setattr(upload_tokens, "TOKEN_TTL_SECONDS", 300)
    token = upload_tokens.issue_upload_token(
        user_id=1,
        room_id=10,
        file_path="race.txt",
        file_name="race.txt",
        file_type="file",
        file_size=10,
    )

    def consume():
        return upload_tokens.consume_upload_token(token, user_id=1, room_id=10, expected_type="file")

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: consume(), range(4)))

    assert sum(1 for item in results if item is not None) == 1


def test_handle_room_security_updated_triggers_decrypt_refresh():
    socket_runtime = (REPO_ROOT / "static/js/services/socket/runtime.js").read_text(encoding="utf-8")
    messages_runtime = (REPO_ROOT / "static/js/features/messages/runtime.js").read_text(encoding="utf-8")

    assert "refreshPendingMessageDecryption" in messages_runtime
    assert "refreshPendingMessageDecryption()" in socket_runtime