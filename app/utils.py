# -*- coding: utf-8 -*-
"""
유틸리티 함수
- 암호화
- 입력 검증
- 파일 검증
"""

from __future__ import annotations

import base64
import hashlib
import html
import importlib
import os
import re
import sys
from types import ModuleType
from typing import Any

from flask import current_app

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad

try:
    from config import ALLOWED_EXTENSIONS
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import ALLOWED_EXTENSIONS


class E2ECrypto:
    """종단간 암호화 도우미."""

    @staticmethod
    def generate_room_key() -> str:
        """채팅방용 대칭키를 생성한다."""
        return base64.b64encode(get_random_bytes(32)).decode("utf-8")

    @staticmethod
    def encrypt_message(plaintext: str, key_b64: str) -> str | None:
        """메시지를 AES-CBC로 암호화한다."""
        try:
            key = base64.b64decode(key_b64)
            iv = get_random_bytes(16)
            cipher = AES.new(key, AES.MODE_CBC, iv)
            padded_data = pad(plaintext.encode("utf-8"), AES.block_size)
            encrypted = cipher.encrypt(padded_data)
            return base64.b64encode(iv + encrypted).decode("utf-8")
        except Exception:
            return None

    @staticmethod
    def decrypt_message(ciphertext_b64: str, key_b64: str) -> str:
        """암호화된 메시지를 복호화한다."""
        try:
            key = base64.b64decode(key_b64)
            data = base64.b64decode(ciphertext_b64)
            iv = data[:16]
            encrypted = data[16:]
            cipher = AES.new(key, AES.MODE_CBC, iv)
            decrypted = unpad(cipher.decrypt(encrypted), AES.block_size)
            return decrypted.decode("utf-8")
        except Exception:
            return "[암호화된 메시지]"


def _get_salt() -> str:
    """비밀번호 해시용 솔트를 가져온다."""
    try:
        salt = current_app.config.get("PASSWORD_SALT")
        if salt:
            return str(salt)
    except RuntimeError:
        pass

    try:
        from config import PASSWORD_SALT

        return PASSWORD_SALT
    except ImportError:
        return "messenger_salt_2025"


def _load_bcrypt() -> ModuleType | None:
    try:
        return importlib.import_module("bcrypt")
    except Exception:
        return None


def hash_password(password: str) -> str:
    """비밀번호를 해시한다. 가능하면 bcrypt를 사용한다."""
    bcrypt_module = _load_bcrypt()
    if bcrypt_module is not None:
        return bcrypt_module.hashpw(password.encode("utf-8"), bcrypt_module.gensalt()).decode("utf-8")

    salt = _get_salt()
    salted = f"{salt}{password}{salt}"
    return hashlib.sha256(salted.encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    """비밀번호를 검증한다. bcrypt와 레거시 SHA-256 해시를 모두 지원한다."""
    try:
        if hashed.startswith("$2"):
            bcrypt_module = _load_bcrypt()
            if bcrypt_module is None:
                return False
            return bool(bcrypt_module.checkpw(password.encode("utf-8"), hashed.encode("utf-8")))

        salt = _get_salt()
        salted = f"{salt}{password}{salt}"
        return hashlib.sha256(salted.encode()).hexdigest() == hashed
    except Exception:
        return False


def validate_username(username: str) -> bool:
    """아이디 형식을 검증한다."""
    if not username or len(username) < 3 or len(username) > 20:
        return False
    return bool(re.match(r"^[a-zA-Z0-9_]+$", username))


def validate_password(password: str) -> tuple[bool, str]:
    """비밀번호 강도를 검증한다."""
    if len(password) < 8:
        return False, "비밀번호는 8자 이상이어야 합니다."
    if not any(c.isalpha() for c in password):
        return False, "비밀번호에는 영문자가 포함되어야 합니다."
    if not any(c.isdigit() for c in password):
        return False, "비밀번호에는 숫자가 포함되어야 합니다."
    return True, ""


def sanitize_input(text: str | None, max_length: int = 1000) -> str:
    """사용자 입력을 XSS-safe 형태로 정리한다."""
    if not text:
        return ""
    return html.escape(text[:max_length]).strip()


def allowed_file(filename: str) -> bool:
    """허용된 확장자인지 확인한다."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_file_header(file: Any) -> bool:
    """파일 시그니처와 확장자가 대체로 일치하는지 확인한다."""
    filename = str(file.filename or "").lower()
    ext = filename.rsplit(".", 1)[1] if "." in filename else ""

    signatures: dict[str, bytes] = {
        "png": b"\x89PNG\r\n\x1a\n",
        "jpg": b"\xff\xd8",
        "jpeg": b"\xff\xd8",
        "gif": b"GIF8",
        "pdf": b"%PDF",
        "zip": b"PK\x03\x04",
        "docx": b"PK\x03\x04",
        "xlsx": b"PK\x03\x04",
        "pptx": b"PK\x03\x04",
        "webp": b"RIFF",
        "bmp": b"BM",
        "ico": b"\x00\x00\x01\x00",
    }

    if ext not in signatures:
        return ext in ALLOWED_EXTENSIONS

    sig = signatures[ext]
    start_pos = file.tell()
    file.seek(0)
    header = file.read(12 if ext == "webp" else len(sig))
    file.seek(start_pos)

    if ext == "webp":
        return bool(header[:4] == b"RIFF" and header[8:12] == b"WEBP")
    return bool(header.startswith(sig))
