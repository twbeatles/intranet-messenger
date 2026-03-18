# -*- coding: utf-8 -*-
"""
QSS styles used by the main server window.
"""


def build_main_window_stylesheet() -> str:
    return """
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
        """

