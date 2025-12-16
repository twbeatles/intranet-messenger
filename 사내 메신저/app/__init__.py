# -*- coding: utf-8 -*-
"""
사내 메신저 앱 패키지
Flask 앱 팩토리 패턴
"""

import os
import sys
import logging
import secrets
from datetime import timedelta

from flask import Flask
from flask_socketio import SocketIO

# config 임포트 (PyInstaller 호환)
try:
    from config import (
        BASE_DIR, DATABASE_PATH, UPLOAD_FOLDER, MAX_CONTENT_LENGTH,
        SESSION_TIMEOUT_HOURS, APP_NAME, VERSION, USE_HTTPS,
        STATIC_FOLDER, TEMPLATE_FOLDER
    )
except ImportError:
    # 패키징된 환경에서 상대 경로 시도
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import (
        BASE_DIR, DATABASE_PATH, UPLOAD_FOLDER, MAX_CONTENT_LENGTH,
        SESSION_TIMEOUT_HOURS, APP_NAME, VERSION, USE_HTTPS,
        STATIC_FOLDER, TEMPLATE_FOLDER
    )

# 로깅 설정
try:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(os.path.join(BASE_DIR, 'server.log'), encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
except (PermissionError, OSError):
    # 파일 로깅 실패 시 콘솔만 사용
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
logger = logging.getLogger(__name__)

# SocketIO 인스턴스 (전역)
socketio = None


def create_app():
    """Flask 앱 팩토리"""
    global socketio
    
    # Static/Template 폴더 설정 (config에서 가져옴)
    static_folder = STATIC_FOLDER
    template_folder = TEMPLATE_FOLDER
    
    # 폴더 존재 확인 (패키징 환경에서는 이미 존재)
    if not os.path.exists(static_folder):
        os.makedirs(static_folder, exist_ok=True)
    if not os.path.exists(template_folder):
        os.makedirs(template_folder, exist_ok=True)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    # Flask 앱 생성
    app = Flask(
        __name__,
        static_folder=static_folder,
        static_url_path='/static',
        template_folder=template_folder
    )
    
    # 설정
    app.config['SECRET_KEY'] = secrets.token_hex(32)
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
    app.config['SESSION_COOKIE_SECURE'] = USE_HTTPS  # HTTPS일 때만 True
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=SESSION_TIMEOUT_HOURS)
    
    # Socket.IO 초기화
    _async_mode = None
    try:
        import simple_websocket  # noqa: F401
        import engineio.async_drivers.threading  # noqa: F401
        _async_mode = 'threading'
    except ImportError:
        pass
    
    try:
        socketio = SocketIO(
            app,
            cors_allowed_origins="*",
            ping_timeout=60,
            ping_interval=25,
            async_mode=_async_mode,
            logger=False,
            engineio_logger=False
        )
    except ValueError as e:
        logger.warning(f"Socket.IO 초기화 경고: {e}, 기본 모드로 재시도")
        socketio = SocketIO(app, cors_allowed_origins="*")
    
    # 라우트 등록
    from app.routes import register_routes
    register_routes(app)
    
    # Socket.IO 이벤트 등록
    from app.sockets import register_socket_events
    register_socket_events(socketio)
    
    # 데이터베이스 초기화
    from app.models import init_db
    init_db()
    
    logger.info(f"{APP_NAME} v{VERSION} 앱 초기화 완료")
    
    return app, socketio
