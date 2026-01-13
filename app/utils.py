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
import html
from flask import current_app

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad

# config 임포트 (PyInstaller 호환)
try:
    from config import ALLOWED_EXTENSIONS
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import ALLOWED_EXTENSIONS


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


def _get_salt():
    """솔트 가져오기 - config에서 직접 로드"""
    try:
        from config import PASSWORD_SALT
        return PASSWORD_SALT
    except ImportError:
        # config 임포트 실패 시 폴백 (PyInstaller 등 특수 환경)
        try:
            return current_app.config.get('PASSWORD_SALT', 'messenger_salt_2025')
        except Exception:
            return 'messenger_salt_2025'

def hash_password(password):
    """[v4.2] 비밀번호 해시 (bcrypt 사용)
    
    bcrypt는 자동으로 솔트를 생성하고 해시에 포함합니다.
    기존 SHA-256 해시와의 호환성을 위해 verify_password() 함수 사용 필요.
    """
    try:
        import bcrypt
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    except ImportError:
        # bcrypt 미설치 시 기존 방식 사용
        salt = _get_salt()
        salted = f"{salt}{password}{salt}"
        return hashlib.sha256(salted.encode()).hexdigest()


def verify_password(password, hashed):
    """[v4.2] 비밀번호 검증 (bcrypt + SHA-256 호환)
    
    bcrypt 해시($2로 시작)와 기존 SHA-256 해시(64자 hex) 모두 지원.
    """
    try:
        # bcrypt 해시인지 확인 ($2a$, $2b$ 등으로 시작)
        if hashed.startswith('$2'):
            import bcrypt
            return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
        else:
            # 기존 SHA-256 해시
            salt = _get_salt()
            salted = f"{salt}{password}{salt}"
            return hashlib.sha256(salted.encode()).hexdigest() == hashed
    except Exception:
        return False


def validate_username(username):
    """아이디 유효성 검사"""
    if not username or len(username) < 3 or len(username) > 20:
        return False
    return bool(re.match(r'^[a-zA-Z0-9_]+$', username))


def validate_password(password):
    """비밀번호 강도 검사"""
    if len(password) < 8:
        return False, "비밀번호는 8자 이상이어야 합니다."
    if not any(c.isalpha() for c in password):
        return False, "비밀번호에는 영문자가 포함되어야 합니다."
    if not any(c.isdigit() for c in password):
        return False, "비밀번호에는 숫자가 포함되어야 합니다."
    return True, ""


def sanitize_input(text, max_length=1000):
    """입력값 정제 (XSS 방지)"""
    if not text:
        return ""
    text = text[:max_length]
    # [v4.3] 태그 제거 대신 이스케이프 처리 (내용 보존)
    return html.escape(text).strip()


def allowed_file(filename):
    """허용된 파일 확장자 확인"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_file_header(file):
    """[v4.3] 파일 매직 넘버(헤더) 검증 - 보안 강화"""
    filename = file.filename.lower()
    ext = filename.rsplit('.', 1)[1] if '.' in filename else ''
    
    # 헤더 시그니처 정의
    signatures = {
        'png': b'\x89PNG\r\n\x1a\n',
        'jpg': b'\xff\xd8',
        'jpeg': b'\xff\xd8',
        'gif': b'GIF8',
        'pdf': b'%PDF',
        'zip': b'PK\x03\x04',
        'docx': b'PK\x03\x04',
        'xlsx': b'PK\x03\x04',
        'pptx': b'PK\x03\x04',
        'webp': b'RIFF', # WEBP is RIFF...WEBP
        'bmp': b'BM',
        'ico': b'\x00\x00\x01\x00'
    }
    
    # 바이너리 검증 대상이 아닌 경우 (txt 등)
    if ext not in signatures:
        # 텍스트 파일 등은 허용하되, 알려지지 않은 확장자는 주의
        return ext in ALLOWED_EXTENSIONS

    if ext in signatures:
        sig = signatures[ext]
        # Read header
        start_pos = file.tell()
        file.seek(0)
        # [v4.5] WEBP는 12바이트 읽어야 함 (RIFF....WEBP)
        header = file.read(12 if ext == 'webp' else len(sig))
        file.seek(start_pos)
        
        # [v4.5] WEBP 특수 검증: RIFF....WEBP 형식
        if ext == 'webp':
            if not (header[:4] == b'RIFF' and header[8:12] == b'WEBP'):
                return False
        elif not header.startswith(sig):
            return False
            
    return True
