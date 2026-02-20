# -*- coding: utf-8 -*-
def _register(client, username, password="Password123!", nickname=None):
    return client.post(
        "/api/register",
        json={"username": username, "password": password, "nickname": nickname or username},
    )


def _login(client, username, password="Password123!"):
    return client.post("/api/login", json={"username": username, "password": password})


def test_search_excludes_encrypted_text_messages(client):
    _register(client, "src1", nickname="S1")
    _register(client, "src2", nickname="S2")

    r = _login(client, "src1")
    assert r.status_code == 200

    users = client.get("/api/users").json
    s2 = next(u for u in users if u["username"] == "src2")

    resp = client.post("/api/rooms", json={"members": [s2["id"]]})
    assert resp.status_code == 200
    room_id = resp.json["room_id"]

    from app.models.messages import create_message
    me = client.get("/api/me").json["user"]
    sender_id = me["id"]

    with client.application.app_context():
        # Plaintext message (searchable)
        create_message(
            room_id=room_id,
            sender_id=sender_id,
            content="hello world",
            message_type="text",
            encrypted=False,
        )
        # Encrypted message (not searchable by content)
        create_message(
            room_id=room_id,
            sender_id=sender_id,
            content="v2:Zm9v:YmFy:YmF6:cXV4",
            message_type="text",
            encrypted=True,
        )

    results = client.get("/api/search?q=hello").json
    assert isinstance(results, list)
    assert any("hello" in (m.get("content") or "") for m in results)
    # Encrypted ciphertext should not appear
    assert not any((m.get("content") or "").startswith("v2:") for m in results)


def test_file_only_search_uses_file_name(client):
    _register(client, "fil1", nickname="F1")
    _register(client, "fil2", nickname="F2")
    _login(client, "fil1")

    users = client.get("/api/users").json
    f2 = next(u for u in users if u["username"] == "fil2")

    resp = client.post("/api/rooms", json={"members": [f2["id"]]})
    room_id = resp.json["room_id"]

    from app.models.messages import create_message
    me = client.get("/api/me").json["user"]
    sender_id = me["id"]

    with client.application.app_context():
        create_message(
            room_id=room_id,
            sender_id=sender_id,
            content="[file]",
            message_type="file",
            file_path="x",
            file_name="report.pdf",
            encrypted=False,
        )

    results = client.get("/api/search?file_only=1&q=report").json
    assert isinstance(results, list)
    assert any((m.get("file_name") or "") == "report.pdf" for m in results)
