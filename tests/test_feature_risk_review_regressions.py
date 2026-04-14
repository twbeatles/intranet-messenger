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


def test_invited_user_gets_room_list_updated_and_messages(app):
    owner = app.test_client()
    member = app.test_client()

    _register(owner, "invite_owner")
    _register(owner, "invite_member")
    _login(owner, "invite_owner")
    room_id = _create_room(owner, name="invite-room")

    users = owner.get("/api/users").json
    member_id = next(u["id"] for u in users if u["username"] == "invite_member")
    _login(member, "invite_member")

    sc_member = _create_socket_client(app, member)
    sc_owner = _create_socket_client(app, owner)
    try:
        sc_member.get_received()
        invite = owner.post(f"/api/rooms/{room_id}/members", json={"user_id": member_id})
        assert invite.status_code == 200

        invited_evt = _first_event(sc_member.get_received(), "room_list_updated")
        assert invited_evt is not None
        assert invited_evt.get("reason") == "room_invited"

        sc_member.get_received()
        sc_owner.emit("send_message", {"room_id": room_id, "content": "welcome", "type": "text", "encrypted": False})
        new_message = _first_event(sc_member.get_received(), "new_message")
        assert new_message is not None
        assert new_message.get("content") == "welcome"
    finally:
        sc_owner.disconnect()
        sc_member.disconnect()


def test_kicked_user_loses_room_subscription(app):
    owner = app.test_client()
    member = app.test_client()

    _register(owner, "kick_owner")
    _register(owner, "kick_member")
    _login(owner, "kick_owner")
    users = owner.get("/api/users").json
    member_id = next(u["id"] for u in users if u["username"] == "kick_member")
    room_id = _create_room(owner, members=[member_id], name="kick-room")
    _login(member, "kick_member")

    sc_owner = _create_socket_client(app, owner)
    sc_member = _create_socket_client(app, member)
    try:
        sc_member.get_received()
        kick = owner.delete(f"/api/rooms/{room_id}/members/{member_id}")
        assert kick.status_code == 200

        received = sc_member.get_received()
        revoked_evt = _first_event(received, "room_access_revoked")
        assert revoked_evt == {"room_id": room_id, "reason": "kicked"}
        list_evt = _first_event(received, "room_list_updated")
        assert list_evt is not None
        assert list_evt.get("reason") == "room_kicked"

        sc_member.get_received()
        sc_owner.emit("send_message", {"room_id": room_id, "content": "after kick", "type": "text", "encrypted": False})
        assert _first_event(sc_member.get_received(), "new_message") is None
    finally:
        sc_member.disconnect()
        sc_owner.disconnect()


def test_leave_room_revokes_subscription(app):
    owner = app.test_client()
    member = app.test_client()

    _register(owner, "leave_owner")
    _register(owner, "leave_member")
    _login(owner, "leave_owner")
    users = owner.get("/api/users").json
    member_id = next(u["id"] for u in users if u["username"] == "leave_member")
    room_id = _create_room(owner, members=[member_id], name="leave-room-revoke")
    _login(member, "leave_member")

    sc_owner = _create_socket_client(app, owner)
    sc_member = _create_socket_client(app, member)
    try:
        sc_member.get_received()
        leave = member.post(f"/api/rooms/{room_id}/leave")
        assert leave.status_code == 200

        received = sc_member.get_received()
        revoked_evt = _first_event(received, "room_access_revoked")
        assert revoked_evt == {"room_id": room_id, "reason": "left"}
        list_evt = _first_event(received, "room_list_updated")
        assert list_evt is not None
        assert list_evt.get("reason") == "room_left"

        sc_member.get_received()
        sc_owner.emit("send_message", {"room_id": room_id, "content": "after leave", "type": "text", "encrypted": False})
        assert _first_event(sc_member.get_received(), "new_message") is None
    finally:
        sc_member.disconnect()
        sc_owner.disconnect()


def test_send_message_rejects_system_type_and_cross_room_reply(app):
    client = app.test_client()
    peer = app.test_client()

    _register(client, "msg_owner")
    _register(client, "msg_peer")
    _login(client, "msg_owner")
    users = client.get("/api/users").json
    peer_id = next(u["id"] for u in users if u["username"] == "msg_peer")
    room_a = _create_room(client, members=[peer_id], name="room-a")
    room_b = _create_room(client, name="room-b")
    _login(peer, "msg_peer")

    sc = _create_socket_client(app, client)
    try:
        sc.emit("send_message", {"room_id": room_a, "content": "forged", "type": "system", "encrypted": False})
        error_evt = _first_event(sc.get_received(), "error")
        assert error_evt is not None

        sc.emit("send_message", {"room_id": room_b, "content": "target", "type": "text", "encrypted": False})
        target_msg = _first_event(sc.get_received(), "new_message")
        assert target_msg and target_msg.get("id")

        sc.emit(
            "send_message",
            {
                "room_id": room_a,
                "content": "bad reply",
                "type": "text",
                "reply_to": target_msg["id"],
                "encrypted": False,
            },
        )
        received = sc.get_received()
        assert _first_event(received, "new_message") is None
        assert _first_event(received, "error") is not None
    finally:
        sc.disconnect()


def test_pin_api_rejects_foreign_room_message(client):
    _register(client, "pin_guard")
    _register(client, "pin_guard_peer")
    _login(client, "pin_guard")
    users = client.get("/api/users").json
    peer_id = next(u["id"] for u in users if u["username"] == "pin_guard_peer")
    room_a = _create_room(client, members=[peer_id], name="pin-a")
    room_b = _create_room(client, name="pin-b")

    from app.models import create_message

    with client.application.app_context():
        message = create_message(room_b, 1, "foreign pin target", "text", encrypted=False)
        assert message is not None

    resp = client.post(f"/api/rooms/{room_a}/pins", json={"message_id": message["id"]})
    assert resp.status_code == 400
    assert resp.json.get("code") == "invalid_pin_message"


def test_message_read_ignores_foreign_message_id(app):
    owner = app.test_client()
    member = app.test_client()

    _register(owner, "read_owner")
    _register(owner, "read_member")
    _login(owner, "read_owner")
    users = owner.get("/api/users").json
    member_id = next(u["id"] for u in users if u["username"] == "read_member")
    room_a = _create_room(owner, members=[member_id], name="read-a")
    room_b = _create_room(owner, name="read-b")
    _login(member, "read_member")

    sc_owner = _create_socket_client(app, owner)
    sc_member = _create_socket_client(app, member)
    try:
        sc_owner.emit("send_message", {"room_id": room_b, "content": "target", "type": "text", "encrypted": False})
        target_msg = _first_event(sc_owner.get_received(), "new_message")
        assert target_msg and target_msg.get("id")

        sc_owner.get_received()
        sc_member.emit("message_read", {"room_id": room_a, "message_id": target_msg["id"]})
        assert _first_event(sc_owner.get_received(), "read_updated") is None
    finally:
        sc_member.disconnect()
        sc_owner.disconnect()


def test_status_message_round_trip_and_clear(client):
    _register(client, "status_user")

    login = client.post("/api/login", json={"username": "status_user", "password": "Password123!"})
    assert login.status_code == 200
    assert "status_message" in login.json["user"]

    update = client.put("/api/profile", json={"nickname": "status_user", "status_message": "hello there"})
    assert update.status_code == 200

    profile = client.get("/api/profile")
    assert profile.status_code == 200
    assert profile.json.get("status_message") == "hello there"

    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json["user"].get("status_message") == "hello there"

    clear = client.put("/api/profile", json={"status_message": ""})
    assert clear.status_code == 200

    profile_after_clear = client.get("/api/profile")
    assert profile_after_clear.status_code == 200
    assert profile_after_clear.json.get("status_message") == ""


def test_delete_room_file_removes_linked_message_and_reply_preview(app):
    owner = app.test_client()
    member = app.test_client()

    _register(owner, "file_owner")
    _register(owner, "file_member")
    _login(owner, "file_owner")
    users = owner.get("/api/users").json
    member_id = next(u["id"] for u in users if u["username"] == "file_member")
    room_id = _create_room(owner, members=[member_id], name="file-room")
    _login(member, "file_member")

    sc_owner = _create_socket_client(app, owner)
    sc_member = _create_socket_client(app, member)
    try:
        upload = owner.post(
            "/api/upload",
            data={"room_id": str(room_id), "file": (io.BytesIO(b"hello file"), "note.txt")},
            content_type="multipart/form-data",
        )
        assert upload.status_code == 200
        token = upload.json.get("upload_token")
        assert token

        sc_owner.emit(
            "send_message",
            {"room_id": room_id, "content": "note.txt", "type": "file", "upload_token": token, "encrypted": False},
        )
        file_msg = _first_event(sc_owner.get_received(), "new_message")
        assert file_msg and file_msg.get("id")

        sc_owner.emit(
            "send_message",
            {
                "room_id": room_id,
                "content": "reply to file",
                "type": "text",
                "reply_to": file_msg["id"],
                "encrypted": False,
            },
        )
        reply_msg = _first_event(sc_owner.get_received(), "new_message")
        assert reply_msg and reply_msg.get("id")

        files = owner.get(f"/api/rooms/{room_id}/files")
        assert files.status_code == 200
        file_id = files.json[0]["id"]

        sc_member.get_received()
        delete_resp = owner.delete(f"/api/rooms/{room_id}/files/{file_id}")
        assert delete_resp.status_code == 200

        deleted_evt = _first_event(sc_member.get_received(), "message_deleted")
        assert deleted_evt == {"message_id": file_msg["id"]}

        messages_resp = owner.get(f"/api/rooms/{room_id}/messages")
        assert messages_resp.status_code == 200
        message_ids = [msg["id"] for msg in messages_resp.json["messages"]]
        assert file_msg["id"] not in message_ids

        reply_record = next(msg for msg in messages_resp.json["messages"] if msg["id"] == reply_msg["id"])
        assert reply_record["reply_to"] == file_msg["id"]
        assert reply_record.get("reply_content") == "[삭제된 메시지]"
    finally:
        sc_member.disconnect()
        sc_owner.disconnect()
