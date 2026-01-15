# -*- coding: utf-8 -*-
"""
파일 저장소 관리 모듈
"""

import logging
import os

from app.models.base import get_db, safe_file_delete

try:
    from config import UPLOAD_FOLDER
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from config import UPLOAD_FOLDER

logger = logging.getLogger(__name__)


def add_room_file(room_id: int, uploaded_by: int, file_path: str, file_name: str, 
                  file_size: int = None, file_type: str = None, message_id: int = None):
    """파일 저장소에 파일 추가"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO room_files (room_id, uploaded_by, file_path, file_name, file_size, file_type, message_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (room_id, uploaded_by, file_path, file_name, file_size, file_type, message_id))
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        logger.error(f"Add room file error: {e}")
        return None


def get_room_files(room_id: int, file_type: str = None):
    """대화방의 파일 목록"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if file_type:
            cursor.execute('''
                SELECT rf.*, u.nickname as uploader_name
                FROM room_files rf
                JOIN users u ON rf.uploaded_by = u.id
                WHERE rf.room_id = ? AND rf.file_type = ?
                ORDER BY rf.uploaded_at DESC
            ''', (room_id, file_type))
        else:
            cursor.execute('''
                SELECT rf.*, u.nickname as uploader_name
                FROM room_files rf
                JOIN users u ON rf.uploaded_by = u.id
                WHERE rf.room_id = ?
                ORDER BY rf.uploaded_at DESC
            ''', (room_id,))
        return [dict(f) for f in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Get room files error: {e}")
        return []


def delete_room_file(file_id: int, user_id: int, room_id: int = None, is_admin: bool = False):
    """파일 삭제"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT uploaded_by, file_path, room_id FROM room_files WHERE id = ?', (file_id,))
        file = cursor.fetchone()
        if not file:
            return False, None
        
        # room_id 검증
        if room_id is not None and file['room_id'] != room_id:
            logger.warning(f"Room_id mismatch in file delete: expected {room_id}, got {file['room_id']}")
            return False, None
        
        # 권한 확인
        if file['uploaded_by'] != user_id and not is_admin:
            return False, None
        
        file_path = file['file_path']
        cursor.execute('DELETE FROM room_files WHERE id = ?', (file_id,))
        conn.commit()
        
        # 실제 파일 삭제
        full_path = os.path.join(UPLOAD_FOLDER, file_path)
        if safe_file_delete(full_path):
            logger.debug(f"File deleted from disk: {file_path}")
        
        return True, file_path
    except Exception as e:
        logger.error(f"Delete room file error: {e}")
        return False, None
