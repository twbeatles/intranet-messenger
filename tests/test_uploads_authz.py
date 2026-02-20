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
    from app.models import add_room_file

    c1 = app.test_client()
    c2 = app.test_client()

    _register(c1, "usr1")
    _register(c1, "usr2")
    _register(c1, "usr3")

    _login(c1, "usr1")

    # create a room with u2
    users = c1.get("/api/users").json
    u2 = next(u for u in users if u["username"] == "usr2")
    room = c1.post("/api/rooms", json={"members": [u2["id"]]}).json
    assert room["success"] is True
    room_id = room["room_id"]

    # Create a physical file + room_files record
    file_path = "testfile.txt"
    upload_root = app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_root, exist_ok=True)
    with open(os.path.join(upload_root, file_path), "wb") as f:
        f.write(b"hello")

    me = c1.get("/api/me").json["user"]
    with app.app_context():
        add_room_file(room_id, uploaded_by=me["id"], file_path=file_path, file_name="testfile.txt", file_size=5, file_type="file")

    # member can download
    r = c1.get(f"/uploads/{file_path}")
    assert r.status_code == 200
    assert r.headers.get("Cache-Control") == "private, no-store"

    # non-member cannot download
    _login(c2, "usr3")
    r = c2.get(f"/uploads/{file_path}")
    assert r.status_code == 403


def test_uploads_profiles_allowed_for_logged_in(app):
    c = app.test_client()
    _register(c, "usr1p")
    _login(c, "usr1p")

    profile_dir = os.path.join(app.config["UPLOAD_FOLDER"], "profiles")
    os.makedirs(profile_dir, exist_ok=True)
    fname = "p.png"
    with open(os.path.join(profile_dir, fname), "wb") as f:
        f.write(b"\\x89PNG\\r\\n\\x1a\\n")  # minimal header

    r = c.get(f"/uploads/profiles/{fname}")
    assert r.status_code == 200
    assert r.headers.get("Cache-Control") == "private, max-age=3600"

