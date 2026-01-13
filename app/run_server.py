# -*- coding: utf-8 -*-
"""
서버 프로세스 실행 모듈
PyQt6와 gevent의 충돌을 피하기 위해 별도 프로세스에서 서버를 실행합니다.
"""

import os
import sys
import time
import threading
import logging
from multiprocessing import Queue

def run_server_process(log_queue, host, port, use_https, ssl_paths=None):
    """
    별도 프로세스에서 Flask-SocketIO 서버 실행
    
    Args:
        log_queue: 로그 및 통계를 보낼 멀티프로세싱 큐
        host: 호스트 주소
        port: 포트 번호
        use_https: HTTPS 사용 여부
        ssl_paths: (cert_path, key_path) 튜플
    """
    # 1. 로깅 설정 (큐로 전송)
    class QueueHandler(logging.Handler):
        def emit(self, record):
            try:
                msg = self.format(record)
                log_queue.put(('log', msg))
            except Exception:
                self.handleError(record)
    
    # 루트 로거 설정
    root_logger = logging.getLogger()
    # 기존 핸들러 제거 (중복 방지)
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
        
    q_handler = QueueHandler()
    q_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    root_logger.addHandler(q_handler)
    
    # 2. 환경 설정
    # Gevent 활성화를 위해 패치 스킵 환경변수 해제
    os.environ['SKIP_GEVENT_PATCH'] = '0'
    
    # 경로 추가
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    
    try:
        from app import create_app
        from app.models import server_stats
        from datetime import datetime
        
        # 3. 앱 생성
        app, socketio = create_app()
        
        # 시작 시간 기록
        server_stats['start_time'] = datetime.now()
        
        # 4. 통계 전송 스레드
        def stats_pusher():
            while True:
                try:
                    # server_stats 단순 복사
                    stats_copy = server_stats.copy()
                    log_queue.put(('stats', stats_copy))
                except Exception:
                    pass
                time.sleep(1)
        
        stats_thread = threading.Thread(target=stats_pusher, daemon=True)
        stats_thread.start()
        
        # 5. SSL 설정
        ssl_context = None
        if use_https and ssl_paths:
             if os.path.exists(ssl_paths[0]) and os.path.exists(ssl_paths[1]):
                 ssl_context = tuple(ssl_paths)
                 logging.info("SSL 인증서가 로드되었습니다.")
             else:
                 logging.warning("SSL 인증서를 찾을 수 없습니다. HTTP로 실행합니다.")
        
        protocol = "https" if ssl_context else "http"
        logging.info(f"서버가 시작됩니다: {protocol}://{host}:{port}")
        
        # 6. 서버 실행
        socketio.run(
            app,
            host=host,
            port=port,
            debug=False,
            use_reloader=False,
            log_output=False,  # 로거가 이미 처리함
            allow_unsafe_werkzeug=True,
            ssl_context=ssl_context
        )
        
    except Exception as e:
        logging.error(f"서버 프로세스 오류: {e}")
        import traceback
        logging.error(traceback.format_exc())
