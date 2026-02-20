# -*- coding: utf-8 -*-


def _register(client, username, password="Password123!", nickname=None):
    return client.post(
        "/api/register",
        json={"username": username, "password": password, "nickname": nickname or username},
    )


def _login(client, username, password="Password123!"):
    return client.post("/api/login", json={"username": username, "password": password})


def test_create_room_accepts_member_ids_alias(client):
    _register(client, "owner001", nickname="Owner")
    _register(client, "peer001", nickname="Peer")
    _login(client, "owner001")

    users = client.get("/api/users").json
    peer = next(u for u in users if u["username"] == "peer001")

    resp = client.post("/api/rooms", json={"name": "Alias Compatible", "member_ids": [peer["id"]]})
    assert resp.status_code == 200
    assert resp.json["success"] is True
    assert isinstance(resp.json["room_id"], int)


def test_create_room_members_takes_precedence_over_member_ids(client):
    _register(client, "owner002", nickname="Owner2")
    _register(client, "peer002a", nickname="PeerA")
    _register(client, "peer002b", nickname="PeerB")
    _login(client, "owner002")

    users = client.get("/api/users").json
    peer_a = next(u for u in users if u["username"] == "peer002a")
    peer_b = next(u for u in users if u["username"] == "peer002b")

    resp = client.post(
        "/api/rooms",
        json={
            "name": "Members Priority",
            "members": [peer_a["id"]],
            "member_ids": [peer_b["id"]],
        },
    )
    assert resp.status_code == 200
    room_id = resp.json["room_id"]

    room_info = client.get(f"/api/rooms/{room_id}/info")
    assert room_info.status_code == 200
    member_ids = sorted(m["id"] for m in room_info.json["members"])
    assert peer_a["id"] in member_ids
    assert peer_b["id"] not in member_ids
