#!/usr/bin/env python3
"""Post-restore verification utility for local environment."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


REQUIRED_TABLES = {
    "users",
    "rooms",
    "room_members",
    "messages",
    "polls",
    "poll_options",
    "poll_votes",
    "room_files",
    "sso_identities",
    "upload_scan_jobs",
    "admin_audit_logs",
}


def _import_defaults():
    try:
        from config import DATABASE_PATH, UPLOAD_FOLDER
    except Exception:
        base_dir = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(base_dir))
        from config import DATABASE_PATH, UPLOAD_FOLDER  # type: ignore
    return Path(DATABASE_PATH), Path(UPLOAD_FOLDER)


def main() -> int:
    default_db, default_uploads = _import_defaults()

    parser = argparse.ArgumentParser(description="Verify restored local state")
    parser.add_argument("--db-path", default=str(default_db), help="SQLite DB path")
    parser.add_argument("--uploads-dir", default=str(default_uploads), help="Uploads directory path")
    args = parser.parse_args()

    db_path = Path(args.db_path).resolve()
    uploads_path = Path(args.uploads_dir).resolve()

    if not db_path.exists():
        print(f"[ERROR] DB file not found: {db_path}")
        return 1
    if not uploads_path.exists():
        print(f"[ERROR] uploads directory not found: {uploads_path}")
        return 1

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check")
        integrity = cur.fetchone()
        if not integrity or integrity[0] != "ok":
            print(f"[ERROR] sqlite integrity_check failed: {integrity}")
            return 1

        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {r[0] for r in cur.fetchall()}
        missing = sorted(REQUIRED_TABLES - existing_tables)
        if missing:
            print("[ERROR] missing required tables:")
            for name in missing:
                print(f" - {name}")
            return 1

        cur.execute("SELECT COUNT(*) FROM users")
        user_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM rooms")
        room_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM messages")
        msg_count = cur.fetchone()[0]
    finally:
        conn.close()

    upload_files = sum(1 for p in uploads_path.rglob("*") if p.is_file())

    print("[OK] restore verification passed")
    print(f" - db_path      : {db_path}")
    print(f" - uploads_path : {uploads_path}")
    print(f" - users        : {user_count}")
    print(f" - rooms        : {room_count}")
    print(f" - messages     : {msg_count}")
    print(f" - upload_files : {upload_files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
