# -*- coding: utf-8 -*-
"""
사내 메신저 앱 패키지
Flask 앱 팩토리 패턴
"""

# gevent monkey patching (반드시 다른 import 전에 실행)
try:
    from gevent import monkey
    monkey.patch_all()
    _GEVENT_AVAILABLE = True
except ImportError:
    _GEVENT_AVAILABLE = False

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
        STATIC_FOLDER, TEMPLATE_FOLDER,
        ASYNC_MODE, PING_TIMEOUT, PING_INTERVAL, MAX_HTTP_BUFFER_SIZE,
        MAX_CONNECTIONS, MESSAGE_QUEUE
    )
except ImportError:
    # 패키징된 환경에서 상대 경로 시도
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import (
        BASE_DIR, DATABASE_PATH, UPLOAD_FOLDER, MAX_CONTENT_LENGTH,
        SESSION_TIMEOUT_HOURS, APP_NAME, VERSION, USE_HTTPS,
        STATIC_FOLDER, TEMPLATE_FOLDER,
        ASYNC_MODE, PING_TIMEOUT, PING_INTERVAL, MAX_HTTP_BUFFER_SIZE,
        MAX_CONNECTIONS, MESSAGE_QUEUE
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
    os.makedirs(os.path.join(UPLOAD_FOLDER, 'profiles'), exist_ok=True)  # 프로필 이미지 폴더
    
    # Flask 앱 생성
    app = Flask(
        __name__,
        static_folder=static_folder,
        static_url_path='/static',
        template_folder=template_folder
    )
    
    # 설정 - SECRET_KEY 영구 저장 (새로고침 시 세션 유지)
    secret_key_file = os.path.join(BASE_DIR, '.secret_key')
    if os.path.exists(secret_key_file):
        with open(secret_key_file, 'r') as f:
            app.config['SECRET_KEY'] = f.read().strip()
    else:
        new_key = secrets.token_hex(32)
        with open(secret_key_file, 'w') as f:
            f.write(new_key)
        app.config['SECRET_KEY'] = new_key
    
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
    app.config['SESSION_COOKIE_SECURE'] = USE_HTTPS  # HTTPS일 때만 True
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=SESSION_TIMEOUT_HOURS)
    app.config['SESSION_PERMANENT'] = True  # 영구 세션 활성화
    
    # Socket.IO 초기화 - 비동기 모드 선택
    # 우선순위: gevent > eventlet > threading
    _async_mode = None
    
    # config에서 설정한 모드 시도
    if ASYNC_MODE == 'gevent' and _GEVENT_AVAILABLE:
        try:
            import gevent  # noqa: F401
            from gevent import pywsgi  # noqa: F401
            try:
                from geventwebsocket.handler import WebSocketHandler  # noqa: F401
                _async_mode = 'gevent_uwsgi'
            except ImportError:
                _async_mode = 'gevent'
            logger.info(f"gevent 비동기 모드 활성화 (고성능 동시 접속 지원)")
        except ImportError:
            logger.warning("gevent를 찾을 수 없습니다. 다른 모드로 대체합니다.")
    
    if _async_mode is None and ASYNC_MODE == 'eventlet':
        try:
            import eventlet  # noqa: F401
            eventlet.monkey_patch()
            _async_mode = 'eventlet'
            logger.info("eventlet 비동기 모드 활성화")
        except ImportError:
            logger.warning("eventlet을 찾을 수 없습니다. 다른 모드로 대체합니다.")
    
    if _async_mode is None:
        try:
            import simple_websocket  # noqa: F401
            import engineio.async_drivers.threading  # noqa: F401
            _async_mode = 'threading'
            logger.info("threading 비동기 모드 활성화 (동시 접속 제한적)")
        except ImportError:
            _async_mode = None
    
    # Socket.IO 인스턴스 생성
    socketio_kwargs = {
        'cors_allowed_origins': "*",
        'ping_timeout': PING_TIMEOUT,
        'ping_interval': PING_INTERVAL,
        'max_http_buffer_size': MAX_HTTP_BUFFER_SIZE,
        'async_mode': _async_mode,
        'logger': False,
        'engineio_logger': False
    }
    
    # Redis 메시지 큐 설정 (대규모 배포용)
    if MESSAGE_QUEUE:
        socketio_kwargs['message_queue'] = MESSAGE_QUEUE
        logger.info(f"메시지 큐 활성화: {MESSAGE_QUEUE}")
    
    try:
        socketio = SocketIO(app, **socketio_kwargs)
        logger.info(f"Socket.IO 초기화 완료 (모드: {_async_mode or 'default'})")
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
