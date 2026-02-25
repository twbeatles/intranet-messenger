# -*- coding: utf-8 -*-
"""
Admin audit log model helpers.
"""

from __future__ import annotations

import json
import logging
from app.models.base import get_db

logger = logging.getLogger(__name__)


def log_admin_action(
    room_id: int,
    actor_user_id: int,
    action: str,
    target_user_id: int | None = None,
    metadata: dict | None = None,
) -> bool:
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO admin_audit_logs (room_id, actor_user_id, target_user_id, action, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                room_id,
                actor_user_id,
                target_user_id,
                action,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Admin audit insert error: {e}")
        return False


def get_admin_audit_logs(room_id: int, limit: int = 200, offset: int = 0):
    conn = get_db()
    cursor = conn.cursor()
    try:
        limit = min(max(int(limit), 1), 1000)
        offset = max(int(offset), 0)
        cursor.execute(
            """
            SELECT aal.id, aal.room_id, aal.actor_user_id, aal.target_user_id, aal.action,
                   aal.metadata_json, aal.created_at,
                   au.nickname AS actor_nickname,
                   tu.nickname AS target_nickname
            FROM admin_audit_logs aal
            LEFT JOIN users au ON aal.actor_user_id = au.id
            LEFT JOIN users tu ON aal.target_user_id = tu.id
            WHERE aal.room_id = ?
            ORDER BY aal.created_at DESC, aal.id DESC
            LIMIT ? OFFSET ?
            """,
            (room_id, limit, offset),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        for row in rows:
            try:
                row["metadata"] = json.loads(row.get("metadata_json") or "{}")
            except Exception:
                row["metadata"] = {}
            row.pop("metadata_json", None)
        return rows
    except Exception as e:
        logger.error(f"Admin audit fetch error: {e}")
        return []

