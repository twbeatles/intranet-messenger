#!/usr/bin/env python3
"""Manual local backup utility for intranet-messenger."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
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


def _count_files(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for p in path.rglob("*") if p.is_file())


def backup_sqlite(src: Path, dst: Path):
    src_conn = sqlite3.connect(str(src))
    try:
        dst_conn = sqlite3.connect(str(dst))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()


def main() -> int:
    default_db, default_uploads = _import_defaults()

    parser = argparse.ArgumentParser(description="Create manual local backup")
    parser.add_argument("--output-root", default="backup/manual", help="Backup root directory")
    parser.add_argument("--db-path", default=str(default_db), help="SQLite DB path")
    parser.add_argument("--uploads-dir", default=str(default_uploads), help="Uploads directory path")
    parser.add_argument("--label", default="", help="Optional backup label")
    args = parser.parse_args()

    db_path = Path(args.db_path).resolve()
    uploads_path = Path(args.uploads_dir).resolve()
    output_root = Path(args.output_root).resolve()

    if not db_path.exists():
        print(f"[ERROR] DB file not found: {db_path}")
        return 1
    if not uploads_path.exists():
        print(f"[ERROR] Upload directory not found: {uploads_path}")
        return 1

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    label = f"_{args.label.strip()}" if args.label.strip() else ""
    backup_dir = output_root / f"backup_{ts}{label}"
    db_out_dir = backup_dir / "db"
    uploads_out_dir = backup_dir / "uploads"

    db_out_dir.mkdir(parents=True, exist_ok=True)

    db_backup_path = db_out_dir / "messenger.db"
    backup_sqlite(db_path, db_backup_path)

    shutil.copytree(uploads_path, uploads_out_dir)

    manifest = {
        "generated_at_utc": ts,
        "source": {
            "db_path": str(db_path),
            "uploads_dir": str(uploads_path),
        },
        "backup": {
            "directory": str(backup_dir),
            "db_backup": str(db_backup_path),
            "uploads_backup": str(uploads_out_dir),
        },
        "stats": {
            "uploads_file_count": _count_files(uploads_out_dir),
            "db_size_bytes": db_backup_path.stat().st_size,
        },
    }

    manifest_path = backup_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[OK] Backup completed")
    print(f" - backup_dir: {backup_dir}")
    print(f" - db_backup : {db_backup_path}")
    print(f" - uploads   : {uploads_out_dir}")
    print(f" - manifest  : {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
