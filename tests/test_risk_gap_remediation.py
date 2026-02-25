# -*- coding: utf-8 -*-

import io


def _register(client, username, password="Password123!", nickname=None):
    response = client.post(
        "/api/register",
        json={
            "username": username,
            "password": password,
            "nickname": nickname or username,
        },
    )
    assert response.status_code == 200


def _login(client, username, password="Password123!"):
    response = client.post(
        "/api/login",
        json={
            "username": username,
            "password": password,
        },
    )
    assert response.status_code == 200


def _create_room(client, member_ids=None, name="room"):
    payload = {"name": name, "members": member_ids or []}
    response = client.post("/api/rooms", json=payload)
    assert response.status_code == 200
    return response.json["room_id"]


def test_poll_vote_rejects_option_from_other_poll(client):
    _register(client, "poll_owner")
    _register(client, "poll_member")
    _login(client, "poll_owner")

    room_id = _create_room(client, member_ids=[1, 2], name="poll-room")

    poll1 = client.post(
        f"/api/rooms/{room_id}/polls",
        json={"question": "Q1", "options": ["A", "B"]},
    ).json["poll"]
    poll2 = client.post(
        f"/api/rooms/{room_id}/polls",
        json={"question": "Q2", "options": ["C", "D"]},
    ).json["poll"]

    foreign_option_id = poll2["options"][0]["id"]
    response = client.post(
        f"/api/polls/{poll1['id']}/vote",
        json={"option_id": foreign_option_id},
    )
    assert response.status_code == 400
    assert "error" in response.json
    assert response.json.get("code") == "invalid_poll_option"

    from app.models import get_db

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM poll_votes WHERE poll_id = ?", (poll1["id"],))
    assert cursor.fetchone()[0] == 0


def test_password_change_invalidates_other_http_session(app):
    client_a = app.test_client()
    client_b = app.test_client()

    _register(client_a, "multi_session_user")
    _login(client_a, "multi_session_user")
    _login(client_b, "multi_session_user")

    response = client_b.put(
        "/api/me/password",
        json={
            "current_password": "Password123!",
            "new_password": "Password456!",
        },
    )
    assert response.status_code == 200
    assert response.json["success"] is True

    stale_request = client_a.get("/api/rooms")
    assert stale_request.status_code == 401


def test_malformed_json_returns_400(client):
    _register(client, "json_guard_user")
    _login(client, "json_guard_user")

    response = client.put(
        "/api/profile",
        data="[]",
        content_type="application/json",
    )
    assert response.status_code == 400

    response = client.put(
        "/api/me/password",
        data="{",
        content_type="application/json",
    )
    assert response.status_code == 400


def test_upload_returns_pending_when_av_enabled(client, monkeypatch):
    _register(client, "upload_pending_user")
    _login(client, "upload_pending_user")
    room_id = _create_room(client, name="upload-pending-room")

    import app.routes as routes

    monkeypatch.setattr(routes, "is_scan_enabled", lambda app: True)
    monkeypatch.setattr(routes, "create_scan_job", lambda **kwargs: "job-test-123")

    response = client.post(
        "/api/upload",
        data={
            "room_id": str(room_id),
            "file": (io.BytesIO(b"\x89PNG\r\n\x1a\n"), "scan.png"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.json["success"] is True
    assert response.json["scan_status"] == "pending"
    assert response.json["job_id"] == "job-test-123"


def test_admin_audit_logs_csv_export(client):
    _register(client, "admin1")
    _register(client, "admin2")
    _login(client, "admin1")
    room_id = _create_room(client, member_ids=[1, 2], name="audit-room")

    promote = client.post(
        f"/api/rooms/{room_id}/admins",
        json={"user_id": 2, "is_admin": True},
    )
    assert promote.status_code == 200

    response = client.get(f"/api/rooms/{room_id}/admin-audit-logs?format=csv")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/csv")
    body = response.data.decode("utf-8")
    assert "set_admin" in body


def test_socket_connect_rejects_invalid_session_token(app):
    client = app.test_client()
    _register(client, "socket_guard")
    _login(client, "socket_guard")

    with client.session_transaction() as sess:
        sess["session_token"] = "invalid-token"

    from app import socketio

    socket_client = socketio.test_client(app, flask_test_client=client)
    assert not socket_client.is_connected()


def test_socket_send_message_rate_limit(app):
    app.config["SOCKET_SEND_MESSAGE_PER_MINUTE"] = 1
    client = app.test_client()
    _register(client, "socket_limit")
    _login(client, "socket_limit")
    room_id = _create_room(client, name="rate-room")

    from app import socketio

    socket_client = socketio.test_client(app, flask_test_client=client)
    assert socket_client.is_connected()
    try:
        socket_client.emit(
            "send_message",
            {"room_id": room_id, "content": "one", "type": "text", "encrypted": False},
        )
        first_events = socket_client.get_received()
        assert any(evt["name"] == "new_message" for evt in first_events)

        socket_client.emit(
            "send_message",
            {"room_id": room_id, "content": "two", "type": "text", "encrypted": False},
        )
        second_events = socket_client.get_received()
        errors = [evt for evt in second_events if evt["name"] == "error"]
        assert errors
        assert any("속도 제한" in (evt["args"][0].get("message") or "") for evt in errors)
    finally:
        socket_client.disconnect()
