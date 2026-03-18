# -*- coding: utf-8 -*-
"""
Database initialization and background worker startup.
"""

from __future__ import annotations

import os
import time

from app.models import cleanup_empty_rooms, cleanup_old_access_logs, cleanup_retention_data, close_expired_polls, init_db


def initialize_runtime(app, socketio, logger):
    init_db()

    def _maintenance_worker():
        interval = max(30, int(app.config.get("MAINTENANCE_INTERVAL_SECONDS", 300)))
        retention_days = int(app.config.get("RETENTION_DAYS", 0) or 0)
        logger.info(f"Maintenance worker started (interval={interval}s, retention_days={retention_days})")
        while True:
            try:
                close_expired_polls()
                cleanup_old_access_logs()
                cleanup_empty_rooms()
                if retention_days > 0:
                    cleanup_retention_data(retention_days)
            except Exception as exc:
                logger.warning(f"Maintenance worker error: {exc}")
            time.sleep(interval)

    is_testing_runtime = bool(app.config.get("TESTING")) or ("PYTEST_CURRENT_TEST" in os.environ)
    if is_testing_runtime:
        logger.info("Testing runtime detected; skipping background maintenance/upload scan workers")
        return

    socketio.start_background_task(_maintenance_worker)
    try:
        from app.upload_scan import init_upload_scan_worker

        init_upload_scan_worker(app)
    except Exception as exc:
        logger.warning(f"Upload scan worker init failed: {exc}")

