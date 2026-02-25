#!/usr/bin/env python3
"""Manual local restore utility for intranet-messenger backups."""

from __future__ import annotations

import argparse
import shutil
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

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safety_root = backup_dir / f"pre_restore_snapshot_{ts}"
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
