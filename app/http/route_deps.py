# -*- coding: utf-8 -*-
"""
Compatibility dependency lookups for code paths that tests monkeypatch via
``app.routes``.
"""

from __future__ import annotations

import app.routes as routes_shim


def get_routes_shim():
    return routes_shim
