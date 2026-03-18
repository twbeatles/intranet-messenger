# -*- coding: utf-8 -*-
"""
Settings and Windows startup helpers for the server window.
"""

from __future__ import annotations

import sys

from PyQt6.QtCore import Qt

try:
    import winreg
except ImportError:  # pragma: no cover - non-Windows fallback
    winreg = None


RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def set_windows_startup(app_name: str, state: int) -> str:
    if winreg is None:
        return ""
    app_path = sys.argv[0]
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE)
    try:
        if state == Qt.CheckState.Checked.value:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, f'"{app_path}"')
            return "Windows 시작 프로그램에 등록되었습니다."
        try:
            winreg.DeleteValue(key, app_name)
            return "Windows 시작 프로그램에서 제거되었습니다."
        except FileNotFoundError:
            return ""
    finally:
        winreg.CloseKey(key)


def is_windows_startup_enabled(app_name: str) -> bool:
    if winreg is None:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, app_name)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except OSError:
        return False


def load_ui_settings(settings, *, default_port: int, default_https: bool) -> dict:
    return {
        "port": settings.value("port", default_port, type=int),
        "auto_start_server": settings.value("auto_start_server", True, type=bool),
        "minimize_to_tray": settings.value("minimize_to_tray", True, type=bool),
        "use_https": settings.value("use_https", default_https, type=bool),
    }


def save_ui_settings(settings, *, port: int, auto_start_server: bool, minimize_to_tray: bool, use_https: bool) -> None:
    settings.setValue("port", port)
    settings.setValue("auto_start_server", auto_start_server)
    settings.setValue("minimize_to_tray", minimize_to_tray)
    settings.setValue("use_https", use_https)
