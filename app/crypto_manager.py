# -*- coding: utf-8 -*-
"""
[v4.2] 암호화 키 관리자
- 마스터 키 기반 대화방 키 암호화
- 기존 평문 키 마이그레이션 지원
"""

import os
import base64
import logging
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad

# config 임포트 (PyInstaller 호환)
try:
    from config import BASE_DIR
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import BASE_DIR

logger = logging.getLogger(__name__)

# 마스터 키 파일 경로
MASTER_KEY_FILE = os.path.join(BASE_DIR, '.master_key')


class CryptoManager:
    """서버 측 암호화 관리자"""
    
    _master_key = None
    
    @classmethod
    def _get_master_key(cls):
        """마스터 키 로드 또는 생성"""
        if cls._master_key is not None:
            return cls._master_key
        
        if os.path.exists(MASTER_KEY_FILE):
            try:
                with open(MASTER_KEY_FILE, 'rb') as f:
                    cls._master_key = f.read()
                logger.debug("마스터 키 로드됨")
            except Exception as e:
                logger.error(f"마스터 키 로드 실패: {e}")
                cls._master_key = cls._generate_master_key()
        else:
            cls._master_key = cls._generate_master_key()
        
        return cls._master_key
    
    @classmethod
    def _generate_master_key(cls):
        """새 마스터 키 생성"""
        key = get_random_bytes(32)  # 256비트
        try:
            with open(MASTER_KEY_FILE, 'wb') as f:
                f.write(key)
            # 파일 권한 설정 (Windows에서는 제한적)
            try:
                os.chmod(MASTER_KEY_FILE, 0o600)
            except Exception:
                pass
            logger.info("새 마스터 키 생성됨")
        except Exception as e:
            logger.error(f"마스터 키 저장 실패: {e}")
        return key
    
    @classmethod
    def encrypt_room_key(cls, room_key_b64: str) -> str:
        """대화방 키를 마스터 키로 암호화
        
        Args:
            room_key_b64: Base64로 인코딩된 대화방 키
            
        Returns:
            암호화된 키 (Base64)
        """
        try:
            master_key = cls._get_master_key()
            iv = get_random_bytes(16)
            cipher = AES.new(master_key, AES.MODE_CBC, iv)
            
            # 대화방 키를 바이트로 변환하여 암호화
            room_key_bytes = room_key_b64.encode('utf-8')
            padded_data = pad(room_key_bytes, AES.block_size)
            encrypted = cipher.encrypt(padded_data)
            
            # IV + 암호문을 Base64로 인코딩
            return base64.b64encode(iv + encrypted).decode('utf-8')
        except Exception as e:
            logger.error(f"대화방 키 암호화 실패: {e}")
            raise e  # 실패 시 예외 발생 (평문 저장 방지)
    
    @classmethod
    def decrypt_room_key(cls, encrypted_key_b64: str) -> str:
        """마스터 키로 대화방 키 복호화
        
        Args:
            encrypted_key_b64: 암호화된 키 (Base64)
            
        Returns:
            복호화된 대화방 키 (Base64)
        """
        try:
            master_key = cls._get_master_key()
            data = base64.b64decode(encrypted_key_b64)
            
            # 데이터가 너무 짧으면 암호화되지 않은 키일 수 있음
            if len(data) < 32:
                # 평문 키로 간주 (마이그레이션 지원)
                return encrypted_key_b64
            
            iv = data[:16]
            encrypted = data[16:]
            
            cipher = AES.new(master_key, AES.MODE_CBC, iv)
            decrypted = unpad(cipher.decrypt(encrypted), AES.block_size)
            
            return decrypted.decode('utf-8')
        except Exception as e:
            # 복호화 실패 시 평문 키일 수 있음 (마이그레이션 지원)
            logger.debug(f"키 복호화 실패 (평문일 수 있음): {e}")
            return encrypted_key_b64
    
    @classmethod
    def is_encrypted(cls, key_b64: str) -> bool:
        """키가 암호화되어 있는지 확인
        
        암호화된 키는 IV(16바이트) + 암호문(최소 16바이트)이므로
        Base64 디코딩 후 최소 32바이트
        """
        try:
            data = base64.b64decode(key_b64)
            return len(data) >= 48  # 44바이트(원본 키) + 패딩 고려
        except Exception:
            return False
