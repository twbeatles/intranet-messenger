# -*- coding: utf-8 -*-
"""GUI entrypoint smoke: ServerWindow/ServerThread exports resolve.

PySide6 wheels link against system GL/EGL libraries (e.g. ``libEGL.so.1``)
that minimal images (``ubuntu-latest`` CI runners, slim containers) do not
ship. The ``unit`` CI job installs those Qt runtime libs (see
``.github/workflows/quality.yml``), but minimal local environments may still
lack them — skip with a clear reason instead of failing the whole run.
"""
from __future__ import annotations

import pytest


def test_gui_entrypoint_exports():
    try:
        from gui.server_window import ServerThread, ServerWindow, kill_process_on_port
    except ImportError as exc:
        pytest.skip(f"Qt native libs unavailable in this environment: {exc}")

    assert ServerWindow is not None
    assert ServerThread is not None
    assert callable(kill_process_on_port)
