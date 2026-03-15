# -*- coding: utf-8 -*-
"""
PyQt6 GUI - 서버 관리 창 v4.2
- HiDPI 디스플레이 지원
- 토스트 알림 시스템
- 체크박스/버튼 UI 개선
- [v4.2] subprocess + HTTP 제어로 gevent 고성능 모드 지원
"""

import os
import sys
import socket
import winreg
import subprocess
import urllib.request
import urllib.error
import json
import threading
from datetime import datetime

# HiDPI 지원 (PyQt6 import 전에 설정)
os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '1'
os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '1'

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSystemTrayIcon, QMenu, QTextEdit,
    QSpinBox, QCheckBox, QGroupBox, QTabWidget, QGraphicsOpacityEffect
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QSettings, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QIcon, QAction, QFont, QColor, QPixmap, QPainter

# 부모 디렉토리에서 import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
            repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            candidates.append(os.path.join(repo_root, '.control_token'))
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
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
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



class ToastWidget(QLabel):
    """토스트 알림 위젯"""
    
    def __init__(self, parent=None, message: str = "", toast_type: str = "info", duration: int = 3000):
        super().__init__(parent)
        self.duration = duration
        
        # 타입별 스타일
        styles = {
            "success": ("✅", "#22C55E", "#0F3D0F"),
            "error": ("❌", "#EF4444", "#3D0F0F"),
            "warning": ("⚠️", "#F59E0B", "#3D2E0F"),
            "info": ("ℹ️", "#3B82F6", "#0F1D3D")
        }
        icon, border_color, bg_color = styles.get(toast_type, styles["info"])
        
        self.setText(f"{icon} {message}")
        self.setStyleSheet(f'''
            QLabel {{
                background-color: {bg_color};
                color: #F8FAFC;
                border: 1px solid {border_color};
                border-radius: 8px;
                padding: 12px 20px;
                font-size: 13px;
                font-weight: 500;
            }}
        ''')
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.adjustSize()
        
        # 페이드 효과
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(1.0)
        
        # 자동 숨김 타이머
        QTimer.singleShot(duration, self._start_fade_out)
    
    def _start_fade_out(self):
        """페이드 아웃 애니메이션 시작"""
        self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_anim.setDuration(300)
        self.fade_anim.setStartValue(1.0)
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.fade_anim.finished.connect(self.deleteLater)
        self.fade_anim.start()


class ServerWindow(QMainWindow):
    """메인 서버 관리 윈도우"""
    
    def __init__(self):
        super().__init__()
        self.server_thread = None
        self.settings = QSettings('MessengerServer', 'Settings')
        self.local_stats = {}  # [v4.16] 로컬 통계 저장소
        self.init_ui()
        self.create_tray_icon()
        self.load_settings()
        
        # 서버 자동 시작 (지연)
        if self.settings.value('auto_start_server', True, type=bool):
            QTimer.singleShot(1000, self.safe_start_server)
    
    def safe_start_server(self):
        """안전한 서버 시작 (예외 처리 포함)"""
        try:
            self.start_server()
        except Exception as e:
            self.add_log(f'서버 자동 시작 실패: {e}')
    
    def init_ui(self):
        """유저 인터페이스 초기화"""
        self.setWindowTitle(f'{APP_NAME} v{VERSION}')
        self.setMinimumSize(800, 700)  # [v4.1] 최소 크기 증가
        self.resize(850, 750)  # [v4.1] 기본 크기 설정
        self.setStyleSheet('''
            QMainWindow { background-color: #0F172A; }
            QWidget { color: #F8FAFC; font-family: 'Segoe UI', sans-serif; }
            QGroupBox { border: 1px solid #334155; border-radius: 8px; margin-top: 12px; padding: 16px; background-color: #1E293B; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 8px; color: #10B981; font-weight: bold; }
            QPushButton { background-color: #10B981; color: white; border: none; padding: 10px 20px; border-radius: 6px; font-weight: bold; min-height: 20px; }
            QPushButton:hover { background-color: #059669; }
            QPushButton:disabled { background-color: #475569; color: #94A3B8; }
            QPushButton#stopBtn { background-color: #EF4444; }
            QPushButton#stopBtn:hover { background-color: #DC2626; }
            QPushButton#genCertBtn { background-color: #F59E0B; }
            QPushButton#genCertBtn:hover { background-color: #D97706; }
            QLineEdit, QSpinBox { background-color: #1E293B; border: 1px solid #334155; border-radius: 4px; padding: 8px; color: #F8FAFC; min-height: 20px; }
            QLineEdit:focus, QSpinBox:focus { border-color: #10B981; }
            QTextEdit { background-color: #0F172A; border: 1px solid #334155; border-radius: 4px; color: #94A3B8; font-family: Consolas, monospace; }
            QCheckBox { color: #F8FAFC; spacing: 8px; padding: 4px 0; min-height: 24px; }
            QCheckBox::indicator { width: 20px; height: 20px; border: 2px solid #475569; border-radius: 4px; background-color: #1E293B; }
            QCheckBox::indicator:checked { background-color: #10B981; border-color: #10B981; image: none; }
            QCheckBox::indicator:hover { border-color: #10B981; }
            QLabel { color: #94A3B8; }
            QTabWidget::pane { border: 1px solid #334155; border-radius: 8px; background-color: #1E293B; }
            QTabBar::tab { background-color: #1E293B; color: #94A3B8; padding: 10px 20px; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }
            QTabBar::tab:selected { background-color: #10B981; color: white; }
        ''')
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        
        # 헤더
        header = QHBoxLayout()
        title = QLabel(f'🔒 {APP_NAME}')
        title.setStyleSheet('font-size: 24px; font-weight: bold; color: #F8FAFC;')
        header.addWidget(title)
        
        self.status_label = QLabel('⚪ 서버 중지됨')
        self.status_label.setStyleSheet('font-size: 14px; color: #94A3B8;')
        header.addStretch()
        header.addWidget(self.status_label)
        layout.addLayout(header)
        
        # 탭 위젯
        tabs = QTabWidget()
        layout.addWidget(tabs)
        
        # 제어 탭
        control_tab = QWidget()
        control_layout = QVBoxLayout(control_tab)
        control_layout.setSpacing(16)
        
        # 서버 설정 그룹
        server_group = QGroupBox('서버 설정')
        server_layout = QHBoxLayout(server_group)
        
        server_layout.addWidget(QLabel('포트:'))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1000, 65535)
        self.port_spin.setValue(DEFAULT_PORT)
        server_layout.addWidget(self.port_spin)
        
        server_layout.addSpacing(10)
        
        self.https_check = QCheckBox('HTTPS 사용')
        self.https_check.setChecked(USE_HTTPS)
        server_layout.addWidget(self.https_check)
        
        server_layout.addSpacing(20)
        
        self.start_btn = QPushButton('▶ 서버 시작')
        self.start_btn.clicked.connect(self.start_server)
        server_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton('■ 서버 중지')
        self.stop_btn.setObjectName('stopBtn')
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_server)
        server_layout.addWidget(self.stop_btn)
        
        server_layout.addStretch()
        control_layout.addWidget(server_group)
        
        # SSL 인증서 그룹
        ssl_group = QGroupBox('SSL 인증서')
        ssl_layout = QVBoxLayout(ssl_group)
        
        self.ssl_status = QLabel('인증서 상태: 확인 중...')
        self.ssl_status.setStyleSheet('color: #F8FAFC;')
        ssl_layout.addWidget(self.ssl_status)
        
        ssl_btn_layout = QHBoxLayout()
        self.gen_cert_btn = QPushButton('🔑 인증서 생성')
        self.gen_cert_btn.setObjectName('genCertBtn')
        self.gen_cert_btn.clicked.connect(self.generate_certificate)
        ssl_btn_layout.addWidget(self.gen_cert_btn)
        ssl_btn_layout.addStretch()
        ssl_layout.addLayout(ssl_btn_layout)
        
        control_layout.addWidget(ssl_group)
        self.update_ssl_status()
        
        # 옵션 그룹
        options_group = QGroupBox('옵션')
        options_layout = QVBoxLayout(options_group)
        options_layout.setSpacing(12)  # [v4.1] 체크박스 간격 증가
        
        self.auto_start_check = QCheckBox('프로그램 시작 시 서버 자동 시작')
        self.auto_start_check.setChecked(True)
        self.auto_start_check.stateChanged.connect(self.save_settings)
        options_layout.addWidget(self.auto_start_check)
        
        self.windows_startup_check = QCheckBox('Windows 시작 시 자동 실행')
        self.windows_startup_check.stateChanged.connect(self.toggle_windows_startup)
        options_layout.addWidget(self.windows_startup_check)
        
        self.minimize_to_tray_check = QCheckBox('닫기 버튼 클릭 시 트레이로 최소화')
        self.minimize_to_tray_check.setChecked(True)
        self.minimize_to_tray_check.stateChanged.connect(self.save_settings)
        options_layout.addWidget(self.minimize_to_tray_check)
        
        control_layout.addWidget(options_group)
        
        # 접속 정보 그룹
        info_group = QGroupBox('접속 정보')
        info_layout = QVBoxLayout(info_group)
        info_layout.setSpacing(10)  # [v4.1] 라벨 간격 증가
        
        hostname = socket.gethostname()
        try:
            local_ip = socket.gethostbyname(hostname)
        except (OSError, socket.error):
            local_ip = '127.0.0.1'
        
        protocol = "https" if USE_HTTPS else "http"
        self.local_url = QLabel(f'🖥️ 로컬 접속: {protocol}://localhost:{self.port_spin.value()}')
        self.local_url.setStyleSheet('font-size: 14px; color: #F8FAFC;')
        info_layout.addWidget(self.local_url)
        
        self.network_url = QLabel(f'🌐 네트워크 접속: {protocol}://{local_ip}:{self.port_spin.value()}')
        self.network_url.setStyleSheet('font-size: 14px; color: #F8FAFC;')
        info_layout.addWidget(self.network_url)
        
        self.encryption_info = QLabel('🔒 종단간 암호화(E2E) 적용: 서버 관리자도 메시지 내용 확인 불가')
        self.encryption_info.setStyleSheet('font-size: 12px; color: #10B981;')
        info_layout.addWidget(self.encryption_info)
        
        control_layout.addWidget(info_group)
        control_layout.addStretch()
        
        tabs.addTab(control_tab, '제어')
        
        # 통계 탭
        stats_tab = QWidget()
        stats_layout = QVBoxLayout(stats_tab)
        
        stats_group = QGroupBox('실시간 통계')
        stats_inner = QVBoxLayout(stats_group)
        
        self.stats_labels = {}
        stats_items = [
            ('active_connections', '현재 접속자'),
            ('total_connections', '총 접속 횟수'),
            ('total_messages', '총 메시지 수'),
            ('uptime', '서버 가동 시간')
        ]
        
        for key, label_text in stats_items:
            row = QHBoxLayout()
            label = QLabel(f'{label_text}:')
            value = QLabel('0')
            value.setStyleSheet('font-size: 18px; font-weight: bold; color: #10B981;')
            row.addWidget(label)
            row.addStretch()
            row.addWidget(value)
            stats_inner.addLayout(row)
            self.stats_labels[key] = value
        
        stats_layout.addWidget(stats_group)
        stats_layout.addStretch()
        
        tabs.addTab(stats_tab, '통계')
        
        # 로그 탭
        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        
        clear_log_btn = QPushButton('로그 지우기')
        clear_log_btn.clicked.connect(lambda: self.log_text.clear())
        log_layout.addWidget(clear_log_btn)
        
        tabs.addTab(log_tab, '로그')
        
        # 포트/HTTPS 변경 시 URL 업데이트
        self.port_spin.valueChanged.connect(self.update_urls)
        self.https_check.stateChanged.connect(self.update_urls)
        
        # 통계 UI 업데이트 타이머 (데이터는 signal로 받지만 UI 갱신은 부하 분산을 위해 유지)
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_stats_ui)
        self.stats_timer.start(1000)
    
    def update_ssl_status(self):
        """SSL 인증서 상태 업데이트"""
        if os.path.exists(SSL_CERT_PATH) and os.path.exists(SSL_KEY_PATH):
            self.ssl_status.setText('✅ 인증서 존재함')
            self.ssl_status.setStyleSheet('color: #22C55E;')
        else:
            self.ssl_status.setText('❌ 인증서 없음 (HTTPS 사용 시 생성 필요)')
            self.ssl_status.setStyleSheet('color: #EF4444;')
    
    def generate_certificate(self):
        """SSL 인증서 생성"""
        try:
            os.makedirs(SSL_DIR, exist_ok=True)
            
            from certs.generate_cert import generate_certificate as gen_cert
            if gen_cert(SSL_CERT_PATH, SSL_KEY_PATH):
                self.add_log('SSL 인증서 생성 완료')
                self.update_ssl_status()
            else:
                self.add_log('SSL 인증서 생성 실패')
        except ImportError:
            self.add_log('cryptography 라이브러리가 필요합니다: pip install cryptography')
        except Exception as e:
            self.add_log(f'인증서 생성 오류: {e}')
    
    def create_tray_icon(self):
        """시스템 트레이 아이콘 생성"""
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor('#10B981'))
        painter = QPainter(pixmap)
        painter.setPen(QColor('white'))
        painter.setFont(QFont('Segoe UI', 14, QFont.Weight.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, '💬')
        painter.end()
        
        self.tray_icon = QSystemTrayIcon(QIcon(pixmap), self)
        
        tray_menu = QMenu()
        
        show_action = QAction('창 열기', self)
        show_action.triggered.connect(self.show_window)
        tray_menu.addAction(show_action)
        
        tray_menu.addSeparator()
        
        start_action = QAction('서버 시작', self)
        start_action.triggered.connect(self.start_server)
        tray_menu.addAction(start_action)
        
        stop_action = QAction('서버 중지', self)
        stop_action.triggered.connect(self.stop_server)
        tray_menu.addAction(stop_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction('종료', self)
        quit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_activated)
        self.tray_icon.show()
    
    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window()
    
    def show_window(self):
        self.show()
        self.activateWindow()
        self.raise_()
    
    def closeEvent(self, event):
        if self.minimize_to_tray_check.isChecked():
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                APP_NAME,
                '프로그램이 트레이로 최소화되었습니다.',
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
        else:
            self.quit_app()
    
    def quit_app(self):
        self.stop_server()
        self.tray_icon.hide()
        QApplication.quit()
    
    def start_server(self):
        if self.server_thread and self.server_thread.isRunning():
            return
        
        self.server_thread = ServerThread(
            port=self.port_spin.value(),
            use_https=self.https_check.isChecked()
        )
        self.server_thread.log_signal.connect(self.add_log)
        self.server_thread.stats_signal.connect(self.update_local_stats)
        self.server_thread.finished.connect(self.on_server_finished)
        self.server_thread.start()
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.port_spin.setEnabled(False)
        self.https_check.setEnabled(False)
        self.status_label.setText('🟢 서버 실행 중')
        self.status_label.setStyleSheet('font-size: 14px; color: #10B981;')
        
        self.show_toast('서버가 시작되었습니다', 'success')
        self.tray_icon.showMessage(APP_NAME, '서버가 시작되었습니다.', QSystemTrayIcon.MessageIcon.Information, 2000)
    
    def on_server_finished(self):
        """[v4.1] 서버 스레드 종료 시 UI 복구"""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.port_spin.setEnabled(True)
        self.https_check.setEnabled(True)
        self.status_label.setText('⚪ 서버 중지됨')
        self.status_label.setStyleSheet('font-size: 14px; color: #94A3B8;')
        self.add_log('서버 프로세스가 종료되었습니다.')
    
    def stop_server(self):
        """[v4.2] Graceful shutdown"""
        if self.server_thread:
            # ServerThread.stop() 내부에서 process.terminate 호출
            self.server_thread.stop()
            self.server_thread.wait(1000)
            self.server_thread = None
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.port_spin.setEnabled(True)
        self.https_check.setEnabled(True)
        self.status_label.setText('⚪ 서버 중지됨')
        self.status_label.setStyleSheet('font-size: 14px; color: #94A3B8;')
        
        self.add_log('서버가 중지되었습니다.')
        self.show_toast('서버가 중지되었습니다', 'warning')
    
    def add_log(self, message: str):
        """로그 추가"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.log_text.append(f'[{timestamp}] {message}')
    
    def show_toast(self, message: str, toast_type: str = "info", duration: int = 3000):
        """토스트 알림 표시"""
        toast = ToastWidget(self, message, toast_type, duration)
        toast.move(self.width() - toast.width() - 20, 60)
        toast.show()
    
    def update_urls(self):
        port = self.port_spin.value()
        protocol = "https" if self.https_check.isChecked() else "http"
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
        except (OSError, socket.error):
            local_ip = '127.0.0.1'
        
        self.local_url.setText(f'🖥️ 로컬 접속: {protocol}://localhost:{port}')
        self.network_url.setText(f'🌐 네트워크 접속: {protocol}://{local_ip}:{port}')
    
    def update_local_stats(self, stats):
        """[v4.16] 서버 프로세스로부터 받은 통계 저장"""
        self.local_stats = stats
        
    def update_stats_ui(self):
        """[v4.16] 저장된 통계로 UI 업데이트"""
        try:
            # 로컬 스코프의 self.local_stats 사용
            stats = self.local_stats
            
            self.stats_labels['active_connections'].setText(str(stats.get('active_connections', 0)))
            self.stats_labels['total_connections'].setText(str(stats.get('total_connections', 0)))
            self.stats_labels['total_messages'].setText(str(stats.get('total_messages', 0)))
            
            if stats.get('start_time'):
                uptime = datetime.now() - stats['start_time']
                hours, remainder = divmod(int(uptime.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                self.stats_labels['uptime'].setText(f'{hours}시간 {minutes}분 {seconds}초')
            else:
                self.stats_labels['uptime'].setText('-')
        except Exception:
            pass
    
    def toggle_windows_startup(self, state):
        key_path = r'Software\Microsoft\Windows\CurrentVersion\Run'
        app_path = os.path.abspath(sys.argv[0])
        
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            
            if state == Qt.CheckState.Checked.value:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{app_path}"')
                self.add_log('Windows 시작 프로그램에 등록되었습니다.')
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                    self.add_log('Windows 시작 프로그램에서 제거되었습니다.')
                except FileNotFoundError:
                    pass
            
            winreg.CloseKey(key)
        except Exception as e:
            self.add_log(f'시작 프로그램 설정 오류: {str(e)}')
        
        self.save_settings()
    
    def load_settings(self):
        self.port_spin.setValue(self.settings.value('port', DEFAULT_PORT, type=int))
        self.auto_start_check.setChecked(self.settings.value('auto_start_server', True, type=bool))
        self.minimize_to_tray_check.setChecked(self.settings.value('minimize_to_tray', True, type=bool))
        self.https_check.setChecked(self.settings.value('use_https', USE_HTTPS, type=bool))
        
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_READ)
            try:
                winreg.QueryValueEx(key, APP_NAME)
                self.windows_startup_check.setChecked(True)
            except FileNotFoundError:
                self.windows_startup_check.setChecked(False)
            winreg.CloseKey(key)
        except OSError:
            self.windows_startup_check.setChecked(False)
    
    def save_settings(self):
        self.settings.setValue('port', self.port_spin.value())
        self.settings.setValue('auto_start_server', self.auto_start_check.isChecked())
        self.settings.setValue('minimize_to_tray', self.minimize_to_tray_check.isChecked())
        self.settings.setValue('use_https', self.https_check.isChecked())
