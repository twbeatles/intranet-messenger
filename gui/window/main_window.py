# -*- coding: utf-8 -*-
"""
Main PyQt server window assembly.
"""

from __future__ import annotations

import os
import socket
import sys
from datetime import datetime

from PyQt6.QtCore import QSettings, QTimer, Qt
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QSpinBox,
    QSystemTrayIcon,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from config import APP_NAME, DEFAULT_PORT, SSL_CERT_PATH, SSL_DIR, SSL_KEY_PATH, USE_HTTPS, VERSION
from gui.services.process_control import ServerThread
from gui.services.settings_service import (
    is_windows_startup_enabled,
    load_ui_settings,
    save_ui_settings,
    set_windows_startup,
)
from gui.styles.qss import build_main_window_stylesheet
from gui.widgets.toast import ToastWidget


class ServerWindow(QMainWindow):
    """Main server management window."""

    def __init__(self):
        super().__init__()
        self.server_thread: ServerThread | None = None
        self.settings = QSettings("MessengerServer", "Settings")
        self.local_stats: dict[str, object] = {}
        self.init_ui()
        self.create_tray_icon()
        self.load_settings()

        if self.settings.value("auto_start_server", True, type=bool):
            QTimer.singleShot(1000, self.safe_start_server)

    def safe_start_server(self):
        try:
            self.start_server()
        except Exception as exc:
            self.add_log(f"서버 자동 시작 실패: {exc}")

    def init_ui(self):
        self.setWindowTitle(f"{APP_NAME} v{VERSION}")
        self.setMinimumSize(800, 700)
        self.resize(850, 750)
        self.setStyleSheet(build_main_window_stylesheet())

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel(f"🔒 {APP_NAME}")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #F8FAFC;")
        header.addWidget(title)

        self.status_label = QLabel("⚪ 서버 중지됨")
        self.status_label.setStyleSheet("font-size: 14px; color: #94A3B8;")
        header.addStretch()
        header.addWidget(self.status_label)
        layout.addLayout(header)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        control_tab = QWidget()
        control_layout = QVBoxLayout(control_tab)
        control_layout.setSpacing(16)

        server_group = QGroupBox("서버 설정")
        server_layout = QHBoxLayout(server_group)

        server_layout.addWidget(QLabel("포트:"))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1000, 65535)
        self.port_spin.setValue(DEFAULT_PORT)
        server_layout.addWidget(self.port_spin)
        server_layout.addSpacing(10)

        self.https_check = QCheckBox("HTTPS 사용")
        self.https_check.setChecked(USE_HTTPS)
        server_layout.addWidget(self.https_check)
        server_layout.addSpacing(20)

        self.start_btn = QPushButton("▶ 서버 시작")
        self.start_btn.clicked.connect(self.start_server)
        server_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("■ 서버 중지")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_server)
        server_layout.addWidget(self.stop_btn)

        server_layout.addStretch()
        control_layout.addWidget(server_group)

        ssl_group = QGroupBox("SSL 인증서")
        ssl_layout = QVBoxLayout(ssl_group)

        self.ssl_status = QLabel("인증서 상태: 확인 중...")
        self.ssl_status.setStyleSheet("color: #F8FAFC;")
        ssl_layout.addWidget(self.ssl_status)

        ssl_btn_layout = QHBoxLayout()
        self.gen_cert_btn = QPushButton("🔑 인증서 생성")
        self.gen_cert_btn.setObjectName("genCertBtn")
        self.gen_cert_btn.clicked.connect(self.generate_certificate)
        ssl_btn_layout.addWidget(self.gen_cert_btn)
        ssl_btn_layout.addStretch()
        ssl_layout.addLayout(ssl_btn_layout)

        control_layout.addWidget(ssl_group)
        self.update_ssl_status()

        options_group = QGroupBox("옵션")
        options_layout = QVBoxLayout(options_group)
        options_layout.setSpacing(12)

        self.auto_start_check = QCheckBox("프로그램 시작 시 서버 자동 시작")
        self.auto_start_check.setChecked(True)
        self.auto_start_check.stateChanged.connect(self.save_settings)
        options_layout.addWidget(self.auto_start_check)

        self.windows_startup_check = QCheckBox("Windows 시작 시 자동 실행")
        self.windows_startup_check.stateChanged.connect(self.toggle_windows_startup)
        options_layout.addWidget(self.windows_startup_check)

        self.minimize_to_tray_check = QCheckBox("닫기 버튼 클릭 시 트레이로 최소화")
        self.minimize_to_tray_check.setChecked(True)
        self.minimize_to_tray_check.stateChanged.connect(self.save_settings)
        options_layout.addWidget(self.minimize_to_tray_check)

        control_layout.addWidget(options_group)

        info_group = QGroupBox("접속 정보")
        info_layout = QVBoxLayout(info_group)
        info_layout.setSpacing(10)

        hostname = socket.gethostname()
        try:
            local_ip = socket.gethostbyname(hostname)
        except (OSError, socket.error):
            local_ip = "127.0.0.1"

        protocol = "https" if USE_HTTPS else "http"
        self.local_url = QLabel(f"🖥️ 로컬 접속: {protocol}://localhost:{self.port_spin.value()}")
        self.local_url.setStyleSheet("font-size: 14px; color: #F8FAFC;")
        info_layout.addWidget(self.local_url)

        self.network_url = QLabel(f"🌐 네트워크 접속: {protocol}://{local_ip}:{self.port_spin.value()}")
        self.network_url.setStyleSheet("font-size: 14px; color: #F8FAFC;")
        info_layout.addWidget(self.network_url)

        self.encryption_info = QLabel("🔒 종단간 암호화(E2E) 적용: 서버 관리자도 메시지 내용 확인 불가")
        self.encryption_info.setStyleSheet("font-size: 12px; color: #10B981;")
        info_layout.addWidget(self.encryption_info)

        control_layout.addWidget(info_group)
        control_layout.addStretch()
        tabs.addTab(control_tab, "제어")

        stats_tab = QWidget()
        stats_layout = QVBoxLayout(stats_tab)

        stats_group = QGroupBox("실시간 통계")
        stats_inner = QVBoxLayout(stats_group)

        self.stats_labels: dict[str, QLabel] = {}
        stats_items = [
            ("active_connections", "현재 접속자"),
            ("total_connections", "총 접속 횟수"),
            ("total_messages", "총 메시지 수"),
            ("uptime", "서버 가동 시간"),
        ]

        for key, label_text in stats_items:
            row = QHBoxLayout()
            label = QLabel(f"{label_text}:")
            value = QLabel("0")
            value.setStyleSheet("font-size: 18px; font-weight: bold; color: #10B981;")
            row.addWidget(label)
            row.addStretch()
            row.addWidget(value)
            stats_inner.addLayout(row)
            self.stats_labels[key] = value

        stats_layout.addWidget(stats_group)
        stats_layout.addStretch()
        tabs.addTab(stats_tab, "통계")

        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)

        clear_log_btn = QPushButton("로그 지우기")
        clear_log_btn.clicked.connect(lambda: self.log_text.clear())
        log_layout.addWidget(clear_log_btn)
        tabs.addTab(log_tab, "로그")

        self.port_spin.valueChanged.connect(self.update_urls)
        self.https_check.stateChanged.connect(self.update_urls)

        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_stats_ui)
        self.stats_timer.start(1000)

    def update_ssl_status(self):
        if os.path.exists(SSL_CERT_PATH) and os.path.exists(SSL_KEY_PATH):
            self.ssl_status.setText("✅ 인증서 존재함")
            self.ssl_status.setStyleSheet("color: #22C55E;")
            return
        self.ssl_status.setText("❌ 인증서 없음 (HTTPS 사용 시 생성 필요)")
        self.ssl_status.setStyleSheet("color: #EF4444;")

    def generate_certificate(self):
        try:
            os.makedirs(SSL_DIR, exist_ok=True)
            from certs.generate_cert import generate_certificate as gen_cert

            if gen_cert(SSL_CERT_PATH, SSL_KEY_PATH):
                self.add_log("SSL 인증서 생성 완료")
                self.update_ssl_status()
            else:
                self.add_log("SSL 인증서 생성 실패")
        except ImportError:
            self.add_log("cryptography 라이브러리가 필요합니다: pip install cryptography")
        except Exception as exc:
            self.add_log(f"인증서 생성 오류: {exc}")

    def create_tray_icon(self):
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor("#10B981"))
        painter = QPainter(pixmap)
        painter.setPen(QColor("white"))
        painter.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "💬")
        painter.end()

        self.tray_icon = QSystemTrayIcon(QIcon(pixmap), self)

        tray_menu = QMenu()

        show_action = QAction("창 열기", self)
        show_action.triggered.connect(self.show_window)
        tray_menu.addAction(show_action)
        tray_menu.addSeparator()

        start_action = QAction("서버 시작", self)
        start_action.triggered.connect(self.start_server)
        tray_menu.addAction(start_action)

        stop_action = QAction("서버 중지", self)
        stop_action.triggered.connect(self.stop_server)
        tray_menu.addAction(stop_action)
        tray_menu.addSeparator()

        quit_action = QAction("종료", self)
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
                "프로그램이 트레이로 최소화되었습니다.",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
            return
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
            use_https=self.https_check.isChecked(),
        )
        self.server_thread.log_signal.connect(self.add_log)
        self.server_thread.stats_signal.connect(self.update_local_stats)
        self.server_thread.finished.connect(self.on_server_finished)
        self.server_thread.start()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.port_spin.setEnabled(False)
        self.https_check.setEnabled(False)
        self.status_label.setText("🟢 서버 실행 중")
        self.status_label.setStyleSheet("font-size: 14px; color: #10B981;")

        self.show_toast("서버가 시작되었습니다", "success")
        self.tray_icon.showMessage(
            APP_NAME,
            "서버가 시작되었습니다.",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def on_server_finished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.port_spin.setEnabled(True)
        self.https_check.setEnabled(True)
        self.status_label.setText("⚪ 서버 중지됨")
        self.status_label.setStyleSheet("font-size: 14px; color: #94A3B8;")
        self.add_log("서버 프로세스가 종료되었습니다.")

    def stop_server(self):
        if self.server_thread:
            self.server_thread.stop()
            self.server_thread.wait(1000)
            self.server_thread = None

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.port_spin.setEnabled(True)
        self.https_check.setEnabled(True)
        self.status_label.setText("⚪ 서버 중지됨")
        self.status_label.setStyleSheet("font-size: 14px; color: #94A3B8;")

        self.add_log("서버가 중지되었습니다.")
        self.show_toast("서버가 중지되었습니다", "warning")

    def add_log(self, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")

    def show_toast(self, message: str, toast_type: str = "info", duration: int = 3000):
        toast = ToastWidget(self, message, toast_type, duration)
        toast.move(self.width() - toast.width() - 20, 60)
        toast.show()

    def update_urls(self):
        port = self.port_spin.value()
        protocol = "https" if self.https_check.isChecked() else "http"
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
        except (OSError, socket.error):
            local_ip = "127.0.0.1"

        self.local_url.setText(f"🖥️ 로컬 접속: {protocol}://localhost:{port}")
        self.network_url.setText(f"🌐 네트워크 접속: {protocol}://{local_ip}:{port}")

    def update_local_stats(self, stats):
        self.local_stats = stats

    def update_stats_ui(self):
        try:
            stats = self.local_stats
            self.stats_labels["active_connections"].setText(str(stats.get("active_connections", 0)))
            self.stats_labels["total_connections"].setText(str(stats.get("total_connections", 0)))
            self.stats_labels["total_messages"].setText(str(stats.get("total_messages", 0)))

            start_time = stats.get("start_time")
            if isinstance(start_time, datetime):
                uptime = datetime.now() - start_time
                hours, remainder = divmod(int(uptime.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                self.stats_labels["uptime"].setText(f"{hours}시간 {minutes}분 {seconds}초")
            else:
                self.stats_labels["uptime"].setText("-")
        except Exception:
            pass

    def toggle_windows_startup(self, state):
        try:
            message = set_windows_startup(APP_NAME, state)
            if message:
                self.add_log(message)
        except Exception as exc:
            self.add_log(f"시작 프로그램 설정 오류: {exc}")
        self.save_settings()

    def load_settings(self):
        loaded = load_ui_settings(self.settings, default_port=DEFAULT_PORT, default_https=USE_HTTPS)
        self.port_spin.setValue(loaded["port"])
        self.auto_start_check.setChecked(loaded["auto_start_server"])
        self.minimize_to_tray_check.setChecked(loaded["minimize_to_tray"])
        self.https_check.setChecked(loaded["use_https"])
        self.windows_startup_check.setChecked(is_windows_startup_enabled(APP_NAME))

    def save_settings(self):
        save_ui_settings(
            self.settings,
            port=self.port_spin.value(),
            auto_start_server=self.auto_start_check.isChecked(),
            minimize_to_tray=self.minimize_to_tray_check.isChecked(),
            use_https=self.https_check.isChecked(),
        )
