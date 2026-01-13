# -*- coding: utf-8 -*-
"""
사내 메신저 v4.1 앱 패키지
Flask 앱 팩토리 패턴
"""

import os
import sys
import logging
import secrets
from datetime import timedelta

# gevent monkey patching (반드시 다른 import 전에 실행)
# [v4.1] GUI 모드에서는 PyQt6와 충돌하므로 비활성화
_SKIP_GEVENT = os.environ.get('SKIP_GEVENT_PATCH', '0') == '1'
_GEVENT_AVAILABLE = False

if not _SKIP_GEVENT:
    try:
        from gevent import monkey
        monkey.patch_all()
        _GEVENT_AVAILABLE = True
    except ImportError:
        _GEVENT_AVAILABLE = False

from flask import Flask
from flask_socketio import SocketIO
from app.extensions import limiter, csrf, compress
from flask_session import Session


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
    from logging.handlers import RotatingFileHandler
    # [v4.2] 로그 파일 로테이션 적용 (10MB, 5백업)
    file_handler = RotatingFileHandler(
        os.path.join(BASE_DIR, 'server.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            file_handler,
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
    
    # [v4.3] 보안 솔트 생성 및 로드 (비밀번호 해시용)
    salt_file = os.path.join(BASE_DIR, '.security_salt')
    if os.path.exists(salt_file):
        with open(salt_file, 'r') as f:
            app.config['PASSWORD_SALT'] = f.read().strip()
    else:
        # 기존 하드코딩된 값과의 호환성은 utils.py에서 처리하거나
        # 새 설치 시에만 적용. 여기서는 새 솔트 생성.
        new_salt = secrets.token_hex(16)
        with open(salt_file, 'w') as f:
            f.write(new_salt)
        app.config['PASSWORD_SALT'] = new_salt
    
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
    app.config['SESSION_COOKIE_SECURE'] = USE_HTTPS  # HTTPS일 때만 True
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=SESSION_TIMEOUT_HOURS)
    
    # [v4.6] Server-Side Session (Filesystem)
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_FILE_DIR'] = os.path.join(BASE_DIR, 'flask_session')
    app.config['SESSION_PERMANENT'] = True
    app.config['SESSION_USE_SIGNER'] = True
    os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)
    Session(app)

    
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
    
    # [v4.3] 보안 확장 초기화
    limiter.init_app(app)
    csrf.init_app(app)
    
    # [v4.4] 성능 최적화 - Gzip 압축 활성화
    compress.init_app(app)
    
    # Socket.IO 이벤트 등록
    from app.sockets import register_socket_events
    register_socket_events(socketio)
    
    # 데이터베이스 초기화
    # 데이터베이스 초기화
    from app.models import init_db, close_thread_db
    init_db()
    
    # [v4.15] 요청 종료 시 DB 연결 정리 (스레드 로컬)
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        close_thread_db()
    
    logger.info(f"{APP_NAME} v{VERSION} 앱 초기화 완료")
    
    # [v4.3] 보안 헤더 설정
    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        # CSP: 기본적으로 self만 허용, 스타일은 inline 허용 (간단한 앱 호환성)
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws: wss:;"
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response

    return app, socketio
