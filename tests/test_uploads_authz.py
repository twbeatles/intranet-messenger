import os


def _register(client, username: str, password: str = "Password123!", nickname: str | None = None):
    res = client.post(
        "/api/register",
        json={"username": username, "password": password, "nickname": nickname or username},
    )
    assert res.status_code == 200
    assert res.json["success"] is True


def _login(client, username: str, password: str = "Password123!"):
    res = client.post("/api/login", json={"username": username, "password": password})
    assert res.status_code == 200
    assert res.json["success"] is True


def test_uploads_requires_login(client):
    r = client.get("/uploads/does-not-matter.txt")
    assert r.status_code == 401


def test_uploads_room_member_only(app):
    import config
    from app.models import add_room_file

    c1 = app.test_client()
    c2 = app.test_client()

    _register(c1, "u1")
    _register(c1, "u2")
    _register(c1, "u3")

    _login(c1, "u1")

    # create a room with u2
    users = c1.get("/api/users").json
    u2 = next(u for u in users if u["username"] == "u2")
    room = c1.post("/api/rooms", json={"members": [u2["id"]]}).json
    assert room["success"] is True
    room_id = room["room_id"]

    # Create a physical file + room_files record
    file_path = "testfile.txt"
    os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
    with open(os.path.join(config.UPLOAD_FOLDER, file_path), "wb") as f:
        f.write(b"hello")

    # uploaded_by=1 is safe here because DB is empty and u1 is the first user created
    add_room_file(room_id, uploaded_by=1, file_path=file_path, file_name="testfile.txt", file_size=5, file_type="file")

    # member can download
    r = c1.get(f"/uploads/{file_path}")
    assert r.status_code == 200

    # non-member cannot download
    _login(c2, "u3")
    r = c2.get(f"/uploads/{file_path}")
    assert r.status_code == 403


def test_uploads_profiles_allowed_for_logged_in(app):
    import config

    c = app.test_client()
    _register(c, "u1p")
    _login(c, "u1p")

    profile_dir = os.path.join(config.UPLOAD_FOLDER, "profiles")
    os.makedirs(profile_dir, exist_ok=True)
    fname = "p.png"
    with open(os.path.join(profile_dir, fname), "wb") as f:
        f.write(b"\\x89PNG\\r\\n\\x1a\\n")  # minimal header

    r = c.get(f"/uploads/profiles/{fname}")
    assert r.status_code == 200

