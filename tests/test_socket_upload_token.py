# -*- coding: utf-8 -*-

import io


def _register(client, username, password="Password123!", nickname=None):
    res = client.post(
        "/api/register",
        json={"username": username, "password": password, "nickname": nickname or username},
    )
    assert res.status_code == 200


def _login(client, username, password="Password123!"):
    res = client.post("/api/login", json={"username": username, "password": password})
    assert res.status_code == 200


def _create_room(client, name):
    res = client.post("/api/rooms", json={"name": name, "members": []})
    assert res.status_code == 200
    return res.json["room_id"]


def _build_socket_client(app, flask_client):
    from app import socketio

    sc = socketio.test_client(app, flask_test_client=flask_client)
    assert sc.is_connected()
    return sc


def _upload_for_room(client, room_id, filename="token-file.txt", data=b"hello"):
    res = client.post(
        "/api/upload",
        data={"room_id": str(room_id), "file": (io.BytesIO(data), filename)},
        content_type="multipart/form-data",
    )
    assert res.status_code == 200
    assert res.json["success"] is True
    return res.json


def test_socket_file_message_with_upload_token_success(app):
    c = app.test_client()
    _register(c, "sockuser1")
    _login(c, "sockuser1")

    room_id = _create_room(c, "Socket Room")
    upload_result = _upload_for_room(c, room_id)
    assert "upload_token" in upload_result

    sc = _build_socket_client(app, c)
    try:
        sc.emit(
            "send_message",
            {
                "room_id": room_id,
                "content": "",
                "type": "file",
                "upload_token": upload_result["upload_token"],
                "encrypted": False,
            },
        )
        received = sc.get_received()
        assert any(evt["name"] == "new_message" for evt in received)
    finally:
        sc.disconnect()


def test_socket_file_message_without_token_blocked(app):
    c = app.test_client()
    _register(c, "sockuser2")
    _login(c, "sockuser2")
    room_id = _create_room(c, "Socket Room 2")

    sc = _build_socket_client(app, c)
    try:
        sc.emit(
            "send_message",
            {"room_id": room_id, "content": "x", "type": "file", "encrypted": False},
        )
        received = sc.get_received()
        errors = [evt for evt in received if evt["name"] == "error"]
        assert errors
        assert any("토큰" in (evt["args"][0].get("message") or "") for evt in errors)
    finally:
        sc.disconnect()


def test_socket_file_message_with_expired_token_blocked(app, monkeypatch):
    c = app.test_client()
    _register(c, "sockuser3")
    _login(c, "sockuser3")
    room_id = _create_room(c, "Socket Room 3")
    me = c.get("/api/me").json["user"]

    import app.upload_tokens as upload_tokens

    monkeypatch.setattr(upload_tokens, "TOKEN_TTL_SECONDS", 0)
    token = upload_tokens.issue_upload_token(
        user_id=me["id"],
        room_id=room_id,
        file_path="expired.txt",
        file_name="expired.txt",
        file_type="file",
        file_size=12,
    )

    sc = _build_socket_client(app, c)
    try:
        sc.emit(
            "send_message",
            {"room_id": room_id, "content": "", "type": "file", "upload_token": token, "encrypted": False},
        )
        received = sc.get_received()
        errors = [evt for evt in received if evt["name"] == "error"]
        assert errors
        assert any("만료" in (evt["args"][0].get("message") or "") for evt in errors)
    finally:
        sc.disconnect()


def test_socket_file_message_room_mismatch_blocked(app):
    c = app.test_client()
    _register(c, "sockuser4")
    _login(c, "sockuser4")
    room1 = _create_room(c, "Socket Room 4-1")
    room2 = _create_room(c, "Socket Room 4-2")

    upload_result = _upload_for_room(c, room1, filename="room-mismatch.txt")

    sc = _build_socket_client(app, c)
    try:
        sc.emit(
            "send_message",
            {
                "room_id": room2,
                "content": "",
                "type": "file",
                "upload_token": upload_result["upload_token"],
                "encrypted": False,
            },
        )
        received = sc.get_received()
        errors = [evt for evt in received if evt["name"] == "error"]
        assert errors
        assert any("대화방" in (evt["args"][0].get("message") or "") for evt in errors)
    finally:
        sc.disconnect()
