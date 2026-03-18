# -*- coding: utf-8 -*-
"""
Compatibility facade for the server window entrypoint.
"""

from __future__ import annotations

import os

# HiDPI flags must be set before PyQt imports.
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

from gui.services.process_control import ServerThread, kill_process_on_port
from gui.window.main_window import ServerWindow

__all__ = ["ServerWindow", "ServerThread", "kill_process_on_port"]
