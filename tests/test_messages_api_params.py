# -*- coding: utf-8 -*-


def _register(client, username, password="Password123!", nickname=None):
    return client.post(
        "/api/register",
        json={"username": username, "password": password, "nickname": nickname or username},
    )


def _login(client, username, password="Password123!"):
    return client.post("/api/login", json={"username": username, "password": password})


def test_get_messages_limit_and_include_meta(client):
    _register(client, "usr1", nickname="U1")
    _register(client, "usr2", nickname="U2")

    r = _login(client, "usr1")
    assert r.status_code == 200

    users = client.get("/api/users").json
    u2 = next(u for u in users if u["username"] == "usr2")

    resp = client.post("/api/rooms", json={"members": [u2["id"]]})
    assert resp.status_code == 200
    room_id = resp.json["room_id"]

    from app.models.messages import create_message

    with client.application.app_context():
        # Create enough messages to test pagination/limit behavior.
        for i in range(40):
            create_message(
                room_id=room_id,
                sender_id=u2["id"],
                content=f"m{i}",
                message_type="text",
                encrypted=False,
            )

    r2 = client.get(f"/api/rooms/{room_id}/messages?limit=30&include_meta=0")
    assert r2.status_code == 200
    data = r2.json
    assert "messages" in data
    assert len(data["messages"]) <= 30
    assert "members" not in data
    assert "encryption_key" not in data

    r3 = client.get(f"/api/rooms/{room_id}/messages?limit=10")
    assert r3.status_code == 200
    data2 = r3.json
    assert "messages" in data2
    assert len(data2["messages"]) <= 10
    assert "members" in data2
    assert "encryption_key" in data2
