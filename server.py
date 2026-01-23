# -*- coding: utf-8 -*-
"""
사내 메신저 v4.36 서버
HTTPS + Socket.IO + Flask
"""

import os
import sys

# 현재 디렉토리를 경로에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# [v4.1] GUI 모드에서는 gevent 비활성화 (PyQt6 충돌 방지)
# 이 설정은 app/__init__.py의 monkey patching 전에 적용되어야 함
if len(sys.argv) <= 1 or sys.argv[1] != '--cli':
    os.environ['SKIP_GEVENT_PATCH'] = '1'

from config import (
    USE_HTTPS, DEFAULT_PORT, SSL_CERT_PATH, SSL_KEY_PATH, SSL_DIR
)


def check_ssl_certificates():
    """SSL 인증서 확인 및 생성"""
    if not USE_HTTPS:
        return None
    
    if os.path.exists(SSL_CERT_PATH) and os.path.exists(SSL_KEY_PATH):
        print(f"SSL 인증서 확인됨: {SSL_CERT_PATH}")
        return (SSL_CERT_PATH, SSL_KEY_PATH)
    
    print("SSL 인증서가 없습니다. 생성 중...")
    
    # ssl 디렉토리 생성
    os.makedirs(SSL_DIR, exist_ok=True)
    
    try:
        from certs.generate_cert import generate_certificate
        if generate_certificate(SSL_CERT_PATH, SSL_KEY_PATH):
            return (SSL_CERT_PATH, SSL_KEY_PATH)
        else:
            print("인증서 생성 실패. HTTP 모드로 실행합니다.")
            return None
    except ImportError as e:
        print(f"cryptography 라이브러리가 필요합니다: {e}")
        print("설치: pip install cryptography")
        print("HTTP 모드로 실행합니다.")
        return None
    except Exception as e:
        print(f"인증서 생성 오류: {e}")
        print("HTTP 모드로 실행합니다.")
        return None


def run_server_cli():
    """명령줄에서 서버 실행"""
    from app import create_app
    
    app, socketio = create_app()
    ssl_context = check_ssl_certificates()
    
    protocol = "https" if ssl_context else "http"
    print(f"\n{'='*50}")
    print(f"사내 메신저 서버 v4.36")
    print(f"{'='*50}")
    print(f"서버 주소: {protocol}://0.0.0.0:{DEFAULT_PORT}")
    print(f"로컬 접속: {protocol}://localhost:{DEFAULT_PORT}")
    print(f"암호화: E2E (종단간 암호화)")
    if ssl_context:
        print(f"SSL: 활성화 (자체 서명 인증서)")
    else:
        print(f"SSL: 비활성화")
    print(f"{'='*50}\n")
    
    try:
        if ssl_context:
            socketio.run(
                app,
                host='0.0.0.0',
                port=DEFAULT_PORT,
                debug=False,
                use_reloader=False,
                log_output=False,
                allow_unsafe_werkzeug=False,
                ssl_context=ssl_context
            )
        else:
            socketio.run(
                app,
                host='0.0.0.0',
                port=DEFAULT_PORT,
                debug=False,
                use_reloader=False,
                log_output=False,
                allow_unsafe_werkzeug=False
            )
    except OSError as e:
        if "10048" in str(e) or "Address already in use" in str(e):
            print(f"오류: 포트 {DEFAULT_PORT}이 이미 사용 중입니다.")
        else:
            print(f"서버 오류: {e}")


def run_server_gui():
    """GUI 모드로 서버 실행"""
    from PyQt6.QtWidgets import QApplication
    from gui.server_window import ServerWindow
    
    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)
    
    window = ServerWindow()
    window.show()
    
    sys.exit(qt_app.exec())


if __name__ == '__main__':
    # 명령줄 인수 확인
    if len(sys.argv) > 1:
        if sys.argv[1] == '--cli':
            run_server_cli()
        elif sys.argv[1] == '--worker':
            # [v4.4] PyInstaller 대응: subprocess 서버 워커로 실행
            # --worker 인자를 제거하고 server_launcher 실행
            sys.argv.pop(1)
            from app.server_launcher import main as launcher_main
            launcher_main()
        else:
            # 기본: GUI 모드
            try:
                run_server_gui()
            except ImportError:
                print("PyQt6를 찾을 수 없습니다. CLI 모드로 실행합니다.")
                run_server_cli()
    else:
        # 인수가 없으면 GUI 모드
        try:
            run_server_gui()
        except ImportError:
            print("PyQt6를 찾을 수 없습니다. CLI 모드로 실행합니다.")
            run_server_cli()
