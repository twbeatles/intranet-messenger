# -*- coding: utf-8 -*-
"""
데이터베이스 모델 및 CRUD 함수
"""

import sqlite3
import logging
import threading
from contextlib import contextmanager

# config 임포트 (PyInstaller 호환)
try:
    from config import DATABASE_PATH, PASSWORD_SALT
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import DATABASE_PATH, PASSWORD_SALT

from app.utils import E2ECrypto, hash_password

logger = logging.getLogger(__name__)

# ============================================================================
# 데이터베이스 연결 관리 (안전한 버전)
# ============================================================================
_db_lock = threading.Lock()
_db_initialized = False


def _create_connection():
    """새 데이터베이스 연결 생성"""
    try:
        conn = sqlite3.connect(DATABASE_PATH, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # 성능 최적화 PRAGMA 설정
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        conn.execute('PRAGMA cache_size=5000')
        conn.execute('PRAGMA temp_store=MEMORY')
        return conn
    except Exception as e:
        logger.error(f"DB connection error: {e}")
        raise


def get_db():
    """데이터베이스 연결 - 매 호출마다 새 연결 (안전성 우선)"""
    return _create_connection()


@contextmanager
def get_db_context():
    """데이터베이스 연결 컨텍스트 매니저 (자동 정리)"""
    conn = None
    try:
        conn = get_db()
        yield conn
        conn.commit()
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception as rollback_err:
                logger.warning(f"Rollback failed: {rollback_err}")
        logger.error(f"Database error: {e}")
        raise
    finally:
        if conn:
            try:
                conn.close()
            except Exception as close_err:
                logger.warning(f"Connection close failed: {close_err}")


def init_db():
    """데이터베이스 초기화"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 사용자 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nickname TEXT,
            profile_image TEXT,
            status TEXT DEFAULT 'offline',
            public_key TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 대화방 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            type TEXT CHECK(type IN ('direct', 'group')),
            created_by INTEGER,
            encryption_key TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    ''')
    
    # 대화방 참여자 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS room_members (
            room_id INTEGER,
            user_id INTEGER,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_read_message_id INTEGER DEFAULT 0,
            pinned INTEGER DEFAULT 0,
            muted INTEGER DEFAULT 0,
            PRIMARY KEY (room_id, user_id),
            FOREIGN KEY (room_id) REFERENCES rooms(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # 메시지 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            content TEXT,
            encrypted INTEGER DEFAULT 1,
            message_type TEXT DEFAULT 'text',
            file_path TEXT,
            file_name TEXT,
            reply_to INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (room_id) REFERENCES rooms(id),
            FOREIGN KEY (sender_id) REFERENCES users(id),
            FOREIGN KEY (reply_to) REFERENCES messages(id)
        )
    ''')
    
    # 접속 로그 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS access_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            ip_address TEXT,
            user_agent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    
    conn.commit()
    conn.close()
    logger.info("데이터베이스 초기화 완료")


# ============================================================================
# 사용자 관리
# ============================================================================
def create_user(username: str, password: str, nickname: str | None = None) -> int | None:
    """사용자 생성
    
    Args:
        username: 사용자 아이디
        password: 비밀번호 (평문)
        nickname: 닉네임 (없으면 username 사용)
    
    Returns:
        생성된 사용자 ID 또는 None (이미 존재하는 경우)
    """
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
    finally:
        conn.close()


def authenticate_user(username: str, password: str) -> dict | None:
    """사용자 인증
    
    Args:
        username: 사용자 아이디
        password: 비밀번호 (평문)
    
    Returns:
        사용자 정보 dict 또는 None (인증 실패)
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'SELECT id, username, nickname, profile_image FROM users WHERE username = ? AND password_hash = ?',
            (username, hash_password(password))
        )
        user = cursor.fetchone()
        return dict(user) if user else None
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        return None
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> dict | None:
    """ID로 사용자 조회
    
    Args:
        user_id: 사용자 ID
    
    Returns:
        사용자 정보 dict 또는 None
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT id, username, nickname, profile_image, status FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        return dict(user) if user else None
    except Exception as e:
        logger.error(f"Get user by id error: {e}")
        return None
    finally:
        conn.close()


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
    finally:
        conn.close()


def update_user_status(user_id, status):
    """사용자 상태 업데이트"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE users SET status = ? WHERE id = ?', (status, user_id))
        conn.commit()
    except Exception as e:
        logger.error(f"Update user status error: {e}")
    finally:
        conn.close()


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
            # status_message 컬럼이 없을 수 있으므로 안전하게 처리
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
            return True
        return False
    except Exception as e:
        logger.error(f"Update user profile error: {e}")
        return False
    finally:
        conn.close()


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
    finally:
        conn.close()



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
    finally:
        conn.close()


# ============================================================================
# 대화방 관리
# ============================================================================
def create_room(name, room_type, created_by, member_ids):
    """대화방 생성"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 1:1 대화방인 경우 기존 대화방 확인
    if room_type == 'direct' and len(member_ids) == 2:
        cursor.execute('''
            SELECT r.id FROM rooms r
            JOIN room_members rm1 ON r.id = rm1.room_id
            JOIN room_members rm2 ON r.id = rm2.room_id
            WHERE r.type = 'direct' AND rm1.user_id = ? AND rm2.user_id = ?
        ''', (member_ids[0], member_ids[1]))
        existing = cursor.fetchone()
        if existing:
            conn.close()
            return existing[0]
    
    # 대화방별 암호화 키 생성
    encryption_key = E2ECrypto.generate_room_key()
    
    cursor.execute(
        'INSERT INTO rooms (name, type, created_by, encryption_key) VALUES (?, ?, ?, ?)',
        (name, room_type, created_by, encryption_key)
    )
    room_id = cursor.lastrowid
    
    for user_id in member_ids:
        cursor.execute(
            'INSERT INTO room_members (room_id, user_id) VALUES (?, ?)',
            (room_id, user_id)
        )
    
    conn.commit()
    conn.close()
    return room_id


def get_room_key(room_id):
    """대화방 암호화 키 조회"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT encryption_key FROM rooms WHERE id = ?', (room_id,))
        result = cursor.fetchone()
        return result['encryption_key'] if result else None
    except Exception as e:
        logger.error(f"Get room key error: {e}")
        return None
    finally:
        conn.close()


def get_user_rooms(user_id):
    """사용자의 대화방 목록"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT r.*, 
                   (SELECT COUNT(*) FROM room_members WHERE room_id = r.id) as member_count,
                   (SELECT m.content FROM messages m WHERE m.room_id = r.id ORDER BY m.id DESC LIMIT 1) as last_message,
                   (SELECT m.created_at FROM messages m WHERE m.room_id = r.id ORDER BY m.id DESC LIMIT 1) as last_message_time,
                   (SELECT COUNT(*) FROM messages m WHERE m.room_id = r.id AND m.id > rm.last_read_message_id) as unread_count,
                   rm.pinned, rm.muted
            FROM rooms r
            JOIN room_members rm ON r.id = rm.room_id
            WHERE rm.user_id = ?
            ORDER BY rm.pinned DESC, last_message_time DESC NULLS LAST
        ''', (user_id,))
        rooms = cursor.fetchall()
        
        result = []
        for room in rooms:
            room_dict = dict(room)
            if room_dict['type'] == 'direct':
                cursor.execute('''
                    SELECT u.id, u.nickname, u.profile_image, u.status
                    FROM users u
                    JOIN room_members rm ON u.id = rm.user_id
                    WHERE rm.room_id = ? AND u.id != ?
                ''', (room_dict['id'], user_id))
                partner = cursor.fetchone()
                if partner:
                    room_dict['partner'] = dict(partner)
                    room_dict['name'] = partner['nickname']
            else:
                cursor.execute('''
                    SELECT u.id, u.nickname, u.profile_image
                    FROM users u
                    JOIN room_members rm ON u.id = rm.user_id
                    WHERE rm.room_id = ?
                ''', (room_dict['id'],))
                room_dict['members'] = [dict(m) for m in cursor.fetchall()]
            result.append(room_dict)
        
        return result
    except Exception as e:
        logger.error(f"Get user rooms error: {e}")
        return []
    finally:
        conn.close()



def get_room_members(room_id):
    """대화방 멤버 조회"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT u.id, u.nickname, u.profile_image, u.status, rm.last_read_message_id, rm.pinned, rm.muted
            FROM users u
            JOIN room_members rm ON u.id = rm.user_id
            WHERE rm.room_id = ?
        ''', (room_id,))
        members = cursor.fetchall()
        return [dict(m) for m in members]
    except Exception as e:
        logger.error(f"Get room members error: {e}")
        return []
    finally:
        conn.close()


def is_room_member(room_id, user_id):
    """대화방 멤버 확인"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'SELECT 1 FROM room_members WHERE room_id = ? AND user_id = ?',
            (room_id, user_id)
        )
        return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Check room membership error: {e}")
        return False
    finally:
        conn.close()


def add_room_member(room_id, user_id):
    """대화방 멤버 추가"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO room_members (room_id, user_id) VALUES (?, ?)', (room_id, user_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def leave_room_db(room_id, user_id):
    """대화방 나가기"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM room_members WHERE room_id = ? AND user_id = ?', (room_id, user_id))
        conn.commit()
    except Exception as e:
        logger.error(f"Leave room error: {e}")
    finally:
        conn.close()


def update_room_name(room_id, new_name):
    """대화방 이름 변경"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE rooms SET name = ? WHERE id = ?', (new_name, room_id))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Update room name error: {e}")
        return False
    finally:
        conn.close()


def get_room_by_id(room_id):
    """대화방 정보 조회"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM rooms WHERE id = ?', (room_id,))
        room = cursor.fetchone()
        return dict(room) if room else None
    except Exception as e:
        logger.error(f"Get room error: {e}")
        return None
    finally:
        conn.close()


def pin_room(user_id, room_id, pinned):
    """대화방 상단 고정"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE room_members SET pinned = ? WHERE user_id = ? AND room_id = ?', 
                      (1 if pinned else 0, user_id, room_id))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Pin room error: {e}")
        return False
    finally:
        conn.close()


def mute_room(user_id, room_id, muted):
    """대화방 알림 끄기"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE room_members SET muted = ? WHERE user_id = ? AND room_id = ?', 
                      (1 if muted else 0, user_id, room_id))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Mute room error: {e}")
        return False
    finally:
        conn.close()


# ============================================================================
# 메시지 관리
# ============================================================================
# 서버 통계 (전역)
server_stats = {
    'start_time': None,
    'total_messages': 0,
    'total_connections': 0,
    'active_connections': 0
}


def create_message(room_id, sender_id, content, message_type='text', file_path=None, file_name=None, reply_to=None, encrypted=True):
    """메시지 생성"""
    from datetime import datetime, timezone, timedelta
    
    # 한국 시간 (KST, GMT+9)
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst).strftime('%Y-%m-%d %H:%M:%S')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO messages (room_id, sender_id, content, encrypted, message_type, file_path, file_name, reply_to, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (room_id, sender_id, content, 1 if encrypted else 0, message_type, file_path, file_name, reply_to, now_kst))
    message_id = cursor.lastrowid
    conn.commit()
    
    cursor.execute('''
        SELECT m.*, u.nickname as sender_name, u.profile_image as sender_image
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        WHERE m.id = ?
    ''', (message_id,))
    message = cursor.fetchone()
    conn.close()
    
    server_stats['total_messages'] += 1
    
    return dict(message)


def get_room_messages(room_id, limit=50, before_id=None):
    """대화방 메시지 조회"""
    conn = get_db()
    cursor = conn.cursor()
    
    if before_id:
        cursor.execute('''
            SELECT m.*, u.nickname as sender_name, u.profile_image as sender_image,
                   rm.content as reply_content, ru.nickname as reply_sender
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            LEFT JOIN messages rm ON m.reply_to = rm.id
            LEFT JOIN users ru ON rm.sender_id = ru.id
            WHERE m.room_id = ? AND m.id < ?
            ORDER BY m.id DESC
            LIMIT ?
        ''', (room_id, before_id, limit))
    else:
        cursor.execute('''
            SELECT m.*, u.nickname as sender_name, u.profile_image as sender_image,
                   rm.content as reply_content, ru.nickname as reply_sender
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            LEFT JOIN messages rm ON m.reply_to = rm.id
            LEFT JOIN users ru ON rm.sender_id = ru.id
            WHERE m.room_id = ?
            ORDER BY m.id DESC
            LIMIT ?
        ''', (room_id, limit))
    
    messages = cursor.fetchall()
    conn.close()
    return [dict(m) for m in reversed(messages)]


def update_last_read(room_id, user_id, message_id):
    """마지막 읽은 메시지 업데이트"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE room_members SET last_read_message_id = ?
        WHERE room_id = ? AND user_id = ? AND last_read_message_id < ?
    ''', (message_id, room_id, user_id, message_id))
    conn.commit()
    conn.close()


def get_unread_count(room_id, message_id):
    """메시지를 읽지 않은 사람 수"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COUNT(*) FROM room_members
        WHERE room_id = ? AND last_read_message_id < ?
    ''', (room_id, message_id))
    count = cursor.fetchone()[0]
    conn.close()
    return count


def delete_message(message_id, user_id):
    """메시지 삭제"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT sender_id, room_id FROM messages WHERE id = ?', (message_id,))
    msg = cursor.fetchone()
    if not msg or msg['sender_id'] != user_id:
        conn.close()
        return False, "삭제 권한이 없습니다."
    
    cursor.execute("UPDATE messages SET content = '[삭제된 메시지]', encrypted = 0 WHERE id = ?", (message_id,))
    conn.commit()
    conn.close()
    return True, msg['room_id']


def edit_message(message_id, user_id, new_content):
    """메시지 수정"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT sender_id, room_id FROM messages WHERE id = ?', (message_id,))
    msg = cursor.fetchone()
    if not msg or msg['sender_id'] != user_id:
        conn.close()
        return False, "수정 권한이 없습니다.", None
    
    cursor.execute("UPDATE messages SET content = ? WHERE id = ?", (new_content, message_id))
    conn.commit()
    conn.close()
    return True, "", msg['room_id']


def search_messages(user_id, query):
    """메시지 검색"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT m.*, r.name as room_name, u.nickname as sender_name
        FROM messages m
        JOIN rooms r ON m.room_id = r.id
        JOIN room_members rm ON r.id = rm.room_id
        JOIN users u ON m.sender_id = u.id
        WHERE rm.user_id = ? AND m.encrypted = 0 AND m.content LIKE ?
        ORDER BY m.created_at DESC
        LIMIT 50
    ''', (user_id, f'%{query}%'))
    results = cursor.fetchall()
    conn.close()
    return [dict(r) for r in results]

    results = cursor.fetchall()
    conn.close()
    return [dict(r) for r in results]

