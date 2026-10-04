# -*- coding: utf-8 -*-
"""ISSUE-003: 복원 스크립트 WAL 처리·서버 감지·스냅샷 분리 회귀 테스트."""

from __future__ import annotations

import importlib.util
import socket
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_restore_module():
    path = REPO_ROOT / "scripts" / "restore_local.py"
    spec = importlib.util.spec_from_file_location("restore_local_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_db(path: Path, marker: str) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO t (v) VALUES (?)", (marker,))
    conn.commit()
    conn.close()


def test_is_server_running_detects_open_and_closed_ports():
    restore = _load_restore_module()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
    assert restore._is_server_running(free_port, timeout=1.0) is False

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        live_port = listener.getsockname()[1]
        assert restore._is_server_running(live_port, timeout=2.0) is True
    finally:
        listener.close()


def test_restore_clears_wal_and_separates_snapshot(tmp_path, monkeypatch):
    restore = _load_restore_module()

    target_db = tmp_path / "target" / "messenger.db"
    target_db.parent.mkdir(parents=True)
    target_uploads = tmp_path / "target" / "uploads"
    target_uploads.mkdir(parents=True)
    (target_uploads / "old.txt").write_text("old", encoding="utf-8")
    _make_db(target_db, "before-restore")
    # 잔존 WAL/-shm 시뮬레이션: 체크포인트 대상 파일이 실제로 제거되는지 검증한다.
    (tmp_path / "target" / "messenger.db-wal").write_bytes(b"\x00" * 32)
    (tmp_path / "target" / "messenger.db-shm").write_bytes(b"\x00" * 32)

    backup_dir = tmp_path / "backup_20260101T000000Z_label"
    (backup_dir / "db").mkdir(parents=True)
    (backup_dir / "uploads").mkdir(parents=True)
    _make_db(backup_dir / "db" / "messenger.db", "from-backup")
    (backup_dir / "uploads" / "new.txt").write_text("new", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "restore_local.py",
            str(backup_dir),
            "--db-path",
            str(target_db),
            "--uploads-dir",
            str(target_uploads),
            "--yes",
            "--force",
        ],
    )
    assert restore.main() == 0

    assert not (tmp_path / "target" / "messenger.db-wal").exists()
    assert not (tmp_path / "target" / "messenger.db-shm").exists()

    conn = sqlite3.connect(str(target_db))
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT v FROM t").fetchone()[0] == "from-backup"
    finally:
        conn.close()
    assert (target_uploads / "new.txt").read_text(encoding="utf-8") == "new"
    assert not (target_uploads / "old.txt").exists()

    snapshots = list((tmp_path / "target").glob("pre_restore_snapshot_*"))
    assert len(snapshots) == 1
    snap_db = snapshots[0] / "messenger.db.before_restore"
    assert snap_db.exists()
    conn = sqlite3.connect(str(snap_db))
    try:
        assert conn.execute("SELECT v FROM t").fetchone()[0] == "before-restore"
    finally:
        conn.close()
    # 스냅샷이 백업 디렉토리 밖에 분리되어 백업본을 오염시키지 않는다.
    assert list(backup_dir.glob("pre_restore_snapshot_*")) == []


def test_restore_refuses_when_server_running(tmp_path, monkeypatch):
    restore = _load_restore_module()

    target_db = tmp_path / "target" / "messenger.db"
    target_db.parent.mkdir(parents=True)
    _make_db(target_db, "before-restore")
    target_uploads = tmp_path / "target" / "uploads"
    target_uploads.mkdir(parents=True)

    backup_dir = tmp_path / "backup_x"
    (backup_dir / "db").mkdir(parents=True)
    (backup_dir / "uploads").mkdir(parents=True)
    _make_db(backup_dir / "db" / "messenger.db", "from-backup")

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        live_port = listener.getsockname()[1]
        monkeypatch.setattr(restore, "_control_port", lambda: live_port)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "restore_local.py",
                str(backup_dir),
                "--db-path",
                str(target_db),
                "--uploads-dir",
                str(target_uploads),
                "--yes",
            ],
        )
        assert restore.main() == 1
    finally:
        listener.close()

    conn = sqlite3.connect(str(target_db))
    try:
        assert conn.execute("SELECT v FROM t").fetchone()[0] == "before-restore"
    finally:
        conn.close()
