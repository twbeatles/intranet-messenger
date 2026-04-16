# -*- coding: utf-8 -*-

import os
import time


def test_issue_and_consume_upload_token_once(monkeypatch):
    import app.upload_tokens as upload_tokens

    monkeypatch.setattr(upload_tokens, "TOKEN_TTL_SECONDS", 300)
    token = upload_tokens.issue_upload_token(
        user_id=1,
        room_id=10,
        file_path="abc.txt",
        file_name="abc.txt",
        file_type="file",
        file_size=123,
    )

    data = upload_tokens.consume_upload_token(token, user_id=1, room_id=10, expected_type="file")
    assert data is not None
    assert data["file_name"] == "abc.txt"
    assert data["file_path"] == "abc.txt"

    # 1회성 소비 보장
    data2 = upload_tokens.consume_upload_token(token, user_id=1, room_id=10, expected_type="file")
    assert data2 is None


def test_upload_token_expires(monkeypatch):
    import app.upload_tokens as upload_tokens

    monkeypatch.setattr(upload_tokens, "TOKEN_TTL_SECONDS", 0)
    token = upload_tokens.issue_upload_token(
        user_id=1,
        room_id=10,
        file_path="exp.txt",
        file_name="exp.txt",
        file_type="file",
        file_size=10,
    )
    time.sleep(0.01)
    assert upload_tokens.consume_upload_token(token, user_id=1, room_id=10, expected_type="file") is None


def test_purge_expired_upload_tokens_removes_orphan_file(tmp_path, monkeypatch):
    import app.upload_tokens as upload_tokens

    now = time.time()
    monkeypatch.setattr(upload_tokens, "TOKEN_TTL_SECONDS", 1)

    class _FakeCursor:
        def execute(self, _query):
            return None

        def fetchall(self):
            return []

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

    monkeypatch.setattr(upload_tokens, "get_db", lambda: _FakeConn())

    orphan_path = os.path.join(str(tmp_path), "orphan.txt")
    with open(orphan_path, "wb") as handle:
        handle.write(b"orphan")
    os.utime(orphan_path, (now - 10, now - 10))

    removed = upload_tokens.purge_expired_upload_tokens(upload_folder=str(tmp_path), now=now)
    assert removed == 1
    assert not os.path.exists(orphan_path)
