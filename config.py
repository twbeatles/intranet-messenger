# -*- coding: utf-8 -*-
"""
사내 메신저 v4.36 설정 파일
"""

import os
import sys

# ============================================================================
# 경로 설정 (PyInstaller 호환)
# ============================================================================
# BUNDLE_DIR: 번들된 리소스 위치 (static, templates, app, gui 등)
# BASE_DIR: 실행 파일 위치 (데이터베이스, 업로드, 로그 등 사용자 데이터)

if getattr(sys, 'frozen', False):
    # PyInstaller로 패키징된 경우
    BUNDLE_DIR = sys._MEIPASS  # 번들 리소스 (static, templates 등)
    BASE_DIR = os.path.dirname(sys.executable)  # 실행 파일 위치 (DB, 로그 등)
else:
    # 개발 환경
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    BASE_DIR = BUNDLE_DIR

# 데이터베이스 (사용자 데이터 - BASE_DIR)
DATABASE_PATH = os.path.join(BASE_DIR, 'messenger.db')

# 업로드 (사용자 데이터 - BASE_DIR)
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'tiff', 'tif', 'ico', 'svg', 'heic', 'heif', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'zip', 'rar', '7z'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

# SSL 인증서 (사용자 데이터 - BASE_DIR)
SSL_DIR = os.path.join(BASE_DIR, 'certs')
SSL_CERT_PATH = os.path.join(SSL_DIR, 'cert.pem')
SSL_KEY_PATH = os.path.join(SSL_DIR, 'key.pem')

# 리소스 폴더 (번들 리소스 - BUNDLE_DIR)
STATIC_FOLDER = os.path.join(BUNDLE_DIR, 'static')
TEMPLATE_FOLDER = os.path.join(BUNDLE_DIR, 'templates')

# ============================================================================
# 서버 설정
# ============================================================================
USE_HTTPS = False
DEFAULT_PORT = 5000
CONTROL_PORT = 5001  # GUI-서버 제어 API 포트
SESSION_TIMEOUT_HOURS = 72  # 3일
PASSWORD_SALT = "messenger_secure_salt_2024"

# Socket.IO CORS
# None이면 Flask-SocketIO 기본 정책(동일 출처)을 따릅니다.
# 필요 시 예: ['http://127.0.0.1:5000', 'http://localhost:5000']
SOCKETIO_CORS_ALLOWED_ORIGINS = None

# ============================================================================
# 동시 접속 및 성능 설정
# ============================================================================
# 비동기 모드: 'gevent' (권장, 고성능), 'eventlet', 'threading' (기본, 제한적)
# gevent를 사용하려면: pip install gevent gevent-websocket
# eventlet을 사용하려면: pip install eventlet
# ASYNC_MODE = 'gevent'  # 수십~수백 명 동시 접속 지원
# ASYNC_MODE = 'gevent'  # 수십~수백 명 동시 접속 지원
ASYNC_MODE = 'gevent'  # 수십~수백 명 동시 접속 지원 (권장)

# Socket.IO 설정
PING_TIMEOUT = 120  # 클라이언트 연결 타임아웃 (초)
PING_INTERVAL = 25  # 핑 간격 (초)
MAX_HTTP_BUFFER_SIZE = 10 * 1024 * 1024  # 10MB (메시지 버퍼 크기)

# 동시 연결 제한 (0 = 무제한)
MAX_CONNECTIONS = 0

# 메시지 큐 설정 (대규모 배포 시 Redis 사용 권장)
# MESSAGE_QUEUE = 'redis://localhost:6379'  # Redis 사용 시 주석 해제
MESSAGE_QUEUE = None  # 단일 서버 모드

# ============================================================================
# 앱 정보
# ============================================================================
APP_NAME = "사내 메신저 서버"
VERSION = "4.36"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


# ============================================================================
# Optional Feature Flags / Integrations
# ============================================================================
# Shared redis endpoint (optional)
REDIS_URL = os.getenv("REDIS_URL")

# Flask-Limiter storage backend
RATE_LIMIT_STORAGE_URI = os.getenv("RATE_LIMIT_STORAGE_URI", REDIS_URL or "memory://")

# State store backend for upload token / socket guard / presence
STATE_STORE_REDIS_URL = os.getenv("STATE_STORE_REDIS_URL", REDIS_URL or "")

# Socket message rate limit (per-user)
SOCKET_SEND_MESSAGE_PER_MINUTE = int(os.getenv("SOCKET_SEND_MESSAGE_PER_MINUTE", "100"))
# Socket pin update event rate limit (per-user)
SOCKET_PIN_UPDATED_PER_MINUTE = int(os.getenv("SOCKET_PIN_UPDATED_PER_MINUTE", "30"))

# Feature toggles
FEATURE_OIDC_ENABLED = _env_bool("FEATURE_OIDC_ENABLED", False)
FEATURE_AV_SCAN_ENABLED = _env_bool("FEATURE_AV_SCAN_ENABLED", False)
FEATURE_REDIS_ENABLED = _env_bool("FEATURE_REDIS_ENABLED", bool(REDIS_URL))

# OIDC settings (optional)
OIDC_PROVIDER_NAME = os.getenv("OIDC_PROVIDER_NAME", "oidc")
OIDC_ISSUER_URL = os.getenv("OIDC_ISSUER_URL", "")
OIDC_AUTHORIZE_URL = os.getenv("OIDC_AUTHORIZE_URL", "")
OIDC_TOKEN_URL = os.getenv("OIDC_TOKEN_URL", "")
OIDC_USERINFO_URL = os.getenv("OIDC_USERINFO_URL", "")
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET", "")
OIDC_SCOPE = os.getenv("OIDC_SCOPE", "openid profile email")
OIDC_REDIRECT_URI = os.getenv("OIDC_REDIRECT_URI", "")
OIDC_JWKS_URL = os.getenv("OIDC_JWKS_URL", "")
OIDC_JWKS_CACHE_SECONDS = int(os.getenv("OIDC_JWKS_CACHE_SECONDS", "300"))

# AV scan settings (optional, clamd TCP)
AV_SCANNER = os.getenv("AV_SCANNER", "clamav")
AV_CLAMD_HOST = os.getenv("AV_CLAMD_HOST", "127.0.0.1")
AV_CLAMD_PORT = int(os.getenv("AV_CLAMD_PORT", "3310"))
AV_SCAN_TIMEOUT_SECONDS = int(os.getenv("AV_SCAN_TIMEOUT_SECONDS", "15"))
UPLOAD_QUARANTINE_FOLDER = os.path.join(UPLOAD_FOLDER, "quarantine")

# Data retention (disabled by default)
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "0"))

# Maintenance worker interval
MAINTENANCE_INTERVAL_SECONDS = int(os.getenv("MAINTENANCE_INTERVAL_SECONDS", "300"))
