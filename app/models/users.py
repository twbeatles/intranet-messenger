# -*- coding: utf-8 -*-
"""
사용자 관리 모듈
"""

import sqlite3
import logging
import threading
import time

from app.models.base import get_db, close_thread_db
from app.utils import hash_password, verify_password

logger = logging.getLogger(__name__)

# 사용자 정보 메모리 캐시
_user_cache = {}
_user_cache_lock = threading.Lock()
USER_CACHE_TTL = 60
USER_CACHE_MAX_SIZE = 500


def create_user(username: str, password: str, nickname: str | None = None) -> int | None:
    """사용자 생성"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO users (username, password_hash, nickname) VALUES (?, ?, ?)',
            (username, hash_password(password), nickname or username)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        logger.warning(f"Username already exists: {username}")
        return None
    except Exception as e:
        logger.error(f"Create user error: {e}")
        return None


def authenticate_user(username: str, password: str) -> dict | None:
    """사용자 인증"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'SELECT id, username, nickname, profile_image, password_hash FROM users WHERE username = ?',
            (username,)
        )
        user = cursor.fetchone()
        
        if user and verify_password(password, user['password_hash']):
            # SHA-256 해시 -> bcrypt 마이그레이션
            if not user['password_hash'].startswith('$2'):
                try:
                    new_hash = hash_password(password)
                    if new_hash.startswith('$2'):
                        cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (new_hash, user['id']))
                        conn.commit()
                        logger.info(f"User {username} password migrated to bcrypt")
                except Exception as e:
                    logger.error(f"Password migration failed for {username}: {e}")
            
            user_dict = dict(user)
            del user_dict['password_hash']
            return user_dict
            
        return None
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        return None


def get_user_by_id(user_id: int) -> dict | None:
    """ID로 사용자 조회"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT id, username, nickname, profile_image, status FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        return dict(user) if user else None
    except Exception as e:
        logger.error(f"Get user by id error: {e}")
        return None


def get_user_by_id_cached(user_id: int) -> dict | None:
    """캐시된 사용자 조회"""
    with _user_cache_lock:
        cached = _user_cache.get(user_id)
        if cached and (time.time() - cached['_cached_at']) < USER_CACHE_TTL:
            return cached['data']
    
    user = get_user_by_id(user_id)
    if user:
        with _user_cache_lock:
            _user_cache[user_id] = {'data': user, '_cached_at': time.time()}
            if len(_user_cache) > USER_CACHE_MAX_SIZE:
                oldest = min(_user_cache.items(), key=lambda x: x[1]['_cached_at'])
                del _user_cache[oldest[0]]
    
    return user


def invalidate_user_cache(user_id: int = None):
    """사용자 캐시 무효화"""
    with _user_cache_lock:
        if user_id is None:
            _user_cache.clear()
        elif user_id in _user_cache:
            del _user_cache[user_id]


def get_all_users():
    """모든 사용자 조회"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT id, username, nickname, profile_image, status FROM users')
        users = cursor.fetchall()
        return [dict(u) for u in users]
    except Exception as e:
        logger.error(f"Get all users error: {e}")
        return []


def update_user_status(user_id, status):
    """사용자 상태 업데이트"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE users SET status = ? WHERE id = ?', (status, user_id))
        conn.commit()
        invalidate_user_cache(user_id)
    except Exception as e:
        logger.error(f"Update user status error: {e}")


def update_user_profile(user_id, nickname=None, profile_image=None, status_message=None):
    """사용자 프로필 업데이트"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        updates = []
        values = []
        
        if nickname is not None:
            updates.append('nickname = ?')
            values.append(nickname)
        if profile_image is not None:
            updates.append('profile_image = ?')
            values.append(profile_image)
        if status_message is not None:
            try:
                cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")
                schema = cursor.fetchone()[0]
                if 'status_message' not in schema:
                    cursor.execute('ALTER TABLE users ADD COLUMN status_message TEXT')
                    conn.commit()
            except Exception as schema_err:
                logger.debug(f"Schema check/update for status_message: {schema_err}")
            updates.append('status_message = ?')
            values.append(status_message)
        
        if updates:
            values.append(user_id)
            cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", values)
            conn.commit()
            invalidate_user_cache(user_id)
            return True
        return False
    except Exception as e:
        logger.error(f"Update user profile error: {e}")
        return False


def get_online_users():
    """온라인 사용자 목록"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, username, nickname, profile_image FROM users WHERE status = 'online'")
        users = cursor.fetchall()
        return [dict(u) for u in users]
    except Exception as e:
        logger.error(f"Get online users error: {e}")
        return []


def log_access(user_id, action, ip_address, user_agent):
    """접속 로그 기록"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        user_agent = user_agent[:500] if user_agent else ''
        cursor.execute(
            'INSERT INTO access_logs (user_id, action, ip_address, user_agent) VALUES (?, ?, ?, ?)',
            (user_id, action, ip_address, user_agent)
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Log access error: {e}")


def change_password(user_id, current_password, new_password):
    """비밀번호 변경 - 세션 토큰도 갱신하여 다른 세션 무효화"""
    import secrets
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            return False, "사용자를 찾을 수 없습니다.", None
            
        if not verify_password(current_password, user['password_hash']):
            return False, "현재 비밀번호가 일치하지 않습니다.", None
            
        new_hash = hash_password(new_password)
        # [v4.21] 새 세션 토큰 생성 (다른 세션 무효화용)
        new_session_token = secrets.token_hex(32)
        
        # session_token 컬럼 확인 및 추가
        try:
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")
            schema = cursor.fetchone()[0]
            if 'session_token' not in schema:
                cursor.execute('ALTER TABLE users ADD COLUMN session_token TEXT')
                conn.commit()
        except Exception as schema_err:
            logger.debug(f"Schema check for session_token: {schema_err}")
        
        cursor.execute(
            "UPDATE users SET password_hash = ?, session_token = ? WHERE id = ?", 
            (new_hash, new_session_token, user_id)
        )
        conn.commit()
        invalidate_user_cache(user_id)
        return True, None, new_session_token
    except Exception as e:
        logger.error(f"Change password error: {e}")
        return False, f"오류 발생: {e}", None


def get_user_session_token(user_id):
    """사용자의 현재 세션 토큰 조회"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT session_token FROM users WHERE id = ?", (user_id,))
        result = cursor.fetchone()
        return result['session_token'] if result and result['session_token'] else None
    except Exception as e:
        logger.debug(f"Get session token error (column may not exist): {e}")
        return None


def delete_user(user_id, password):
    """회원 탈퇴"""
    import os
    try:
        from config import UPLOAD_FOLDER
    except ImportError:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from config import UPLOAD_FOLDER
    
    from app.models.base import safe_file_delete
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT password_hash, profile_image FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            return False, "사용자를 찾을 수 없습니다."
            
        if not verify_password(password, user['password_hash']):
            return False, "비밀번호가 일치하지 않습니다."
        
        # 프로필 이미지 삭제
        if user['profile_image']:
            try:
                profile_path = os.path.join(UPLOAD_FOLDER, user['profile_image'])
                safe_file_delete(profile_path)
            except Exception as e:
                logger.warning(f"Profile image deletion failed: {e}")
        
        # 외래키 참조 정리
        cursor.execute("UPDATE rooms SET created_by = NULL WHERE created_by = ?", (user_id,))

        # polls.created_by는 NOT NULL이므로 재할당하거나 삭제
        cursor.execute("SELECT id, room_id FROM polls WHERE created_by = ?", (user_id,))
        owned_polls = cursor.fetchall()
        for poll in owned_polls:
            cursor.execute("""
                SELECT rm.user_id
                FROM room_members rm
                WHERE rm.room_id = ? AND rm.user_id != ?
                ORDER BY CASE WHEN COALESCE(rm.role, 'member') = 'admin' THEN 0 ELSE 1 END, rm.user_id ASC
                LIMIT 1
            """, (poll['room_id'], user_id))
            replacement = cursor.fetchone()
            if replacement:
                cursor.execute("UPDATE polls SET created_by = ? WHERE id = ?", (replacement['user_id'], poll['id']))
            else:
                cursor.execute("DELETE FROM polls WHERE id = ?", (poll['id'],))
        
        # 업로드 파일 삭제
        cursor.execute("SELECT file_path FROM room_files WHERE uploaded_by = ?", (user_id,))
        files_to_delete = cursor.fetchall()
        for f in files_to_delete:
            try:
                full_path = os.path.join(UPLOAD_FOLDER, f['file_path'])
                safe_file_delete(full_path)
            except Exception as e:
                logger.warning(f"File deletion failed during user delete: {e}")
        cursor.execute("DELETE FROM room_files WHERE uploaded_by = ?", (user_id,))
        
        # 메시지 익명화
        cursor.execute("""
            UPDATE messages SET content = '[탈퇴한 사용자의 메시지]', encrypted = 0 
            WHERE sender_id = ?
        """, (user_id,))
        
        cursor.execute("UPDATE access_logs SET user_id = NULL WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM poll_votes WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM message_reactions WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM pinned_messages WHERE pinned_by = ?", (user_id,))
        cursor.execute("DELETE FROM room_members WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        
        conn.commit()
        invalidate_user_cache(user_id)
        logger.info(f"User {user_id} deleted with all related data cleaned up")
        return True, None
    except Exception as e:
        conn.rollback()
        logger.error(f"회원 탈퇴 오류: {e}")
        return False, "탈퇴 처리 중 오류가 발생했습니다."
