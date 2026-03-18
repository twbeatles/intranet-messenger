# -*- coding: utf-8 -*-
"""
PyQt6 GUI - 서버 관리 창 v4.2
- HiDPI 디스플레이 지원
- 토스트 알림 시스템
- 체크박스/버튼 UI 개선
- [v4.2] subprocess + HTTP 제어로 gevent 고성능 모드 지원
"""

import json
import os
import socket
import subprocess
import sys
import threading
import urllib.error
import urllib.request

# HiDPI 지원 (PyQt6 import 전에 설정)
os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '1'
os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '1'

from PyQt6.QtCore import QThread, pyqtSignal

# 프로젝트 루트에서 import
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
from config import APP_NAME, VERSION, DEFAULT_PORT, CONTROL_PORT, BASE_DIR, USE_HTTPS, SSL_CERT_PATH, SSL_KEY_PATH, SSL_DIR


def kill_process_on_port(port: int) -> bool:
    """
    [v4.3] 특정 포트를 사용 중인 프로세스 강제 종료
    서버 재시작 시 WinError 10048 (포트 충돌) 방지
    
    Returns:
        bool: 프로세스가 종료되었으면 True, 아니면 False
    """
    if sys.platform != 'win32':
        return False
    
    try:
        # netstat로 포트 사용 중인 프로세스 PID 찾기
        result = subprocess.run(
            ['netstat', '-ano'],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        target_pid = None
        for line in result.stdout.split('\n'):
            # LISTENING 상태이면서 해당 포트를 사용하는 프로세스 찾기
            if f':{port}' in line and 'LISTENING' in line:
                parts = line.split()
                if len(parts) >= 5:
                    target_pid = parts[-1]
                    break
        
        if target_pid and target_pid.isdigit():
            # taskkill로 프로세스 종료
            subprocess.run(
                ['taskkill', '/F', '/PID', target_pid],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            # 포트 해제 대기
            import time
            time.sleep(1)
            return True
            
    except Exception:
        pass
    
    return False


class ServerThread(QThread):
    """Flask 서버를 별도 subprocess에서 실행하고 모니터링"""
    log_signal = pyqtSignal(str)
    stats_signal = pyqtSignal(dict)
    
    def __init__(self, host='0.0.0.0', port=5000, use_https=False):
        super().__init__()
        self.host = host
        self.port = port
        self.use_https = use_https
        self.running = True
        self.process = None
        self.last_log_id = 0
        self.control_port = CONTROL_PORT
        self._control_token = None

    def _load_control_token(self):
        """서버가 생성한 .control_token 로딩 (없으면 빈 문자열)."""
        if self._control_token is not None:
            return self._control_token

        candidates = []
        try:
            candidates.append(os.path.join(BASE_DIR, '.control_token'))
        except Exception:
            pass

        try:
            candidates.append(os.path.join(os.path.dirname(sys.executable), '.control_token'))
        except Exception:
            pass

        try:
            candidates.append(os.path.join(PROJECT_ROOT, '.control_token'))
        except Exception:
            pass

        for p in candidates:
            try:
                if p and os.path.exists(p):
                    with open(p, 'r', encoding='utf-8', errors='replace') as f:
                        tok = (f.read() or '').strip()
                        if tok:
                            self._control_token = tok
                            return tok
            except Exception:
                continue

        self._control_token = ''
        return self._control_token

    def _control_base_urls(self):
        # New: dedicated localhost-only control port + token
        # Fallback: legacy main port /control (migration)
        return [
            f"http://127.0.0.1:{self.control_port}/control",
            f"http://127.0.0.1:{self.port}/control",
        ]

    def _request_control(self, path: str, method: str = 'GET', data: bytes | None = None, timeout: int = 3):
        token = self._load_control_token()
        last_err = None

        for base in self._control_base_urls():
            try:
                url = f"{base}{path}"
                req = urllib.request.Request(url, method=method, data=data)
                if token:
                    req.add_header('X-Control-Token', token)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return resp.read()
            except Exception as e:
                last_err = e
                continue

        raise last_err if last_err else RuntimeError("Control request failed")
        
    def run(self):
        try:
            # [v4.3] 기존 서버가 점유한 포트를 먼저 정리한다. (WinError 10048 방지)
            if kill_process_on_port(self.port):
                self.log_signal.emit(f"Port {self.port} process terminated")

            # Control API 포트도 동일하게 정리한다. (WinError 10048 방지)
            if kill_process_on_port(self.control_port):
                self.log_signal.emit(f"Port {self.control_port} process terminated")

            # [v4.5] 실행 환경 확인 (PyInstaller vs Source)
            if getattr(sys, 'frozen', False):
                # PyInstaller Frozen 환경: 자신의 EXE를 워커 모드로 실행
                cmd = [sys.executable, '--worker', '--port', str(self.port)]
            else:
                # 소스 코드 환경
                launcher_path = os.path.join(
                    PROJECT_ROOT,
                    'app', 'server_launcher.py'
                )
                
                # [v4.35] pythonw.exe 대신 python.exe 명시적 사용 (stdout 필요)
                python_exe = sys.executable
                if python_exe.endswith('pythonw.exe'):
                    python_exe = python_exe.replace('pythonw.exe', 'python.exe')
                
                cmd = [python_exe, launcher_path, '--port', str(self.port)]
            if self.use_https:
                cmd.append('--https')
            
            self.log_signal.emit(f"서버 시작 중: {' '.join(cmd)}")
            
            # [v4.4] stdout을 PIPE로 연결하여 실시간 로그 캡처
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # stderr도 stdout으로 통합
                text=True,
                bufsize=1,
                encoding='utf-8',  # 명시적 인코딩
                errors='replace',  # 디코딩 에러 방지
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            
            # [v4.4] 로그 읽기 스레드 시작 (메인 루프 블로킹 방지)
            log_thread = threading.Thread(target=self.read_output, daemon=True)
            log_thread.start()
            
            self.log_signal.emit("서버 프로세스 시작됨 (gevent 고성능 모드)")
            
            # 서버 시작 대기
            import time
            time.sleep(2)
            
            # HTTP 폴링으로 통계 모니터링 (로그는 stdout 스레드에서 처리)
            # Control API is served on 127.0.0.1:CONTROL_PORT with token (fallback supported)
            consecutive_errors = 0
            
            while self.running and self.process.poll() is None:
                try:
                    # 통계 조회
                    try:
                        raw = self._request_control('/stats', method='GET', timeout=3)
                        stats = json.loads(raw.decode('utf-8', errors='replace'))
                        self.stats_signal.emit(stats)
                        consecutive_errors = 0
                    except (urllib.error.URLError, socket.timeout):
                        pass # 아직 준비 안됨 or 타임아웃
                    
                    time.sleep(1) # 1초 간격 통계 갱신
                    
                except Exception as e:
                    consecutive_errors += 1
                    if consecutive_errors >= 10:
                        self.log_signal.emit(f"모니터링 연결 지연...")
                        consecutive_errors = 0
                    time.sleep(2)
                    
        except Exception as e:
            self.log_signal.emit(f"서버 프로세스 시작 오류: {e}")
        finally:
            self.cleanup()

    def read_output(self):
        """서버 프로세스의 stdout을 읽어서 로그로 전송"""
        if not self.process:
            return
        stdout = self.process.stdout
        if stdout is None:
            return
            
        try:
            for line in iter(stdout.readline, ''):
                if not line:
                    break
                line = line.strip()
                if line:
                    # [v4.4] 불필요한 폴링 로그 필터링
                    if '/control/stats' in line or '/control/logs' in line:
                        continue
                    self.log_signal.emit(line)
        except Exception as e:
            pass # 프로세스 종료 시 발생 가능

    def stop(self):
        """서버 프로세스 종료"""
        self.running = False
        
        # HTTP로 graceful shutdown 요청
        try:
            self._request_control('/shutdown', method='POST', data=b'', timeout=2)
        except Exception:
            pass  # 이미 종료되었거나 응답 없음
        
        self.cleanup()
        
    def cleanup(self):
        """프로세스 정리"""
        if self.process and self.process.poll() is None:
            self.log_signal.emit("서버 프로세스 종료 중...")
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        
        # [v4.3] 프로세스 종료 후에도 포트가 점유된 경우 강제 해제
        kill_process_on_port(self.port)



