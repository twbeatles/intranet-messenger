# -*- coding: utf-8 -*-
"""
데이터베이스 모델 및 CRUD 함수
"""

import sqlite3
import logging
import threading
import time
from contextlib import contextmanager

# config 임포트 (PyInstaller 호환)
try:
    from config import DATABASE_PATH, PASSWORD_SALT, UPLOAD_FOLDER
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import DATABASE_PATH, PASSWORD_SALT, UPLOAD_FOLDER

from app.utils import E2ECrypto, hash_password, verify_password

logger = logging.getLogger(__name__)

# ============================================================================
# 데이터베이스 연결 관리 (스레드 로컬 풀링 버전)
# [v4.4] 성능 최적화: 스레드별 연결 재사용
# ============================================================================
_db_lock = threading.Lock()
_db_initialized = False
_db_local = threading.local()  # [v4.4] 스레드 로컬 저장소

# [v4.19] 사용자 정보 메모리 캐시 (LRU 스타일)
_user_cache = {}
_user_cache_lock = threading.Lock()
USER_CACHE_TTL = 60  # 60초
USER_CACHE_MAX_SIZE = 500  # 최대 500명


def _create_connection():
    """새 데이터베이스 연결 생성 (재시도 로직 포함)"""
    max_retries = 3
    retry_delay = 0.1
    
    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect(DATABASE_PATH, timeout=30, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            
            # 성능 최적화 설정
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            conn.execute('PRAGMA cache_size=-64000') # 64MB cache
            conn.execute('PRAGMA temp_store=MEMORY')
            conn.execute('PRAGMA mmap_size=268435456') # 256MB mmap
            conn.execute('PRAGMA foreign_keys=ON')
            
            return conn
        except sqlite3.OperationalError as e:
            if attempt == max_retries - 1:
                logger.error(f"DB Connection failed after {max_retries} retries: {e}")
                raise
            time.sleep(retry_delay)
            retry_delay *= 2


def get_db():
    """데이터베이스 연결 - 스레드별 연결 재사용 (성능 최적화)"""
    # [v4.4] 스레드 로컬 연결 풀링
    if not hasattr(_db_local, 'connection') or _db_local.connection is None:
        _db_local.connection = _create_connection()
    else:
        # 연결이 유효한지 확인
        try:
            _db_local.connection.execute('SELECT 1')
        except (sqlite3.ProgrammingError, sqlite3.OperationalError):
            # 연결이 끊어졌거나 에러가 발생하면 재연결 시도
            try:
                if hasattr(_db_local.connection, 'close'):
                    _db_local.connection.close()
            except Exception:
                pass
            _db_local.connection = _create_connection()
            
    return _db_local.connection


def close_thread_db():
    """현재 스레드의 데이터베이스 연결 종료 (정리용)"""
    if hasattr(_db_local, 'connection') and _db_local.connection:
        try:
            _db_local.connection.close()
        except Exception:
            pass
        _db_local.connection = None


@contextmanager
def get_db_context():
    """데이터베이스 연결 컨텍스트 매니저 (자동 롤백, 커밋 지원)"""
    conn = get_db()
    try:
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
    # [v4.5] 스레드 로컬 연결은 닫지 않음 (재사용 풀링)


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
    
    # [v4.16] Auto-migration: Check and add missing columns
    required_columns = {
        'room_members': {
            'role': 'TEXT DEFAULT "member"',
            'pinned': 'INTEGER DEFAULT 0',
            'muted': 'INTEGER DEFAULT 0',
            'last_read_message_id': 'INTEGER DEFAULT 0'
        },
        'messages': {
            'reply_to': 'INTEGER'
        }
    }

    try:
        for table, cols in required_columns.items():
            cursor.execute(f"PRAGMA table_info({table})")
            existing_cols = [row[1] for row in cursor.fetchall()]  # Name is usually at index 1
            
            for col_name, col_def in cols.items():
                if col_name not in existing_cols:
                    logger.info(f"Migrating: Adding column '{col_name}' to table '{table}'")
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
    
    # [v4.1] 성능 최적화를 위한 인덱스 추가
    try:
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_room_id ON messages(room_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_room_members_user_id ON room_members(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_room_members_room_id ON room_members(room_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_message_reactions_message_id ON message_reactions(message_id)')
        # [v4.19] 복합 인덱스 추가 (성능 최적화)
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_room_id_desc ON messages(room_id, id DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_room_members_room_user ON room_members(room_id, user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_poll_votes_poll_user ON poll_votes(poll_id, user_id)')
        logger.debug("Database indexes created/verified")
    except Exception as e:
        logger.debug(f"Index creation: {e}")
    
    conn.commit()
    close_thread_db()  # [v4.12] 스레드 로컬 연결 정리 (풀링 호환)
    
    # [v4.7] 서버 시작 시 유지보수 작업 실행
    close_expired_polls()
    cleanup_old_access_logs()
    cleanup_empty_rooms()  # [v4.12] 빈 대화방 정리 추가
    cleanup_old_session_files()  # [v4.21] 만료된 세션 파일 정리
    
    logger.info("데이터베이스 초기화 완료")


def close_expired_polls():
    """[v4.7] 만료된 투표 자동 마감"""
    from datetime import datetime
    conn = get_db()
    cursor = conn.cursor()
    try:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            UPDATE polls SET closed = 1 
            WHERE ends_at IS NOT NULL AND ends_at < ? AND closed = 0
        ''', (now,))
        count = cursor.rowcount
        conn.commit()
        if count > 0:
            logger.info(f"Closed {count} expired polls")
        return count
    except Exception as e:
        logger.error(f"Close expired polls error: {e}")
        return 0
    finally:
        close_thread_db()  # [v4.12] 스레드 로컬 연결 정리


def cleanup_old_access_logs(days_to_keep=90):
    """[v4.7] 오래된 접속 로그 정리"""
    from datetime import datetime, timedelta
    conn = get_db()
    cursor = conn.cursor()
    try:
        cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('DELETE FROM access_logs WHERE created_at < ?', (cutoff_date,))
        count = cursor.rowcount
        conn.commit()
        if count > 0:
            logger.info(f"Cleaned up {count} old access logs (older than {days_to_keep} days)")
        return count
    except Exception as e:
        logger.error(f"Cleanup access logs error: {e}")
        return 0
    finally:
        close_thread_db()  # [v4.12] 스레드 로컬 연결 정리


def safe_file_delete(file_path: str, max_retries: int = 3) -> bool:
    """[v4.14] 파일 삭제 재시도 로직 - 간헐적 PermissionError 방지"""
    import os
    import time
    for attempt in range(max_retries):
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            return True  # 파일이 이미 없으면 성공으로 간주
        except PermissionError:
            if attempt < max_retries - 1:
                time.sleep(0.5)  # 잠시 대기 후 재시도
            else:
                logger.warning(f"File deletion failed after {max_retries} retries: {file_path}")
        except Exception as e:
            logger.warning(f"File deletion attempt {attempt+1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(0.3)
    return False


def cleanup_old_session_files(max_age_hours=24):
    """[v4.21] 만료된 Flask 세션 파일 정리
    
    서버 재시작 시 호출되어 오래된 세션 파일을 삭제합니다.
    Flask-Session의 파일 기반 세션은 자동 정리되지 않으므로 수동 정리 필요.
    
    Args:
        max_age_hours: 이 시간보다 오래된 세션 파일 삭제 (기본 24시간)
    
    Returns:
        삭제된 파일 수
    """
    import os
    from datetime import datetime, timedelta
    
    try:
        from config import BASE_DIR
    except ImportError:
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    session_dir = os.path.join(BASE_DIR, 'flask_session')
    if not os.path.exists(session_dir):
        return 0
    
    cutoff = datetime.now() - timedelta(hours=max_age_hours)
    removed = 0
    
    try:
        for filename in os.listdir(session_dir):
            filepath = os.path.join(session_dir, filename)
            if os.path.isfile(filepath):
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                    if mtime < cutoff:
                        if safe_file_delete(filepath):
                            removed += 1
                except (OSError, ValueError):
                    continue
        
        if removed > 0:
            logger.info(f"Cleaned up {removed} expired session files (older than {max_age_hours}h)")
    except Exception as e:
        logger.error(f"Session cleanup error: {e}")
    
    return removed


def cleanup_empty_rooms():
    """[v4.7] 멤버가 없는 빈 대화방 정리
    
    [v4.31] 트랜잭션 안전성 추가 - 부분 삭제 방지
    """
    import os
    conn = get_db()
    cursor = conn.cursor()
    try:
        # 멤버가 없는 방 찾기
        cursor.execute('''
            SELECT r.id FROM rooms r
            LEFT JOIN room_members rm ON r.id = rm.room_id
            GROUP BY r.id
            HAVING COUNT(rm.user_id) = 0
        ''')
        empty_rooms = [row['id'] for row in cursor.fetchall()]
        
        if not empty_rooms:
            return 0
        
        # [v4.31] 명시적 트랜잭션 시작
        cursor.execute('BEGIN IMMEDIATE')
        
        for room_id in empty_rooms:
            # 관련 파일 삭제 (트랜잭션 외부 - 파일 시스템 작업)
            cursor.execute('SELECT file_path FROM room_files WHERE room_id = ?', (room_id,))
            files = cursor.fetchall()
            for f in files:
                # [v4.14] safe_file_delete 사용으로 재시도 로직 적용
                full_path = os.path.join(UPLOAD_FOLDER, f['file_path'])
                safe_file_delete(full_path)
            
            # 관련 데이터 삭제
            cursor.execute('DELETE FROM messages WHERE room_id = ?', (room_id,))
            cursor.execute('DELETE FROM pinned_messages WHERE room_id = ?', (room_id,))
            cursor.execute('DELETE FROM polls WHERE room_id = ?', (room_id,))
            cursor.execute('DELETE FROM room_files WHERE room_id = ?', (room_id,))
            cursor.execute('DELETE FROM rooms WHERE id = ?', (room_id,))
        
        conn.commit()
        logger.info(f"Cleaned up {len(empty_rooms)} empty rooms: {empty_rooms}")
        return len(empty_rooms)
    except Exception as e:
        # [v4.31] 오류 시 롤백
        try:
            conn.rollback()
        except:
            pass
        logger.error(f"Cleanup empty rooms error: {e}")
        return 0
    finally:
        close_thread_db()  # [v4.12] 스레드 로컬 연결 정리


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
        pass  # [v4.17] 스레드 로컬 연결 유지 (get_db() 풀링 사용)


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
        # [v4.2] verify_password 사용을 위해 비밀번호 해시 직접 조회
        cursor.execute(
            'SELECT id, username, nickname, profile_image, password_hash FROM users WHERE username = ?',
            (username,)
        )
        user = cursor.fetchone()
        
        if user and verify_password(password, user['password_hash']):
            # [v4.2] 기존 SHA-256 해시인 경우 bcrypt로 마이그레이션
            if not user['password_hash'].startswith('$2'):
                try:
                    new_hash = hash_password(password)
                    if new_hash.startswith('$2'):
                        cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (new_hash, user['id']))
                        conn.commit()
                        logger.info(f"User {username} password migrated to bcrypt")
                except Exception as e:
                    logger.error(f"Password migration failed for {username}: {e}")
            
            # 비밀번호 해시는 반환하지 않음
            user_dict = dict(user)
            del user_dict['password_hash']
            return user_dict
            
        return None
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        return None
    finally:
        pass  # [v4.17] 스레드 로컬 연결 유지


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
        pass  # [v4.17] 스레드 로컬 연결 유지


def get_user_by_id_cached(user_id: int) -> dict | None:
    """[v4.19] 캐시된 사용자 조회 (성능 최적화)
    
    LRU 스타일 메모리 캐시를 사용하여 DB 조회를 최소화합니다.
    
    Args:
        user_id: 사용자 ID
    
    Returns:
        사용자 정보 dict 또는 None
    """
    import time
    
    with _user_cache_lock:
        cached = _user_cache.get(user_id)
        if cached and (time.time() - cached['_cached_at']) < USER_CACHE_TTL:
            return cached['data']
    
    user = get_user_by_id(user_id)
    if user:
        with _user_cache_lock:
            _user_cache[user_id] = {'data': user, '_cached_at': time.time()}
            # 캐시 크기 제한 (최대 500명)
            if len(_user_cache) > USER_CACHE_MAX_SIZE:
                oldest = min(_user_cache.items(), key=lambda x: x[1]['_cached_at'])
                del _user_cache[oldest[0]]
    
    return user


def invalidate_user_cache(user_id: int = None):
    """[v4.19] 사용자 캐시 무효화
    
    Args:
        user_id: 무효화할 사용자 ID (None이면 전체 캐시 삭제)
    """
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
    finally:
        pass  # [v4.17] 스레드 로컬 연결 유지


def update_user_status(user_id, status):
    """사용자 상태 업데이트"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE users SET status = ? WHERE id = ?', (status, user_id))
        conn.commit()
        # [v4.20] 캐시 무효화
        invalidate_user_cache(user_id)
    except Exception as e:
        logger.error(f"Update user status error: {e}")
    finally:
        pass  # [v4.17] 스레드 로컬 연결 유지


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
            # [v4.20] 캐시 무효화
            invalidate_user_cache(user_id)
            return True
        return False
    except Exception as e:
        logger.error(f"Update user profile error: {e}")
        return False
    finally:
        pass  # [v4.17] 스레드 로컬 연결 유지


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
        pass  # [v4.17] 스레드 로컬 연결 유지



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
        pass  # [v4.17] 스레드 로컬 연결 유지


# ============================================================================
# 대화방 관리
# ============================================================================
def create_room(name, room_type, created_by, member_ids):
    """대화방 생성"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
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
                return existing[0]  # [v4.17] 기존 대화방 반환
        
        # 대화방별 암호화 키 생성 및 마스터 키로 암호화
        raw_key = E2ECrypto.generate_room_key()
        # [v4.2] 마스터 키로 암호화하여 저장
        try:
            from app.crypto_manager import CryptoManager
            encryption_key = CryptoManager.encrypt_room_key(raw_key)
        except Exception as e:
            logger.warning(f"Key encryption failed, storing raw: {e}")
            encryption_key = raw_key
        
        cursor.execute(
            'INSERT INTO rooms (name, type, created_by, encryption_key) VALUES (?, ?, ?, ?)',
            (name, room_type, created_by, encryption_key)
        )
        room_id = cursor.lastrowid
        
        for user_id in member_ids:
            # [v4.20] 생성자에게 명시적 관리자 역할 부여
            role = 'admin' if user_id == created_by else 'member'
            cursor.execute(
                'INSERT INTO room_members (room_id, user_id, role) VALUES (?, ?, ?)',
                (room_id, user_id, role)
            )
        
        conn.commit()
        return room_id
    except Exception as e:
        conn.rollback()
        logger.error(f"Create room error: {e}")
        raise
    finally:
        pass  # [v4.17] 스레드 로컬 연결 유지


def get_room_key(room_id):
    """대화방 암호화 키 조회 (복호화하여 반환)"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT encryption_key FROM rooms WHERE id = ?', (room_id,))
        result = cursor.fetchone()
        if not result:
            return None
        
        encrypted_key = result['encryption_key']
        # [v4.2] 마스터 키로 복호화
        try:
            from app.crypto_manager import CryptoManager
            return CryptoManager.decrypt_room_key(encrypted_key)
        except Exception as e:
            logger.debug(f"Key decryption failed, returning as-is: {e}")
            return encrypted_key
    except Exception as e:
        logger.error(f"Get room key error: {e}")
        return None
    finally:
        pass  # [v4.17] 스레드 로컬 연결 유지


def get_user_rooms(user_id):
    """사용자의 대화방 목록 (N+1 문제 해결)"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # 1. 사용자가 참여한 대화방 목록 및 메타데이터 조회
        cursor.execute('''
            SELECT r.*, 
                   (SELECT COUNT(*) FROM room_members WHERE room_id = r.id) as member_count,
                   (SELECT m.content FROM messages m WHERE m.room_id = r.id ORDER BY m.id DESC LIMIT 1) as last_message,
                   (SELECT m.created_at FROM messages m WHERE m.room_id = r.id ORDER BY m.id DESC LIMIT 1) as last_message_time,
                   (SELECT COUNT(*) FROM messages m WHERE m.room_id = r.id AND m.id > rm.last_read_message_id AND m.sender_id != ?) as unread_count,
                   rm.pinned, rm.muted
            FROM rooms r
            JOIN room_members rm ON r.id = rm.room_id
            WHERE rm.user_id = ?
            ORDER BY rm.pinned DESC, last_message_time DESC NULLS LAST
        ''', (user_id, user_id))
        rooms = [dict(r) for r in cursor.fetchall()]
        
        if not rooms:
            return []
            
        room_ids = [r['id'] for r in rooms]
        
        # 2. 관련 대화방들의 모든 멤버 정보 한 번에 조회
        placeholders = ','.join('?' * len(room_ids))
        cursor.execute(f'''
            SELECT rm.room_id, u.id, u.nickname, u.profile_image, u.status
            FROM users u
            JOIN room_members rm ON u.id = rm.user_id
            WHERE rm.room_id IN ({placeholders})
        ''', room_ids)
        
        all_members = cursor.fetchall()
        
        # 3. room_id별 멤버 그룹화
        members_by_room = {}
        for m in all_members:
            rid = m['room_id']
            if rid not in members_by_room:
                members_by_room[rid] = []
            members_by_room[rid].append(dict(m))
            
        # 4. 각 대화방에 정보 매핑
        result = []
        for room in rooms:
            rid = room['id']
            room_members = members_by_room.get(rid, [])
            
            if room['type'] == 'direct':
                # 상대방 찾기 (자신이 아닌 멤버)
                partner = next((m for m in room_members if m['id'] != user_id), None)
                if partner:
                    room['partner'] = partner
                    room['name'] = partner['nickname']
            else:
                # 그룹방은 전체 멤버 리스트 포함
                room['members'] = room_members
                
            result.append(room)
        
        return result
    except Exception as e:
        logger.error(f"Get user rooms error: {e}")
        return []
    finally:
        pass  # [v4.18] 스레드 로컬 연결 유지



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
        pass  # [v4.18] 스레드 로컬 연결 유지


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
        pass  # [v4.18] 스레드 로컬 연결 유지


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
        pass  # [v4.18] 스레드 로컬 연결 유지


def leave_room_db(room_id, user_id):
    """[v4.21] 대화방 나가기 - 관리자 권한도 함께 제거, 마지막 관리자면 자동 위임
    
    트랜잭션 안전성 개선 - get_db_context() 대신 명시적 에러 처리
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # [v4.13] 나가는 사용자가 마지막 관리자인 경우 다른 멤버에게 권한 위임
        # 트랜잭션 내에서 읽고 쓰므로 정합성 보장
        if is_room_admin(room_id, user_id):
            # 현재 관리자 목록 조회 (트랜잭션 내)
            cursor.execute('''
                SELECT u.id FROM users u
                JOIN room_members rm ON u.id = rm.user_id
                WHERE rm.room_id = ? AND (rm.role = 'admin' OR u.id = (SELECT created_by FROM rooms WHERE id = ?))
            ''', (room_id, room_id))
            admin_ids = [row['id'] for row in cursor.fetchall()]
            
            if len(admin_ids) == 1 and admin_ids[0] == user_id:  # 마지막 관리자
                # 다른 멤버 중 하나에게 관리자 권한 위임
                members = get_room_members(room_id)
                for member in members:
                    if member['id'] != user_id:
                        cursor.execute('UPDATE room_members SET role = ? WHERE room_id = ? AND user_id = ?',
                                       ('admin', room_id, member['id']))
                        logger.info(f"Admin auto-delegated: room {room_id}, from {user_id} to {member['id']}")
                        break
        
        cursor.execute('DELETE FROM room_members WHERE room_id = ? AND user_id = ?', (room_id, user_id))
        conn.commit()
    except Exception as e:
        logger.error(f"Leave room error: {e}")
        # [v4.20] 예외 발생 시 롤백
        try:
            conn.rollback()
        except Exception:
            pass


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
        pass  # [v4.18] 스레드 로컬 연결 유지


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
        pass  # [v4.18] 스레드 로컬 연결 유지


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
        pass  # [v4.18] 스레드 로컬 연결 유지


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
        pass  # [v4.18] 스레드 로컬 연결 유지


# ============================================================================
# 메시지 관리
# ============================================================================
# 서버 통계 (전역) - Thread Safe
server_stats = {
    'start_time': None,
    'total_messages': 0,
    'total_connections': 0,
    'active_connections': 0
}
_stats_lock = threading.Lock()

def update_server_stats(key, value=1, increment=True):
    """서버 통계 안전하게 업데이트"""
    with _stats_lock:
        if increment:
            server_stats[key] += value
        else:
            server_stats[key] = value

def get_server_stats():
    """서버 통계 안전하게 조회"""
    with _stats_lock:
        return server_stats.copy()


def create_message(room_id, sender_id, content, message_type='text', file_path=None, file_name=None, reply_to=None, encrypted=True):
    """메시지 생성"""
    from datetime import datetime, timezone, timedelta
    
    # 한국 시간 (KST, GMT+9)
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst).strftime('%Y-%m-%d %H:%M:%S')
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO messages (room_id, sender_id, content, encrypted, message_type, file_path, file_name, reply_to, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (room_id, sender_id, content, 1 if encrypted else 0, message_type, file_path, file_name, reply_to, now_kst))
        message_id = cursor.lastrowid
        conn.commit()
        
        cursor.execute('''
            SELECT m.*, u.nickname as sender_name, u.profile_image as sender_image,
                   rm.content as reply_content, ru.nickname as reply_sender
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            LEFT JOIN messages rm ON m.reply_to = rm.id
            LEFT JOIN users ru ON rm.sender_id = ru.id
            WHERE m.id = ?
        ''', (message_id,))
        message = cursor.fetchone()
        
        update_server_stats('total_messages')
        
        return dict(message) if message else None
    except Exception as e:
        logger.error(f"Create message error: {e}")
        return None
    finally:
        pass  # [v4.18] 스레드 로컬 연결 유지


def get_room_messages(room_id, limit=50, before_id=None, include_reactions=True):
    """대화방 메시지 조회
    
    [v4.19] include_reactions=True일 경우 리액션 데이터도 배치 로드하여
    N+1 쿼리 문제를 방지합니다.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
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
        message_list = [dict(m) for m in reversed(messages)]
        
        # [v4.19] 리액션 데이터 배치 로드 (N+1 문제 해결)
        if include_reactions and message_list:
            message_ids = [m['id'] for m in message_list]
            reactions_map = get_messages_reactions(message_ids)
            for msg in message_list:
                msg['reactions'] = reactions_map.get(msg['id'], [])
        
        return message_list
    except Exception as e:
        logger.error(f"Get room messages error: {e}")
        return []
    finally:
        pass  # [v4.18] 스레드 로컬 연결 유지


def update_last_read(room_id, user_id, message_id):
    """마지막 읽은 메시지 업데이트"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE room_members SET last_read_message_id = ?
            WHERE room_id = ? AND user_id = ? AND last_read_message_id < ?
        ''', (message_id, room_id, user_id, message_id))
        conn.commit()
    except Exception as e:
        logger.error(f"Update last read error: {e}")
    finally:
        pass  # [v4.18] 스레드 로컬 연결 유지


def get_unread_count(room_id, message_id, sender_id=None):
    """메시지를 읽지 않은 사람 수 (발신자 제외)"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if sender_id:
            # 발신자는 자신의 메시지를 이미 읽은 것으로 간주
            cursor.execute('''
                SELECT COUNT(*) FROM room_members
                WHERE room_id = ? AND last_read_message_id < ? AND user_id != ?
            ''', (room_id, message_id, sender_id))
        else:
            cursor.execute('''
                SELECT COUNT(*) FROM room_members
                WHERE room_id = ? AND last_read_message_id < ?
            ''', (room_id, message_id))
        count = cursor.fetchone()[0]
        return count
    except Exception as e:
        logger.error(f"Get unread count error: {e}")
        return 0
    finally:
        pass  # [v4.18] 스레드 로컬 연결 유지


def get_room_last_reads(room_id: int) -> list[tuple[int, int]]:
    """[v4.19] 대화방 멤버들의 마지막 읽은 메시지 ID 및 사용자 ID 목록 (배치 조회)
    
    unread_count를 배치 계산할 때 사용하여 N+1 쿼리를 방지합니다.
    
    Args:
        room_id: 대화방 ID
    
    Returns:
        List of tuples: (last_read_message_id, user_id)
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT last_read_message_id, user_id FROM room_members WHERE room_id = ?
        ''', (room_id,))
        return [(row[0] or 0, row[1]) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Get room last reads error: {e}")
        return []
    finally:
        pass  # [v4.19] 스레드 로컬 연결 유지


def get_message_room_id(message_id: int) -> int | None:
    """[v4.4] 메시지 ID로 대화방 ID 조회"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT room_id FROM messages WHERE id = ?', (message_id,))
        result = cursor.fetchone()
        return result['room_id'] if result else None
    except Exception as e:
        logger.error(f"Get message room_id error: {e}")
        return None
    finally:
        pass  # [v4.18] 스레드 로컬 연결 유지


def delete_message(message_id, user_id):
    """메시지 삭제"""
    import os
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT sender_id, room_id, file_path FROM messages WHERE id = ?', (message_id,))
        msg = cursor.fetchone()
        if not msg or msg['sender_id'] != user_id:
            return False, "삭제 권한이 없습니다."
        
        cursor.execute("UPDATE messages SET content = '[삭제된 메시지]', encrypted = 0, file_path = NULL, file_name = NULL WHERE id = ?", (message_id,))
        
        # [v4.14] room_files 테이블에서도 삭제 (트랜잭션 포함)
        if msg['file_path']:
             cursor.execute('DELETE FROM room_files WHERE file_path = ?', (msg['file_path'],))
             
        conn.commit()
        
        # [v4.15] DB 커밋 성공 후에만 실제 파일 삭제 시도 (원자성 보장)
        if msg['file_path']:
            full_path = os.path.join(UPLOAD_FOLDER, msg['file_path'])
            if safe_file_delete(full_path):
                logger.debug(f"Message attachment deleted: {msg['file_path']}")
            else:
                logger.warning(f"Failed to delete attachment file: {msg['file_path']}")
        
        return True, msg['room_id']
    except Exception as e:
        logger.error(f"Delete message error: {e}")
        return False, "메시지 삭제 중 오류가 발생했습니다."
    finally:
        pass  # [v4.18] 스레드 로컬 연결 유지


def edit_message(message_id, user_id, new_content):
    """메시지 수정"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT sender_id, room_id FROM messages WHERE id = ?', (message_id,))
        msg = cursor.fetchone()
        if not msg or msg['sender_id'] != user_id:
            return False, "수정 권한이 없습니다.", None
        
        cursor.execute("UPDATE messages SET content = ? WHERE id = ?", (new_content, message_id))
        conn.commit()
        return True, "", msg['room_id']
    except Exception as e:
        logger.error(f"Edit message error: {e}")
        return False, "메시지 수정 중 오류가 발생했습니다.", None
    finally:
        pass  # [v4.18] 스레드 로컬 연결 유지


def search_messages(user_id, query):
    """메시지 검색"""
    conn = get_db()
    cursor = conn.cursor()
    try:
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
        return [dict(r) for r in results]
    except Exception as e:
        logger.error(f"Search messages error: {e}")
        return []
    finally:
        pass  # [v4.18] 스레드 로컬 연결 유지


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
        pass  # [v4.18] 스레드 로컬 연결 유지


def unpin_message(pin_id: int, user_id: int, room_id: int = None):
    """[v4.20] 공지 해제 - 모든 멤버가 가능 (정책 변경)"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # 공지 존재 확인
        cursor.execute('SELECT pinned_by, room_id FROM pinned_messages WHERE id = ?', (pin_id,))
        pin = cursor.fetchone()
        if not pin:
            return False
        
        actual_room_id = pin['room_id']
        
        # [v4.20] 멤버 여부만 확인 (관리자 제한 제거)
        if not is_room_member(actual_room_id, user_id):
            logger.warning(f"Unauthorized unpin attempt: user={user_id}, pin={pin_id}")
            return False
        
        cursor.execute('DELETE FROM pinned_messages WHERE id = ?', (pin_id,))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Unpin message error: {e}")
        return False
    finally:
        pass  # [v4.18] 스레드 로컬 연결 유지



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
        pass  # [v4.18] 스레드 로컬 연결 유지


# ============================================================================
# 투표 관리
# ============================================================================
def create_poll(room_id: int, created_by: int, question: str, options: list,
                multiple_choice: bool = False, anonymous: bool = False, ends_at: str = None):
    """투표 생성
    
    [v4.21] 옵션 검증 추가: 빈 옵션 필터링 및 개수 제한
    """
    # [v4.21] 옵션 검증 - models.py 레벨에서도 검증
    if not options:
        logger.warning(f"Poll creation failed: no options provided")
        return None
    
    # 빈 옵션 필터링 및 최대 10개 제한
    options = [opt.strip() for opt in options if opt and isinstance(opt, str) and opt.strip()][:10]
    
    if len(options) < 2:
        logger.warning(f"Poll creation failed: insufficient valid options (need 2+, got {len(options)})")
        return None
    
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
        pass  # [v4.18] 스레드 로컬 연결 유지


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
        pass  # [v4.18] 스레드 로컬 연결 유지


def get_room_polls(room_id: int):
    """대화방의 투표 목록"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # [v4.5] 만료된 투표 자동 마감
        from datetime import datetime
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
            UPDATE polls SET closed = 1 
            WHERE room_id = ? AND ends_at IS NOT NULL AND ends_at <= ? AND closed = 0
        """, (room_id, now))
        if cursor.rowcount > 0:
            conn.commit()
            logger.debug(f"Auto-closed {cursor.rowcount} expired polls in room {room_id}")
        
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
        pass  # [v4.18] 스레드 로컬 연결 유지


def vote_poll(poll_id: int, option_id: int, user_id: int):
    """투표 참여"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # 중복 투표 체크 및 마감 상태 확인
        cursor.execute('SELECT multiple_choice, closed, ends_at FROM polls WHERE id = ?', (poll_id,))
        poll = cursor.fetchone()
        if not poll:
            return False, "투표를 찾을 수 없습니다."
        
        # [v4.2] ends_at 기반 자동 마감 체크
        if poll['closed']:
            return False, "마감된 투표입니다."
        
        if poll['ends_at']:
            from datetime import datetime
            try:
                ends_at = datetime.strptime(poll['ends_at'], '%Y-%m-%d %H:%M:%S')
                if datetime.now() > ends_at:
                    # 자동 마감 처리
                    cursor.execute('UPDATE polls SET closed = 1 WHERE id = ?', (poll_id,))
                    conn.commit()
                    return False, "마감 시간이 지난 투표입니다."
            except ValueError:
                pass  # 날짜 형식 오류 시 무시
        
        if not poll['multiple_choice']:
            # 기존 투표 삭제 후 새 투표
            cursor.execute('DELETE FROM poll_votes WHERE poll_id = ? AND user_id = ?', (poll_id, user_id))
        
        # [v4.12] option_id가 해당 poll에 속하는지 검증
        cursor.execute('SELECT id FROM poll_options WHERE id = ? AND poll_id = ?', (option_id, poll_id))
        if not cursor.fetchone():
            return False, "유효하지 않은 투표 옵션입니다."
        
        cursor.execute('''
            INSERT OR IGNORE INTO poll_votes (poll_id, option_id, user_id) VALUES (?, ?, ?)
        ''', (poll_id, option_id, user_id))
        conn.commit()
        return True, ""
    except Exception as e:
        logger.error(f"Vote poll error: {e}")
        return False, str(e)
    finally:
        pass  # [v4.18] 스레드 로컬 연결 유지


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
        pass  # [v4.18] 스레드 로컬 연결 유지


def close_poll(poll_id: int, user_id: int):
    """투표 마감"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT created_by, room_id FROM polls WHERE id = ?', (poll_id,))
        poll = cursor.fetchone()
        if not poll:
            return False
        # [v4.6] 생성자 또는 방 관리자만 마감 가능
        if poll['created_by'] != user_id and not is_room_admin(poll['room_id'], user_id):
            return False
        cursor.execute('UPDATE polls SET closed = 1 WHERE id = ?', (poll_id,))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Close poll error: {e}")
        return False
    finally:
        pass  # [v4.18] 스레드 로컬 연결 유지


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
        pass  # [v4.18] 스레드 로컬 연결 유지


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
        pass  # [v4.18] 스레드 로컬 연결 유지


def delete_room_file(file_id: int, user_id: int, room_id: int = None, is_admin: bool = False):
    """[v4.4] 파일 삭제 - DB 레코드 및 실제 파일
    
    [v4.8] is_admin=True면 업로더가 아니어도 삭제 가능
    [v4.9] room_id 검증 추가 - 다른 방의 파일 삭제 방지
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT uploaded_by, file_path, room_id FROM room_files WHERE id = ?', (file_id,))
        file = cursor.fetchone()
        if not file:
            return False, None
        
        # [v4.9] room_id 검증 - 파일이 해당 방에 속하는지 확인
        if room_id is not None and file['room_id'] != room_id:
            logger.warning(f"Room_id mismatch in file delete: expected {room_id}, got {file['room_id']}")
            return False, None
        
        # [v4.8] 업로더 또는 관리자만 삭제 가능
        if file['uploaded_by'] != user_id and not is_admin:
            return False, None
        
        file_path = file['file_path']
        cursor.execute('DELETE FROM room_files WHERE id = ?', (file_id,))
        conn.commit()
        
        # [v4.14] safe_file_delete 사용으로 재시도 로직 적용
        import os
        full_path = os.path.join(UPLOAD_FOLDER, file_path)
        if safe_file_delete(full_path):
            logger.debug(f"File deleted from disk: {file_path}")
        
        return True, file_path
    except Exception as e:
        logger.error(f"Delete room file error: {e}")
        return False, None
    finally:
        pass  # [v4.18] 스레드 로컬 연결 유지


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
        pass  # [v4.18] 스레드 로컬 연결 유지


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
        pass  # [v4.18] 스레드 로컬 연결 유지


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
        pass  # [v4.18] 스레드 로컬 연결 유지


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
        pass  # [v4.18] 스레드 로컬 연결 유지


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
        pass  # [v4.18] 스레드 로컬 연결 유지


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
        pass  # [v4.18] 스레드 로컬 연결 유지


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
        pass  # [v4.18] 스레드 로컬 연결 유지


# ============================================================================
# [v4.1] 계정 보안 관리
# ============================================================================
def change_password(user_id, current_password, new_password):
    """비밀번호 변경"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # 현재 비밀번호 확인
        cursor.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            return False, "사용자를 찾을 수 없습니다."
            
        # [v4.2] verify_password 사용하여 기존/신규 해시 모두 검증
        if not verify_password(current_password, user['password_hash']):
            return False, "현재 비밀번호가 일치하지 않습니다."
            
        # 새 비밀번호 설정 (bcrypt 해시 자동 적용됨)
        new_hash = hash_password(new_password)
        cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
        conn.commit()
        return True, None
    except Exception as e:
        logger.error(f"Change password error: {e}")
        return False, f"오류 발생: {e}"
    finally:
        pass  # [v4.18] 스레드 로컬 연결 유지


def delete_user(user_id, password):
    """회원 탈퇴 (계정 삭제 및 데이터 정리)"""
    import os  # [v4.7] 파일 작업을 위해 상단에서 import
    conn = get_db()
    cursor = conn.cursor()
    try:
        # 비밀번호 확인
        cursor.execute("SELECT password_hash, profile_image FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            return False, "사용자를 찾을 수 없습니다."
            
        if not verify_password(password, user['password_hash']):
            return False, "비밀번호가 일치하지 않습니다."
        
        # [v4.5] 데이터 참조 무결성을 위해 관련된 데이터 정리
        
        # [v4.7] 0. 프로필 이미지 파일 삭제
        if user['profile_image']:
            try:
                profile_path = os.path.join(UPLOAD_FOLDER, user['profile_image'])
                if os.path.exists(profile_path):
                    os.remove(profile_path)
                    logger.debug(f"Profile image deleted: {user['profile_image']}")
            except Exception as e:
                logger.warning(f"Profile image deletion failed: {e}")
        
        # [v4.15] 0.3. 사용자가 생성한 대화방의 created_by 정리 (외래키 참조 제거)
        cursor.execute("UPDATE rooms SET created_by = NULL WHERE created_by = ?", (user_id,))
        
        # [v4.15] 0.5. 사용자가 생성한 투표 마감 및 created_by 정리
        cursor.execute("UPDATE polls SET closed = 1, created_by = NULL WHERE created_by = ?", (user_id,))
        
        # [v4.6] 1. 사용자가 업로드한 파일 삭제 (파일 시스템)
        cursor.execute("SELECT file_path FROM room_files WHERE uploaded_by = ?", (user_id,))
        files_to_delete = cursor.fetchall()
        for f in files_to_delete:
            try:
                full_path = os.path.join(UPLOAD_FOLDER, f['file_path'])
                if os.path.exists(full_path):
                    os.remove(full_path)
                    logger.debug(f"File deleted during user cleanup: {f['file_path']}")
            except Exception as e:
                logger.warning(f"File deletion failed during user delete: {e}")
        cursor.execute("DELETE FROM room_files WHERE uploaded_by = ?", (user_id,))
        
        # 1. 메시지 익명화 (sender_id는 NOT NULL이므로 유지, 내용만 익명화)
        # [v4.21] sender_id NOT NULL 제약조건 준수 - 메시지 내용만 익명화
        cursor.execute("""
            UPDATE messages SET content = '[탈퇴한 사용자의 메시지]', encrypted = 0 
            WHERE sender_id = ?
        """, (user_id,))
        
        # 1-1. 접속 로그 정리 (user_id FK 참조 해제)
        cursor.execute("UPDATE access_logs SET user_id = NULL WHERE user_id = ?", (user_id,))
        
        # 2. 투표 기록 삭제
        cursor.execute("DELETE FROM poll_votes WHERE user_id = ?", (user_id,))
        
        # 3. 리액션 삭제
        cursor.execute("DELETE FROM message_reactions WHERE user_id = ?", (user_id,))
        
        # 4. 공지사항에서 사용자 참조 정리 (pinned_by는 FK)
        cursor.execute("DELETE FROM pinned_messages WHERE pinned_by = ?", (user_id,))
        
        # 5. 대화방 멤버에서 제거 (admin role is stored in room_members.role, so it's deleted automatically)
        cursor.execute("DELETE FROM room_members WHERE user_id = ?", (user_id,))
        
        # 6. 사용자 삭제
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        
        conn.commit()
        logger.info(f"User {user_id} deleted with all related data cleaned up")
        return True, None
    except Exception as e:
        conn.rollback()
        logger.error(f"회원 탈퇴 오류: {e}")
        return False, "탈퇴 처리 중 오류가 발생했습니다."
    finally:
        pass  # [v4.18] 스레드 로컬 연결 유지
