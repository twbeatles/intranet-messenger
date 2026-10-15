# -*- coding: utf-8 -*-
"""Backup / restore / deletion integrity tests (MSG-05/06/07 + AUTH-06).

All scenarios run against the real test SQLite file and the real test
uploads directory (isolated per test by conftest). Results are verified with
independent oracles: sqlite integrity_check, row counts, file SHA-256 and
on-disk presence -- never by re-importing the production filter to compute
the expectation.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

from tests.test_feature_risk_review_plan import _login

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    path = REPO_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _db_row_count(db_path: str, table: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    finally:
        conn.close()


def _find_backup_dir(output_root: Path):
    dirs = [p for p in output_root.iterdir() if p.is_dir() and p.name.startswith("backup_")]
    assert len(dirs) == 1
    return dirs[0]


def _make_room_with_attachment(client, app, owner_name: str, viewer_name: str,
                               room_name: str, payload: bytes):
    from tests.test_feature_risk_review_plan import _create_room, _login, _register

    _register(client, owner_name)
    _register(client, viewer_name)
    _login(client, owner_name)
    from app.models import create_message, create_room
    from app.services.runtime_paths import get_upload_folder

    owner_id = int(client.get("/api/me").json["user"]["id"])
    viewer_id = next(u["id"] for u in client.get("/api/users").json
                     if u["username"] == viewer_name)
    room_id = create_room(room_name, "group", owner_id, [owner_id, viewer_id])
    upload_folder = get_upload_folder()
    stored = f"{room_name}.bin"
    (Path(upload_folder) / stored).write_bytes(payload)
    msg = create_message(room_id, owner_id, "shared file", "file",
                         file_path=stored, file_name=stored)
    assert msg and msg["id"]
    return owner_id, viewer_id, room_id, int(msg["id"]), stored


def test_msg05_live_wal_backup_integrity(app, tmp_path, monkeypatch):
    """MSG-05: WAL 활성 상태의 실 DB를 백업하면 integrity ok + 행/첨부 일치."""
    import config

    backup = _load_script("backup_local.py")
    client = app.test_client()
    payload = b"msg05-attachment-bytes"
    _, _, room_id, msg_id, stored = _make_room_with_attachment(
        client, app, "msg05_owner", "msg05_viewer", "msg05-room", payload)

    # WAL 모드를 켜고 체크포인트 없이 백업한다 (미체크포인트 상태 재현).
    conn = sqlite3.connect(config.DATABASE_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("INSERT INTO messages (room_id, sender_id, content, encrypted, message_type, key_version) VALUES (?, ?, ?, 0, 'text', 1)",
                     (room_id, 1, "msg05-uncheckpointed"))
        conn.commit()
    finally:
        conn.close()

    out_root = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["backup_local.py", "--output-root", str(out_root),
                                      "--db-path", config.DATABASE_PATH,
                                      "--uploads-dir", config.UPLOAD_FOLDER,
                                      "--label", "msg05"])
    assert backup.main() == 0

    backup_dir = _find_backup_dir(out_root)
    backup_db = backup_dir / "db" / "messenger.db"
    conn = sqlite3.connect(str(backup_db))
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        live_messages = _db_row_count(config.DATABASE_PATH, "messages")
        assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == live_messages
        assert conn.execute("SELECT COUNT(*) FROM messages WHERE id = ?",
                            (msg_id,)).fetchone()[0] == 1
    finally:
        conn.close()
    assert _sha256(backup_dir / "uploads" / stored) == hashlib.sha256(payload).hexdigest()
    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["stats"]["db_size_bytes"] > 0
    assert manifest["stats"]["uploads_file_count"] >= 1


def test_msg06_backup_mutate_restore_roundtrip(app, tmp_path, monkeypatch):
    """MSG-06: backup -> 변경 -> restore 후 기준점 DB+파일 SHA 일치, WAL 잔재 0."""
    import config

    backup = _load_script("backup_local.py")
    restore = _load_script("restore_local.py")
    client = app.test_client()
    payload = b"msg06-baseline-bytes"
    _, _, room_id, msg_id, stored = _make_room_with_attachment(
        client, app, "msg06_owner", "msg06_viewer", "msg06-room", payload)

    from app.models import create_message
    baseline_count = _db_row_count(config.DATABASE_PATH, "messages")
    baseline_sha = _sha256(Path(config.UPLOAD_FOLDER) / stored)

    out_root = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["backup_local.py", "--output-root", str(out_root),
                                      "--db-path", config.DATABASE_PATH,
                                      "--uploads-dir", config.UPLOAD_FOLDER,
                                      "--label", "msg06"])
    assert backup.main() == 0
    backup_dir = _find_backup_dir(out_root)

    # 기준점 이후 변경: 새 메시지 + 새 첨부.
    owner_id = int(client.get("/api/me").json["user"]["id"])
    extra = create_message(room_id, owner_id, "msg06-post-backup", "text", encrypted=False)
    assert extra and extra["id"]
    (Path(config.UPLOAD_FOLDER) / "msg06-extra.bin").write_bytes(b"extra")
    assert _db_row_count(config.DATABASE_PATH, "messages") == baseline_count + 1

    # The app holds the test DB file open (WAL lock on Windows), so release
    # the thread-local connection before restoring -- same precondition the
    # runbook requires (server stopped).
    from app.models.base import close_thread_db
    close_thread_db()
    snapshots_before = set(Path(config.DATABASE_PATH).parent.glob("pre_restore_snapshot_*"))
    monkeypatch.setattr(sys, "argv", ["restore_local.py", str(backup_dir),
                                      "--db-path", config.DATABASE_PATH,
                                      "--uploads-dir", config.UPLOAD_FOLDER,
                                      "--yes", "--force"])
    assert restore.main() == 0

    assert _db_row_count(config.DATABASE_PATH, "messages") == baseline_count
    conn = sqlite3.connect(config.DATABASE_PATH)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT COUNT(*) FROM messages WHERE id = ?",
                            (extra["id"],)).fetchone()[0] == 0
    finally:
        conn.close()
    assert (Path(config.UPLOAD_FOLDER) / stored).exists()
    assert _sha256(Path(config.UPLOAD_FOLDER) / stored) == baseline_sha
    assert not (Path(config.UPLOAD_FOLDER) / "msg06-extra.bin").exists()
    assert not Path(str(config.DATABASE_PATH) + "-wal").exists()
    assert not Path(str(config.DATABASE_PATH) + "-shm").exists()
    # The shared pytest tmp dir may hold older snapshots, so only require
    # exactly one NEW snapshot, holding the pre-restore (mutated) state.
    snapshots_after = set(Path(config.DATABASE_PATH).parent.glob("pre_restore_snapshot_*"))
    new_snapshots = snapshots_after - snapshots_before
    assert len(new_snapshots) == 1
    fresh = new_snapshots.pop()
    assert (fresh / "messenger.db.before_restore").exists()
    snap_conn = sqlite3.connect(str(fresh / "messenger.db.before_restore"))
    try:
        assert snap_conn.execute("SELECT COUNT(*) FROM messages WHERE id = ?",
                                 (extra["id"],)).fetchone()[0] == 1
    finally:
        snap_conn.close()
    assert list(backup_dir.glob("pre_restore_snapshot_*")) == []


def test_msg07_restore_uploads_copy_failure_is_never_silent_success(tmp_path, monkeypatch):
    """MSG-07: uploads 복사 실패는 성공으로 보고되지 않는다 (예외 가시화 + 스냅샷 보존)."""
    import shutil as shutil_module

    restore = _load_script("restore_local.py")
    target_db = tmp_path / "target" / "messenger.db"
    target_db.parent.mkdir(parents=True)
    target_uploads = tmp_path / "target" / "uploads"
    target_uploads.mkdir(parents=True)
    (target_uploads / "old.txt").write_text("old", encoding="utf-8")
    conn = sqlite3.connect(str(target_db))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO t (v) VALUES ('before-restore')")
    conn.commit()
    conn.close()

    backup_dir = tmp_path / "backup_msg07"
    (backup_dir / "db").mkdir(parents=True)
    (backup_dir / "uploads").mkdir(parents=True)
    conn = sqlite3.connect(str(backup_dir / "db" / "messenger.db"))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO t (v) VALUES ('from-backup')")
    conn.commit()
    conn.close()
    (backup_dir / "uploads" / "new.txt").write_text("new", encoding="utf-8")

    real_copytree = shutil_module.copytree

    def fail_on_uploads_restore(src, dst, *args, **kwargs):
        if Path(dst) == target_uploads:
            raise OSError("injected disk-full during uploads restore")
        return real_copytree(src, dst, *args, **kwargs)

    monkeypatch.setattr(shutil_module, "copytree", fail_on_uploads_restore)
    monkeypatch.setattr(sys, "argv", ["restore_local.py", str(backup_dir),
                                      "--db-path", str(target_db),
                                      "--uploads-dir", str(target_uploads),
                                      "--yes", "--force"])
    with pytest.raises(OSError):
        restore.main()

    # 실패가 0(성공)으로 위장되지 않았고, 안전 스냅샷에 복구용 사본이 남는다.
    snapshots = list((tmp_path / "target").glob("pre_restore_snapshot_*"))
    assert len(snapshots) == 1
    assert (snapshots[0] / "messenger.db.before_restore").exists()


def test_auth06_deleted_owner_leaves_no_dangling_links(app):
    """AUTH-06: 탈퇴자 바이트 삭제 후 메시지 참조 정리 + 잔류 멤버 방 정합 + dangling 0."""
    from app.models import delete_user, get_db
    from app.services.runtime_paths import get_upload_folder

    client = app.test_client()
    viewer = app.test_client()
    payload = b"auth06-attachment-bytes"
    owner_id, viewer_id, room_id, msg_id, stored = _make_room_with_attachment(
        client, app, "auth06_owner", "auth06_viewer", "auth06-room", payload)
    disk_path = os.path.join(get_upload_folder(), stored)
    assert os.path.exists(disk_path)

    success, error = delete_user(owner_id, "Password123!")
    assert success, error

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT file_path, file_name FROM messages WHERE sender_id = ?", (owner_id,))
    for row in cur.fetchall():
        assert row["file_path"] is None
        assert row["file_name"] is None
    cur.execute("SELECT COUNT(*) AS cnt FROM room_files WHERE uploaded_by = ?", (owner_id,))
    assert cur.fetchone()["cnt"] == 0
    # dangling link 0: room_files가 가리키는 파일은 모두 디스크에 존재한다.
    cur.execute("SELECT file_path FROM room_files WHERE file_path IS NOT NULL")
    upload_folder = get_upload_folder()
    for row in cur.fetchall():
        assert os.path.exists(os.path.join(upload_folder, row["file_path"]))
    assert not os.path.exists(disk_path)

    # 잔류 멤버(viewer)의 방은 유지되고, 삭제된 첨부 메시지는 history에서 숨겨진다.
    _login(viewer, "auth06_viewer")
    rooms = viewer.get("/api/rooms").json
    assert room_id in [r["id"] for r in rooms]
    history = viewer.get(f"/api/rooms/{room_id}/messages").json["messages"]
    assert msg_id not in [m["id"] for m in history]
