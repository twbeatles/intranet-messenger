# -*- coding: utf-8 -*-
"""
유틸리티 함수
- 암호화
- 유효성 검사
- 헬퍼 함수
"""

import hashlib
import base64
import re

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad

# config 임포트 (PyInstaller 호환)
try:
    from config import PASSWORD_SALT, ALLOWED_EXTENSIONS
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import PASSWORD_SALT, ALLOWED_EXTENSIONS


class E2ECrypto:
    """종단간 암호화 클래스"""
    
    @staticmethod
    def generate_room_key():
        """대화방별 암호화 키 생성 (32바이트 = 256비트)"""
        return base64.b64encode(get_random_bytes(32)).decode('utf-8')
    
    @staticmethod
    def encrypt_message(plaintext, key_b64):
        """메시지 암호화"""
        try:
            key = base64.b64decode(key_b64)
            iv = get_random_bytes(16)
            cipher = AES.new(key, AES.MODE_CBC, iv)
            padded_data = pad(plaintext.encode('utf-8'), AES.block_size)
            encrypted = cipher.encrypt(padded_data)
            return base64.b64encode(iv + encrypted).decode('utf-8')
        except Exception:
            return None
    
    @staticmethod
    def decrypt_message(ciphertext_b64, key_b64):
        """메시지 복호화"""
        try:
            key = base64.b64decode(key_b64)
            data = base64.b64decode(ciphertext_b64)
            iv = data[:16]
            encrypted = data[16:]
            cipher = AES.new(key, AES.MODE_CBC, iv)
            decrypted = unpad(cipher.decrypt(encrypted), AES.block_size)
            return decrypted.decode('utf-8')
        except Exception:
            return "[암호화된 메시지]"


def hash_password(password):
    """비밀번호 해시 (솔트 적용)"""
    salted = f"{PASSWORD_SALT}{password}{PASSWORD_SALT}"
    return hashlib.sha256(salted.encode()).hexdigest()


def validate_username(username):
    """아이디 유효성 검사"""
    if not username or len(username) < 3 or len(username) > 20:
        return False
    return bool(re.match(r'^[a-zA-Z0-9_]+$', username))


def validate_password(password):
    """비밀번호 강도 검사"""
    if len(password) < 4:
        return False, "비밀번호는 4자 이상이어야 합니다."
    return True, ""


def sanitize_input(text, max_length=1000):
    """입력값 정제 (XSS 방지)"""
    if not text:
        return ""
    text = text[:max_length]
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()


def allowed_file(filename):
    """허용된 파일 확장자 확인"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
