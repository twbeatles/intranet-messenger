# -*- coding: utf-8 -*-
"""
사내 메신저 v4.1 앱 패키지
Flask 앱 팩토리 패턴
"""

import os
import sys
import logging
import secrets
import time
import json
import re
from datetime import timedelta

# gevent monkey patching (반드시 다른 import 전에 실행)
# [v4.1] GUI 모드에서는 PyQt6와 충돌하므로 비활성화
# [v4.2] server_launcher.py에서 이미 패치한 경우 감지
_SKIP_GEVENT = os.environ.get('SKIP_GEVENT_PATCH', '0') == '1'
_GEVENT_AVAILABLE = False
_GEVENT_ALREADY_PATCHED = False

# 이미 gevent가 패치되었는지 확인
try:
    from gevent import monkey
    _GEVENT_ALREADY_PATCHED = monkey.is_module_patched('socket')
    if _GEVENT_ALREADY_PATCHED:
        _GEVENT_AVAILABLE = True
except ImportError:
    pass

if not _SKIP_GEVENT and not _GEVENT_ALREADY_PATCHED:
    try:
        from gevent import monkey
        monkey.patch_all()
        _GEVENT_AVAILABLE = True
    except ImportError:
        _GEVENT_AVAILABLE = False

from flask import Flask, jsonify, redirect, request, session
from flask_socketio import SocketIO
from app.extensions import limiter, csrf, compress
from flask_session import Session
try:
    from cachelib.file import FileSystemCache
except Exception:
    FileSystemCache = None


# config 임포트 (PyInstaller 호환)
try:
    from config import (
        BASE_DIR, DATABASE_PATH, UPLOAD_FOLDER, MAX_CONTENT_LENGTH,
        SESSION_TIMEOUT_HOURS, APP_NAME, VERSION, USE_HTTPS,
        STATIC_FOLDER, TEMPLATE_FOLDER,
        ASYNC_MODE, PING_TIMEOUT, PING_INTERVAL, MAX_HTTP_BUFFER_SIZE,
        MAX_CONNECTIONS, MESSAGE_QUEUE, SOCKETIO_CORS_ALLOWED_ORIGINS,
        RATE_LIMIT_STORAGE_URI, STATE_STORE_REDIS_URL,
        MAINTENANCE_INTERVAL_SECONDS, RETENTION_DAYS,
        FEATURE_OIDC_ENABLED, FEATURE_AV_SCAN_ENABLED, FEATURE_REDIS_ENABLED,
        OIDC_PROVIDER_NAME, OIDC_ISSUER_URL, OIDC_AUTHORIZE_URL, OIDC_TOKEN_URL, OIDC_USERINFO_URL,
        OIDC_CLIENT_ID, OIDC_CLIENT_SECRET, OIDC_SCOPE, OIDC_REDIRECT_URI,
        AV_SCANNER, AV_CLAMD_HOST, AV_CLAMD_PORT, AV_SCAN_TIMEOUT_SECONDS, UPLOAD_QUARANTINE_FOLDER,
        SOCKET_SEND_MESSAGE_PER_MINUTE
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
        MAX_CONNECTIONS, MESSAGE_QUEUE, SOCKETIO_CORS_ALLOWED_ORIGINS,
        RATE_LIMIT_STORAGE_URI, STATE_STORE_REDIS_URL,
        MAINTENANCE_INTERVAL_SECONDS, RETENTION_DAYS,
        FEATURE_OIDC_ENABLED, FEATURE_AV_SCAN_ENABLED, FEATURE_REDIS_ENABLED,
        OIDC_PROVIDER_NAME, OIDC_ISSUER_URL, OIDC_AUTHORIZE_URL, OIDC_TOKEN_URL, OIDC_USERINFO_URL,
        OIDC_CLIENT_ID, OIDC_CLIENT_SECRET, OIDC_SCOPE, OIDC_REDIRECT_URI,
        AV_SCANNER, AV_CLAMD_HOST, AV_CLAMD_PORT, AV_SCAN_TIMEOUT_SECONDS, UPLOAD_QUARANTINE_FOLDER,
        SOCKET_SEND_MESSAGE_PER_MINUTE
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

_MOJIBAKE_HINT_TOKENS = (
    "濡쒓렇", "꾩슂", "뺤옣", "먯꽌", "룞", "몄씠", "⑸땲", "뒿", "媛뺥",
    "앹꽦", "怨듭", "뚯씪", "紐낆쓽", "쒖냼", "먮룞", "쒕쾭", "곗씠",
)
_MOJIBAKE_LATIN_RE = re.compile(r"[Ã-ÿ]{2,}")


def _looks_like_mojibake(text: str) -> bool:
    if not isinstance(text, str) or not text:
        return False
    if any(token in text for token in _MOJIBAKE_HINT_TOKENS):
        return True
    if _MOJIBAKE_LATIN_RE.search(text):
        return True
    if text.count("?") >= 2 and any(ord(ch) > 127 for ch in text):
        return True
    return False


def _fallback_message_for_status(status_code: int) -> str:
    if status_code == 400:
        return "요청 값이 올바르지 않습니다."
    if status_code == 401:
        return "로그인이 필요합니다."
    if status_code == 403:
        return "접근 권한이 없습니다."
    if status_code == 404:
        return "요청한 리소스를 찾을 수 없습니다."
    if status_code == 429:
        return "요청 한도를 초과했습니다."
    if status_code >= 500:
        return "서버 내부 오류가 발생했습니다."
    return "요청 처리 중 오류가 발생했습니다."


def _normalize_json_response_messages(payload, status_code: int):
    changed = False

    def walk(node, key_name=None):
        nonlocal changed

        if isinstance(node, dict):
            return {k: walk(v, key_name=k) for k, v in node.items()}

        if isinstance(node, list):
            return [walk(item, key_name=key_name) for item in node]

        if isinstance(node, str) and key_name in ("error", "message", "detail"):
            if _looks_like_mojibake(node):
                changed = True
                return _fallback_message_for_status(status_code)
            return node

        return node

    normalized = walk(payload)
    return normalized, changed


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
    os.makedirs(UPLOAD_QUARANTINE_FOLDER, exist_ok=True)
    
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
    app.config['RATELIMIT_STORAGE_URI'] = RATE_LIMIT_STORAGE_URI
    app.config['STATE_STORE_REDIS_URL'] = STATE_STORE_REDIS_URL
    app.config['RETENTION_DAYS'] = RETENTION_DAYS
    app.config['MAINTENANCE_INTERVAL_SECONDS'] = MAINTENANCE_INTERVAL_SECONDS
    app.config['FEATURE_OIDC_ENABLED'] = FEATURE_OIDC_ENABLED
    app.config['FEATURE_AV_SCAN_ENABLED'] = FEATURE_AV_SCAN_ENABLED
    app.config['FEATURE_REDIS_ENABLED'] = FEATURE_REDIS_ENABLED
    app.config['OIDC_PROVIDER_NAME'] = OIDC_PROVIDER_NAME
    app.config['OIDC_ISSUER_URL'] = OIDC_ISSUER_URL
    app.config['OIDC_AUTHORIZE_URL'] = OIDC_AUTHORIZE_URL
    app.config['OIDC_TOKEN_URL'] = OIDC_TOKEN_URL
    app.config['OIDC_USERINFO_URL'] = OIDC_USERINFO_URL
    app.config['OIDC_CLIENT_ID'] = OIDC_CLIENT_ID
    app.config['OIDC_CLIENT_SECRET'] = OIDC_CLIENT_SECRET
    app.config['OIDC_SCOPE'] = OIDC_SCOPE
    app.config['OIDC_REDIRECT_URI'] = OIDC_REDIRECT_URI
    app.config['AV_SCANNER'] = AV_SCANNER
    app.config['AV_CLAMD_HOST'] = AV_CLAMD_HOST
    app.config['AV_CLAMD_PORT'] = AV_CLAMD_PORT
    app.config['AV_SCAN_TIMEOUT_SECONDS'] = AV_SCAN_TIMEOUT_SECONDS
    app.config['UPLOAD_QUARANTINE_FOLDER'] = UPLOAD_QUARANTINE_FOLDER
    app.config['SOCKET_SEND_MESSAGE_PER_MINUTE'] = SOCKET_SEND_MESSAGE_PER_MINUTE

    if str(app.config.get('RATELIMIT_STORAGE_URI', '')).startswith('redis'):
        try:
            import redis  # type: ignore # noqa: F401
        except Exception as exc:
            logger.warning(f"Redis client unavailable for rate limit storage, falling back to memory:// ({exc})")
            app.config['RATELIMIT_STORAGE_URI'] = 'memory://'
    
    # [v4.37] Server-Side Session
    # Prefer cachelib backend to avoid deprecated filesystem session interface.
    session_dir = os.path.join(BASE_DIR, 'flask_session')
    os.makedirs(session_dir, exist_ok=True)
    app.config['SESSION_PERMANENT'] = True
    if FileSystemCache is not None:
        app.config['SESSION_TYPE'] = 'cachelib'
        app.config['SESSION_CACHELIB'] = FileSystemCache(
            cache_dir=session_dir,
            threshold=1000,
            mode=0o600,
        )
    else:
        # Fallback for extremely minimal environments.
        app.config['SESSION_TYPE'] = 'filesystem'
        app.config['SESSION_FILE_DIR'] = session_dir
    Session(app)

    from app.state_store import state_store
    state_store.init_app(redis_url=app.config.get('STATE_STORE_REDIS_URL') or None)

    
    # Socket.IO 초기화 - 비동기 모드 선택
    # 우선순위: gevent (이미 패치된 경우) > config 설정 > threading
    _async_mode = None
    
    # [v4.2] gevent가 이미 패치되었으면 무조건 gevent 모드 사용
    if _GEVENT_AVAILABLE:
        try:
            import gevent  # noqa: F401
            from gevent import pywsgi  # noqa: F401
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
        'ping_timeout': PING_TIMEOUT,
        'ping_interval': PING_INTERVAL,
        'max_http_buffer_size': MAX_HTTP_BUFFER_SIZE,
        'async_mode': _async_mode,
        'logger': False,
        'engineio_logger': False
    }

    # CORS: 기본은 동일 출처. 필요 시 config에서 화이트리스트 지정.
    if SOCKETIO_CORS_ALLOWED_ORIGINS is not None:
        socketio_kwargs['cors_allowed_origins'] = SOCKETIO_CORS_ALLOWED_ORIGINS
    
    # Redis 메시지 큐 설정 (대규모 배포용)
    if MESSAGE_QUEUE:
        socketio_kwargs['message_queue'] = MESSAGE_QUEUE
        logger.info(f"메시지 큐 활성화: {MESSAGE_QUEUE}")
    
    try:
        socketio = SocketIO(app, **socketio_kwargs)
        logger.info(f"Socket.IO 초기화 완료 (모드: {_async_mode or 'default'})")
    except ValueError as e:
        logger.warning(f"Socket.IO 초기화 경고: {e}, 기본 모드로 재시도")
        # 재시도 시에도 CORS는 기본(동일 출처)을 유지
        socketio = SocketIO(app, logger=False, engineio_logger=False)
    
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
    from app.models import (
        init_db, close_thread_db, get_user_session_token, close_expired_polls,
        cleanup_old_access_logs, cleanup_empty_rooms, cleanup_retention_data
    )
    init_db()

    @app.before_request
    def enforce_session_token():
        if 'user_id' not in session:
            return None

        path = request.path or ''
        if path.startswith('/control/') or path.startswith('/static/'):
            return None
        if path in (
            '/api/login',
            '/api/register',
            '/api/logout',
            '/api/config',
            '/api/auth/providers',
            '/auth/oidc/login',
            '/auth/oidc/callback',
        ):
            return None

        user_id = session.get('user_id')
        db_token = get_user_session_token(user_id)
        sess_token = session.get('session_token')
        if not db_token or not sess_token or db_token != sess_token:
            session.clear()
            if path.startswith('/api') or path.startswith('/uploads'):
                return jsonify({'error': '세션이 만료되었거나 다른 세션에서 무효화되었습니다.'}), 401
            return redirect('/')
        return None
    
    # [v4.15] 요청 종료 시 DB 연결 정리 (스레드 로컬)
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        close_thread_db()

    def _maintenance_worker():
        interval = max(30, int(app.config.get('MAINTENANCE_INTERVAL_SECONDS', 300)))
        retention_days = int(app.config.get('RETENTION_DAYS', 0) or 0)
        logger.info(f"Maintenance worker started (interval={interval}s, retention_days={retention_days})")
        while True:
            try:
                close_expired_polls()
                cleanup_old_access_logs()
                cleanup_empty_rooms()
                if retention_days > 0:
                    cleanup_retention_data(retention_days)
            except Exception as exc:
                logger.warning(f"Maintenance worker error: {exc}")
            time.sleep(interval)

    is_testing_runtime = bool(app.config.get('TESTING')) or ('PYTEST_CURRENT_TEST' in os.environ)
    if is_testing_runtime:
        logger.info("Testing runtime detected; skipping background maintenance/upload scan workers")
    else:
        socketio.start_background_task(_maintenance_worker)

        try:
            from app.upload_scan import init_upload_scan_worker

            init_upload_scan_worker(app)
        except Exception as exc:
            logger.warning(f"Upload scan worker init failed: {exc}")
    
    logger.info(f"{APP_NAME} v{VERSION} 앱 초기화 완료")
    
    # [v4.3] 보안 헤더 설정
    @app.after_request
    def add_security_headers(response):
        if (request.path or "").startswith("/api") and response.mimetype == "application/json":
            payload = response.get_json(silent=True)
            if payload is not None:
                normalized_payload, changed = _normalize_json_response_messages(payload, response.status_code)
                if changed:
                    response.set_data(json.dumps(normalized_payload, ensure_ascii=False).encode("utf-8"))
                    response.headers["Content-Type"] = "application/json; charset=utf-8"

        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        # CSP: 기본적으로 self만 허용, 스타일과 스크립트 inline 허용 (onclick 핸들러 필요)
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws: wss:;"
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response

    return app, socketio
