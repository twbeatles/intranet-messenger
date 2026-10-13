# -*- coding: utf-8 -*-
"""bcrypt 5.x 72바이트 제한 회귀 테스트.

bcrypt 5.0부터 72바이트를 초과하는 비밀번호는 ValueError를 발생시킨다
(4.x에서는 조용히 잘라냈다). 회원가입·비밀번호 변경 진입점이 400으로
거부하는지, 로그인이 500 대신 401로 실패하는지 검증한다.
"""

import pytest

from app.utils import (
    MAX_BCRYPT_PASSWORD_BYTES,
    hash_password,
    validate_password,
    verify_password,
)

assert MAX_BCRYPT_PASSWORD_BYTES == 72

LONG_PASSWORD = "Aa1" + "x" * 100  # 103자, 103바이트
BOUNDARY_PASSWORD = "Aa1" + "y" * 69  # 정확히 72바이트
MULTIBYTE_LONG = "Test1234" + "가" * 25  # 8 + 75 = 83바이트


def test_validate_rejects_over_72_bytes():
    ok, msg = validate_password(LONG_PASSWORD)
    assert ok is False
    assert "72" in msg


def test_validate_rejects_multibyte_over_72_bytes():
    ok, _ = validate_password(MULTIBYTE_LONG)
    assert ok is False


def test_validate_accepts_exactly_72_bytes():
    ok, _ = validate_password(BOUNDARY_PASSWORD)
    assert ok is True


def test_hash_password_raises_on_over_72_bytes():
    with pytest.raises(ValueError):
        hash_password(LONG_PASSWORD)


def test_hash_verify_roundtrip():
    hashed = hash_password("Password123!")
    assert hashed.startswith("$2")
    assert verify_password("Password123!", hashed) is True
    assert verify_password("WrongPass999", hashed) is False


def test_verify_long_password_returns_false_without_raising():
    hashed = hash_password("Password123!")
    assert verify_password(LONG_PASSWORD, hashed) is False


def test_register_rejects_long_password_with_400(client):
    response = client.post("/api/register", json={
        "username": "longpwuser",
        "password": LONG_PASSWORD,
        "nickname": "LongPw",
    })
    assert response.status_code == 400


def test_login_with_long_password_returns_401_not_500(client):
    client.post("/api/register", json={
        "username": "longpwlogin",
        "password": "Password123!",
        "nickname": "LongLogin",
    })
    response = client.post("/api/login", json={
        "username": "longpwlogin",
        "password": LONG_PASSWORD,
    })
    assert response.status_code == 401
