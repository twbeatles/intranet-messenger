# -*- coding: utf-8 -*-
"""
데이터베이스 연결 및 초기화 모듈
"""

import sqlite3
import logging
import threading
import time
import os
from contextlib import contextmanager
from datetime import datetime, timedelta

# config 임포트 (PyInstaller 호환)
try:
    from config import DATABASE_PATH, UPLOAD_FOLDER, RETENTION_DAYS
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from config import DATABASE_PATH, UPLOAD_FOLDER, RETENTION_DAYS

logger = logging.getLogger(__name__)

# ============================================================================
# 데이터베이스 연결 관리 (스레드 로컬 풀링 버전)
# ============================================================================
_db_lock = threading.Lock()
_db_initialized = False
_db_local = threading.local()


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
            conn.execute('PRAGMA cache_size=-64000')
            conn.execute('PRAGMA temp_store=MEMORY')
            conn.execute('PRAGMA mmap_size=268435456')
            conn.execute('PRAGMA foreign_keys=ON')
            # [v4.2] busy_timeout 추가 - DB 잠금 시 대기 시간 (ms)
            conn.execute('PRAGMA busy_timeout=30000')
            
            return conn
        except sqlite3.OperationalError as e:
            if attempt == max_retries - 1:
                logger.error(f"DB Connection failed after {max_retries} retries: {e}")
                raise
            time.sleep(retry_delay)
            retry_delay *= 2


def get_db():
    """데이터베이스 연결 - 스레드별 연결 재사용 (성능 최적화)"""
    if not hasattr(_db_local, 'connection') or _db_local.connection is None:
        _db_local.connection = _create_connection()
    else:
        try:
            _db_local.connection.execute('SELECT 1')
        except (sqlite3.ProgrammingError, sqlite3.OperationalError):
            try:
                if hasattr(_db_local.connection, 'close'):
                    _db_local.connection.close()
            except Exception:
                pass
            _db_local.connection = _create_connection()
            
    return _db_local.connection


def close_thread_db():
    """현재 스레드의 데이터베이스 연결 종료"""
    if hasattr(_db_local, 'connection') and _db_local.connection:
        try:
            _db_local.connection.close()
        except Exception:
            pass
        _db_local.connection = None


@contextmanager
def get_db_context():
    """데이터베이스 연결 컨텍스트 매니저"""
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


def safe_file_delete(file_path: str, max_retries: int = 3) -> bool:
    """파일 삭제 재시도 로직"""
    for attempt in range(max_retries):
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            return True
        except PermissionError:
            if attempt < max_retries - 1:
                time.sleep(0.5)
            else:
                logger.warning(f"File deletion failed after {max_retries} retries: {file_path}")
        except Exception as e:
            logger.warning(f"File deletion attempt {attempt+1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(0.3)
    return False


def init_db():
    """데이터베이스 초기화"""
    global _db_initialized
    
    # [v4.2] 이미 초기화되었으면 스킵 (중복 호출 방지)
    if _db_initialized:
        logger.debug("Database already initialized, skipping")
        return
    
    # 새로운 연결 생성하여 테이블 생성 (스레드 로컬 대신 직접 연결)
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA foreign_keys=ON')
        cursor = conn.cursor()
        
        logger.info(f"Initializing database at: {DATABASE_PATH}")
    
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
                status_message TEXT,
                session_token TEXT,
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

        # OIDC identity table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sso_identities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                subject TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                email TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(provider, subject),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        # Upload scan queue/status table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS upload_scan_jobs (
                job_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                room_id INTEGER NOT NULL,
                temp_path TEXT NOT NULL,
                final_path TEXT,
                file_name TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_size INTEGER,
                status TEXT NOT NULL DEFAULT 'pending',
                result TEXT,
                token TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (room_id) REFERENCES rooms(id)
            )
        ''')

        # Structured admin audit log table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                actor_user_id INTEGER NOT NULL,
                target_user_id INTEGER,
                action TEXT NOT NULL,
                metadata_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (room_id) REFERENCES rooms(id),
                FOREIGN KEY (actor_user_id) REFERENCES users(id),
                FOREIGN KEY (target_user_id) REFERENCES users(id)
            )
        ''')
        
        # Auto-migration
        required_columns = {
            'users': {
                'status_message': 'TEXT',
                'session_token': 'TEXT'
            },
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
                existing_cols = [row[1] for row in cursor.fetchall()]
                
                for col_name, col_def in cols.items():
                    if col_name not in existing_cols:
                        logger.info(f"Migrating: Adding column '{col_name}' to table '{table}'")
                        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
        except Exception as e:
            logger.error(f"Migration failed: {e}")
        
        # 인덱스 생성
        try:
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_room_id ON messages(room_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_file_name ON messages(file_name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_room_members_user_id ON room_members(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_room_members_room_id ON room_members(room_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_message_reactions_message_id ON message_reactions(message_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_room_id_desc ON messages(room_id, id DESC)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_room_members_room_user ON room_members(room_id, user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_poll_votes_poll_user ON poll_votes(poll_id, user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_room_files_file_path ON room_files(file_path)')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_status ON users(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_session_token ON users(session_token)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sso_provider_subject ON sso_identities(provider, subject)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_upload_scan_jobs_status ON upload_scan_jobs(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_upload_scan_jobs_user ON upload_scan_jobs(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_admin_audit_logs_room_created ON admin_audit_logs(room_id, created_at DESC)")

            # Full-text search (FTS5) for plaintext (encrypted=0) text/system messages.
            # If this SQLite build doesn't support FTS5, skip silently.
            try:
                cursor.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
                    USING fts5(
                        content,
                        room_id UNINDEXED,
                        sender_id UNINDEXED,
                        created_at UNINDEXED,
                        tokenize='unicode61'
                    )
                """)

                cursor.execute("""
                    CREATE TRIGGER IF NOT EXISTS messages_fts_ai
                    AFTER INSERT ON messages BEGIN
                        INSERT INTO messages_fts(rowid, content, room_id, sender_id, created_at)
                        SELECT new.id, new.content, new.room_id, new.sender_id, new.created_at
                        WHERE new.encrypted = 0
                          AND new.message_type IN ('text', 'system')
                          AND new.content IS NOT NULL;
                    END;
                """)
                cursor.execute("""
                    CREATE TRIGGER IF NOT EXISTS messages_fts_ad
                    AFTER DELETE ON messages BEGIN
                        DELETE FROM messages_fts WHERE rowid = old.id;
                    END;
                """)
                cursor.execute("""
                    CREATE TRIGGER IF NOT EXISTS messages_fts_au
                    AFTER UPDATE ON messages BEGIN
                        DELETE FROM messages_fts WHERE rowid = old.id;
                        INSERT INTO messages_fts(rowid, content, room_id, sender_id, created_at)
                        SELECT new.id, new.content, new.room_id, new.sender_id, new.created_at
                        WHERE new.encrypted = 0
                          AND new.message_type IN ('text', 'system')
                          AND new.content IS NOT NULL;
                    END;
                """)

                # Backfill once for existing DBs where the FTS table is newly created.
                cursor.execute("SELECT COUNT(*) FROM messages_fts")
                fts_count = cursor.fetchone()[0]
                if not fts_count:
                    cursor.execute("""
                        INSERT INTO messages_fts(rowid, content, room_id, sender_id, created_at)
                        SELECT id, content, room_id, sender_id, created_at
                        FROM messages
                        WHERE encrypted = 0
                          AND message_type IN ('text', 'system')
                          AND content IS NOT NULL
                    """)
            except Exception as e:
                logger.debug(f"FTS5 init skipped: {e}")
            logger.debug("Database indexes created/verified")
        except Exception as e:
            logger.debug(f"Index creation: {e}")
        
        conn.commit()
        _db_initialized = True
        logger.info("데이터베이스 초기화 완료")
        
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    
    # 서버 시작 시 유지보수 작업 실행 (별도 연결 사용)
    try:
        close_expired_polls()
        cleanup_old_access_logs()
        cleanup_empty_rooms()
        if RETENTION_DAYS > 0:
            cleanup_retention_data(RETENTION_DAYS)
    except Exception as e:
        logger.warning(f"Maintenance tasks error: {e}")


def close_expired_polls():
    """만료된 투표 자동 마감"""
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
        close_thread_db()


def cleanup_old_access_logs(days_to_keep=90):
    """오래된 접속 로그 정리"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('DELETE FROM access_logs WHERE created_at < ?', (cutoff_date,))
        count = cursor.rowcount
        conn.commit()
        if count > 0:
            logger.info(f"Cleaned up {count} old access logs")
        return count
    except Exception as e:
        logger.error(f"Cleanup access logs error: {e}")
        return 0
    finally:
        close_thread_db()


def cleanup_retention_data(days_to_keep: int):
    """Apply retention policy to message/file data."""
    if days_to_keep <= 0:
        return {"messages": 0, "files": 0}

    conn = get_db()
    cursor = conn.cursor()
    try:
        cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).strftime('%Y-%m-%d %H:%M:%S')

        # 1) Delete old uploaded files first (physical + DB row).
        cursor.execute('SELECT id, file_path FROM room_files WHERE uploaded_at < ?', (cutoff_date,))
        old_files = cursor.fetchall()
        deleted_files = 0
        for row in old_files:
            full_path = os.path.join(UPLOAD_FOLDER, row['file_path'])
            safe_file_delete(full_path)
            cursor.execute('DELETE FROM room_files WHERE id = ?', (row['id'],))
            deleted_files += 1

        # 2) Delete old messages. Remove pins first to avoid FK failures.
        cursor.execute('SELECT id FROM messages WHERE created_at < ?', (cutoff_date,))
        old_msg_ids = [r['id'] for r in cursor.fetchall()]
        deleted_messages = 0
        if old_msg_ids:
            placeholders = ",".join(["?"] * len(old_msg_ids))
            cursor.execute(f'DELETE FROM pinned_messages WHERE message_id IN ({placeholders})', old_msg_ids)
            cursor.execute(f'DELETE FROM messages WHERE id IN ({placeholders})', old_msg_ids)
            deleted_messages = cursor.rowcount

        conn.commit()
        if deleted_messages or deleted_files:
            logger.info(
                f"Retention cleanup completed (days={days_to_keep}, messages={deleted_messages}, files={deleted_files})"
            )
        return {"messages": deleted_messages, "files": deleted_files}
    except Exception as e:
        logger.error(f"Retention cleanup error: {e}")
        return {"messages": 0, "files": 0}
    finally:
        close_thread_db()


def cleanup_empty_rooms():
    """멤버가 없는 빈 대화방 정리"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT r.id FROM rooms r
            LEFT JOIN room_members rm ON r.id = rm.room_id
            GROUP BY r.id
            HAVING COUNT(rm.user_id) = 0
        ''')
        empty_rooms = [row['id'] for row in cursor.fetchall()]
        
        if not empty_rooms:
            return 0
        
        for room_id in empty_rooms:
            cursor.execute('SELECT file_path FROM room_files WHERE room_id = ?', (room_id,))
            files = cursor.fetchall()
            for f in files:
                full_path = os.path.join(UPLOAD_FOLDER, f['file_path'])
                safe_file_delete(full_path)
            
            cursor.execute('DELETE FROM messages WHERE room_id = ?', (room_id,))
            cursor.execute('DELETE FROM pinned_messages WHERE room_id = ?', (room_id,))
            cursor.execute('DELETE FROM polls WHERE room_id = ?', (room_id,))
            cursor.execute('DELETE FROM room_files WHERE room_id = ?', (room_id,))
            cursor.execute('DELETE FROM rooms WHERE id = ?', (room_id,))
        
        conn.commit()
        logger.info(f"Cleaned up {len(empty_rooms)} empty rooms: {empty_rooms}")
        return len(empty_rooms)
    except Exception as e:
        logger.error(f"Cleanup empty rooms error: {e}")
        return 0
    finally:
        close_thread_db()
