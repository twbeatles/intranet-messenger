# -*- coding: utf-8 -*-

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
