# -*- coding: utf-8 -*-
"""
Runtime path helpers that resolve config-backed directories lazily.
"""

from __future__ import annotations

import os
import sys

import config


def _config_value(name: str, default: str | None = None) -> str:
    value = getattr(config, name, default)
    if isinstance(value, str) and value:
        return value
    return default or ""


def get_bundle_dir() -> str:
    configured = _config_value("BUNDLE_DIR")
    if configured:
        return configured
    if getattr(sys, "frozen", False):
        bundle_dir = getattr(sys, "_MEIPASS", None)
        if isinstance(bundle_dir, str) and bundle_dir:
            return bundle_dir
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_base_dir() -> str:
    configured = _config_value("BASE_DIR")
    if configured:
        return configured
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return get_bundle_dir()


def get_static_folder() -> str:
    return _config_value("STATIC_FOLDER", os.path.join(get_bundle_dir(), "static"))


def get_template_folder() -> str:
    return _config_value("TEMPLATE_FOLDER", os.path.join(get_bundle_dir(), "templates"))


def get_upload_folder() -> str:
    return _config_value("UPLOAD_FOLDER", os.path.join(get_base_dir(), "uploads"))


def get_upload_quarantine_folder() -> str:
    return _config_value("UPLOAD_QUARANTINE_FOLDER", os.path.join(get_upload_folder(), "quarantine"))


def get_session_dir() -> str:
    return os.path.join(get_base_dir(), "flask_session")


def get_secret_key_path() -> str:
    return os.path.join(get_base_dir(), ".secret_key")


def get_security_salt_path() -> str:
    return os.path.join(get_base_dir(), ".security_salt")


def get_control_token_path(base_dir: str | None = None) -> str:
    return os.path.join(base_dir or get_base_dir(), ".control_token")
