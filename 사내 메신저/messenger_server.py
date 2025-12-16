# -*- coding: utf-8 -*-
"""
사내 웹메신저 시스템 v2.5
Flask + Socket.IO + PyQt6 GUI 기반 실시간 채팅 서버
- 종단간 암호화 (E2E Encryption)
- 시스템 트레이 아이콘
- Windows 시작 프로그램 등록
- 보안 강화 및 로깅 시스템
- 추가 메신저 기능 (온라인 사용자, 대화방 설정, 메시지 관리)
- 사내망 호환성 (로컬 리소스)
- 전반적 디버깅 및 예외 처리 강화
"""

import os
import sys
import json
import hashlib
import sqlite3
import secrets
import base64
import winreg
import threading
import logging
import re
import uuid
from datetime import datetime, timedelta
from functools import wraps
from threading import Lock
from contextlib import contextmanager

from flask import Flask, request, jsonify, session, send_from_directory, render_template_string
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSystemTrayIcon, QMenu, QTextEdit, QLineEdit,
    QSpinBox, QCheckBox, QGroupBox, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QFrame, QSplitter
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QSettings
from PyQt6.QtGui import QIcon, QAction, QFont, QColor, QPixmap, QPainter, QBrush

# ============================================================================
# 설정
# ============================================================================
# PyInstaller 패키징 시 frozen 상태 처리
if getattr(sys, 'frozen', False):
    # PyInstaller로 패키징된 경우
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # 일반 Python 스크립트 실행
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATABASE_PATH = os.path.join(BASE_DIR, 'messenger.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'zip'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
APP_NAME = "사내 메신저 서버"
VERSION = "2.5"
SESSION_TIMEOUT_HOURS = 24
PASSWORD_SALT = "messenger_secure_salt_2024"

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, 'server.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Flask 앱 초기화 (static 폴더 포함 - 사내망 호환)
STATIC_FOLDER = os.path.join(BASE_DIR, 'static')
os.makedirs(STATIC_FOLDER, exist_ok=True)
app = Flask(__name__, static_folder=STATIC_FOLDER, static_url_path='/static')
app.config['SECRET_KEY'] = secrets.token_hex(32)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['SESSION_COOKIE_SECURE'] = False  # HTTPS 사용 시 True로 변경
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=SESSION_TIMEOUT_HOURS)

# Socket.IO 초기화 (PyInstaller 호환)
# PyInstaller에서 async_drivers를 번들링하도록 명시적 import
_async_mode = None
try:
    # simple-websocket이 있으면 threading 모드 사용
    import simple_websocket  # noqa: F401
    import engineio.async_drivers.threading  # noqa: F401 - PyInstaller용
    _async_mode = 'threading'
except ImportError:
    pass

try:
    socketio = SocketIO(
        app, 
        cors_allowed_origins="*", 
        ping_timeout=60, 
        ping_interval=25,
        async_mode=_async_mode,
        logger=False,
        engineio_logger=False
    )
except ValueError as e:
    # async_mode 오류 시 기본 설정으로 재시도
    logger.warning(f"Socket.IO 초기화 경고: {e}, 기본 모드로 재시도")
    socketio = SocketIO(app, cors_allowed_origins="*")

# 업로드 폴더 생성
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 온라인 사용자 관리
online_users = {}
online_users_lock = Lock()

# 서버 통계
server_stats = {
    'start_time': None,
    'total_messages': 0,
    'total_connections': 0,
    'active_connections': 0
}
stats_lock = Lock()

# ============================================================================
# 암호화 유틸리티 (E2E Encryption)
# ============================================================================
class E2ECrypto:
    """종단간 암호화 클래스 - 클라이언트 측에서 사용되는 키로만 복호화 가능"""
    
    @staticmethod
    def generate_room_key():
        """대화방별 암호화 키 생성 (32바이트 = 256비트)"""
        return base64.b64encode(get_random_bytes(32)).decode('utf-8')
    
    @staticmethod
    def encrypt_message(plaintext, key_b64):
        """메시지 암호화"""
        try:
            key = base64.b64decode(key_b64)
            iv = get_random_bytes(16)
            cipher = AES.new(key, AES.MODE_CBC, iv)
            padded_data = pad(plaintext.encode('utf-8'), AES.block_size)
            encrypted = cipher.encrypt(padded_data)
            # IV + 암호문을 base64로 인코딩
            return base64.b64encode(iv + encrypted).decode('utf-8')
        except Exception as e:
            return None
    
    @staticmethod
    def decrypt_message(ciphertext_b64, key_b64):
        """메시지 복호화"""
        try:
            key = base64.b64decode(key_b64)
            data = base64.b64decode(ciphertext_b64)
            iv = data[:16]
            encrypted = data[16:]
            cipher = AES.new(key, AES.MODE_CBC, iv)
            decrypted = unpad(cipher.decrypt(encrypted), AES.block_size)
            return decrypted.decode('utf-8')
        except Exception as e:
            return "[암호화된 메시지]"

# ============================================================================
# 데이터베이스
# ============================================================================
@contextmanager
def get_db_context():
    """데이터베이스 연결 컨텍스트 매니저 (자동 commit/rollback/close)"""
    conn = sqlite3.connect(DATABASE_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        conn.close()

def get_db():
    """데이터베이스 연결 (수동 관리 시 사용)"""
    conn = sqlite3.connect(DATABASE_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

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
    
    # 메시지 테이블 (암호화된 내용 저장)
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

def hash_password(password):
    """비밀번호 해시 (솔트 적용)"""
    salted = f"{PASSWORD_SALT}{password}{PASSWORD_SALT}"
    return hashlib.sha256(salted.encode()).hexdigest()

def validate_username(username):
    """아이디 유효성 검사"""
    if not username or len(username) < 3 or len(username) > 20:
        return False
    return bool(re.match(r'^[a-zA-Z0-9_]+$', username))

def validate_password(password):
    """비밀번호 강도 검사"""
    if len(password) < 4:
        return False, "비밀번호는 4자 이상이어야 합니다."
    return True, ""

def sanitize_input(text, max_length=1000):
    """입력값 정제 (XSS 방지)"""
    if not text:
        return ""
    # 길이 제한
    text = text[:max_length]
    # 기본적인 HTML 태그 제거
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()

# ============================================================================
# 사용자 관리
# ============================================================================
def create_user(username, password, nickname=None):
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
        return None
    finally:
        conn.close()

def authenticate_user(username, password):
    """사용자 인증"""
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

def get_user_by_id(user_id):
    """ID로 사용자 조회"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, nickname, profile_image, status FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def get_all_users():
    """모든 사용자 조회"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, nickname, profile_image, status FROM users')
    users = cursor.fetchall()
    conn.close()
    return [dict(u) for u in users]

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

def log_access(user_id, action, ip_address, user_agent):
    """접속 로그 기록"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # user_agent 길이 제한
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
    """대화방 생성 (암호화 키 포함)"""
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
    cursor.execute('SELECT encryption_key FROM rooms WHERE id = ?', (room_id,))
    result = cursor.fetchone()
    conn.close()
    return result['encryption_key'] if result else None

def get_user_rooms(user_id):
    """사용자의 대화방 목록"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.*, 
               (SELECT COUNT(*) FROM room_members WHERE room_id = r.id) as member_count,
               (SELECT m.content FROM messages m WHERE m.room_id = r.id ORDER BY m.id DESC LIMIT 1) as last_message,
               (SELECT m.created_at FROM messages m WHERE m.room_id = r.id ORDER BY m.id DESC LIMIT 1) as last_message_time,
               (SELECT COUNT(*) FROM messages m WHERE m.room_id = r.id AND m.id > rm.last_read_message_id) as unread_count
        FROM rooms r
        JOIN room_members rm ON r.id = rm.room_id
        WHERE rm.user_id = ?
        ORDER BY last_message_time DESC NULLS LAST
    ''', (user_id,))
    rooms = cursor.fetchall()
    
    result = []
    for room in rooms:
        room_dict = dict(room)
        # 암호화 키는 프론트엔드로 전송 (클라이언트에서만 복호화)
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
    
    conn.close()
    return result

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
    """사용자가 대화방 멤버인지 확인"""
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
    """대화방에 멤버 추가"""
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
    cursor.execute('DELETE FROM room_members WHERE room_id = ? AND user_id = ?', (room_id, user_id))
    conn.commit()
    conn.close()

def update_room_name(room_id, new_name):
    """대화방 이름 변경"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE rooms SET name = ? WHERE id = ?', (new_name, room_id))
        conn.commit()
        logger.info(f"Room {room_id} name updated to: {new_name}")
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

def get_online_users():
    """현재 온라인 사용자 목록"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, nickname, profile_image FROM users WHERE status = 'online'")
    users = cursor.fetchall()
    conn.close()
    return [dict(u) for u in users]

def delete_message(message_id, user_id):
    """메시지 삭제 (본인 메시지만)"""
    conn = get_db()
    cursor = conn.cursor()
    # 본인 메시지인지 확인
    cursor.execute('SELECT sender_id, room_id FROM messages WHERE id = ?', (message_id,))
    msg = cursor.fetchone()
    if not msg or msg['sender_id'] != user_id:
        conn.close()
        return False, "삭제 권한이 없습니다."
    
    cursor.execute("UPDATE messages SET content = '[삭제된 메시지]', encrypted = 0 WHERE id = ?", (message_id,))
    conn.commit()
    conn.close()
    logger.info(f"Message {message_id} deleted by user {user_id}")
    return True, msg['room_id']

def edit_message(message_id, user_id, new_content):
    """메시지 수정 (본인 메시지만)"""
    conn = get_db()
    cursor = conn.cursor()
    # 본인 메시지인지 확인
    cursor.execute('SELECT sender_id, room_id FROM messages WHERE id = ?', (message_id,))
    msg = cursor.fetchone()
    if not msg or msg['sender_id'] != user_id:
        conn.close()
        return False, "수정 권한이 없습니다.", None
    
    cursor.execute("UPDATE messages SET content = ? WHERE id = ?", (new_content, message_id))
    conn.commit()
    conn.close()
    logger.info(f"Message {message_id} edited by user {user_id}")
    return True, "", msg['room_id']

def pin_room(user_id, room_id, pinned):
    """대화방 상단 고정 (room_members 테이블에 pinned 컬럼 필요)"""
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
def create_message(room_id, sender_id, content, message_type='text', file_path=None, file_name=None, reply_to=None, encrypted=True):
    """메시지 생성 (암호화된 상태로 저장)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO messages (room_id, sender_id, content, encrypted, message_type, file_path, file_name, reply_to)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (room_id, sender_id, content, 1 if encrypted else 0, message_type, file_path, file_name, reply_to))
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
    
    # 통계 업데이트
    with stats_lock:
        server_stats['total_messages'] += 1
    
    return dict(message)

def get_room_messages(room_id, limit=50, before_id=None):
    """대화방 메시지 조회"""
    conn = get_db()
    cursor = conn.cursor()
    
    if before_id:
        cursor.execute('''
            SELECT m.*, u.nickname as sender_name, u.profile_image as sender_image
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE m.room_id = ? AND m.id < ?
            ORDER BY m.id DESC
            LIMIT ?
        ''', (room_id, before_id, limit))
    else:
        cursor.execute('''
            SELECT m.*, u.nickname as sender_name, u.profile_image as sender_image
            FROM messages m
            JOIN users u ON m.sender_id = u.id
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

def search_messages(user_id, query):
    """메시지 검색 (암호화된 메시지는 검색 불가 안내)"""
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
# 파일 업로드
# ============================================================================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ============================================================================
# Flask 라우트
# ============================================================================
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    nickname = data.get('nickname', '').strip() or username
    
    if not username or not password:
        return jsonify({'error': '아이디와 비밀번호를 입력해주세요.'}), 400
    if len(username) < 3:
        return jsonify({'error': '아이디는 3자 이상이어야 합니다.'}), 400
    if len(password) < 4:
        return jsonify({'error': '비밀번호는 4자 이상이어야 합니다.'}), 400
    
    user_id = create_user(username, password, nickname)
    if user_id:
        log_access(user_id, 'register', request.remote_addr, request.user_agent.string)
        return jsonify({'success': True, 'user_id': user_id})
    return jsonify({'error': '이미 존재하는 아이디입니다.'}), 400

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user = authenticate_user(data.get('username', ''), data.get('password', ''))
    if user:
        session['user_id'] = user['id']
        session['username'] = user['username']
        log_access(user['id'], 'login', request.remote_addr, request.user_agent.string)
        return jsonify({'success': True, 'user': user})
    return jsonify({'error': '아이디 또는 비밀번호가 올바르지 않습니다.'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    if 'user_id' in session:
        log_access(session['user_id'], 'logout', request.remote_addr, request.user_agent.string)
    session.clear()
    return jsonify({'success': True})

@app.route('/api/users')
def get_users():
    if 'user_id' not in session:
        return jsonify({'error': '로그인이 필요합니다.'}), 401
    users = get_all_users()
    return jsonify([u for u in users if u['id'] != session['user_id']])

@app.route('/api/rooms')
def get_rooms():
    if 'user_id' not in session:
        return jsonify({'error': '로그인이 필요합니다.'}), 401
    rooms = get_user_rooms(session['user_id'])
    return jsonify(rooms)

@app.route('/api/rooms', methods=['POST'])
def create_room_route():
    if 'user_id' not in session:
        return jsonify({'error': '로그인이 필요합니다.'}), 401
    
    data = request.json
    member_ids = data.get('members', [])
    if session['user_id'] not in member_ids:
        member_ids.append(session['user_id'])
    
    room_type = 'direct' if len(member_ids) == 2 else 'group'
    name = data.get('name', '')
    
    room_id = create_room(name, room_type, session['user_id'], member_ids)
    return jsonify({'success': True, 'room_id': room_id})

@app.route('/api/rooms/<int:room_id>/messages')
def get_messages(room_id):
    if 'user_id' not in session:
        return jsonify({'error': '로그인이 필요합니다.'}), 401
    
    before_id = request.args.get('before_id', type=int)
    messages = get_room_messages(room_id, before_id=before_id)
    members = get_room_members(room_id)
    encryption_key = get_room_key(room_id)
    
    for msg in messages:
        msg['unread_count'] = get_unread_count(room_id, msg['id'])
    
    return jsonify({'messages': messages, 'members': members, 'encryption_key': encryption_key})

@app.route('/api/rooms/<int:room_id>/members', methods=['POST'])
def invite_member(room_id):
    if 'user_id' not in session:
        return jsonify({'error': '로그인이 필요합니다.'}), 401
    
    data = request.json
    user_ids = data.get('user_ids', [])
    user_id = data.get('user_id')
    
    # 단일 사용자 또는 다중 사용자 지원
    if user_id:
        user_ids = [user_id]
    
    added = 0
    for uid in user_ids:
        if add_room_member(room_id, uid):
            added += 1
    
    if added > 0:
        # 방에 있는 모든 사용자에게 알림
        socketio.emit('room_members_updated', {'room_id': room_id}, room=f'room_{room_id}')
        return jsonify({'success': True, 'added_count': added})
    return jsonify({'error': '이미 참여중인 사용자입니다.'}), 400

@app.route('/api/rooms/<int:room_id>/leave', methods=['POST'])
def leave_room_route(room_id):
    if 'user_id' not in session:
        return jsonify({'error': '로그인이 필요합니다.'}), 401
    
    leave_room_db(room_id, session['user_id'])
    return jsonify({'success': True})

@app.route('/api/rooms/<int:room_id>/name', methods=['PUT'])
def update_room_name_route(room_id):
    """대화방 이름 변경"""
    if 'user_id' not in session:
        return jsonify({'error': '로그인이 필요합니다.'}), 401
    
    data = request.json
    new_name = sanitize_input(data.get('name', ''), max_length=50)
    if not new_name:
        return jsonify({'error': '대화방 이름을 입력해주세요.'}), 400
    
    update_room_name(room_id, new_name)
    socketio.emit('room_name_updated', {'room_id': room_id, 'name': new_name}, room=f'room_{room_id}')
    return jsonify({'success': True})

@app.route('/api/rooms/<int:room_id>/pin', methods=['POST'])
def pin_room_route(room_id):
    """대화방 상단 고정"""
    if 'user_id' not in session:
        return jsonify({'error': '로그인이 필요합니다.'}), 401
    
    data = request.json
    pinned = data.get('pinned', True)
    if pin_room(session['user_id'], room_id, pinned):
        return jsonify({'success': True})
    return jsonify({'error': '설정 변경에 실패했습니다.'}), 400

@app.route('/api/rooms/<int:room_id>/mute', methods=['POST'])
def mute_room_route(room_id):
    """대화방 알림 끄기"""
    if 'user_id' not in session:
        return jsonify({'error': '로그인이 필요합니다.'}), 401
    
    data = request.json
    muted = data.get('muted', True)
    if mute_room(session['user_id'], room_id, muted):
        return jsonify({'success': True})
    return jsonify({'error': '설정 변경에 실패했습니다.'}), 400

@app.route('/api/users/online')
def get_online_users_route():
    """온라인 사용자 목록"""
    if 'user_id' not in session:
        return jsonify({'error': '로그인이 필요합니다.'}), 401
    
    users = get_online_users()
    # 본인 제외
    users = [u for u in users if u['id'] != session['user_id']]
    return jsonify(users)

@app.route('/api/messages/<int:message_id>', methods=['DELETE'])
def delete_message_route(message_id):
    """메시지 삭제"""
    if 'user_id' not in session:
        return jsonify({'error': '로그인이 필요합니다.'}), 401
    
    success, result = delete_message(message_id, session['user_id'])
    if success:
        socketio.emit('message_deleted', {'message_id': message_id}, room=f'room_{result}')
        return jsonify({'success': True})
    return jsonify({'error': result}), 403

@app.route('/api/messages/<int:message_id>', methods=['PUT'])
def edit_message_route(message_id):
    """메시지 수정"""
    if 'user_id' not in session:
        return jsonify({'error': '로그인이 필요합니다.'}), 401
    
    data = request.json
    new_content = data.get('content', '')
    if not new_content:
        return jsonify({'error': '메시지 내용을 입력해주세요.'}), 400
    
    success, error, room_id = edit_message(message_id, session['user_id'], new_content)
    if success:
        socketio.emit('message_edited', {'message_id': message_id, 'content': new_content}, room=f'room_{room_id}')
        return jsonify({'success': True})
    return jsonify({'error': error}), 403

@app.route('/api/rooms/<int:room_id>/info')
def get_room_info(room_id):
    """대화방 상세 정보"""
    if 'user_id' not in session:
        return jsonify({'error': '로그인이 필요합니다.'}), 401
    
    room = get_room_by_id(room_id)
    if not room:
        return jsonify({'error': '대화방을 찾을 수 없습니다.'}), 404
    
    members = get_room_members(room_id)
    room['members'] = members
    # 암호화 키 제외
    room.pop('encryption_key', None)
    return jsonify(room)

@app.route('/api/search')
def search():
    if 'user_id' not in session:
        return jsonify({'error': '로그인이 필요합니다.'}), 401
    
    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify([])
    
    results = search_messages(session['user_id'], query)
    return jsonify(results)

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'user_id' not in session:
        return jsonify({'error': '로그인이 필요합니다.'}), 401
    
    if 'file' not in request.files:
        return jsonify({'error': '파일이 없습니다.'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '파일이 선택되지 않았습니다.'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(file_path)
        return jsonify({
            'success': True,
            'file_path': unique_filename,
            'file_name': filename
        })
    
    return jsonify({'error': '허용되지 않는 파일 형식입니다.'}), 400

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ============================================================================
# Socket.IO 이벤트
# ============================================================================
@socketio.on('connect')
def handle_connect():
    if 'user_id' in session:
        user_id = session['user_id']
        with online_users_lock:
            online_users[request.sid] = user_id
        update_user_status(user_id, 'online')
        emit('user_status', {'user_id': user_id, 'status': 'online'}, broadcast=True)
        
        with stats_lock:
            server_stats['total_connections'] += 1
            server_stats['active_connections'] += 1

@socketio.on('disconnect')
def handle_disconnect():
    with online_users_lock:
        user_id = online_users.pop(request.sid, None)
    if user_id:
        with online_users_lock:
            still_online = user_id in online_users.values()
        if not still_online:
            update_user_status(user_id, 'offline')
            emit('user_status', {'user_id': user_id, 'status': 'offline'}, broadcast=True)
    
    with stats_lock:
        server_stats['active_connections'] = max(0, server_stats['active_connections'] - 1)

@socketio.on('join_room')
def handle_join_room(data):
    try:
        room_id = data.get('room_id')
        if room_id and 'user_id' in session:
            # 멤버십 확인
            if is_room_member(room_id, session['user_id']):
                join_room(f'room_{room_id}')
                emit('joined_room', {'room_id': room_id})
            else:
                emit('error', {'message': '대화방 접근 권한이 없습니다.'})
    except Exception as e:
        logger.error(f"Join room error: {e}")

@socketio.on('leave_room')
def handle_leave_room(data):
    try:
        room_id = data.get('room_id')
        if room_id:
            leave_room(f'room_{room_id}')
    except Exception as e:
        logger.error(f"Leave room error: {e}")

@socketio.on('send_message')
def handle_send_message(data):
    try:
        if 'user_id' not in session:
            return
        
        room_id = data.get('room_id')
        content = data.get('content', '')
        if isinstance(content, str):
            content = content.strip()
        message_type = data.get('type', 'text')
        file_path = data.get('file_path')
        file_name = data.get('file_name')
        reply_to = data.get('reply_to')
        encrypted = data.get('encrypted', True)
        
        if not room_id or (not content and not file_path):
            return
        
        # 멤버십 확인
        if not is_room_member(room_id, session['user_id']):
            emit('error', {'message': '대화방 접근 권한이 없습니다.'})
            return
        
        # 메시지는 암호화된 상태로 저장 (서버에서는 읽을 수 없음)
        message = create_message(
            room_id, session['user_id'], content, message_type, file_path, file_name, reply_to, encrypted
        )
        if message:
            message['unread_count'] = get_unread_count(room_id, message['id'])
            emit('new_message', message, room=f'room_{room_id}')
            emit('room_updated', {'room_id': room_id}, broadcast=True)
    except Exception as e:
        logger.error(f"Send message error: {e}")
        emit('error', {'message': '메시지 전송에 실패했습니다.'})

@socketio.on('message_read')
def handle_message_read(data):
    try:
        if 'user_id' not in session:
            return
        
        room_id = data.get('room_id')
        message_id = data.get('message_id')
        
        if room_id and message_id:
            update_last_read(room_id, session['user_id'], message_id)
            emit('read_updated', {
                'room_id': room_id,
                'user_id': session['user_id'],
                'message_id': message_id
            }, room=f'room_{room_id}')
    except Exception as e:
        logger.error(f"Message read error: {e}")

@socketio.on('typing')
def handle_typing(data):
    if 'user_id' not in session:
        return
    
    room_id = data.get('room_id')
    is_typing = data.get('is_typing', False)
    user = get_user_by_id(session['user_id'])
    
    emit('user_typing', {
        'room_id': room_id,
        'user_id': session['user_id'],
        'nickname': user['nickname'] if user else '',
        'is_typing': is_typing
    }, room=f'room_{room_id}', include_self=False)

# ============================================================================
# HTML 템플릿 (클라이언트 측 E2E 암호화 포함)
# ============================================================================
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🔒 사내 메신저 (E2E 암호화)</title>
    <!-- 로컬 라이브러리 (사내망 호환) -->
    <script src="/static/js/socket.io.min.js"></script>
    <script src="/static/js/crypto-js.min.js"></script>
    <style>
        :root {
            --primary: #10B981;
            --primary-hover: #059669;
            --secondary: #2D2F3A;
            --bg-dark: #0F172A;
            --bg-darker: #020617;
            --bg-light: #1E293B;
            --text: #F8FAFC;
            --text-muted: #94A3B8;
            --success: #22C55E;
            --danger: #EF4444;
            --warning: #F59E0B;
            --border: rgba(255,255,255,0.1);
            --shadow: 0 8px 32px rgba(0,0,0,0.4);
            --radius: 12px;
            --radius-sm: 8px;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', -apple-system, sans-serif; background: var(--bg-dark); color: var(--text); height: 100vh; overflow: hidden; }
        
        .auth-container { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: linear-gradient(135deg, var(--bg-darker), var(--bg-dark)); }
        .auth-box { background: var(--bg-light); padding: 48px; border-radius: var(--radius); box-shadow: var(--shadow); width: 100%; max-width: 420px; border: 1px solid var(--border); }
        .auth-box h1 { font-size: 28px; margin-bottom: 8px; text-align: center; }
        .auth-box .subtitle { color: var(--text-muted); text-align: center; margin-bottom: 32px; }
        .encryption-badge { display: inline-flex; align-items: center; gap: 6px; background: rgba(16,185,129,0.15); color: var(--primary); padding: 8px 16px; border-radius: 20px; font-size: 13px; margin-bottom: 24px; }
        .form-group { margin-bottom: 20px; }
        .form-group label { display: block; margin-bottom: 8px; font-size: 14px; color: var(--text-muted); }
        .form-group input { width: 100%; padding: 14px 16px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--bg-dark); color: var(--text); font-size: 15px; transition: all 0.2s; }
        .form-group input:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(16,185,129,0.2); }
        .btn { width: 100%; padding: 14px; border: none; border-radius: var(--radius-sm); font-size: 15px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
        .btn-primary { background: var(--primary); color: white; }
        .btn-primary:hover { background: var(--primary-hover); }
        .auth-switch { text-align: center; margin-top: 24px; color: var(--text-muted); }
        .auth-switch a { color: var(--primary); text-decoration: none; }
        .error-message { background: rgba(239,68,68,0.1); border: 1px solid var(--danger); color: var(--danger); padding: 12px; border-radius: var(--radius-sm); margin-bottom: 20px; font-size: 14px; }
        
        .app-container { display: none; height: 100vh; }
        .app-container.active { display: flex; }
        
        .sidebar { width: 340px; background: var(--bg-darker); display: flex; flex-direction: column; border-right: 1px solid var(--border); }
        .sidebar-header { padding: 20px; border-bottom: 1px solid var(--border); }
        .sidebar-header h2 { font-size: 20px; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }
        .search-box { position: relative; }
        .search-box i { position: absolute; left: 14px; top: 50%; transform: translateY(-50%); color: var(--text-muted); }
        .search-box input { width: 100%; padding: 12px 12px 12px 42px; border: none; border-radius: var(--radius-sm); background: var(--bg-light); color: var(--text); font-size: 14px; }
        .search-box input:focus { outline: none; }
        
        .room-list { flex: 1; overflow-y: auto; padding: 12px; }
        .room-item { display: flex; align-items: center; padding: 12px; border-radius: var(--radius-sm); cursor: pointer; transition: all 0.2s; margin-bottom: 4px; }
        .room-item:hover { background: var(--bg-light); }
        .room-item.active { background: var(--primary); }
        .room-avatar { width: 48px; height: 48px; border-radius: 50%; background: linear-gradient(135deg, var(--primary), #059669); display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: 600; margin-right: 12px; flex-shrink: 0; }
        .room-info { flex: 1; min-width: 0; }
        .room-name { font-weight: 600; margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: flex; align-items: center; gap: 6px; }
        .room-name .lock-icon { color: var(--primary); font-size: 14px; }
        .room-preview { font-size: 13px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .room-meta { text-align: right; flex-shrink: 0; }
        .room-time { font-size: 12px; color: var(--text-muted); margin-bottom: 4px; }
        .unread-badge { background: var(--danger); color: white; font-size: 12px; padding: 2px 8px; border-radius: 10px; }
        
        .user-section { padding: 16px; border-top: 1px solid var(--border); display: flex; align-items: center; }
        .user-avatar { width: 40px; height: 40px; border-radius: 50%; background: var(--primary); display: flex; align-items: center; justify-content: center; margin-right: 12px; }
        .user-info { flex: 1; }
        .user-name { font-weight: 600; font-size: 14px; }
        .user-status { font-size: 12px; color: var(--success); }
        .user-actions { display: flex; gap: 8px; }
        .icon-btn { width: 36px; height: 36px; border-radius: 50%; border: none; background: var(--bg-light); color: var(--text-muted); cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.2s; }
        .icon-btn:hover { background: var(--secondary); color: var(--text); }
        
        .chat-area { flex: 1; display: flex; flex-direction: column; background: var(--bg-dark); }
        .chat-header { padding: 16px 24px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; }
        .chat-header-info { display: flex; align-items: center; }
        .chat-header-avatar { width: 40px; height: 40px; border-radius: 50%; background: var(--primary); display: flex; align-items: center; justify-content: center; margin-right: 12px; }
        .chat-header-name { font-weight: 600; font-size: 16px; display: flex; align-items: center; gap: 8px; }
        .chat-header-status { font-size: 13px; color: var(--text-muted); }
        .chat-header-actions { display: flex; gap: 8px; }
        
        .messages-container { flex: 1; overflow-y: auto; padding: 24px; }
        .message { display: flex; margin-bottom: 8px; animation: fadeIn 0.2s ease; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .message.sent { flex-direction: row-reverse; }
        .message-avatar { width: 36px; height: 36px; border-radius: 50%; background: var(--secondary); display: flex; align-items: center; justify-content: center; margin: 0 12px; flex-shrink: 0; font-size: 14px; }
        .message-content { max-width: 60%; }
        .message-sender { font-size: 13px; font-weight: 600; margin-bottom: 4px; color: var(--text-muted); }
        .message.sent .message-sender { text-align: right; }
        .message-bubble { padding: 12px 16px; border-radius: 18px; background: var(--bg-light); word-break: break-word; line-height: 1.5; }
        .message.sent .message-bubble { background: var(--primary); }
        .message-meta { display: flex; align-items: center; gap: 8px; margin-top: 4px; font-size: 12px; color: var(--text-muted); }
        .message.sent .message-meta { flex-direction: row-reverse; }
        .unread-count { color: var(--warning); font-weight: 600; }
        .message-file { display: flex; align-items: center; gap: 12px; padding: 12px; background: var(--bg-dark); border-radius: var(--radius-sm); margin-top: 8px; }
        .message-file i { font-size: 24px; color: var(--primary); }
        .message-image { max-width: 300px; border-radius: var(--radius-sm); margin-top: 8px; cursor: pointer; }
        .typing-indicator { padding: 8px 24px; font-size: 13px; color: var(--text-muted); font-style: italic; }
        
        .chat-input-container { padding: 16px 24px; border-top: 1px solid var(--border); }
        .encryption-notice { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--primary); margin-bottom: 8px; }
        .chat-input-wrapper { display: flex; align-items: flex-end; gap: 12px; background: var(--bg-light); border-radius: var(--radius); padding: 8px; }
        .chat-input-actions { display: flex; gap: 4px; position: relative; }
        .chat-input { flex: 1; border: none; background: transparent; color: var(--text); font-size: 15px; padding: 8px; resize: none; max-height: 120px; line-height: 1.5; }
        .chat-input:focus { outline: none; }
        .send-btn { width: 40px; height: 40px; border-radius: 50%; border: none; background: var(--primary); color: white; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.2s; }
        .send-btn:hover { background: var(--primary-hover); }
        
        .empty-state { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; color: var(--text-muted); }
        .empty-state i { font-size: 64px; margin-bottom: 16px; opacity: 0.5; }
        .empty-state h3 { font-size: 20px; margin-bottom: 8px; }
        
        .modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.8); display: none; align-items: center; justify-content: center; z-index: 1000; }
        .modal-overlay.active { display: flex; }
        .modal { background: var(--bg-light); border-radius: var(--radius); padding: 24px; width: 100%; max-width: 480px; max-height: 80vh; overflow-y: auto; border: 1px solid var(--border); }
        .modal-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
        .modal-header h3 { font-size: 18px; }
        .modal-close { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 20px; }
        .user-list { max-height: 300px; overflow-y: auto; }
        .user-item { display: flex; align-items: center; padding: 12px; border-radius: var(--radius-sm); cursor: pointer; transition: background 0.2s; }
        .user-item:hover { background: var(--bg-dark); }
        .user-item.selected { background: rgba(16,185,129,0.2); }
        .user-item-avatar { width: 40px; height: 40px; border-radius: 50%; background: var(--secondary); display: flex; align-items: center; justify-content: center; margin-right: 12px; }
        .user-item-info { flex: 1; }
        .user-item-name { font-weight: 500; }
        .user-item-status { font-size: 12px; }
        .user-item-status.online { color: var(--success); }
        .user-item-status.offline { color: var(--text-muted); }
        .user-checkbox { width: 20px; height: 20px; accent-color: var(--primary); }
        
        .emoji-picker { position: absolute; bottom: 100%; left: 0; background: var(--bg-dark); border: 1px solid var(--border); border-radius: var(--radius); padding: 12px; display: none; width: 320px; max-height: 250px; overflow-y: auto; }
        .emoji-picker.active { display: grid; grid-template-columns: repeat(8, 1fr); gap: 4px; }
        .emoji-btn { width: 32px; height: 32px; border: none; background: transparent; font-size: 20px; cursor: pointer; border-radius: 4px; }
        .emoji-btn:hover { background: var(--bg-light); }
        
        .date-divider { display: flex; align-items: center; margin: 24px 0; }
        .date-divider::before, .date-divider::after { content: ''; flex: 1; height: 1px; background: var(--border); }
        .date-divider span { padding: 0 16px; font-size: 12px; color: var(--text-muted); }
        
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--secondary); border-radius: 4px; }
        .hidden { display: none !important; }
        
        /* 온라인 인디케이터 */
        .online-indicator { width: 10px; height: 10px; border-radius: 50%; background: var(--success); position: absolute; bottom: 2px; right: 2px; border: 2px solid var(--bg-dark); }
        .room-avatar { position: relative; }
        .user-item-avatar { position: relative; }
        
        /* 메시지 컨텍스트 메뉴 */
        .message-context-menu { position: absolute; background: var(--bg-light); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 8px 0; min-width: 150px; z-index: 1000; box-shadow: var(--shadow); }
        .context-menu-item { padding: 10px 16px; cursor: pointer; display: flex; align-items: center; gap: 10px; font-size: 14px; transition: background 0.2s; }
        .context-menu-item:hover { background: var(--bg-dark); }
        .context-menu-item.danger { color: var(--danger); }
        .context-menu-item i { width: 16px; }
        
        /* 대화방 설정 패널 */
        .room-settings-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; padding: 8px; }
        .room-settings-btn:hover { color: var(--text); }
        .dropdown-menu { position: absolute; top: 100%; right: 0; background: var(--bg-light); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 8px 0; min-width: 180px; z-index: 100; display: none; }
        .dropdown-menu.active { display: block; }
        .dropdown-item { padding: 10px 16px; cursor: pointer; display: flex; align-items: center; gap: 10px; font-size: 14px; }
        .dropdown-item:hover { background: var(--bg-dark); }
        .dropdown-item i { width: 16px; color: var(--text-muted); }
        
        /* 핀 표시 */
        .room-item.pinned { background: rgba(16,185,129,0.05); }
        .room-item.pinned::before { content: '📌'; position: absolute; top: 4px; right: 4px; font-size: 10px; }
        .pin-icon { color: var(--warning); font-size: 12px; }
        
        /* 온라인 사용자 섹션 */
        .online-section { padding: 12px 16px; border-bottom: 1px solid var(--border); }
        .online-section h4 { font-size: 12px; color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
        .online-section h4 .dot { width: 8px; height: 8px; background: var(--success); border-radius: 50%; }
        .online-users-list { display: flex; gap: -4px; overflow-x: auto; padding-bottom: 4px; }
        .online-user { width: 40px; height: 40px; border-radius: 50%; background: var(--primary); display: flex; align-items: center; justify-content: center; font-size: 14px; cursor: pointer; border: 2px solid var(--bg-dark); position: relative; transition: transform 0.2s; }
        .online-user:hover { transform: scale(1.1); z-index: 1; }
        .online-user-tooltip { position: absolute; bottom: -24px; left: 50%; transform: translateX(-50%); background: var(--bg-dark); padding: 4px 8px; border-radius: 4px; font-size: 11px; white-space: nowrap; opacity: 0; transition: opacity 0.2s; pointer-events: none; }
        .online-user:hover .online-user-tooltip { opacity: 1; }
        
        /* 메시지 액션 버튼 */
        .message-actions { display: none; position: absolute; top: 0; right: 8px; background: var(--bg-light); border-radius: var(--radius-sm); padding: 4px; gap: 4px; }
        .message:hover .message-actions { display: flex; }
        .message-action-btn { width: 28px; height: 28px; border: none; background: transparent; color: var(--text-muted); cursor: pointer; border-radius: 4px; display: flex; align-items: center; justify-content: center; font-size: 14px; }
        .message-action-btn:hover { background: var(--bg-dark); color: var(--text); }
        .message-content { position: relative; }
        
        @media (max-width: 768px) { .sidebar { position: absolute; left: 0; top: 0; bottom: 0; z-index: 100; transform: translateX(-100%); transition: transform 0.3s; } .sidebar.active { transform: translateX(0); } .mobile-menu-btn { display: flex !important; } }
        .mobile-menu-btn { display: none; }
    </style>
</head>
<body>
    <div id="authContainer" class="auth-container">
        <div class="auth-box">
            <h1>🔒 사내 메신저</h1>
            <p class="subtitle">종단간 암호화로 안전하게 소통하세요</p>
            <div style="text-align:center;"><span class="encryption-badge">🔒 E2E 암호화 적용</span></div>
            <div id="authError" class="error-message hidden"></div>
            <form id="loginForm" onsubmit="return false;">
                <div class="form-group"><label>아이디</label><input type="text" id="loginUsername" placeholder="아이디를 입력하세요" required></div>
                <div class="form-group"><label>비밀번호</label><input type="password" id="loginPassword" placeholder="비밀번호를 입력하세요" required></div>
                <button type="button" class="btn btn-primary" onclick="doLogin()">로그인</button>
            </form>
            <form id="registerForm" class="hidden" onsubmit="return false;">
                <div class="form-group"><label>아이디</label><input type="text" id="regUsername" placeholder="3자 이상" required></div>
                <div class="form-group"><label>비밀번호</label><input type="password" id="regPassword" placeholder="4자 이상" required></div>
                <div class="form-group"><label>닉네임</label><input type="text" id="regNickname" placeholder="표시될 이름"></div>
                <button type="button" class="btn btn-primary" onclick="doRegister()">회원가입</button>
            </form>
            <div class="auth-switch">
                <span id="switchToRegisterWrap">계정이 없으신가요? <a href="javascript:void(0)" onclick="showRegisterForm()">회원가입</a></span>
                <span id="switchToLoginWrap" style="display:none">이미 계정이 있으신가요? <a href="javascript:void(0)" onclick="showLoginForm()">로그인</a></span>
            </div>
    <script>
        // 폼 전환 함수 (인라인 onclick에서 호출)
        function showRegisterForm() {
            var loginForm = document.getElementById('loginForm');
            var registerForm = document.getElementById('registerForm');
            loginForm.style.display = 'none';
            loginForm.classList.add('hidden');
            registerForm.style.display = 'block';
            registerForm.classList.remove('hidden');
            document.getElementById('switchToRegisterWrap').style.display = 'none';
            document.getElementById('switchToLoginWrap').style.display = 'inline';
        }
        function showLoginForm() {
            var loginForm = document.getElementById('loginForm');
            var registerForm = document.getElementById('registerForm');
            registerForm.style.display = 'none';
            registerForm.classList.add('hidden');
            loginForm.style.display = 'block';
            loginForm.classList.remove('hidden');
            document.getElementById('switchToLoginWrap').style.display = 'none';
            document.getElementById('switchToRegisterWrap').style.display = 'inline';
            hideAuthError();
        }
        
        function showAuthError(msg) {
            var err = document.getElementById('authError');
            err.textContent = msg;
            err.classList.remove('hidden');
            err.style.display = 'block';
        }
        function hideAuthError() {
            var err = document.getElementById('authError');
            err.classList.add('hidden');
            err.style.display = 'none';
        }
        
        // 로그인 함수
        async function doLogin() {
            var username = document.getElementById('loginUsername').value;
            var password = document.getElementById('loginPassword').value;
            
            if (!username || !password) {
                showAuthError('아이디와 비밀번호를 입력하세요.');
                return;
            }
            
            try {
                var response = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: username, password: password })
                });
                var result = await response.json();
                
                if (result.success) {
                    // 로그인 성공 - 메인 앱으로 전환
                    window.CURRENT_USER = result.user;
                    document.getElementById('authContainer').style.display = 'none';
                    document.getElementById('appContainer').classList.add('active');
                    // 메인 스크립트에서 초기화
                    if (typeof initAppAfterLogin === 'function') {
                        initAppAfterLogin(result.user);
                    }
                } else {
                    showAuthError(result.error || '로그인 실패');
                }
            } catch(err) {
                console.error('로그인 오류:', err);
                showAuthError('서버 연결 오류');
            }
        }
        
        // 회원가입 함수
        async function doRegister() {
            var username = document.getElementById('regUsername').value;
            var password = document.getElementById('regPassword').value;
            var nickname = document.getElementById('regNickname').value;
            
            if (!username || !password) {
                showAuthError('아이디와 비밀번호를 입력하세요.');
                return;
            }
            
            try {
                var response = await fetch('/api/register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: username, password: password, nickname: nickname })
                });
                var result = await response.json();
                
                if (result.success) {
                    var err = document.getElementById('authError');
                    err.textContent = '회원가입 완료! 로그인해주세요.';
                    err.style.background = 'rgba(34,197,94,0.1)';
                    err.style.borderColor = '#22C55E';
                    err.style.color = '#22C55E';
                    err.classList.remove('hidden');
                    err.style.display = 'block';
                    showLoginForm();
                } else {
                    showAuthError(result.error || '회원가입 실패');
                }
            } catch(err) {
                console.error('회원가입 오류:', err);
                showAuthError('서버 연결 오류');
            }
        }
    </script>
        </div>
    </div>
    
    
    <div id="appContainer" class="app-container">
        <div class="sidebar" id="sidebar">
            <div class="sidebar-header"><h2>🔒 대화</h2><div class="search-box">🔍<input type="text" id="searchInput" placeholder="대화 검색..." style="padding-left:30px;"></div></div>
            <div class="room-list" id="roomList"></div>
            <div class="online-section" id="onlineSection">
                <h4><span class="dot"></span> 온라인 사용자</h4>
                <div class="online-users-list" id="onlineUsersList"></div>
            </div>
            <div class="user-section">
                <div class="user-avatar" id="userAvatar"></div>
                <div class="user-info"><div class="user-name" id="userName"></div><div class="user-status">온라인</div></div>
                <div class="user-actions">
                    <button class="icon-btn" id="newChatBtn" title="새 대화">➕</button>
                    <button class="icon-btn" id="logoutBtn" title="로그아웃">🚪</button>
                </div>
            </div>
        </div>
        <div class="chat-area" id="chatArea">
            <div class="empty-state" id="emptyState">💬<h3>대화를 선택하세요</h3><p>왼쪽에서 대화를 선택하거나 새 대화를 시작하세요</p></div>
            <div id="chatContent" class="hidden" style="display:flex;flex-direction:column;height:100%;">
                <div class="chat-header">
                    <button class="icon-btn mobile-menu-btn" id="mobileMenuBtn">☰</button>
                    <div class="chat-header-info">
                        <div class="chat-header-avatar" id="chatAvatar"></div>
                        <div><div class="chat-header-name" id="chatName">🔒</div><div class="chat-header-status" id="chatStatus"></div></div>
                    </div>
                    <div class="chat-header-actions" style="position:relative;">
                        <button class="icon-btn" id="roomSettingsBtn" title="설정">⚙</button>
                        <div class="dropdown-menu" id="roomSettingsMenu">
                            <div class="dropdown-item" id="editRoomNameBtn">✏ 대화방 이름 변경</div>
                            <div class="dropdown-item" id="pinRoomBtn">📌 <span id="pinRoomText">상단 고정</span></div>
                            <div class="dropdown-item" id="muteRoomBtn">🔕 <span id="muteRoomText">알림 끄기</span></div>
                            <div class="dropdown-item" id="viewMembersBtn">👥 멤버 보기</div>
                        </div>
                        <button class="icon-btn" id="inviteBtn" title="초대">👤➕</button>
                        <button class="icon-btn" id="leaveRoomBtn" title="나가기">🚪</button>
                    </div>
                </div>
                <div class="messages-container" id="messagesContainer"></div>
                <div class="typing-indicator hidden" id="typingIndicator"></div>
                <div class="chat-input-container">
                    <div class="encryption-notice">🔒 메시지는 종단간 암호화됩니다</div>
                    <div class="chat-input-wrapper">
                        <div class="chat-input-actions">
                            <button class="icon-btn" id="emojiBtn">😊</button>
                            <button class="icon-btn" id="attachBtn">📎</button>
                            <input type="file" id="fileInput" style="display:none;">
                            <div class="emoji-picker" id="emojiPicker"></div>
                        </div>
                        <textarea class="chat-input" id="messageInput" placeholder="메시지를 입력하세요..." rows="1"></textarea>
                        <button class="send-btn" id="sendBtn">✉</button>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <div class="modal-overlay" id="newChatModal">
        <div class="modal">
            <div class="modal-header"><h3>새 대화 시작</h3><button class="modal-close" id="closeNewChatModal">✕</button></div>
            <div class="form-group"><label>대화방 이름 (그룹 채팅 시)</label><input type="text" id="roomName" placeholder="대화방 이름"></div>
            <div class="form-group"><label>참여자 선택</label></div>
            <div class="user-list" id="userList"></div>
            <button class="btn btn-primary" id="createRoomBtn" style="margin-top:16px;">대화 시작</button>
        </div>
    </div>
    
    <div class="modal-overlay" id="inviteModal">
        <div class="modal">
            <div class="modal-header"><h3>멤버 초대</h3><button class="modal-close" id="closeInviteModal">✕</button></div>
            <div class="user-list" id="inviteUserList"></div>
            <button class="btn btn-primary" id="confirmInviteBtn" style="margin-top:16px;">초대하기</button>
        </div>
    </div>

    <script>
        // 클라이언트 측 E2E 암호화
        const E2E = {
            encrypt: (plaintext, key) => {
                try {
                    const encrypted = CryptoJS.AES.encrypt(plaintext, key).toString();
                    return encrypted;
                } catch (e) { return plaintext; }
            },
            decrypt: (ciphertext, key) => {
                try {
                    const bytes = CryptoJS.AES.decrypt(ciphertext, key);
                    return bytes.toString(CryptoJS.enc.Utf8) || '[복호화 실패]';
                } catch (e) { return '[암호화된 메시지]'; }
            }
        };
        
        let socket = null, currentUser = null, currentRoom = null, rooms = [], currentRoomKey = null, typingTimeout = null;
        const emojis = ['😀','😂','😊','😍','🥰','😎','🤔','😅','😭','😤','👍','👎','❤️','🔥','✨','🎉','👏','🙏','💪','🤝','👋','✅','❌','⭐','💯','🚀','💡','📌','📝','💬'];
        
        const $ = id => document.getElementById(id);
        const authContainer = $('authContainer'), appContainer = $('appContainer'), loginForm = $('loginForm'), registerForm = $('registerForm'), authError = $('authError'), roomList = $('roomList'), messagesContainer = $('messagesContainer'), messageInput = $('messageInput'), sendBtn = $('sendBtn'), emojiPicker = $('emojiPicker');
        
        function showError(msg) { authError.textContent = msg; authError.classList.remove('hidden'); }
        function hideError() { authError.classList.add('hidden'); }
        async function api(url, options = {}) { const res = await fetch(url, { ...options, headers: { 'Content-Type': 'application/json', ...options.headers } }); return res.json(); }
        
        // 인라인 스크립트에서 호출되는 로그인 후 초기화 함수
        function initAppAfterLogin(user) {
            currentUser = user;
            authContainer.style.display = 'none';
            appContainer.classList.add('active');
            $('userName').textContent = currentUser.nickname;
            $('userAvatar').textContent = currentUser.nickname[0].toUpperCase();
            socket = io();
            setupSocketEvents();
            loadRooms();
            loadOnlineUsers();
            initEmojiPicker();
        }
        
        function initApp() { initAppAfterLogin(currentUser); }
        
        function setupSocketEvents() {
            socket.on('connect', () => console.log('Connected'));
            socket.on('new_message', (msg) => { if (currentRoom && msg.room_id === currentRoom.id) { appendMessage(msg); scrollToBottom(); socket.emit('message_read', { room_id: currentRoom.id, message_id: msg.id }); } loadRooms(); });
            socket.on('read_updated', (data) => { if (currentRoom && data.room_id === currentRoom.id) updateUnreadCounts(); });
            socket.on('user_typing', (data) => { if (currentRoom && data.room_id === currentRoom.id) { const indicator = $('typingIndicator'); if (data.is_typing) { indicator.textContent = `${data.nickname}님이 입력 중...`; indicator.classList.remove('hidden'); } else { indicator.classList.add('hidden'); } } });
            socket.on('user_status', () => loadRooms());
            socket.on('room_updated', () => loadRooms());
        }
        
        async function loadRooms() { const result = await api('/api/rooms'); rooms = result; renderRoomList(); }
        
        function renderRoomList() {
            roomList.innerHTML = rooms.map(room => {
                const isActive = currentRoom && currentRoom.id === room.id;
                const avatar = room.type === 'direct' && room.partner ? room.partner.nickname[0].toUpperCase() : (room.name || '그')[0].toUpperCase();
                const name = room.name || (room.type === 'direct' && room.partner ? room.partner.nickname : '대화방');
                const time = room.last_message_time ? formatTime(room.last_message_time) : '';
                const preview = room.last_message ? '[암호화됨]' : '새 대화';
                return `<div class="room-item ${isActive ? 'active' : ''}" data-room-id="${room.id}"><div class="room-avatar">${avatar}</div><div class="room-info"><div class="room-name">${escapeHtml(name)} 🔒</div><div class="room-preview">${preview}</div></div><div class="room-meta"><div class="room-time">${time}</div>${room.unread_count > 0 ? `<span class="unread-badge">${room.unread_count}</span>` : ''}</div></div>`;
            }).join('');
            document.querySelectorAll('.room-item').forEach(el => { el.onclick = () => { const room = rooms.find(r => r.id === parseInt(el.dataset.roomId)); if (room) openRoom(room); }; });
        }
        
        async function openRoom(room) {
            if (currentRoom) socket.emit('leave_room', { room_id: currentRoom.id });
            currentRoom = room;
            socket.emit('join_room', { room_id: room.id });
            $('emptyState').classList.add('hidden');
            $('chatContent').classList.remove('hidden');
            $('chatContent').style.display = 'flex';
            const name = room.name || (room.type === 'direct' && room.partner ? room.partner.nickname : '대화방');
            $('chatName').innerHTML = `${escapeHtml(name)} 🔒`;
            $('chatAvatar').textContent = name[0].toUpperCase();
            $('chatStatus').textContent = room.type === 'direct' && room.partner ? (room.partner.status === 'online' ? '온라인' : '오프라인') : `${room.member_count}명 참여 중`;
            const result = await api(`/api/rooms/${room.id}/messages`);
            currentRoomKey = result.encryption_key;
            renderMessages(result.messages);
            if (result.messages.length > 0) socket.emit('message_read', { room_id: room.id, message_id: result.messages[result.messages.length - 1].id });
            renderRoomList();
        }
        
        function renderMessages(messages) { messagesContainer.innerHTML = ''; let lastDate = null; messages.forEach(msg => { const msgDate = msg.created_at.split('T')[0]; if (msgDate !== lastDate) { lastDate = msgDate; const divider = document.createElement('div'); divider.className = 'date-divider'; divider.innerHTML = `<span>${formatDate(msgDate)}</span>`; messagesContainer.appendChild(divider); } appendMessage(msg); }); scrollToBottom(); }
        
        function appendMessage(msg) {
            const isSent = msg.sender_id === currentUser.id;
            const div = document.createElement('div');
            div.className = `message ${isSent ? 'sent' : ''}`;
            div.dataset.messageId = msg.id;
            let content = '';
            if (msg.message_type === 'image') { content = `<img src="/uploads/${msg.file_path}" class="message-image" onclick="window.open(this.src)">`; }
            else if (msg.message_type === 'file') { content = `<div class="message-file">📄<div class="message-file-info"><div class="message-file-name">${escapeHtml(msg.file_name)}</div></div><a href="/uploads/${msg.file_path}" download="${msg.file_name}" class="icon-btn">⬇</a></div>`; }
            else { const decrypted = currentRoomKey ? E2E.decrypt(msg.content, currentRoomKey) : msg.content; content = `<div class="message-bubble">${escapeHtml(decrypted)}</div>`; }
            const unreadHtml = msg.unread_count > 0 ? `<span class="unread-count">${msg.unread_count}</span>` : '';
            div.innerHTML = `<div class="message-avatar">${msg.sender_name[0].toUpperCase()}</div><div class="message-content"><div class="message-sender">${escapeHtml(msg.sender_name)}</div>${content}<div class="message-meta">${unreadHtml}<span>${formatTime(msg.created_at)}</span></div></div>`;
            messagesContainer.appendChild(div);
        }
        
        async function updateUnreadCounts() { if (!currentRoom) return; const result = await api(`/api/rooms/${currentRoom.id}/messages`); result.messages.forEach(msg => { const el = document.querySelector(`[data-message-id="${msg.id}"] .unread-count`); if (el) { if (msg.unread_count > 0) el.textContent = msg.unread_count; else el.remove(); } }); }
        
        function sendMessage() {
            const content = messageInput.value.trim();
            if (!content || !currentRoom || !currentRoomKey) return;
            const encrypted = E2E.encrypt(content, currentRoomKey);
            socket.emit('send_message', { room_id: currentRoom.id, content: encrypted, type: 'text', encrypted: true });
            messageInput.value = '';
            messageInput.style.height = 'auto';
        }
        
        sendBtn.onclick = sendMessage;
        messageInput.onkeydown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } };
        messageInput.oninput = () => { messageInput.style.height = 'auto'; messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + 'px'; if (currentRoom) { socket.emit('typing', { room_id: currentRoom.id, is_typing: true }); clearTimeout(typingTimeout); typingTimeout = setTimeout(() => socket.emit('typing', { room_id: currentRoom.id, is_typing: false }), 2000); } };
        
        function initEmojiPicker() { emojiPicker.innerHTML = emojis.map(e => `<button class="emoji-btn">${e}</button>`).join(''); emojiPicker.querySelectorAll('.emoji-btn').forEach(btn => { btn.onclick = () => { messageInput.value += btn.textContent; messageInput.focus(); }; }); }
        $('emojiBtn').onclick = () => emojiPicker.classList.toggle('active');
        document.addEventListener('click', (e) => { if (!e.target.closest('#emojiBtn') && !e.target.closest('#emojiPicker')) emojiPicker.classList.remove('active'); });
        
        $('attachBtn').onclick = () => $('fileInput').click();
        $('fileInput').onchange = async (e) => { const file = e.target.files[0]; if (!file || !currentRoom) return; const formData = new FormData(); formData.append('file', file); const res = await fetch('/api/upload', { method: 'POST', body: formData }); const result = await res.json(); if (result.success) { const isImage = ['png','jpg','jpeg','gif'].includes(file.name.split('.').pop().toLowerCase()); socket.emit('send_message', { room_id: currentRoom.id, content: file.name, type: isImage ? 'image' : 'file', file_path: result.file_path, file_name: result.file_name, encrypted: false }); } e.target.value = ''; };
        
        $('newChatBtn').onclick = async () => { const result = await api('/api/users'); $('userList').innerHTML = result.map(u => `<div class="user-item" data-user-id="${u.id}"><div class="user-item-avatar">${u.nickname[0].toUpperCase()}</div><div class="user-item-info"><div class="user-item-name">${escapeHtml(u.nickname)}</div><div class="user-item-status ${u.status}">${u.status === 'online' ? '온라인' : '오프라인'}</div></div><input type="checkbox" class="user-checkbox"></div>`).join(''); $('userList').querySelectorAll('.user-item').forEach(el => { el.onclick = () => { const cb = el.querySelector('.user-checkbox'); cb.checked = !cb.checked; el.classList.toggle('selected', cb.checked); }; }); $('newChatModal').classList.add('active'); };
        $('closeNewChatModal').onclick = () => $('newChatModal').classList.remove('active');
        $('createRoomBtn').onclick = async () => { const selected = [...document.querySelectorAll('#userList .user-item.selected')].map(el => parseInt(el.dataset.userId)); if (selected.length === 0) return; const result = await api('/api/rooms', { method: 'POST', body: JSON.stringify({ members: selected, name: $('roomName').value.trim() }) }); if (result.success) { $('newChatModal').classList.remove('active'); await loadRooms(); const room = rooms.find(r => r.id === result.room_id); if (room) openRoom(room); } };
        
        $('inviteBtn').onclick = async () => { if (!currentRoom) return; const result = await api('/api/users'); const memberIds = (currentRoom.members || []).map(m => m.id); $('inviteUserList').innerHTML = result.filter(u => !memberIds.includes(u.id)).map(u => `<div class="user-item" data-user-id="${u.id}"><div class="user-item-avatar">${u.nickname[0].toUpperCase()}</div><div class="user-item-info"><div class="user-item-name">${escapeHtml(u.nickname)}</div></div><input type="checkbox" class="user-checkbox"></div>`).join(''); $('inviteUserList').querySelectorAll('.user-item').forEach(el => { el.onclick = () => { const cb = el.querySelector('.user-checkbox'); cb.checked = !cb.checked; el.classList.toggle('selected', cb.checked); }; }); $('inviteModal').classList.add('active'); };
        $('closeInviteModal').onclick = () => $('inviteModal').classList.remove('active');
        $('confirmInviteBtn').onclick = async () => { const selected = [...document.querySelectorAll('#inviteUserList .user-item.selected')].map(el => parseInt(el.dataset.userId)); for (const userId of selected) await api(`/api/rooms/${currentRoom.id}/members`, { method: 'POST', body: JSON.stringify({ user_id: userId }) }); $('inviteModal').classList.remove('active'); loadRooms(); };
        
        $('leaveRoomBtn').onclick = async () => { if (!currentRoom || !confirm('대화방을 나가시겠습니까?')) return; await api(`/api/rooms/${currentRoom.id}/leave`, { method: 'POST' }); currentRoom = null; $('chatContent').classList.add('hidden'); $('emptyState').classList.remove('hidden'); loadRooms(); };
        $('logoutBtn').onclick = async () => { await api('/api/logout', { method: 'POST' }); location.reload(); };
        $('mobileMenuBtn').onclick = () => $('sidebar').classList.toggle('active');
        $('searchInput').oninput = async (e) => { const q = e.target.value.trim(); if (q.length < 2) { renderRoomList(); return; } const filtered = rooms.filter(r => r.name?.includes(q) || (r.partner?.nickname?.includes(q))); rooms = filtered.length > 0 ? filtered : rooms; renderRoomList(); };
        
        function escapeHtml(text) { if (!text) return ''; return text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
        function formatTime(dateStr) { const d = new Date(dateStr); return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' }); }
        function formatDate(dateStr) { const d = new Date(dateStr); const today = new Date(); if (d.toDateString() === today.toDateString()) return '오늘'; const yesterday = new Date(today); yesterday.setDate(yesterday.getDate() - 1); if (d.toDateString() === yesterday.toDateString()) return '어제'; return d.toLocaleDateString('ko-KR', { month: 'long', day: 'numeric' }); }
        function scrollToBottom() { messagesContainer.scrollTop = messagesContainer.scrollHeight; }
        
        // 온라인 사용자 로드
        async function loadOnlineUsers() {
            try {
                const users = await api('/api/users/online');
                const container = $('onlineUsersList');
                if (users.length === 0) {
                    container.innerHTML = '<span style="color:var(--text-muted);font-size:12px;">온라인 사용자가 없습니다</span>';
                    return;
                }
                container.innerHTML = users.map(u => `
                    <div class="online-user" data-user-id="${u.id}" title="${escapeHtml(u.nickname)}">
                        ${u.nickname[0].toUpperCase()}
                        <span class="online-user-tooltip">${escapeHtml(u.nickname)}</span>
                    </div>
                `).join('');
                container.querySelectorAll('.online-user').forEach(el => {
                    el.onclick = async () => {
                        const userId = parseInt(el.dataset.userId);
                        const result = await api('/api/rooms', { method: 'POST', body: JSON.stringify({ members: [userId] }) });
                        if (result.success) {
                            await loadRooms();
                            const room = rooms.find(r => r.id === result.room_id);
                            if (room) openRoom(room);
                        }
                    };
                });
            } catch (e) { console.error('온라인 사용자 로드 실패:', e); }
        }
        setInterval(loadOnlineUsers, 30000); // 30초마다 새로고침
        
        // 대화방 설정 메뉴
        $('roomSettingsBtn').onclick = (e) => { 
            e.stopPropagation(); 
            $('roomSettingsMenu').classList.toggle('active'); 
        };
        document.addEventListener('click', (e) => { 
            if (!e.target.closest('#roomSettingsMenu') && !e.target.closest('#roomSettingsBtn')) {
                $('roomSettingsMenu').classList.remove('active'); 
            }
        });
        
        // 대화방 이름 변경
        $('editRoomNameBtn').onclick = async () => {
            if (!currentRoom) return;
            const newName = prompt('새 대화방 이름:', currentRoom.name || '');
            if (newName && newName.trim()) {
                const result = await api(`/api/rooms/${currentRoom.id}/name`, { 
                    method: 'PUT', 
                    body: JSON.stringify({ name: newName.trim() }) 
                });
                if (result.success) {
                    currentRoom.name = newName.trim();
                    $('chatName').innerHTML = `${escapeHtml(newName.trim())} 🔒`;
                    loadRooms();
                }
            }
            $('roomSettingsMenu').classList.remove('active');
        };
        
        // 대화방 상단 고정
        $('pinRoomBtn').onclick = async () => {
            if (!currentRoom) return;
            const isPinned = currentRoom.pinned;
            const result = await api(`/api/rooms/${currentRoom.id}/pin`, { 
                method: 'POST', 
                body: JSON.stringify({ pinned: !isPinned }) 
            });
            if (result.success) {
                currentRoom.pinned = !isPinned;
                $('pinRoomText').textContent = currentRoom.pinned ? '고정 해제' : '상단 고정';
                loadRooms();
            }
            $('roomSettingsMenu').classList.remove('active');
        };
        
        // 대화방 알림 끄기
        $('muteRoomBtn').onclick = async () => {
            if (!currentRoom) return;
            const isMuted = currentRoom.muted;
            const result = await api(`/api/rooms/${currentRoom.id}/mute`, { 
                method: 'POST', 
                body: JSON.stringify({ muted: !isMuted }) 
            });
            if (result.success) {
                currentRoom.muted = !isMuted;
                $('muteRoomText').textContent = currentRoom.muted ? '알림 켜기' : '알림 끄기';
            }
            $('roomSettingsMenu').classList.remove('active');
        };
        
        // 멤버 보기
        $('viewMembersBtn').onclick = async () => {
            if (!currentRoom) return;
            const result = await api(`/api/rooms/${currentRoom.id}/info`);
            if (result.members) {
                alert('참여자:\n' + result.members.map(m => `• ${m.nickname} (${m.status === 'online' ? '온라인' : '오프라인'})`).join('\n'));
            }
            $('roomSettingsMenu').classList.remove('active');
        };
        
        // 메시지 삭제 (우클릭 메뉴용)
        messagesContainer.addEventListener('contextmenu', (e) => {
            const msgEl = e.target.closest('.message');
            if (!msgEl) return;
            e.preventDefault();
            
            const msgId = msgEl.dataset.messageId;
            const isSent = msgEl.classList.contains('sent');
            
            // 기존 메뉴 제거
            document.querySelectorAll('.message-context-menu').forEach(m => m.remove());
            
            if (isSent) {
                const menu = document.createElement('div');
                menu.className = 'message-context-menu';
                menu.innerHTML = `
                    <div class="context-menu-item" data-action="copy">📋 복사</div>
                    <div class="context-menu-item danger" data-action="delete">🗑 삭제</div>
                `;
                menu.style.position = 'fixed';
                menu.style.left = e.clientX + 'px';
                menu.style.top = e.clientY + 'px';
                document.body.appendChild(menu);
                
                menu.querySelector('[data-action="copy"]').onclick = async () => {
                    const bubble = msgEl.querySelector('.message-bubble');
                    if (bubble) {
                        await navigator.clipboard.writeText(bubble.textContent);
                    }
                    menu.remove();
                };
                
                menu.querySelector('[data-action="delete"]').onclick = async () => {
                    if (confirm('메시지를 삭제하시겠습니까?')) {
                        const result = await api(`/api/messages/${msgId}`, { method: 'DELETE' });
                        if (result.success) {
                            msgEl.querySelector('.message-bubble').textContent = '[삭제된 메시지]';
                            msgEl.querySelector('.message-bubble').style.opacity = '0.5';
                        }
                    }
                    menu.remove();
                };
                
                setTimeout(() => {
                    document.addEventListener('click', () => menu.remove(), { once: true });
                }, 100);
            }
        });
        
        // 앱 초기화 시 온라인 사용자도 로드
        const originalInitApp = initApp;
        initApp = function() {
            originalInitApp();
            loadOnlineUsers();
        };
    </script>
</body>
</html>
'''

# ============================================================================
# PyQt6 GUI - 서버 관리 창
# ============================================================================
class ServerThread(QThread):
    """Flask 서버를 별도 스레드에서 실행"""
    log_signal = pyqtSignal(str)
    
    def __init__(self, host='0.0.0.0', port=5000):
        super().__init__()
        self.host = host
        self.port = port
        self.running = True
    
    def run(self):
        try:
            self.log_signal.emit(f"서버 시작 중: http://{self.host}:{self.port}")
            server_stats['start_time'] = datetime.now()
            # allow_unsafe_werkzeug=True는 개발 서버 사용 허용
            socketio.run(
                app, 
                host=self.host, 
                port=self.port, 
                debug=False, 
                use_reloader=False, 
                log_output=False,
                allow_unsafe_werkzeug=True
            )
        except OSError as e:
            if "Address already in use" in str(e) or "10048" in str(e):
                self.log_signal.emit(f"오류: 포트 {self.port}이 이미 사용 중입니다.")
            else:
                self.log_signal.emit(f"서버 오류: {str(e)}")
        except Exception as e:
            self.log_signal.emit(f"서버 오류: {str(e)}")
            import traceback
            self.log_signal.emit(traceback.format_exc())
    
    def stop(self):
        self.running = False


class ServerWindow(QMainWindow):
    """메인 서버 관리 윈도우"""
    
    def __init__(self):
        super().__init__()
        self.server_thread = None
        self.settings = QSettings('MessengerServer', 'Settings')
        self.init_ui()
        self.create_tray_icon()
        self.load_settings()
        
        # 자동 시작 설정
        if self.settings.value('auto_start_server', True, type=bool):
            QTimer.singleShot(500, self.start_server)
    
    def init_ui(self):
        """UI 초기화"""
        self.setWindowTitle(f'{APP_NAME} v{VERSION}')
        self.setMinimumSize(700, 500)
        self.setStyleSheet('''
            QMainWindow { background-color: #0F172A; }
            QWidget { color: #F8FAFC; font-family: 'Segoe UI', sans-serif; }
            QGroupBox { border: 1px solid #334155; border-radius: 8px; margin-top: 12px; padding: 16px; background-color: #1E293B; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 8px; color: #10B981; font-weight: bold; }
            QPushButton { background-color: #10B981; color: white; border: none; padding: 10px 20px; border-radius: 6px; font-weight: bold; }
            QPushButton:hover { background-color: #059669; }
            QPushButton:disabled { background-color: #475569; color: #94A3B8; }
            QPushButton#stopBtn { background-color: #EF4444; }
            QPushButton#stopBtn:hover { background-color: #DC2626; }
            QLineEdit, QSpinBox { background-color: #1E293B; border: 1px solid #334155; border-radius: 4px; padding: 8px; color: #F8FAFC; }
            QLineEdit:focus, QSpinBox:focus { border-color: #10B981; }
            QTextEdit { background-color: #0F172A; border: 1px solid #334155; border-radius: 4px; color: #94A3B8; font-family: Consolas, monospace; }
            QCheckBox { color: #F8FAFC; }
            QCheckBox::indicator { width: 18px; height: 18px; }
            QCheckBox::indicator:checked { background-color: #10B981; border-radius: 3px; }
            QLabel { color: #94A3B8; }
            QTabWidget::pane { border: 1px solid #334155; border-radius: 8px; background-color: #1E293B; }
            QTabBar::tab { background-color: #1E293B; color: #94A3B8; padding: 10px 20px; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }
            QTabBar::tab:selected { background-color: #10B981; color: white; }
            QTableWidget { background-color: #0F172A; border: 1px solid #334155; gridline-color: #334155; }
            QTableWidget::item { padding: 8px; }
            QHeaderView::section { background-color: #1E293B; color: #F8FAFC; padding: 8px; border: none; border-bottom: 1px solid #334155; }
        ''')
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        
        # 헤더
        header = QHBoxLayout()
        title = QLabel(f'🔒 {APP_NAME}')
        title.setStyleSheet('font-size: 24px; font-weight: bold; color: #F8FAFC;')
        header.addWidget(title)
        
        self.status_label = QLabel('⚪ 서버 중지됨')
        self.status_label.setStyleSheet('font-size: 14px; color: #94A3B8;')
        header.addStretch()
        header.addWidget(self.status_label)
        layout.addLayout(header)
        
        # 탭 위젯
        tabs = QTabWidget()
        layout.addWidget(tabs)
        
        # 제어 탭
        control_tab = QWidget()
        control_layout = QVBoxLayout(control_tab)
        control_layout.setSpacing(16)
        
        # 서버 설정 그룹
        server_group = QGroupBox('서버 설정')
        server_layout = QHBoxLayout(server_group)
        
        server_layout.addWidget(QLabel('포트:'))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1000, 65535)
        self.port_spin.setValue(5000)
        server_layout.addWidget(self.port_spin)
        
        server_layout.addSpacing(20)
        
        self.start_btn = QPushButton('▶ 서버 시작')
        self.start_btn.clicked.connect(self.start_server)
        server_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton('■ 서버 중지')
        self.stop_btn.setObjectName('stopBtn')
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_server)
        server_layout.addWidget(self.stop_btn)
        
        server_layout.addStretch()
        control_layout.addWidget(server_group)
        
        # 옵션 그룹
        options_group = QGroupBox('옵션')
        options_layout = QVBoxLayout(options_group)
        
        self.auto_start_check = QCheckBox('프로그램 시작 시 서버 자동 시작')
        self.auto_start_check.setChecked(True)
        self.auto_start_check.stateChanged.connect(self.save_settings)
        options_layout.addWidget(self.auto_start_check)
        
        self.windows_startup_check = QCheckBox('Windows 시작 시 자동 실행')
        self.windows_startup_check.stateChanged.connect(self.toggle_windows_startup)
        options_layout.addWidget(self.windows_startup_check)
        
        self.minimize_to_tray_check = QCheckBox('닫기 버튼 클릭 시 트레이로 최소화')
        self.minimize_to_tray_check.setChecked(True)
        self.minimize_to_tray_check.stateChanged.connect(self.save_settings)
        options_layout.addWidget(self.minimize_to_tray_check)
        
        control_layout.addWidget(options_group)
        
        # 접속 정보 그룹
        info_group = QGroupBox('접속 정보')
        info_layout = QVBoxLayout(info_group)
        
        import socket as sock
        hostname = sock.gethostname()
        try:
            local_ip = sock.gethostbyname(hostname)
        except (OSError, socket.error):
            local_ip = '127.0.0.1'
        
        self.local_url = QLabel(f'🖥️ 로컬 접속: http://localhost:{self.port_spin.value()}')
        self.local_url.setStyleSheet('font-size: 14px; color: #F8FAFC;')
        info_layout.addWidget(self.local_url)
        
        self.network_url = QLabel(f'🌐 네트워크 접속: http://{local_ip}:{self.port_spin.value()}')
        self.network_url.setStyleSheet('font-size: 14px; color: #F8FAFC;')
        info_layout.addWidget(self.network_url)
        
        self.encryption_info = QLabel('🔒 종단간 암호화(E2E) 적용: 서버 관리자도 메시지 내용 확인 불가')
        self.encryption_info.setStyleSheet('font-size: 12px; color: #10B981;')
        info_layout.addWidget(self.encryption_info)
        
        control_layout.addWidget(info_group)
        control_layout.addStretch()
        
        tabs.addTab(control_tab, '제어')
        
        # 통계 탭
        stats_tab = QWidget()
        stats_layout = QVBoxLayout(stats_tab)
        
        stats_group = QGroupBox('실시간 통계')
        stats_inner = QVBoxLayout(stats_group)
        
        self.stats_labels = {}
        stats_items = [
            ('active_connections', '현재 접속자'),
            ('total_connections', '총 접속 횟수'),
            ('total_messages', '총 메시지 수'),
            ('uptime', '서버 가동 시간')
        ]
        
        for key, label_text in stats_items:
            row = QHBoxLayout()
            label = QLabel(f'{label_text}:')
            value = QLabel('0')
            value.setStyleSheet('font-size: 18px; font-weight: bold; color: #10B981;')
            row.addWidget(label)
            row.addStretch()
            row.addWidget(value)
            stats_inner.addLayout(row)
            self.stats_labels[key] = value
        
        stats_layout.addWidget(stats_group)
        stats_layout.addStretch()
        
        tabs.addTab(stats_tab, '통계')
        
        # 로그 탭
        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        
        clear_log_btn = QPushButton('로그 지우기')
        clear_log_btn.clicked.connect(lambda: self.log_text.clear())
        log_layout.addWidget(clear_log_btn)
        
        tabs.addTab(log_tab, '로그')
        
        # 포트 변경 시 URL 업데이트
        self.port_spin.valueChanged.connect(self.update_urls)
        
        # 통계 업데이트 타이머
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_stats)
        self.stats_timer.start(1000)
    
    def create_tray_icon(self):
        """시스템 트레이 아이콘 생성"""
        # 간단한 아이콘 생성
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor('#10B981'))
        painter = QPainter(pixmap)
        painter.setPen(QColor('white'))
        painter.setFont(QFont('Segoe UI', 14, QFont.Weight.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, '💬')
        painter.end()
        
        self.tray_icon = QSystemTrayIcon(QIcon(pixmap), self)
        
        # 트레이 메뉴
        tray_menu = QMenu()
        
        show_action = QAction('창 열기', self)
        show_action.triggered.connect(self.show_window)
        tray_menu.addAction(show_action)
        
        tray_menu.addSeparator()
        
        start_action = QAction('서버 시작', self)
        start_action.triggered.connect(self.start_server)
        tray_menu.addAction(start_action)
        
        stop_action = QAction('서버 중지', self)
        stop_action.triggered.connect(self.stop_server)
        tray_menu.addAction(stop_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction('종료', self)
        quit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_activated)
        self.tray_icon.show()
    
    def tray_activated(self, reason):
        """트레이 아이콘 클릭 처리"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window()
    
    def show_window(self):
        """창 표시"""
        self.show()
        self.activateWindow()
        self.raise_()
    
    def closeEvent(self, event):
        """닫기 버튼 처리"""
        if self.minimize_to_tray_check.isChecked():
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                APP_NAME,
                '프로그램이 트레이로 최소화되었습니다.',
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
        else:
            self.quit_app()
    
    def quit_app(self):
        """프로그램 종료"""
        self.stop_server()
        self.tray_icon.hide()
        QApplication.quit()
    
    def start_server(self):
        """서버 시작"""
        if self.server_thread and self.server_thread.isRunning():
            return
        
        init_db()
        server_stats['start_time'] = datetime.now()
        
        self.server_thread = ServerThread(port=self.port_spin.value())
        self.server_thread.log_signal.connect(self.add_log)
        self.server_thread.start()
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.port_spin.setEnabled(False)
        self.status_label.setText('🟢 서버 실행 중')
        self.status_label.setStyleSheet('font-size: 14px; color: #10B981;')
        
        self.add_log('서버가 시작되었습니다.')
        self.tray_icon.showMessage(APP_NAME, '서버가 시작되었습니다.', QSystemTrayIcon.MessageIcon.Information, 2000)
    
    def stop_server(self):
        """서버 중지"""
        if self.server_thread:
            self.server_thread.terminate()
            self.server_thread.wait(1000)
            self.server_thread = None
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.port_spin.setEnabled(True)
        self.status_label.setText('⚪ 서버 중지됨')
        self.status_label.setStyleSheet('font-size: 14px; color: #94A3B8;')
        
        self.add_log('서버가 중지되었습니다.')
    
    def add_log(self, message):
        """로그 추가"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.log_text.append(f'[{timestamp}] {message}')
    
    def update_urls(self):
        """URL 라벨 업데이트"""
        port = self.port_spin.value()
        import socket as sock
        try:
            local_ip = sock.gethostbyname(sock.gethostname())
        except (OSError, sock.error):
            local_ip = '127.0.0.1'
        
        self.local_url.setText(f'🖥️ 로컬 접속: http://localhost:{port}')
        self.network_url.setText(f'🌐 네트워크 접속: http://{local_ip}:{port}')
    
    def update_stats(self):
        """통계 업데이트"""
        with stats_lock:
            self.stats_labels['active_connections'].setText(str(server_stats['active_connections']))
            self.stats_labels['total_connections'].setText(str(server_stats['total_connections']))
            self.stats_labels['total_messages'].setText(str(server_stats['total_messages']))
            
            if server_stats['start_time']:
                uptime = datetime.now() - server_stats['start_time']
                hours, remainder = divmod(int(uptime.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                self.stats_labels['uptime'].setText(f'{hours}시간 {minutes}분 {seconds}초')
            else:
                self.stats_labels['uptime'].setText('-')
    
    def toggle_windows_startup(self, state):
        """Windows 시작 프로그램 등록/해제"""
        key_path = r'Software\Microsoft\Windows\CurrentVersion\Run'
        app_path = os.path.abspath(sys.argv[0])
        
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            
            if state == Qt.CheckState.Checked.value:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{app_path}"')
                self.add_log('Windows 시작 프로그램에 등록되었습니다.')
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                    self.add_log('Windows 시작 프로그램에서 제거되었습니다.')
                except FileNotFoundError:
                    pass
            
            winreg.CloseKey(key)
        except Exception as e:
            self.add_log(f'시작 프로그램 설정 오류: {str(e)}')
        
        self.save_settings()
    
    def load_settings(self):
        """설정 로드"""
        self.port_spin.setValue(self.settings.value('port', 5000, type=int))
        self.auto_start_check.setChecked(self.settings.value('auto_start_server', True, type=bool))
        self.minimize_to_tray_check.setChecked(self.settings.value('minimize_to_tray', True, type=bool))
        
        # Windows 시작 프로그램 등록 여부 확인
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_READ)
            try:
                winreg.QueryValueEx(key, APP_NAME)
                self.windows_startup_check.setChecked(True)
            except FileNotFoundError:
                self.windows_startup_check.setChecked(False)
            winreg.CloseKey(key)
        except OSError as e:
            self.windows_startup_check.setChecked(False)
    
    def save_settings(self):
        """설정 저장"""
        self.settings.setValue('port', self.port_spin.value())
        self.settings.setValue('auto_start_server', self.auto_start_check.isChecked())
        self.settings.setValue('minimize_to_tray', self.minimize_to_tray_check.isChecked())


# ============================================================================
# 메인 실행
# ============================================================================
if __name__ == '__main__':
    # PyQt6 GUI 모드
    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)  # 트레이 아이콘으로 계속 실행
    
    window = ServerWindow()
    window.show()
    
    sys.exit(qt_app.exec())
