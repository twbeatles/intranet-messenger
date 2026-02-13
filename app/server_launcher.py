#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
독립 서버 실행 스크립트
GUI에서 subprocess로 실행되며, gevent 고성능 모드를 사용합니다.
"""

import os
import sys

# 경로 설정 (반드시 가장 먼저)
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# gevent 모드를 사용하도록 환경변수 설정
os.environ['SKIP_GEVENT_PATCH'] = '0'

# gevent 패칭 (모든 import 전에 실행!)
try:
    from gevent import monkey
    monkey.patch_all()
    _GEVENT_PATCHED = True
except ImportError:
    _GEVENT_PATCHED = False

import argparse
import logging
import signal
import threading

from config import DEFAULT_PORT, CONTROL_PORT, USE_HTTPS, SSL_CERT_PATH, SSL_KEY_PATH


def setup_logging():
    """로깅 설정"""
    from logging.handlers import RotatingFileHandler
    
    log_file = os.path.join(current_dir, 'server.log')
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[file_handler, logging.StreamHandler()]
    )
    
    return logging.getLogger(__name__)


def start_control_server(logger):
    """GUI용 Control API를 별도 포트(127.0.0.1:CONTROL_PORT)에서 실행."""
    try:
        from flask import Flask
        from app.control_api import control_bp, init_control_logging, get_or_create_control_token
        from config import BASE_DIR

        # 토큰 파일을 미리 생성해 GUI가 읽을 수 있게 함
        get_or_create_control_token(BASE_DIR)

        control_app = Flask('control')
        control_app.register_blueprint(control_bp)
        init_control_logging()

        def _serve_gevent():
            from gevent import pywsgi
            server = pywsgi.WSGIServer(('127.0.0.1', CONTROL_PORT), control_app, log=None)
            server.serve_forever()

        def _serve_werkzeug():
            from werkzeug.serving import make_server
            http_server = make_server('127.0.0.1', CONTROL_PORT, control_app, threaded=True)
            http_server.serve_forever()

        def _serve():
            try:
                _serve_gevent()
            except Exception as e:
                logger.warning(f"Control API gevent server failed, falling back to werkzeug: {e}")
                _serve_werkzeug()

        t = threading.Thread(target=_serve, daemon=True)
        t.start()
        logger.info(f"Control API listening on http://127.0.0.1:{CONTROL_PORT}/control")
        return True
    except Exception as e:
        logger.error(f"Failed to start Control API: {e}")
        return False


def run_server(port=DEFAULT_PORT, use_https=USE_HTTPS, enable_control=True):
    """서버 실행"""
    logger = setup_logging()
    
    if _GEVENT_PATCHED:
        logger.info("gevent 고성능 모드로 서버 시작")
    else:
        logger.info("threading 모드로 서버 시작 (gevent 미설치)")
    
    # Flask 앱 생성
    from app import create_app
    from app.models import server_stats
    from datetime import datetime
    
    app, socketio = create_app()
    server_stats['start_time'] = datetime.now()
    
    # 제어 API는 별도 포트에서 localhost로만 노출
    if enable_control:
        start_control_server(logger)
    
    # SSL 설정
    ssl_context = None
    if use_https and os.path.exists(SSL_CERT_PATH) and os.path.exists(SSL_KEY_PATH):
        ssl_context = (SSL_CERT_PATH, SSL_KEY_PATH)
        logger.info("SSL 인증서 로드됨")
    
    protocol = "https" if ssl_context else "http"
    logger.info(f"서버 시작: {protocol}://0.0.0.0:{port}")
    
    # Graceful shutdown 핸들러
    def signal_handler(signum, frame):
        logger.info("종료 신호 수신, 서버 종료 중...")
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # 서버 실행
    try:
        run_kwargs = {
            'host': '0.0.0.0',
            'port': port,
            'debug': False,
            'use_reloader': False,
            'log_output': True,
            'allow_unsafe_werkzeug': True,
        }
        # SSL 설정은 gevent 모드에서 다르게 처리됨
        if ssl_context:
            run_kwargs['ssl_context'] = ssl_context
        
        socketio.run(app, **run_kwargs)
    except Exception as e:
        logger.error(f"서버 오류: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description='사내 메신저 서버')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='서버 포트')
    parser.add_argument('--https', action='store_true', default=USE_HTTPS, help='HTTPS 사용')
    parser.add_argument('--no-control', action='store_true', help='제어 API 비활성화')
    
    args = parser.parse_args()
    run_server(port=args.port, use_https=args.https, enable_control=not args.no_control)


if __name__ == '__main__':
    main()
