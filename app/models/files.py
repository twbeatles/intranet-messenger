# -*- coding: utf-8 -*-
"""
Room file storage models.
"""

from __future__ import annotations

import logging
import os

from app.models.base import get_db, safe_file_delete
from app.services.runtime_paths import get_upload_folder

logger = logging.getLogger(__name__)


def add_room_file(
    room_id: int,
    uploaded_by: int,
    file_path: str,
    file_name: str,
    file_size: int | None = None,
    file_type: str | None = None,
    message_id: int | None = None,
):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            '''
                INSERT INTO room_files (room_id, uploaded_by, file_path, file_name, file_size, file_type, message_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (room_id, uploaded_by, file_path, file_name, file_size, file_type, message_id),
        )
        conn.commit()
        return cursor.lastrowid
    except Exception as exc:
        logger.error(f"Add room file error: {exc}")
        return None


def get_room_files(room_id: int, file_type: str | None = None):
    conn = get_db()
    cursor = conn.cursor()
    try:
        if file_type:
            cursor.execute(
                '''
                    SELECT rf.*, u.nickname AS uploader_name
                    FROM room_files rf
                    JOIN users u ON rf.uploaded_by = u.id
                    WHERE rf.room_id = ? AND rf.file_type = ?
                    ORDER BY rf.uploaded_at DESC
                ''',
                (room_id, file_type),
            )
        else:
            cursor.execute(
                '''
                    SELECT rf.*, u.nickname AS uploader_name
                    FROM room_files rf
                    JOIN users u ON rf.uploaded_by = u.id
                    WHERE rf.room_id = ?
                    ORDER BY rf.uploaded_at DESC
                ''',
                (room_id,),
            )
        return [dict(file_row) for file_row in cursor.fetchall()]
    except Exception as exc:
        logger.error(f"Get room files error: {exc}")
        return []


def delete_room_file(
    file_id: int,
    user_id: int,
    room_id: int | None = None,
    is_admin: bool = False,
):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT uploaded_by, file_path, room_id, message_id FROM room_files WHERE id = ?', (file_id,))
        file_row = cursor.fetchone()
        if not file_row:
            return False, None
        if room_id is not None and file_row['room_id'] != room_id:
            logger.warning(f"Room_id mismatch in file delete: expected {room_id}, got {file_row['room_id']}")
            return False, None
        if file_row['uploaded_by'] != user_id and not is_admin:
            return False, None

        file_path = file_row['file_path']
        message_id = file_row['message_id']

        cursor.execute('DELETE FROM room_files WHERE id = ?', (file_id,))
        pin_removed = False
        if message_id:
            cursor.execute('DELETE FROM pinned_messages WHERE message_id = ?', (message_id,))
            pin_removed = cursor.rowcount > 0
            cursor.execute(
                "UPDATE messages SET content = '[삭제된 메시지]', encrypted = 0, file_path = NULL, file_name = NULL WHERE id = ?",
                (message_id,),
            )
        conn.commit()

        full_path = os.path.join(get_upload_folder(), file_path)
        if safe_file_delete(full_path):
            logger.debug(f"File deleted from disk: {file_path}")

        return True, {
            'file_path': file_path,
            'room_id': file_row['room_id'],
            'message_id': message_id,
            'pin_removed': pin_removed,
        }
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        logger.error(f"Delete room file error: {exc}")
        return False, None
