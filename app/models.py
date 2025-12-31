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
    
    # 공지사항 고정 메시지 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pinned_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER NOT NULL,
            message_id INTEGER,
            content TEXT,
            pinned_by INTEGER NOT NULL,
            pinned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (room_id) REFERENCES rooms(id),
            FOREIGN KEY (message_id) REFERENCES messages(id),
            FOREIGN KEY (pinned_by) REFERENCES users(id)
        )
    ''')
    
    # 투표 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS polls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER NOT NULL,
            created_by INTEGER NOT NULL,
            question TEXT NOT NULL,
            multiple_choice INTEGER DEFAULT 0,
            anonymous INTEGER DEFAULT 0,
            closed INTEGER DEFAULT 0,
            ends_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (room_id) REFERENCES rooms(id),
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    ''')
    
    # 투표 옵션 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS poll_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            poll_id INTEGER NOT NULL,
            option_text TEXT NOT NULL,
            FOREIGN KEY (poll_id) REFERENCES polls(id) ON DELETE CASCADE
        )
    ''')
    
    # 투표 참여 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS poll_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            poll_id INTEGER NOT NULL,
            option_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(poll_id, option_id, user_id),
            FOREIGN KEY (poll_id) REFERENCES polls(id) ON DELETE CASCADE,
            FOREIGN KEY (option_id) REFERENCES poll_options(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # 파일 저장소 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS room_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER NOT NULL,
            message_id INTEGER,
            file_path TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_size INTEGER,
            file_type TEXT,
            uploaded_by INTEGER NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (room_id) REFERENCES rooms(id),
            FOREIGN KEY (message_id) REFERENCES messages(id),
            FOREIGN KEY (uploaded_by) REFERENCES users(id)
        )
    ''')
    
    # 메시지 리액션 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS message_reactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            emoji TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(message_id, user_id, emoji),
            FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # room_members 테이블에 role 컬럼 추가 (마이그레이션)
    try:
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='room_members'")
        schema = cursor.fetchone()
        if schema and 'role' not in schema[0]:
            cursor.execute('ALTER TABLE room_members ADD COLUMN role TEXT DEFAULT "member"')
    except Exception as e:
        logger.debug(f"Role column migration: {e}")
    
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


# ============================================================================
# 공지사항 고정 메시지 관리
# ============================================================================
def pin_message(room_id: int, pinned_by: int, message_id: int = None, content: str = None):
    """메시지 또는 공지 고정"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO pinned_messages (room_id, message_id, content, pinned_by)
            VALUES (?, ?, ?, ?)
        ''', (room_id, message_id, content, pinned_by))
        conn.commit()
        pin_id = cursor.lastrowid
        return pin_id
    except Exception as e:
        logger.error(f"Pin message error: {e}")
        return None
    finally:
        conn.close()


def unpin_message(pin_id: int, user_id: int, room_id: int = None):
    """공지 해제"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # 관리자 또는 고정한 사람만 해제 가능
        cursor.execute('DELETE FROM pinned_messages WHERE id = ?', (pin_id,))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Unpin message error: {e}")
        return False
    finally:
        conn.close()


def get_pinned_messages(room_id: int):
    """대화방의 고정된 메시지 목록"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT pm.*, u.nickname as pinned_by_name,
                   m.content as message_content, m.sender_id, mu.nickname as message_sender
            FROM pinned_messages pm
            JOIN users u ON pm.pinned_by = u.id
            LEFT JOIN messages m ON pm.message_id = m.id
            LEFT JOIN users mu ON m.sender_id = mu.id
            WHERE pm.room_id = ?
            ORDER BY pm.pinned_at DESC
        ''', (room_id,))
        return [dict(p) for p in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Get pinned messages error: {e}")
        return []
    finally:
        conn.close()


# ============================================================================
# 투표 관리
# ============================================================================
def create_poll(room_id: int, created_by: int, question: str, options: list,
                multiple_choice: bool = False, anonymous: bool = False, ends_at: str = None):
    """투표 생성"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO polls (room_id, created_by, question, multiple_choice, anonymous, ends_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (room_id, created_by, question, 1 if multiple_choice else 0, 1 if anonymous else 0, ends_at))
        poll_id = cursor.lastrowid
        
        for option_text in options:
            cursor.execute('''
                INSERT INTO poll_options (poll_id, option_text) VALUES (?, ?)
            ''', (poll_id, option_text))
        
        conn.commit()
        return poll_id
    except Exception as e:
        logger.error(f"Create poll error: {e}")
        return None
    finally:
        conn.close()


def get_poll(poll_id: int):
    """투표 정보 조회"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT p.*, u.nickname as creator_name
            FROM polls p
            JOIN users u ON p.created_by = u.id
            WHERE p.id = ?
        ''', (poll_id,))
        poll = cursor.fetchone()
        if not poll:
            return None
        
        poll_dict = dict(poll)
        
        # 옵션과 투표 수 조회
        cursor.execute('''
            SELECT po.id, po.option_text, COUNT(pv.id) as vote_count
            FROM poll_options po
            LEFT JOIN poll_votes pv ON po.id = pv.option_id
            WHERE po.poll_id = ?
            GROUP BY po.id
        ''', (poll_id,))
        poll_dict['options'] = [dict(o) for o in cursor.fetchall()]
        
        # 총 투표자 수
        cursor.execute('''
            SELECT COUNT(DISTINCT user_id) FROM poll_votes WHERE poll_id = ?
        ''', (poll_id,))
        poll_dict['total_voters'] = cursor.fetchone()[0]
        
        return poll_dict
    except Exception as e:
        logger.error(f"Get poll error: {e}")
        return None
    finally:
        conn.close()


def get_room_polls(room_id: int):
    """대화방의 투표 목록"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT p.*, u.nickname as creator_name
            FROM polls p
            JOIN users u ON p.created_by = u.id
            WHERE p.room_id = ?
            ORDER BY p.created_at DESC
        ''', (room_id,))
        polls = []
        for poll in cursor.fetchall():
            poll_dict = dict(poll)
            cursor.execute('''
                SELECT po.id, po.option_text, COUNT(pv.id) as vote_count
                FROM poll_options po
                LEFT JOIN poll_votes pv ON po.id = pv.option_id
                WHERE po.poll_id = ?
                GROUP BY po.id
            ''', (poll_dict['id'],))
            poll_dict['options'] = [dict(o) for o in cursor.fetchall()]
            polls.append(poll_dict)
        return polls
    except Exception as e:
        logger.error(f"Get room polls error: {e}")
        return []
    finally:
        conn.close()


def vote_poll(poll_id: int, option_id: int, user_id: int):
    """투표 참여"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # 중복 투표 체크 (단일 선택인 경우)
        cursor.execute('SELECT multiple_choice, closed FROM polls WHERE id = ?', (poll_id,))
        poll = cursor.fetchone()
        if not poll or poll['closed']:
            return False, "마감된 투표입니다."
        
        if not poll['multiple_choice']:
            # 기존 투표 삭제 후 새 투표
            cursor.execute('DELETE FROM poll_votes WHERE poll_id = ? AND user_id = ?', (poll_id, user_id))
        
        cursor.execute('''
            INSERT OR IGNORE INTO poll_votes (poll_id, option_id, user_id) VALUES (?, ?, ?)
        ''', (poll_id, option_id, user_id))
        conn.commit()
        return True, ""
    except Exception as e:
        logger.error(f"Vote poll error: {e}")
        return False, str(e)
    finally:
        conn.close()


def get_user_votes(poll_id: int, user_id: int):
    """사용자의 투표 내역"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT option_id FROM poll_votes WHERE poll_id = ? AND user_id = ?', (poll_id, user_id))
        return [r['option_id'] for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Get user votes error: {e}")
        return []
    finally:
        conn.close()


def close_poll(poll_id: int, user_id: int):
    """투표 마감"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT created_by FROM polls WHERE id = ?', (poll_id,))
        poll = cursor.fetchone()
        if not poll or poll['created_by'] != user_id:
            return False
        cursor.execute('UPDATE polls SET closed = 1 WHERE id = ?', (poll_id,))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Close poll error: {e}")
        return False
    finally:
        conn.close()


# ============================================================================
# 파일 저장소 관리
# ============================================================================
def add_room_file(room_id: int, uploaded_by: int, file_path: str, file_name: str, 
                  file_size: int = None, file_type: str = None, message_id: int = None):
    """파일 저장소에 파일 추가"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO room_files (room_id, message_id, file_path, file_name, file_size, file_type, uploaded_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (room_id, message_id, file_path, file_name, file_size, file_type, uploaded_by))
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        logger.error(f"Add room file error: {e}")
        return None
    finally:
        conn.close()


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
                WHERE rf.room_id = ? AND rf.file_type LIKE ?
                ORDER BY rf.uploaded_at DESC
            ''', (room_id, f'{file_type}%'))
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
    finally:
        conn.close()


def delete_room_file(file_id: int, user_id: int):
    """파일 삭제"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT uploaded_by, file_path FROM room_files WHERE id = ?', (file_id,))
        file = cursor.fetchone()
        if not file or file['uploaded_by'] != user_id:
            return False, None
        cursor.execute('DELETE FROM room_files WHERE id = ?', (file_id,))
        conn.commit()
        return True, file['file_path']
    except Exception as e:
        logger.error(f"Delete room file error: {e}")
        return False, None
    finally:
        conn.close()


# ============================================================================
# 메시지 리액션 관리
# ============================================================================
def add_reaction(message_id: int, user_id: int, emoji: str):
    """리액션 추가"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR IGNORE INTO message_reactions (message_id, user_id, emoji)
            VALUES (?, ?, ?)
        ''', (message_id, user_id, emoji))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Add reaction error: {e}")
        return False
    finally:
        conn.close()


def remove_reaction(message_id: int, user_id: int, emoji: str):
    """리액션 제거"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            DELETE FROM message_reactions WHERE message_id = ? AND user_id = ? AND emoji = ?
        ''', (message_id, user_id, emoji))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Remove reaction error: {e}")
        return False
    finally:
        conn.close()


def toggle_reaction(message_id: int, user_id: int, emoji: str):
    """리액션 토글 (있으면 제거, 없으면 추가)"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT id FROM message_reactions WHERE message_id = ? AND user_id = ? AND emoji = ?
        ''', (message_id, user_id, emoji))
        exists = cursor.fetchone()
        
        if exists:
            cursor.execute('DELETE FROM message_reactions WHERE id = ?', (exists['id'],))
            action = 'removed'
        else:
            cursor.execute('''
                INSERT INTO message_reactions (message_id, user_id, emoji) VALUES (?, ?, ?)
            ''', (message_id, user_id, emoji))
            action = 'added'
        
        conn.commit()
        return True, action
    except Exception as e:
        logger.error(f"Toggle reaction error: {e}")
        return False, None
    finally:
        conn.close()


def get_message_reactions(message_id: int):
    """메시지의 리액션 목록"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT emoji, COUNT(*) as count, GROUP_CONCAT(user_id) as user_ids
            FROM message_reactions
            WHERE message_id = ?
            GROUP BY emoji
        ''', (message_id,))
        reactions = []
        for r in cursor.fetchall():
            reactions.append({
                'emoji': r['emoji'],
                'count': r['count'],
                'user_ids': [int(uid) for uid in r['user_ids'].split(',')]
            })
        return reactions
    except Exception as e:
        logger.error(f"Get message reactions error: {e}")
        return []
    finally:
        conn.close()


def get_messages_reactions(message_ids: list):
    """여러 메시지의 리액션 일괄 조회"""
    if not message_ids:
        return {}
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        placeholders = ','.join('?' * len(message_ids))
        cursor.execute(f'''
            SELECT message_id, emoji, COUNT(*) as count, GROUP_CONCAT(user_id) as user_ids
            FROM message_reactions
            WHERE message_id IN ({placeholders})
            GROUP BY message_id, emoji
        ''', message_ids)
        
        result = {}
        for r in cursor.fetchall():
            mid = r['message_id']
            if mid not in result:
                result[mid] = []
            result[mid].append({
                'emoji': r['emoji'],
                'count': r['count'],
                'user_ids': [int(uid) for uid in r['user_ids'].split(',')]
            })
        return result
    except Exception as e:
        logger.error(f"Get messages reactions error: {e}")
        return {}
    finally:
        conn.close()


# ============================================================================
# 대화방 관리자 권한
# ============================================================================
def set_room_admin(room_id: int, user_id: int, is_admin: bool = True):
    """관리자 권한 설정"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        role = 'admin' if is_admin else 'member'
        cursor.execute('UPDATE room_members SET role = ? WHERE room_id = ? AND user_id = ?', 
                      (role, room_id, user_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Set room admin error: {e}")
        return False
    finally:
        conn.close()


def is_room_admin(room_id: int, user_id: int):
    """관리자 여부 확인"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # 방 생성자는 자동으로 관리자
        cursor.execute('SELECT created_by FROM rooms WHERE id = ?', (room_id,))
        room = cursor.fetchone()
        if room and room['created_by'] == user_id:
            return True
        
        cursor.execute('SELECT role FROM room_members WHERE room_id = ? AND user_id = ?', (room_id, user_id))
        member = cursor.fetchone()
        return member and member['role'] == 'admin'
    except Exception as e:
        logger.error(f"Check room admin error: {e}")
        return False
    finally:
        conn.close()


def get_room_admins(room_id: int):
    """대화방 관리자 목록"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT u.id, u.nickname, u.profile_image, rm.role
            FROM users u
            JOIN room_members rm ON u.id = rm.user_id
            WHERE rm.room_id = ? AND (rm.role = 'admin' OR u.id = (SELECT created_by FROM rooms WHERE id = ?))
        ''', (room_id, room_id))
        return [dict(a) for a in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Get room admins error: {e}")
        return []
    finally:
        conn.close()


# ============================================================================
# 고급 검색
# ============================================================================
def advanced_search(user_id: int, query: str = None, room_id: int = None, 
                    sender_id: int = None, date_from: str = None, date_to: str = None,
                    file_only: bool = False, limit: int = 50):
    """고급 메시지 검색"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        conditions = ['rm.user_id = ?']
        params = [user_id]
        
        if query:
            conditions.append('m.content LIKE ?')
            params.append(f'%{query}%')
        if room_id:
            conditions.append('m.room_id = ?')
            params.append(room_id)
        if sender_id:
            conditions.append('m.sender_id = ?')
            params.append(sender_id)
        if date_from:
            conditions.append('m.created_at >= ?')
            params.append(date_from)
        if date_to:
            conditions.append('m.created_at <= ?')
            params.append(date_to)
        if file_only:
            conditions.append("m.message_type IN ('file', 'image')")
        
        where_clause = ' AND '.join(conditions)
        params.append(limit)
        
        cursor.execute(f'''
            SELECT m.*, r.name as room_name, u.nickname as sender_name
            FROM messages m
            JOIN rooms r ON m.room_id = r.id
            JOIN room_members rm ON r.id = rm.room_id
            JOIN users u ON m.sender_id = u.id
            WHERE {where_clause}
            ORDER BY m.created_at DESC
            LIMIT ?
        ''', params)
        
        return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Advanced search error: {e}")
        return []
    finally:
        conn.close()


# ============================================================================
# [v4.1] 계정 보안 관리
# ============================================================================
def change_password(user_id, current_password, new_password):
    """비밀번호 변경"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 현재 비밀번호 확인
    cursor.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return False, "사용자를 찾을 수 없습니다."
        
    current_hash = hash_password(current_password)
    if user['password_hash'] != current_hash:
        conn.close()
        return False, "현재 비밀번호가 일치하지 않습니다."
        
    # 새 비밀번호 설정
    new_hash = hash_password(new_password)
    cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
    conn.commit()
    conn.close()
    return True, None


def delete_user(user_id, password):
    """회원 탈퇴 (계정 삭제 및 데이터 정리)"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 비밀번호 확인
    cursor.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return False, "사용자를 찾을 수 없습니다."
        
    pw_hash = hash_password(password)
    if user['password_hash'] != pw_hash:
        conn.close()
        return False, "비밀번호가 일치하지 않습니다."
        
    try:
        # 1. 대화방 멤버에서 제거
        cursor.execute("DELETE FROM room_members WHERE user_id = ?", (user_id,))
        
        # 2. 사용자 삭제
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        
        conn.commit()
        return True, None
    except Exception as e:
        conn.rollback()
        logger.error(f"회원 탈퇴 오류: {e}")
        return False, "탈퇴 처리 중 오류가 발생했습니다."
    finally:
        conn.close()
