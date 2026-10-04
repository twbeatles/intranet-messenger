#!/usr/bin/env python3
"""Manual local restore utility for intranet-messenger backups."""

from __future__ import annotations

import argparse
import shutil
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path


def _import_defaults():
    try:
        from config import DATABASE_PATH, UPLOAD_FOLDER
    except Exception:
        base_dir = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(base_dir))
        from config import DATABASE_PATH, UPLOAD_FOLDER  # type: ignore
    return Path(DATABASE_PATH), Path(UPLOAD_FOLDER)


def _control_port() -> int:
    try:
        from config import CONTROL_PORT

        return int(CONTROL_PORT)
    except Exception:
        return 5001


def _is_server_running(port: int, timeout: float = 2.0) -> bool:
    """제어 포트에 TCP 연결이 되면 서버 실행 중으로 판단한다."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _checkpoint_and_clear_wal(db_path: Path) -> bool:
    """WAL 체크포인트 후 -wal/-shm 잔존 파일을 제거한다. 실패 시 False."""
    import sqlite3

    try:
        conn = sqlite3.connect(str(db_path), timeout=10)
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        print(f"[ERROR] WAL checkpoint failed: {exc}")
        return False
    for suffix in ("-wal", "-shm"):
        try:
            Path(str(db_path) + suffix).unlink(missing_ok=True)
        except Exception as exc:
            print(f"[ERROR] Failed to remove {db_path}{suffix}: {exc}")
            return False
    return True


def _fail(message: str) -> int:
    print(f"[ERROR] {message}")
    return 1


def main() -> int:
    default_db, default_uploads = _import_defaults()

    parser = argparse.ArgumentParser(description="Restore from local backup")
    parser.add_argument("backup_dir", help="Backup directory created by backup_local.py")
    parser.add_argument("--db-path", default=str(default_db), help="Target SQLite DB path")
    parser.add_argument("--uploads-dir", default=str(default_uploads), help="Target uploads directory")
    parser.add_argument("--yes", action="store_true", help="Apply restore without confirmation prompt")
    parser.add_argument("--force", action="store_true", help="Bypass the running-server check (use only when the server is certainly stopped)")
    args = parser.parse_args()

    backup_dir = Path(args.backup_dir).resolve()
    backup_db = backup_dir / "db" / "messenger.db"
    backup_uploads = backup_dir / "uploads"

    target_db = Path(args.db_path).resolve()
    target_uploads = Path(args.uploads_dir).resolve()

    if not backup_dir.exists():
        return _fail(f"backup_dir does not exist: {backup_dir}")
    if not backup_db.exists():
        return _fail(f"backup DB not found: {backup_db}")
    if not backup_uploads.exists():
        return _fail(f"backup uploads not found: {backup_uploads}")

    if not args.yes:
        print("[WARN] This operation overwrites local DB and uploads.")
        print("       Stop the app/server before continuing.")
        print("       Re-run with --yes to execute restore.")
        return 2

    if not args.force and _is_server_running(_control_port()):
        print("[ERROR] Server appears to be running. Stop the server first,")
        print("        or re-run with --force only when it is certainly stopped.")
        return 1

    if target_db.exists() and not _checkpoint_and_clear_wal(target_db):
        return _fail("WAL checkpoint before restore failed; restore aborted without changes.")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    # ISSUE-003: 스냅샷을 백업 디렉토리 안이 아닌 대상 옆(형제 디렉토리)에 분리한다.
    safety_root = target_db.parent / f"pre_restore_snapshot_{ts}"
    safety_root.mkdir(parents=True, exist_ok=True)

    target_db.parent.mkdir(parents=True, exist_ok=True)
    target_uploads.parent.mkdir(parents=True, exist_ok=True)

    if target_db.exists():
        shutil.copy2(target_db, safety_root / "messenger.db.before_restore")

    if target_uploads.exists():
        shutil.copytree(target_uploads, safety_root / "uploads.before_restore")
        shutil.rmtree(target_uploads)

    shutil.copy2(backup_db, target_db)
    shutil.copytree(backup_uploads, target_uploads)

    print("[OK] Restore completed")
    print(f" - target_db      : {target_db}")
    print(f" - target_uploads : {target_uploads}")
    print(f" - safety_snapshot: {safety_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
