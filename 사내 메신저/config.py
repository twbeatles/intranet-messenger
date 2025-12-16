# -*- coding: utf-8 -*-
"""
사내 메신저 v3.0 설정 파일
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
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'zip'}
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
SESSION_TIMEOUT_HOURS = 24
PASSWORD_SALT = "messenger_secure_salt_2024"

# ============================================================================
# 앱 정보
# ============================================================================
APP_NAME = "사내 메신저 서버"
VERSION = "3.0"
