# -*- coding: utf-8 -*-
import sqlite3
import pytest


def _fts5_supported(conn: sqlite3.Connection) -> bool:
    try:
        # Some builds don't expose compile options reliably; try creating a temp table.
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_test USING fts5(x)")
        conn.execute("DROP TABLE _fts5_test")
        return True
    except Exception:
        return False


def test_fts_objects_created_if_supported(app):
    import config

    conn = sqlite3.connect(config.DATABASE_PATH)
    try:
        if not _fts5_supported(conn):
            pytest.skip("SQLite FTS5 not supported in this environment")

        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='messages_fts'"
        ).fetchone()
        assert row is not None

        trg = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name='messages_fts_ai'"
        ).fetchone()
        assert trg is not None
    finally:
        conn.close()

