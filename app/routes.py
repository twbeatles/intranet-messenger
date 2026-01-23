# -*- coding: utf-8 -*-
"""
Flask HTTP 라우트
"""

import os
import uuid
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, session, send_from_directory, render_template
from werkzeug.utils import secure_filename

from app.models import (
    create_user, authenticate_user, get_all_users, get_user_rooms,
    create_room, get_room_messages, get_room_members, get_room_key,
    add_room_member, leave_room_db, update_room_name, get_room_by_id,
    pin_room, mute_room, get_online_users, delete_message, edit_message,
    search_messages, log_access, get_unread_count, update_user_profile,
    get_user_by_id, is_room_member, get_db, get_message_room_id,
    # v4.0 추가 기능
    pin_message, unpin_message, get_pinned_messages,
    create_poll, get_poll, get_room_polls, vote_poll, get_user_votes, close_poll,
    add_room_file, get_room_files, delete_room_file,
    add_reaction, remove_reaction, toggle_reaction, get_message_reactions, get_messages_reactions,
    set_room_admin, is_room_admin, get_room_admins, advanced_search,
    # v4.1 추가 기능
    change_password, delete_user,
    # [v4.15] 파일 삭제 안전 함수
    safe_file_delete,
    # [v4.19] 성능 최적화 함수
    get_room_last_reads
)
from app.utils import sanitize_input, allowed_file, validate_file_header
from app.extensions import limiter, csrf

# config 임포트 (PyInstaller 호환)
try:
    from config import UPLOAD_FOLDER
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import UPLOAD_FOLDER

logger = logging.getLogger(__name__)


def register_routes(app):
    """라우트 등록"""
    
    @app.route('/')
    def index():
        return render_template('index.html')
    
    @app.route('/api/me')
    def get_current_user():
        """현재 로그인된 사용자 정보 반환 (새로고침 시 세션 체크용)"""
        if 'user_id' in session:
            user = get_user_by_id(session['user_id'])
            if user:
                return jsonify({'logged_in': True, 'user': user})
        return jsonify({'logged_in': False})
    
    @app.route('/api/register', methods=['POST'])
    @csrf.exempt  # [v4.2] 회원가입은 미인증 상태이므로 CSRF 예외
    @limiter.limit("5 per minute")
    def register():
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '')
        nickname = data.get('nickname', '').strip() or username
        
        if not username or not password:
            return jsonify({'error': '아이디와 비밀번호를 입력해주세요.'}), 400
        
        # [v4.15] 아이디 형식 검사
        from app.utils import validate_username, validate_password
        if not validate_username(username):
            return jsonify({'error': '아이디는 3-20자 영문, 숫자, 밑줄만 사용 가능합니다.'}), 400
        
        # [v4.3] 비밀번호 강도 검사
        is_valid, error_msg = validate_password(password)
        if not is_valid:
            return jsonify({'error': error_msg}), 400
        
        user_id = create_user(username, password, nickname)
        if user_id:
            log_access(user_id, 'register', request.remote_addr, request.user_agent.string)
            return jsonify({'success': True, 'user_id': user_id})
        return jsonify({'error': '이미 존재하는 아이디입니다.'}), 400
    
    from flask_wtf.csrf import generate_csrf

    @app.route('/api/login', methods=['POST'])
    @csrf.exempt  # [v4.2] 로그인은 미인증 상태이므로 CSRF 예외
    @limiter.limit("10 per minute")
    def login():
        data = request.json
        user = authenticate_user(data.get('username', ''), data.get('password', ''))
        if user:
            # [v4.17] 세션 고정 공격 방지: 사용자 데이터만 교체 (CSRF 토큰 보존 방식 개선)
            # session.clear()를 사용하면 CSRF 세션 토큰도 삭제되므로,
            # 대신 사용자 관련 데이터만 교체하고 세션 ID 재생성
            old_csrf = session.get('csrf_token')  # 기존 CSRF 토큰 백업
            session.clear()
            session.permanent = True  # 세션 영구화 (새로고침 시 유지)
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['nickname'] = user.get('nickname', user['username'])  # 성능 최적화용 캐싱
            log_access(user['id'], 'login', request.remote_addr, request.user_agent.string)
            
            # [v4.17] 새 CSRF 토큰 생성 - session 설정 후 호출해야 세션에 저장됨
            new_csrf_token = generate_csrf()
            
            return jsonify({
                'success': True, 
                'user': user,
                'csrf_token': new_csrf_token
            })
        return jsonify({'error': '아이디 또는 비밀번호가 올바르지 않습니다.'}), 401
    
    @app.route('/api/logout', methods=['POST'])
    @csrf.exempt  # [v4.2] 로그아웃 CSRF 예외 (세션 삭제 작업으로 위험 낮음)
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
        
        try:
            room_id = create_room(name, room_type, session['user_id'], member_ids)
            return jsonify({'success': True, 'room_id': room_id})
        except Exception as e:
            logger.error(f"Room creation failed: {e}")
            return jsonify({'error': '대화방 생성에 실패했습니다.'}), 500
    
    @app.route('/api/rooms/<int:room_id>/messages')
    def get_messages(room_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        # 대화방 멤버십 확인
        if not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '대화방 접근 권한이 없습니다.'}), 403
        
        try:
            before_id = request.args.get('before_id', type=int)
            messages = get_room_messages(room_id, before_id=before_id)
            members = get_room_members(room_id)
            encryption_key = get_room_key(room_id)
            
            # [v4.31] 읽음 상태 계산 최적화: O(n*m) → O(n+m)
            if messages:
                last_reads = get_room_last_reads(room_id)
                member_count = len(members) if members else 0
                
                # 각 사용자별 마지막 읽은 메시지 ID를 딕셔너리로 변환 (O(m))
                user_last_read = {}
                for lr, uid in last_reads:
                    user_last_read[uid] = lr
                
                # 메시지별 안읽음 카운트 계산 (O(n))
                for msg in messages:
                    sender_id = msg['sender_id']
                    msg_id = msg['id']
                    
                    # 발신자 제외한 멤버 중 이 메시지를 안 읽은 사람 수
                    unread = 0
                    for uid, last_read_id in user_last_read.items():
                        if uid != sender_id and last_read_id < msg_id:
                            unread += 1
                    msg['unread_count'] = unread
            
            return jsonify({'messages': messages, 'members': members, 'encryption_key': encryption_key})
        except Exception as e:
            logger.error(f"메시지 로드 오류: {e}")
            return jsonify({'error': '메시지 로드 실패'}), 500
    
    @app.route('/api/rooms/<int:room_id>/members', methods=['POST'])
    def invite_member(room_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        # [v4.5] 멤버십 확인 - 방 멤버만 초대 가능
        if not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '대화방 접근 권한이 없습니다.'}), 403
        
        data = request.json
        user_ids = data.get('user_ids', [])
        user_id = data.get('user_id')
        
        if user_id:
            user_ids = [user_id]
        
        # [v4.8] 존재하는 사용자만 필터링
        valid_user_ids = [uid for uid in user_ids if get_user_by_id(uid)]
        
        added = 0
        for uid in valid_user_ids:
            if add_room_member(room_id, uid):
                added += 1
        
        if added > 0:
            return jsonify({'success': True, 'added_count': added})
        return jsonify({'error': '이미 참여중인 사용자입니다.'}), 400
    
    @app.route('/api/rooms/<int:room_id>/leave', methods=['POST'])
    def leave_room_route(room_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        leave_room_db(room_id, session['user_id'])
        return jsonify({'success': True})
    
    @app.route('/api/rooms/<int:room_id>/members/<int:target_user_id>', methods=['DELETE'])
    def kick_member(room_id, target_user_id):
        """[v4.9] 관리자가 멤버를 강제 퇴장시키기"""
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        # 관리자 권한 확인
        if not is_room_admin(room_id, session['user_id']):
            return jsonify({'error': '관리자만 멤버를 퇴장시킬 수 있습니다.'}), 403
        
        # 자기 자신은 퇴장시킬 수 없음
        if target_user_id == session['user_id']:
            return jsonify({'error': '자신을 퇴장시킬 수 없습니다.'}), 400
        
        # [v4.10] 대상이 관리자인지 확인 - 관리자는 강퇴 불가
        if is_room_admin(room_id, target_user_id):
            return jsonify({'error': '관리자는 강퇴할 수 없습니다.'}), 403
        
        # 대상이 해당 방의 멤버인지 확인
        if not is_room_member(room_id, target_user_id):
            return jsonify({'error': '해당 사용자는 대화방 멤버가 아닙니다.'}), 400
        
        leave_room_db(room_id, target_user_id)
        return jsonify({'success': True})
    
    @app.route('/api/rooms/<int:room_id>/name', methods=['PUT'])
    def update_room_name_route(room_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        # [v4.4] 멤버십 및 관리자 권한 확인
        if not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '대화방 접근 권한이 없습니다.'}), 403
        if not is_room_admin(room_id, session['user_id']):
            return jsonify({'error': '관리자만 대화방 이름을 변경할 수 있습니다.'}), 403
        
        data = request.json
        new_name = sanitize_input(data.get('name', ''), max_length=50)
        if not new_name:
            return jsonify({'error': '대화방 이름을 입력해주세요.'}), 400
        
        update_room_name(room_id, new_name)
        return jsonify({'success': True})
    
    @app.route('/api/rooms/<int:room_id>/pin', methods=['POST'])
    def pin_room_route(room_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        # [v4.4] 멤버십 확인
        if not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '대화방 접근 권한이 없습니다.'}), 403
        
        data = request.json
        pinned = data.get('pinned', True)
        if pin_room(session['user_id'], room_id, pinned):
            return jsonify({'success': True})
        return jsonify({'error': '설정 변경에 실패했습니다.'}), 400
    
    @app.route('/api/rooms/<int:room_id>/mute', methods=['POST'])
    def mute_room_route(room_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        # [v4.4] 멤버십 확인
        if not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '대화방 접근 권한이 없습니다.'}), 403
        
        data = request.json
        muted = data.get('muted', True)
        if mute_room(session['user_id'], room_id, muted):
            return jsonify({'success': True})
        return jsonify({'error': '설정 변경에 실패했습니다.'}), 400
    
    @app.route('/api/users/online')
    def get_online_users_route():
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        users = get_online_users()
        users = [u for u in users if u['id'] != session['user_id']]
        return jsonify(users)
    
    @app.route('/api/messages/<int:message_id>', methods=['DELETE'])
    def delete_message_route(message_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        success, result = delete_message(message_id, session['user_id'])
        if success:
            return jsonify({'success': True, 'room_id': result})
        return jsonify({'error': result}), 403
    
    @app.route('/api/messages/<int:message_id>', methods=['PUT'])
    def edit_message_route(message_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        data = request.json
        new_content = data.get('content', '')
        if not new_content:
            return jsonify({'error': '메시지 내용을 입력해주세요.'}), 400
        
        success, error, room_id = edit_message(message_id, session['user_id'], new_content)
        if success:
            return jsonify({'success': True, 'room_id': room_id})
        return jsonify({'error': error}), 403
    
    @app.route('/api/rooms/<int:room_id>/info')
    def get_room_info(room_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        # [v4.8] 멤버십 확인 추가
        if not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '대화방 접근 권한이 없습니다.'}), 403
        
        room = get_room_by_id(room_id)
        if not room:
            return jsonify({'error': '대화방을 찾을 수 없습니다.'}), 404
        
        members = get_room_members(room_id)
        room['members'] = members
        room.pop('encryption_key', None)
        return jsonify(room)
    
    @app.route('/api/search')
    @limiter.limit("30 per minute")
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
        
        # [v4.2] 선제적 파일 크기 검사 (메모리 로드 전)
        max_size = 16 * 1024 * 1024  # 16MB
        if request.content_length and request.content_length > max_size:
            return jsonify({'error': f'파일 크기는 16MB 이하여야 합니다.'}), 413
        
        if 'file' not in request.files:
            return jsonify({'error': '파일이 없습니다.'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '파일이 선택되지 않았습니다.'}), 400
        
        if file and allowed_file(file.filename):
            # [v4.3] 파일 내용 검증 (Magic Number)
            if not validate_file_header(file):
                logger.warning(f"File signature mismatch: {file.filename}")
                return jsonify({'error': '파일 내용이 확장자와 일치하지 않습니다.'}), 400

            filename = secure_filename(file.filename)
            # [v4.14] UUID 추가로 동시 업로드 시 파일명 충돌 방지
            unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}_{filename}"
            file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
            file.save(file_path)
            return jsonify({
                'success': True,
                'file_path': unique_filename,
                'file_name': filename
            })
        
        return jsonify({'error': '허용되지 않는 파일 형식입니다.'}), 400
    
    @app.route('/uploads/<path:filename>')
    def uploaded_file(filename):
        # 경로 트래버설 공격 방지
        # 1. 파일명 정제
        safe_filename = secure_filename(os.path.basename(filename))
        
        # 2. 하위 디렉토리 경로 처리 (profiles/ 등)
        if '/' in filename:
            subdir = os.path.dirname(filename)
            # 허용된 하위 디렉토리만 접근 가능
            allowed_subdirs = ['profiles']
            if subdir not in allowed_subdirs:
                return jsonify({'error': '접근이 거부되었습니다.'}), 403
            safe_path = os.path.join(subdir, safe_filename)
        else:
            safe_path = safe_filename
        
        # 3. 최종 경로 검증
        full_path = os.path.realpath(os.path.join(UPLOAD_FOLDER, safe_path))
        if not full_path.startswith(os.path.realpath(UPLOAD_FOLDER)):
            logger.warning(f"Path traversal attempt: {filename}")
            return jsonify({'error': '잘못된 경로입니다.'}), 400
        
        # 4. 파일 존재 확인
        if not os.path.isfile(full_path):
            return jsonify({'error': '파일을 찾을 수 없습니다.'}), 404
        
        # [v4.4] 캐시 헤더 추가 (성능 최적화)
        response = send_from_directory(os.path.dirname(full_path), os.path.basename(full_path))
        response.headers['Cache-Control'] = 'public, max-age=31536000'  # 1년 캐시 (파일명에 타임스탬프 포함)
        response.headers['Vary'] = 'Accept-Encoding'
        return response
    
    # Service Worker
    @app.route('/sw.js')
    def service_worker():
        return send_from_directory(app.static_folder, 'sw.js', mimetype='application/javascript')
    
    # ============================================================================
    # 프로필 API
    # ============================================================================
    @app.route('/api/profile')
    def get_profile():
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        user = get_user_by_id(session['user_id'])
        if user:
            return jsonify(user)
        return jsonify({'error': '사용자를 찾을 수 없습니다.'}), 404
    
    @app.route('/api/profile', methods=['PUT'])
    def update_profile():
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        data = request.json
        nickname = sanitize_input(data.get('nickname', ''), max_length=20)
        status_message = sanitize_input(data.get('status_message', ''), max_length=100)
        
        if nickname and len(nickname) < 2:
            return jsonify({'error': '닉네임은 2자 이상이어야 합니다.'}), 400
        
        success = update_user_profile(
            session['user_id'],
            nickname=nickname if nickname else None,
            status_message=status_message if status_message else None
        )
        
        if success:
            # 세션 닉네임도 업데이트
            if nickname:
                session['nickname'] = nickname
            return jsonify({'success': True})
        return jsonify({'error': '프로필 업데이트에 실패했습니다.'}), 500
    
    @app.route('/api/profile/image', methods=['POST'])
    def upload_profile_image():
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        if 'file' not in request.files:
            return jsonify({'error': '파일이 없습니다.'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '파일이 선택되지 않았습니다.'}), 400
        
        # 이미지 파일만 허용
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        if ext not in allowed_extensions:
            return jsonify({'error': '이미지 파일만 업로드 가능합니다.'}), 400
        
        # [v4.3] 파일 내용 검증
        if not validate_file_header(file):
            return jsonify({'error': '유효하지 않은 이미지 파일입니다.'}), 400
        
        # 파일 크기 제한 (5MB)
        file.seek(0, 2)
        size = file.tell()
        file.seek(0)
        if size > 5 * 1024 * 1024:
            return jsonify({'error': '파일 크기는 5MB 이하여야 합니다.'}), 400
        
        # 프로필 이미지 폴더 생성
        profile_folder = os.path.join(UPLOAD_FOLDER, 'profiles')
        os.makedirs(profile_folder, exist_ok=True)
        
        # [v4.12] 기존 프로필 이미지 삭제 (디스크 공간 절약)
        user = get_user_by_id(session['user_id'])
        if user and user.get('profile_image'):
            try:
                old_image_path = os.path.join(UPLOAD_FOLDER, user['profile_image'])
                # [v4.14] safe_file_delete 사용
                if safe_file_delete(old_image_path):
                    logger.debug(f"Old profile image deleted: {user['profile_image']}")
            except Exception as e:
                logger.warning(f"Old profile image deletion failed: {e}")
        
        # 파일 저장 - [v4.14] UUID 추가로 동시 업로드 시 파일명 충돌 방지
        filename = f"{session['user_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}.{ext}"
        file_path = os.path.join(profile_folder, filename)
        file.save(file_path)
        
        # DB 업데이트
        try:
            profile_image = f"profiles/{filename}"
            success = update_user_profile(session['user_id'], profile_image=profile_image)
            
            if success:
                return jsonify({'success': True, 'profile_image': profile_image})
            return jsonify({'error': '프로필 이미지 데이터베이스 업데이트 실패'}), 500
        except Exception as e:
            logger.error(f"Profile update error: {e}")
            return jsonify({'error': f'프로필 처리 중 오류가 발생했습니다: {str(e)}'}), 500
    
    @app.route('/api/profile/image', methods=['DELETE'])
    def delete_profile_image():
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        # [v4.4] 기존 프로필 이미지 조회 후 삭제
        user = get_user_by_id(session['user_id'])
        if user and user.get('profile_image'):
            try:
                old_image_path = os.path.join(UPLOAD_FOLDER, user['profile_image'])
                # [v4.14] safe_file_delete 사용
                safe_file_delete(old_image_path)
            except Exception as e:
                logger.warning(f"Profile image file deletion failed: {e}")
        
        # DB에서 프로필 이미지 삭제 (null로 설정)
        success = update_user_profile(session['user_id'], profile_image='')
        
        if success:
            return jsonify({'success': True})
        return jsonify({'error': '프로필 이미지 삭제에 실패했습니다.'}), 500
    
    # ============================================================================
    # 공지사항 (Pinned Messages) API
    # ============================================================================
    @app.route('/api/rooms/<int:room_id>/pins')
    def get_room_pins(room_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        if not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '접근 권한이 없습니다.'}), 403
        pins = get_pinned_messages(room_id)
        return jsonify(pins)
    
    @app.route('/api/rooms/<int:room_id>/pins', methods=['POST'])
    def create_pin(room_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        if not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '접근 권한이 없습니다.'}), 403
        
        # [v4.20] 모든 멤버가 공지 등록 가능 (관리자 제한 제거)
        
        data = request.json
        message_id = data.get('message_id')
        content = sanitize_input(data.get('content', ''), max_length=500)
        
        if not message_id and not content:
            return jsonify({'error': '고정할 메시지 또는 내용을 입력해주세요.'}), 400
        
        pin_id = pin_message(room_id, session['user_id'], message_id, content)
        if pin_id:
            return jsonify({'success': True, 'pin_id': pin_id})
        return jsonify({'error': '공지 고정에 실패했습니다.'}), 500
    
    @app.route('/api/rooms/<int:room_id>/pins/<int:pin_id>', methods=['DELETE'])
    def delete_pin(room_id, pin_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        if not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '접근 권한이 없습니다.'}), 403
        
        # [v4.20] 모든 멤버가 공지 삭제 가능 (관리자 제한 제거)
        
        if unpin_message(pin_id, session['user_id'], room_id):
            return jsonify({'success': True})
        return jsonify({'error': '공지 해제에 실패했습니다.'}), 500
    
    # ============================================================================
    # 투표 (Polls) API
    # ============================================================================
    @app.route('/api/rooms/<int:room_id>/polls')
    def get_polls(room_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        if not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '접근 권한이 없습니다.'}), 403
        
        polls = get_room_polls(room_id)
        for poll in polls:
            poll['my_votes'] = get_user_votes(poll['id'], session['user_id'])
        return jsonify(polls)
    
    @app.route('/api/rooms/<int:room_id>/polls', methods=['POST'])
    def create_poll_route(room_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        if not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '접근 권한이 없습니다.'}), 403
        
        data = request.json
        question = sanitize_input(data.get('question', ''), max_length=200)
        options = data.get('options', [])
        multiple_choice = data.get('multiple_choice', False)
        anonymous = data.get('anonymous', False)
        ends_at = data.get('ends_at')  # [v4.8] ISO 형식 날짜/시간 문자열
        
        if not question:
            return jsonify({'error': '질문을 입력해주세요.'}), 400
        if len(options) < 2:
            return jsonify({'error': '최소 2개의 옵션이 필요합니다.'}), 400
        
        # [v4.9] ends_at 형식 검증
        if ends_at:
            from datetime import datetime
            try:
                # ISO 형식 파싱 시도
                ends_at_dt = datetime.fromisoformat(ends_at.replace('Z', '+00:00'))
                if ends_at_dt < datetime.now(ends_at_dt.tzinfo) if ends_at_dt.tzinfo else ends_at_dt < datetime.now():
                    return jsonify({'error': '마감 시간은 현재 시간 이후여야 합니다.'}), 400
                # DB 저장 형식으로 변환 (UTC 없이 문자열)
                ends_at = ends_at_dt.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                return jsonify({'error': '올바른 날짜/시간 형식이 아닙니다. (ISO 8601)'}), 400
        
        options = [sanitize_input(opt, max_length=100) for opt in options[:10]]
        
        poll_id = create_poll(room_id, session['user_id'], question, options, multiple_choice, anonymous, ends_at)
        if poll_id:
            poll = get_poll(poll_id)
            return jsonify({'success': True, 'poll': poll})
        return jsonify({'error': '투표 생성에 실패했습니다.'}), 500
    
    @app.route('/api/polls/<int:poll_id>/vote', methods=['POST'])
    def vote_poll_route(poll_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        # [v4.6] 투표가 속한 방의 멤버십 확인
        poll = get_poll(poll_id)
        if not poll:
            return jsonify({'error': '투표를 찾을 수 없습니다.'}), 404
        if not is_room_member(poll['room_id'], session['user_id']):
            return jsonify({'error': '접근 권한이 없습니다.'}), 403
        
        data = request.json
        option_id = data.get('option_id')
        
        if not option_id:
            return jsonify({'error': '옵션을 선택해주세요.'}), 400
        
        success, error = vote_poll(poll_id, option_id, session['user_id'])
        if success:
            poll = get_poll(poll_id)
            poll['my_votes'] = get_user_votes(poll_id, session['user_id'])
            return jsonify({'success': True, 'poll': poll})
        return jsonify({'error': error}), 400
    
    @app.route('/api/polls/<int:poll_id>/close', methods=['POST'])
    def close_poll_route(poll_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        # [v4.5] 투표가 속한 방의 멤버십 확인
        poll = get_poll(poll_id)
        if not poll:
            return jsonify({'error': '투표를 찾을 수 없습니다.'}), 404
        if not is_room_member(poll['room_id'], session['user_id']):
            return jsonify({'error': '접근 권한이 없습니다.'}), 403
        
        # [v4.21] 투표 생성자 또는 관리자만 마감 가능
        is_admin = is_room_admin(poll['room_id'], session['user_id'])
        success, error = close_poll(poll_id, session['user_id'], is_admin=is_admin)
        if success:
            return jsonify({'success': True})
        return jsonify({'error': error or '투표 마감에 실패했습니다.'}), 403
    
    # ============================================================================
    # 파일 저장소 (Room Files) API
    # ============================================================================
    @app.route('/api/rooms/<int:room_id>/files')
    def get_files(room_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        if not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '접근 권한이 없습니다.'}), 403
        
        file_type = request.args.get('type')  # 'image', 'file', etc.
        files = get_room_files(room_id, file_type)
        return jsonify(files)
    
    @app.route('/api/rooms/<int:room_id>/files/<int:file_id>', methods=['DELETE'])
    def delete_file_route(room_id, file_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        if not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '접근 권한이 없습니다.'}), 403
        # [v4.8] 관리자도 파일 삭제 가능
        is_admin = is_room_admin(room_id, session['user_id'])
        # [v4.9] room_id 전달하여 다른 방 파일 삭제 방지
        success, file_path = delete_room_file(file_id, session['user_id'], room_id=room_id, is_admin=is_admin)
        if success:
            return jsonify({'success': True})
        return jsonify({'error': '파일 삭제 권한이 없습니다.'}), 403
    
    # ============================================================================
    # 리액션 (Reactions) API
    # ============================================================================
    @app.route('/api/messages/<int:message_id>/reactions')
    def get_reactions(message_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        # [v4.4] 메시지 접근 권한 확인
        room_id = get_message_room_id(message_id)
        if room_id is None or not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '대화방 접근 권한이 없습니다.'}), 403
        
        reactions = get_message_reactions(message_id)
        return jsonify(reactions)
    
    @app.route('/api/messages/<int:message_id>/reactions', methods=['POST'])
    def add_reaction_route(message_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        # [v4.4] 메시지 접근 권한 확인
        room_id = get_message_room_id(message_id)
        if room_id is None or not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '대화방 접근 권한이 없습니다.'}), 403
        
        data = request.json
        emoji = data.get('emoji', '')
        if not emoji or len(emoji) > 10:
            return jsonify({'error': '유효하지 않은 이모지입니다.'}), 400
        
        success, action = toggle_reaction(message_id, session['user_id'], emoji)
        if success:
            reactions = get_message_reactions(message_id)
            return jsonify({'success': True, 'action': action, 'reactions': reactions})
        return jsonify({'error': '리액션 추가에 실패했습니다.'}), 500
    
    # ============================================================================
    # 관리자 권한 (Admin) API
    # ============================================================================
    @app.route('/api/rooms/<int:room_id>/admins')
    def get_admins(room_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        if not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '접근 권한이 없습니다.'}), 403
        
        admins = get_room_admins(room_id)
        return jsonify(admins)
    
    @app.route('/api/rooms/<int:room_id>/admins', methods=['POST'])
    def set_admin_route(room_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        if not is_room_admin(room_id, session['user_id']):
            return jsonify({'error': '관리자 권한이 필요합니다.'}), 403
        
        data = request.json
        target_user_id = data.get('user_id')
        is_admin = data.get('is_admin', True)
        
        if not target_user_id:
            return jsonify({'error': '사용자를 선택해주세요.'}), 400
        
        # [v4.13] 마지막 관리자 해제 방지
        if not is_admin:
            admins = get_room_admins(room_id)
            if len(admins) <= 1:
                return jsonify({'error': '최소 한 명의 관리자가 필요합니다.'}), 400
        
        if set_room_admin(room_id, target_user_id, is_admin):
            return jsonify({'success': True})
        return jsonify({'error': '관리자 설정에 실패했습니다.'}), 500
    
    @app.route('/api/rooms/<int:room_id>/admin-check')
    def check_admin(room_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        # [v4.22] 멤버십 확인 추가
        if not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '접근 권한이 없습니다.'}), 403
        is_admin = is_room_admin(room_id, session['user_id'])
        return jsonify({'is_admin': is_admin})
    
    # ============================================================================
    # 고급 검색 API
    # ============================================================================
    @app.route('/api/search/advanced', methods=['POST'])
    def advanced_search_route():
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        data = request.json
        results = advanced_search(
            user_id=session['user_id'],
            query=data.get('query'),
            room_id=data.get('room_id'),
            sender_id=data.get('sender_id'),
            date_from=data.get('date_from'),
            date_to=data.get('date_to'),
            file_only=data.get('file_only', False)
        )
        return jsonify(results)

    # ============================================================================
    # [v4.1] 계정 보안 라우트
    # ============================================================================
    @app.route('/api/me/password', methods=['PUT'])
    def update_password():
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
            
        data = request.json
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        
        if not current_password or not new_password:
            return jsonify({'error': '입력값이 부족합니다.'}), 400
            
        # [v4.3] 비밀번호 강도 검사
        from app.utils import validate_password
        is_valid, error_msg = validate_password(new_password)
        if not is_valid:
            return jsonify({'error': error_msg}), 400
            
        # [v4.21] 새 세션 토큰과 함께 비밀번호 변경
        success, error, new_session_token = change_password(session['user_id'], current_password, new_password)
        
        if success:
            # 현재 세션에 새 토큰 저장 (다른 세션은 무효화됨)
            if new_session_token:
                session['session_token'] = new_session_token
            log_access(session['user_id'], 'change_password', request.remote_addr, request.user_agent.string)
            return jsonify({
                'success': True,
                'message': '비밀번호가 변경되었습니다. 다른 기기에서의 세션은 로그아웃됩니다.'
            })
        else:
            return jsonify({'error': error}), 400

    @app.route('/api/me', methods=['DELETE'])
    def delete_account():
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
            
        data = request.json
        password = data.get('password')
        
        if not password:
            return jsonify({'error': '비밀번호를 입력해주세요.'}), 400
            
        success, error = delete_user(session['user_id'], password)
        
        if success:
            log_access(session['user_id'], 'delete_account', request.remote_addr, request.user_agent.string)
            session.clear()
            return jsonify({'success': True})
        else:
            return jsonify({'error': error}), 400
