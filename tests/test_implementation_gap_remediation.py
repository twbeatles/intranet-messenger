# -*- coding: utf-8 -*-

from __future__ import annotations

import io

from tests.test_feature_risk_review_plan import (
    _create_room,
    _create_socket_client,
    _first_event,
    _login,
    _register,
)


def _user_id(client, username: str) -> int:
    users = client.get("/api/users").json
    return next(user["id"] for user in users if user["username"] == username)


def test_pre_invite_file_is_hidden_from_new_member_list_and_download(app):
    owner = app.test_client()
    member = app.test_client()

    _register(owner, "gap_file_owner")
    _register(owner, "gap_file_member")
    _login(owner, "gap_file_owner")
    room_id = _create_room(owner, name="gap-file-room")
    member_id = _user_id(owner, "gap_file_member")

    upload = owner.post(
        "/api/upload",
        data={"room_id": str(room_id), "file": (io.BytesIO(b"secret file"), "secret.txt")},
        content_type="multipart/form-data",
    )
    assert upload.status_code == 200
    token = upload.json["upload_token"]

    sc_owner = _create_socket_client(app, owner)
    try:
        sc_owner.emit(
            "send_message",
            {"room_id": room_id, "content": "secret.txt", "type": "file", "upload_token": token, "encrypted": False},
        )
        file_msg = _first_event(sc_owner.get_received(), "new_message")
        assert file_msg and file_msg["id"]
    finally:
        sc_owner.disconnect()

    owner_files = owner.get(f"/api/rooms/{room_id}/files")
    assert owner_files.status_code == 200
    assert len(owner_files.json) == 1
    file_path = owner_files.json[0]["file_path"]
    assert owner.get(f"/uploads/{file_path}").status_code == 200

    _login(member, "gap_file_member")
    invite = owner.post(f"/api/rooms/{room_id}/members", json={"user_id": member_id})
    assert invite.status_code == 200

    member_files = member.get(f"/api/rooms/{room_id}/files")
    assert member_files.status_code == 200
    assert member_files.json == []
    assert member.get(f"/uploads/{file_path}").status_code == 403


def test_pre_invite_pin_reaction_and_reply_are_hidden_or_rejected(app):
    owner = app.test_client()
    member = app.test_client()

    _register(owner, "gap_pin_owner")
    _register(owner, "gap_pin_member")
    _login(owner, "gap_pin_owner")
    room_id = _create_room(owner, name="gap-pin-room")
    member_id = _user_id(owner, "gap_pin_member")

    sc_owner = _create_socket_client(app, owner)
    try:
        sc_owner.emit("send_message", {"room_id": room_id, "content": "old pinned", "type": "text", "encrypted": False})
        old_msg = _first_event(sc_owner.get_received(), "new_message")
        assert old_msg and old_msg["id"]
    finally:
        sc_owner.disconnect()

    pin = owner.post(f"/api/rooms/{room_id}/pins", json={"message_id": old_msg["id"]})
    assert pin.status_code == 200

    _login(member, "gap_pin_member")
    invite = owner.post(f"/api/rooms/{room_id}/members", json={"user_id": member_id})
    assert invite.status_code == 200

    assert member.get(f"/api/rooms/{room_id}/pins").json == []
    assert member.post(f"/api/rooms/{room_id}/pins", json={"message_id": old_msg["id"]}).status_code == 400
    assert member.post(f"/api/messages/{old_msg['id']}/reactions", json={"emoji": "ok"}).status_code == 403

    sc_member = _create_socket_client(app, member)
    try:
        sc_member.emit(
            "send_message",
            {"room_id": room_id, "content": "reply attempt", "type": "text", "encrypted": False, "reply_to": old_msg["id"]},
        )
        received = sc_member.get_received()
        assert _first_event(received, "new_message") is None
        assert _first_event(received, "error") is not None
    finally:
        sc_member.disconnect()


def test_room_metadata_socket_events_are_server_authoritative(app):
    owner = app.test_client()
    member = app.test_client()

    _register(owner, "gap_evt_owner")
    _register(owner, "gap_evt_member")
    _login(owner, "gap_evt_owner")
    member_id = _user_id(owner, "gap_evt_member")
    room_id = _create_room(owner, members=[member_id], name="canonical-room")
    _login(member, "gap_evt_member")

    sc_owner = _create_socket_client(app, owner)
    try:
        sc_owner.emit("room_name_updated", {"room_id": room_id, "name": "forged-room"})
        sc_owner.emit("admin_updated", {"room_id": room_id, "user_id": member_id, "is_admin": True})
    finally:
        sc_owner.disconnect()

    info = owner.get(f"/api/rooms/{room_id}/info")
    assert info.status_code == 200
    assert info.json["name"] == "canonical-room"

    admins = owner.get(f"/api/rooms/{room_id}/admins")
    assert admins.status_code == 200
    assert member_id not in {admin["id"] for admin in admins.json}

    sc_member = _create_socket_client(app, member)
    try:
        sc_member.get_received()
        rename = owner.put(f"/api/rooms/{room_id}/name", json={"name": "server-room"})
        assert rename.status_code == 200
        assert _first_event(sc_member.get_received(), "room_name_updated") == {"room_id": room_id, "name": "server-room"}

        promote = owner.post(f"/api/rooms/{room_id}/admins", json={"user_id": member_id, "is_admin": True})
        assert promote.status_code == 200
        assert _first_event(sc_member.get_received(), "admin_updated") == {
            "room_id": room_id,
            "user_id": member_id,
            "is_admin": True,
        }
    finally:
        sc_member.disconnect()


def test_left_member_cannot_edit_or_delete_old_message_over_http_or_socket(app):
    owner = app.test_client()
    member = app.test_client()

    _register(owner, "gap_left_owner")
    _register(owner, "gap_left_member")
    _login(owner, "gap_left_owner")
    member_id = _user_id(owner, "gap_left_member")
    room_id = _create_room(owner, members=[member_id], name="gap-left-room")
    _login(member, "gap_left_member")

    sc_member = _create_socket_client(app, member)
    try:
        sc_member.emit("send_message", {"room_id": room_id, "content": "before leave", "type": "text", "encrypted": False})
        msg = _first_event(sc_member.get_received(), "new_message")
        assert msg and msg["id"]

        leave = member.post(f"/api/rooms/{room_id}/leave")
        assert leave.status_code == 200

        assert member.put(f"/api/messages/{msg['id']}", json={"content": "edited"}).status_code == 403
        assert member.delete(f"/api/messages/{msg['id']}").status_code == 403

        sc_member.get_received()
        sc_member.emit("edit_message", {"message_id": msg["id"], "content": "edited", "encrypted": False})
        assert _first_event(sc_member.get_received(), "error") is not None

        sc_member.emit("delete_message", {"message_id": msg["id"]})
        assert _first_event(sc_member.get_received(), "error") is not None
    finally:
        sc_member.disconnect()


def test_admin_audit_log_pagination_is_clamped(client):
    _register(client, "gap_audit_owner")
    _login(client, "gap_audit_owner")
    room_id = _create_room(client, name="gap-audit-room")

    too_large = client.get(f"/api/rooms/{room_id}/admin-audit-logs", query_string={"limit": 9999, "offset": -10})
    assert too_large.status_code == 200
    assert too_large.json["limit"] == 500
    assert too_large.json["offset"] == 0

    invalid = client.get(f"/api/rooms/{room_id}/admin-audit-logs", query_string={"limit": "abc", "offset": "abc"})
    assert invalid.status_code == 200
    assert invalid.json["limit"] == 200
    assert invalid.json["offset"] == 0
