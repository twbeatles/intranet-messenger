# -*- coding: utf-8 -*-


def _register(client, username, password="Password123!", nickname=None):
    return client.post(
        "/api/register",
        json={"username": username, "password": password, "nickname": nickname or username},
    )


def _login(client, username, password="Password123!"):
    return client.post("/api/login", json={"username": username, "password": password})


def test_create_room_with_members_payload(client):
    _register(client, "roomowner", nickname="Room Owner")
    _register(client, "roompeer", nickname="Room Peer")
    _login(client, "roomowner")

    users = client.get("/api/users").json
    peer = next(u for u in users if u["username"] == "roompeer")

    resp = client.post("/api/rooms", json={"name": "Team Room", "members": [peer["id"]]})
    assert resp.status_code == 200
    assert resp.json["success"] is True
    assert isinstance(resp.json["room_id"], int)


def test_create_room_member_ids_alias_supported(client):
    _register(client, "aliasowner", nickname="Alias Owner")
    _register(client, "aliaspeer", nickname="Alias Peer")
    _login(client, "aliasowner")

    users = client.get("/api/users").json
    peer = next(u for u in users if u["username"] == "aliaspeer")

    resp = client.post("/api/rooms", json={"name": "Alias Room", "member_ids": [peer["id"]]})
    assert resp.status_code == 200
    assert resp.json["success"] is True
    assert isinstance(resp.json["room_id"], int)
