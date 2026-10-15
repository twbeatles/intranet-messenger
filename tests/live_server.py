# -*- coding: utf-8 -*-
"""Isolated live-server launcher for browser E2E (test-only, never production).

Usage: python tests/live_server.py <port> <base_dir>
Serves 127.0.0.1 only. All runtime state (DB, uploads, sessions, secrets)
lives under <base_dir>; the repository checkout is only read for code.
Prints READY <port> on stdout once the socket binds.
"""

from __future__ import annotations

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)


def main() -> None:
    port = int(sys.argv[1])
    base_dir = sys.argv[2]
    upload_dir = os.path.join(base_dir, "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    import config

    config.BASE_DIR = base_dir
    config.DATABASE_PATH = os.path.join(base_dir, "messenger.db")
    config.UPLOAD_FOLDER = upload_dir
    config.UPLOAD_QUARANTINE_FOLDER = os.path.join(upload_dir, "quarantine")
    os.makedirs(config.UPLOAD_QUARANTINE_FOLDER, exist_ok=True)

    import importlib

    import app.models.base as base_module

    importlib.reload(base_module)
    base_module._db_initialized = False

    from app import create_app

    flask_app, socketio = create_app()
    with flask_app.app_context():
        base_module.init_db()

    print(f"READY {port}", flush=True)
    socketio.run(flask_app, host="127.0.0.1", port=port, debug=False,
                 use_reloader=False, log_output=False)


if __name__ == "__main__":
    main()
