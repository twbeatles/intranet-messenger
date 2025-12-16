# -*- coding: utf-8 -*-
"""
PyQt6 GUI - 서버 관리 창
"""

import os
import sys
import socket
import winreg
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSystemTrayIcon, QMenu, QTextEdit,
    QSpinBox, QCheckBox, QGroupBox, QTabWidget
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QSettings
from PyQt6.QtGui import QIcon, QAction, QFont, QColor, QPixmap, QPainter

# 부모 디렉토리에서 import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import APP_NAME, VERSION, DEFAULT_PORT, USE_HTTPS, SSL_CERT_PATH, SSL_KEY_PATH, SSL_DIR


class ServerThread(QThread):
    """Flask 서버를 별도 스레드에서 실행"""
    log_signal = pyqtSignal(str)
    
    def __init__(self, host='0.0.0.0', port=5000, use_https=True):
        super().__init__()
        self.host = host
        self.port = port
        self.use_https = use_https
        self.running = True
    
    def run(self):
        try:
            from app import create_app
            from app.models import server_stats
            
            app, socketio = create_app()
            server_stats['start_time'] = datetime.now()
            
            protocol = "https" if self.use_https else "http"
            self.log_signal.emit(f"서버 시작 중: {protocol}://{self.host}:{self.port}")
            
            # SSL 인증서 확인
            ssl_context = None
            if self.use_https:
                if os.path.exists(SSL_CERT_PATH) and os.path.exists(SSL_KEY_PATH):
                    ssl_context = (SSL_CERT_PATH, SSL_KEY_PATH)
                    self.log_signal.emit("SSL 인증서 로드됨")
                else:
                    self.log_signal.emit("SSL 인증서 없음. HTTP 모드로 실행")
            
            if ssl_context:
                socketio.run(
                    app,
                    host=self.host,
                    port=self.port,
                    debug=False,
                    use_reloader=False,
                    log_output=False,
                    allow_unsafe_werkzeug=True,
                    ssl_context=ssl_context
                )
            else:
                socketio.run(
                    app,
                    host=self.host,
                    port=self.port,
                    debug=False,
                    use_reloader=False,
                    log_output=False,
                    allow_unsafe_werkzeug=True
                )
        except OSError as e:
            if "Address already in use" in str(e) or "10048" in str(e):
                self.log_signal.emit(f"오류: 포트 {self.port}이 이미 사용 중입니다.")
            else:
                self.log_signal.emit(f"서버 오류: {str(e)}")
        except Exception as e:
            self.log_signal.emit(f"서버 오류: {str(e)}")
            import traceback
            self.log_signal.emit(traceback.format_exc())
    
    def stop(self):
        self.running = False


class ServerWindow(QMainWindow):
    """메인 서버 관리 윈도우"""
    
    def __init__(self):
        super().__init__()
        self.server_thread = None
        self.settings = QSettings('MessengerServer', 'Settings')
        self.init_ui()
        self.create_tray_icon()
        self.load_settings()
        
        if self.settings.value('auto_start_server', True, type=bool):
            QTimer.singleShot(500, self.start_server)
    
    def init_ui(self):
        """UI 초기화"""
        self.setWindowTitle(f'{APP_NAME} v{VERSION}')
        self.setMinimumSize(700, 500)
        self.setStyleSheet('''
            QMainWindow { background-color: #0F172A; }
            QWidget { color: #F8FAFC; font-family: 'Segoe UI', sans-serif; }
            QGroupBox { border: 1px solid #334155; border-radius: 8px; margin-top: 12px; padding: 16px; background-color: #1E293B; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 8px; color: #10B981; font-weight: bold; }
            QPushButton { background-color: #10B981; color: white; border: none; padding: 10px 20px; border-radius: 6px; font-weight: bold; }
            QPushButton:hover { background-color: #059669; }
            QPushButton:disabled { background-color: #475569; color: #94A3B8; }
            QPushButton#stopBtn { background-color: #EF4444; }
            QPushButton#stopBtn:hover { background-color: #DC2626; }
            QPushButton#genCertBtn { background-color: #F59E0B; }
            QPushButton#genCertBtn:hover { background-color: #D97706; }
            QLineEdit, QSpinBox { background-color: #1E293B; border: 1px solid #334155; border-radius: 4px; padding: 8px; color: #F8FAFC; }
            QLineEdit:focus, QSpinBox:focus { border-color: #10B981; }
            QTextEdit { background-color: #0F172A; border: 1px solid #334155; border-radius: 4px; color: #94A3B8; font-family: Consolas, monospace; }
            QCheckBox { color: #F8FAFC; }
            QCheckBox::indicator { width: 18px; height: 18px; }
            QCheckBox::indicator:checked { background-color: #10B981; border-radius: 3px; }
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
        
        # 통계 업데이트 타이머
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_stats)
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
        
        # 데이터베이스 초기화
        from app.models import init_db
        init_db()
        
        self.server_thread = ServerThread(
            port=self.port_spin.value(),
            use_https=self.https_check.isChecked()
        )
        self.server_thread.log_signal.connect(self.add_log)
        self.server_thread.start()
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.port_spin.setEnabled(False)
        self.https_check.setEnabled(False)
        self.status_label.setText('🟢 서버 실행 중')
        self.status_label.setStyleSheet('font-size: 14px; color: #10B981;')
        
        self.add_log('서버가 시작되었습니다.')
        self.tray_icon.showMessage(APP_NAME, '서버가 시작되었습니다.', QSystemTrayIcon.MessageIcon.Information, 2000)
    
    def stop_server(self):
        if self.server_thread:
            self.server_thread.terminate()
            self.server_thread.wait(1000)
            self.server_thread = None
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.port_spin.setEnabled(True)
        self.https_check.setEnabled(True)
        self.status_label.setText('⚪ 서버 중지됨')
        self.status_label.setStyleSheet('font-size: 14px; color: #94A3B8;')
        
        self.add_log('서버가 중지되었습니다.')
    
    def add_log(self, message):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.log_text.append(f'[{timestamp}] {message}')
    
    def update_urls(self):
        port = self.port_spin.value()
        protocol = "https" if self.https_check.isChecked() else "http"
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
        except (OSError, socket.error):
            local_ip = '127.0.0.1'
        
        self.local_url.setText(f'🖥️ 로컬 접속: {protocol}://localhost:{port}')
        self.network_url.setText(f'🌐 네트워크 접속: {protocol}://{local_ip}:{port}')
    
    def update_stats(self):
        try:
            from app.models import server_stats
            
            self.stats_labels['active_connections'].setText(str(server_stats.get('active_connections', 0)))
            self.stats_labels['total_connections'].setText(str(server_stats.get('total_connections', 0)))
            self.stats_labels['total_messages'].setText(str(server_stats.get('total_messages', 0)))
            
            if server_stats.get('start_time'):
                uptime = datetime.now() - server_stats['start_time']
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
