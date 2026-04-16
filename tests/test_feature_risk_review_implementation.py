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


def test_invited_user_only_sees_post_invite_history_and_security_payload(app):
    owner = app.test_client()
    member = app.test_client()

    _register(owner, "secure_owner")
    _register(owner, "secure_member")
    _login(owner, "secure_owner")
    room_id = _create_room(owner, name="secure-room")

    users = owner.get("/api/users").json
    member_id = next(user["id"] for user in users if user["username"] == "secure_member")
    _login(member, "secure_member")

    sc_owner = _create_socket_client(app, owner)
    sc_member = _create_socket_client(app, member)
    try:
        sc_owner.emit("send_message", {"room_id": room_id, "content": "before invite", "type": "text", "encrypted": False})
        before_msg = _first_event(sc_owner.get_received(), "new_message")
        assert before_msg and before_msg["id"]

        sc_member.get_received()
        invite = owner.post(f"/api/rooms/{room_id}/members", json={"user_id": member_id})
        assert invite.status_code == 200

        member_events = sc_member.get_received()
        security_evt = _first_event(member_events, "room_security_updated")
        assert security_evt is not None
        assert security_evt["room_id"] == room_id
        assert security_evt["key_version"] == 2
        assert security_evt["member_key_version"] == 2

        member_history = member.get(f"/api/rooms/{room_id}/messages")
        assert member_history.status_code == 200
        assert member_history.json["key_version"] == 2
        assert member_history.json["member_key_version"] == 2
        assert member_history.json["messages"] == []

        owner_history = owner.get(f"/api/rooms/{room_id}/messages")
        assert owner_history.status_code == 200
        assert owner_history.json["key_version"] == 2
        assert any(msg["id"] == before_msg["id"] for msg in owner_history.json["messages"])
        assert set(owner_history.json["encryption_keys"].keys()) >= {"1", "2"}
    finally:
        sc_member.disconnect()
        sc_owner.disconnect()


def test_leave_rotates_room_key_and_emits_security_update(app):
    owner = app.test_client()
    member = app.test_client()

    _register(owner, "leave_secure_owner")
    _register(owner, "leave_secure_member")
    _login(owner, "leave_secure_owner")
    users = owner.get("/api/users").json
    member_id = next(user["id"] for user in users if user["username"] == "leave_secure_member")
    room_id = _create_room(owner, members=[member_id], name="leave-secure-room")
    _login(member, "leave_secure_member")

    sc_owner = _create_socket_client(app, owner)
    sc_member = _create_socket_client(app, member)
    try:
        sc_owner.get_received()
        leave = member.post(f"/api/rooms/{room_id}/leave")
        assert leave.status_code == 200

        owner_events = sc_owner.get_received()
        security_evt = _first_event(owner_events, "room_security_updated")
        assert security_evt is not None
        assert security_evt["room_id"] == room_id
        assert security_evt["key_version"] == 2

        owner_history = owner.get(f"/api/rooms/{room_id}/messages")
        assert owner_history.status_code == 200
        assert owner_history.json["key_version"] == 2
        assert owner_history.json["member_key_version"] == 1
    finally:
        sc_member.disconnect()
        sc_owner.disconnect()


def test_room_name_and_admin_routes_emit_canonical_socket_events(app):
    owner = app.test_client()
    member = app.test_client()

    _register(owner, "room_evt_owner")
    _register(owner, "room_evt_member")
    _login(owner, "room_evt_owner")
    users = owner.get("/api/users").json
    member_id = next(user["id"] for user in users if user["username"] == "room_evt_member")
    room_id = _create_room(owner, members=[member_id], name="event-room")
    _login(member, "room_evt_member")

    sc_owner = _create_socket_client(app, owner)
    sc_member = _create_socket_client(app, member)
    try:
        sc_member.get_received()
        rename = owner.put(f"/api/rooms/{room_id}/name", json={"name": "renamed-room"})
        assert rename.status_code == 200
        rename_evt = _first_event(sc_member.get_received(), "room_name_updated")
        assert rename_evt == {"room_id": room_id, "name": "renamed-room"}

        sc_member.get_received()
        promote = owner.post(f"/api/rooms/{room_id}/admins", json={"user_id": member_id, "is_admin": True})
        assert promote.status_code == 200
        admin_evt = _first_event(sc_member.get_received(), "admin_updated")
        assert admin_evt == {"room_id": room_id, "user_id": member_id, "is_admin": True}
    finally:
        sc_member.disconnect()
        sc_owner.disconnect()


def test_delete_pinned_file_emits_pin_updated_and_search_hides_deleted_attachment(app):
    owner = app.test_client()
    member = app.test_client()

    _register(owner, "pin_file_owner")
    _register(owner, "pin_file_member")
    _login(owner, "pin_file_owner")
    users = owner.get("/api/users").json
    member_id = next(user["id"] for user in users if user["username"] == "pin_file_member")
    room_id = _create_room(owner, members=[member_id], name="pin-file-room")
    _login(member, "pin_file_member")

    sc_owner = _create_socket_client(app, owner)
    sc_member = _create_socket_client(app, member)
    try:
        upload = owner.post(
            "/api/upload",
            data={"room_id": str(room_id), "file": (io.BytesIO(b"hello file"), "note.txt")},
            content_type="multipart/form-data",
        )
        assert upload.status_code == 200
        token = upload.json["upload_token"]

        sc_owner.emit(
            "send_message",
            {"room_id": room_id, "content": "note.txt", "type": "file", "upload_token": token, "encrypted": False},
        )
        file_msg = _first_event(sc_owner.get_received(), "new_message")
        assert file_msg and file_msg["id"]

        pin_resp = owner.post(f"/api/rooms/{room_id}/pins", json={"message_id": file_msg["id"]})
        assert pin_resp.status_code == 200

        files = owner.get(f"/api/rooms/{room_id}/files")
        assert files.status_code == 200
        file_id = files.json[0]["id"]

        sc_member.get_received()
        delete_resp = owner.delete(f"/api/rooms/{room_id}/files/{file_id}")
        assert delete_resp.status_code == 200

        member_events = sc_member.get_received()
        assert _first_event(member_events, "message_deleted") == {"message_id": file_msg["id"]}
        assert _first_event(member_events, "pin_updated") == {"room_id": room_id}

        search_resp = owner.get("/api/search", query_string={"q": "삭제된", "room_id": room_id})
        assert search_resp.status_code == 200
        assert search_resp.json == []

        file_search_resp = owner.get("/api/search", query_string={"file_only": "1", "room_id": room_id})
        assert file_search_resp.status_code == 200
        assert file_search_resp.json == []
    finally:
        sc_member.disconnect()
        sc_owner.disconnect()
