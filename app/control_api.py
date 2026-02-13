# -*- coding: utf-8 -*-
"""
서버 제어 API
GUI에서 서버 상태 조회 및 제어를 위한 내부 API
"""

import logging
import os
import secrets
from collections import deque
from flask import Blueprint, jsonify, request

# 로그 버퍼 (최근 100개 로그 저장)
_log_buffer = deque(maxlen=100)
_shutdown_requested = False

control_bp = Blueprint('control', __name__, url_prefix='/control')
logger = logging.getLogger(__name__)


def _get_base_dir():
    try:
        from config import BASE_DIR
        return BASE_DIR
    except Exception:
        # Fallback: 프로젝트 루트(소스 실행 가정)
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_or_create_control_token(base_dir: str = None) -> str:
    """Control API 인증 토큰 생성/로딩.

    토큰은 {BASE_DIR}/.control_token에 저장됩니다.
    """
    base_dir = base_dir or _get_base_dir()
    token_path = os.path.join(base_dir, '.control_token')

    try:
        if os.path.exists(token_path):
            with open(token_path, 'r', encoding='utf-8', errors='replace') as f:
                token = (f.read() or '').strip()
                if token:
                    return token
    except Exception:
        pass

    token = secrets.token_hex(32)
    try:
        with open(token_path, 'w', encoding='utf-8') as f:
            f.write(token)
        try:
            os.chmod(token_path, 0o600)
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"Failed to write control token: {e}")
    return token


def _is_localhost(addr: str) -> bool:
    if not addr:
        return False
    return addr in ('127.0.0.1', '::1', '::ffff:127.0.0.1')


def require_control_auth():
    """localhost + token header 인증."""
    if not _is_localhost(request.remote_addr):
        return jsonify({'error': 'forbidden'}), 403

    expected = get_or_create_control_token()
    provided = request.headers.get('X-Control-Token', '')
    if not provided or provided != expected:
        return jsonify({'error': 'unauthorized'}), 401
    return None


@control_bp.before_request
def _auth_before_request():
    return require_control_auth()


class BufferLogHandler(logging.Handler):
    """로그를 버퍼에 저장하는 핸들러"""
    def emit(self, record):
        try:
            msg = self.format(record)
            _log_buffer.append(msg)
        except Exception:
            self.handleError(record)


def init_control_logging():
    """제어 API용 로그 핸들러 등록"""
    handler = BufferLogHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logging.getLogger().addHandler(handler)


@control_bp.route('/status', methods=['GET'])
def get_status():
    """서버 상태 조회"""
    return jsonify({
        'status': 'running',
        'shutdown_requested': _shutdown_requested
    })


@control_bp.route('/stats', methods=['GET'])
def get_stats():
    """서버 통계 조회"""
    try:
        from app.models import get_server_stats
        stats = get_server_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@control_bp.route('/logs', methods=['GET'])
def get_logs():
    """최신 로그 조회"""
    # last_id 파라미터로 마지막으로 받은 로그 이후만 조회 가능
    last_id = request.args.get('last_id', 0, type=int)
    logs = list(_log_buffer)
    
    # 간단한 슬라이싱 (last_id는 인덱스로 사용)
    if last_id > 0 and last_id < len(logs):
        logs = logs[last_id:]
    
    return jsonify({
        'logs': logs,
        'next_id': len(_log_buffer)
    })


@control_bp.route('/shutdown', methods=['POST'])
def shutdown():
    """?? ?? ??"""
    global _shutdown_requested
    _shutdown_requested = True

    # Control API? ?? ??? ?? ?? ???????, ???? ??? ???? ?.
    import os
    import signal
    try:
        os.kill(os.getpid(), signal.SIGTERM)
    except Exception:
        os._exit(0)

    return jsonify({'message': 'Shutdown initiated'})
