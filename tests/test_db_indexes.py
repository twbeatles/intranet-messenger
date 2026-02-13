# -*- coding: utf-8 -*-
import sqlite3


def test_expected_indexes_exist(app):
    # app fixture already initialized DB with init_db()
    import config

    con = sqlite3.connect(config.DATABASE_PATH)
    try:
        cur = con.cursor()
        cur.execute("select name from sqlite_master where type='index'")
        names = {r[0] for r in cur.fetchall()}
    finally:
        con.close()

    assert "idx_room_files_file_path" in names
    assert "idx_users_status" in names
    assert "idx_messages_file_name" in names
