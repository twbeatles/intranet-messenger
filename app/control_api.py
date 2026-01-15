# -*- coding: utf-8 -*-
"""
서버 제어 API
GUI에서 서버 상태 조회 및 제어를 위한 내부 API
"""

import logging
from collections import deque
from flask import Blueprint, jsonify, request

# 로그 버퍼 (최근 100개 로그 저장)
_log_buffer = deque(maxlen=100)
_shutdown_requested = False

control_bp = Blueprint('control', __name__, url_prefix='/control')
logger = logging.getLogger(__name__)


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
    """서버 종료 요청"""
    global _shutdown_requested
    _shutdown_requested = True
    
    # Werkzeug 개발 서버 종료
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        # gevent 등 다른 서버 사용 시
        import os
        import signal
        os.kill(os.getpid(), signal.SIGTERM)
    else:
        func()
    
    return jsonify({'message': 'Shutdown initiated'})
