# -*- coding: utf-8 -*-
"""스캔 job 재시도/취소 API 회귀 테스트."""

from __future__ import annotations

import os


def _register(client, username: str):
    res = client.post(
        "/api/register",
        json={"username": username, "password": "Password123!", "nickname": username},
    )
    assert res.status_code == 200


def _login(client, username: str):
    res = client.post("/api/login", json={"username": username, "password": "Password123!"})
    assert res.status_code == 200


def _setup_room(app, owner, other_username: str = "scanmate"):
    _register(owner, other_username)
    users = owner.get("/api/users").json
    other_id = next(u["id"] for u in users if u["username"] == other_username)
    room = owner.post("/api/rooms", json={"members": [other_id]}).json
    assert room["success"] is True
    return room["room_id"]


def _make_job(app, client, temp_name: str = "scan-tmp.bin"):
    from app.upload_scan import create_scan_job

    me = client.get("/api/me").json["user"]
    room_id = _setup_room(app, client)
    quarantine_dir = os.path.join(app.config["UPLOAD_FOLDER"], "quarantine")
    os.makedirs(quarantine_dir, exist_ok=True)
    temp_abs = os.path.join(quarantine_dir, temp_name)
    with open(temp_abs, "wb") as handle:
        handle.write(b"scan-temp-bytes")
    job_id = create_scan_job(
        user_id=me["id"],
        room_id=room_id,
        temp_path=f"quarantine/{temp_name}",
        final_path=temp_name,
        file_name=temp_name,
        file_type="file",
        file_size=15,
    )
    return job_id, temp_abs, me["id"]


def test_retry_failed_scan_job(app):
    from app.upload_scan import _update_scan_job, get_scan_job

    c = app.test_client()
    _register(c, "scanretry")
    _login(c, "scanretry")
    job_id, _temp_abs, _uid = _make_job(app, c)
    _update_scan_job(job_id, "error", "clamav scan failed: timeout")

    res = c.post(f"/api/upload/jobs/{job_id}/retry")
    assert res.status_code == 200
    assert res.json["scan_status"] == "pending"
    job = get_scan_job(job_id)
    assert job and job["status"] == "pending"


def test_retry_rejects_non_error_and_foreign_jobs(app):
    from app.upload_scan import _update_scan_job

    owner = app.test_client()
    stranger = app.test_client()
    _register(owner, "scanowner")
    _register(owner, "scanstranger")
    _login(owner, "scanowner")
    job_id, _temp_abs, _uid = _make_job(app, owner)

    # pending 상태 재시도 거부
    res = owner.post(f"/api/upload/jobs/{job_id}/retry")
    assert res.status_code == 400

    # infected 상태 재시도 거부 (재업로드 요구)
    _update_scan_job(job_id, "infected", "EICAR FOUND")
    res = owner.post(f"/api/upload/jobs/{job_id}/retry")
    assert res.status_code == 400

    # 타인 job 재시도 거부
    _update_scan_job(job_id, "error", "boom")
    _login(stranger, "scanstranger")
    res = stranger.post(f"/api/upload/jobs/{job_id}/retry")
    assert res.status_code == 403

    # 없는 job
    res = owner.post("/api/upload/jobs/does-not-exist/retry")
    assert res.status_code == 404


def test_cancel_scan_job_removes_temp(app):
    from app.upload_scan import get_scan_job

    c = app.test_client()
    _register(c, "scancancel")
    _login(c, "scancancel")
    job_id, temp_abs, _uid = _make_job(app, c, temp_name="cancel-me.bin")
    assert os.path.exists(temp_abs)

    res = c.delete(f"/api/upload/jobs/{job_id}")
    assert res.status_code == 200
    assert res.json["scan_status"] == "cancelled"
    job = get_scan_job(job_id)
    assert job and job["status"] == "cancelled"
    assert not os.path.exists(temp_abs)

    # 중복 취소 거부
    res = c.delete(f"/api/upload/jobs/{job_id}")
    assert res.status_code == 400


def test_cancel_clean_job_rejected(app):
    from app.upload_scan import _update_scan_job

    c = app.test_client()
    _register(c, "scancancel2")
    _login(c, "scancancel2")
    job_id, _temp_abs, _uid = _make_job(app, c, temp_name="clean.bin")
    _update_scan_job(job_id, "clean", "clean", token="tok")

    res = c.delete(f"/api/upload/jobs/{job_id}")
    assert res.status_code == 400
