# -*- coding: utf-8 -*-
import pytest


def _register(client, username, password="Password123!", nickname=None):
    return client.post(
        "/api/register",
        json={"username": username, "password": password, "nickname": nickname or username},
    )


def _login(client, username, password="Password123!"):
    return client.post("/api/login", json={"username": username, "password": password})


def test_rooms_payload_members_default_excluded_and_preview_present(client):
    # 3 users -> group room
    _register(client, "usr1", nickname="U1")
    _register(client, "usr2", nickname="U2")
    _register(client, "usr3", nickname="U3")

    r = _login(client, "usr1")
    assert r.status_code == 200

    users = client.get("/api/users").json
    u2 = next(u for u in users if u["username"] == "usr2")
    u3 = next(u for u in users if u["username"] == "usr3")

    resp = client.post("/api/rooms", json={"name": "G", "members": [u2["id"], u3["id"]]})
    assert resp.status_code == 200
    room_id = resp.json["room_id"]

    # Insert an encrypted last message so preview becomes "[암호화된 메시지]"
    from app.models.messages import create_message

    with client.application.app_context():
        create_message(
            room_id=room_id,
            sender_id=u2["id"],
            content="v2:Zm9v:YmFy:YmF6:cXV4",
            message_type="text",
            encrypted=True,
        )

    rooms = client.get("/api/rooms").json
    room = next(r for r in rooms if r["id"] == room_id)

    # Default: group room members should be omitted
    assert room.get("type") == "group"
    assert "members" not in room

    # Preview fields
    assert "last_message_preview" in room
    assert room["last_message_preview"] == "[암호화된 메시지]"
    assert room.get("last_message") is None

    rooms2 = client.get("/api/rooms?include_members=1").json
    room2 = next(r for r in rooms2 if r["id"] == room_id)
    assert "members" in room2
    member_ids = sorted(m["id"] for m in room2["members"])
    assert u2["id"] in member_ids
    assert u3["id"] in member_ids
