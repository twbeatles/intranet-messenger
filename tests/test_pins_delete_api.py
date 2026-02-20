# -*- coding: utf-8 -*-


def test_delete_nonexistent_pin_returns_not_found(client):
    client.post("/api/register", json={"username": "pinowner", "password": "Password123!", "nickname": "Pin Owner"})
    client.post("/api/login", json={"username": "pinowner", "password": "Password123!"})

    room_resp = client.post("/api/rooms", json={"name": "Pin Room", "members": []})
    assert room_resp.status_code == 200
    room_id = room_resp.json["room_id"]

    resp = client.delete(f"/api/rooms/{room_id}/pins/999999")
    assert resp.status_code == 404
    assert resp.json.get("success") is not True
    assert "찾을 수 없습니다" in (resp.json.get("error") or "")
