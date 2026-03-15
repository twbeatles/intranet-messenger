# -*- coding: utf-8 -*-
"""
Flask HTTP 라우트
"""

import os
import uuid
import logging
import csv
import io
from datetime import datetime
from typing import Any, cast

from flask import request, jsonify, session, send_from_directory, render_template, redirect, url_for, make_response
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
    create_message,
    # v4.1 추가 기능
    change_password, delete_user, get_or_create_oidc_user,
    log_admin_action, get_admin_audit_logs,
    # [v4.15] 파일 삭제 안전 함수
    safe_file_delete,
    # [v4.19] 성능 최적화용 함수
    get_room_last_reads
)
from app.utils import sanitize_input, allowed_file, validate_file_header
from app.extensions import limiter, csrf
from app.upload_tokens import issue_upload_token
from app.upload_scan import is_scan_enabled, create_scan_job, get_scan_job
from app.oidc import (
    oidc_enabled,
    get_provider_metadata,
    build_authorize_redirect,
    exchange_code_for_userinfo,
)

# config import (PyInstaller 호환)
try:
    from config import (
        UPLOAD_FOLDER,
        MAX_CONTENT_LENGTH,
        FEATURE_OIDC_ENABLED,
        FEATURE_AV_SCAN_ENABLED,
        FEATURE_REDIS_ENABLED,
        SOCKET_SEND_MESSAGE_PER_MINUTE,
    )
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import (
        UPLOAD_FOLDER,
        MAX_CONTENT_LENGTH,
        FEATURE_OIDC_ENABLED,
        FEATURE_AV_SCAN_ENABLED,
        FEATURE_REDIS_ENABLED,
        SOCKET_SEND_MESSAGE_PER_MINUTE,
    )

logger = logging.getLogger(__name__)


def register_routes(app):
    upload_rate_limit = "10 per minute"
    advanced_search_rate_limit = "30 per minute"

    def json_error(message: str, status: int = 400, code: str | None = None):
        payload = {'error': message}
        if code:
            payload['code'] = code
        return jsonify(payload), status

    def parse_json_payload(required: bool = True) -> tuple[dict[str, Any], Any | None]:
        data = request.get_json(silent=True)
        if data is None:
            if required:
                return {}, json_error('JSON body is required.', 400, 'invalid_json')
            return {}, None
        if not isinstance(data, dict):
            return {}, json_error('JSON object payload is required.', 400, 'invalid_json')
        return cast(dict[str, Any], data), None

    def parse_int_from_json(
        data: dict[str, Any],
        key: str,
        default: int,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> tuple[int, Any | None]:
        value = data.get(key, default)
        if value in (None, ""):
            value = default
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default, json_error(f"Invalid integer for '{key}'.", 400, f"invalid_{key}")
        if minimum is not None:
            parsed = max(parsed, minimum)
        if maximum is not None:
            parsed = min(parsed, maximum)
        return parsed, None

    def _get_socketio():
        try:
            from app import socketio as socketio_instance
            return socketio_instance
        except Exception:
            return None

    def _emit_room_members_updated(room_id: int):
        socketio_instance = _get_socketio()
        if not socketio_instance:
            return
        try:
            socketio_instance.emit('room_members_updated', {'room_id': room_id}, to=f'room_{room_id}')
        except Exception as e:
            logger.warning(f"room_members_updated emit failed: room_id={room_id}, error={e}")

    def _emit_pin_updated(room_id: int):
        socketio_instance = _get_socketio()
        if not socketio_instance:
            return
        try:
            socketio_instance.emit('pin_updated', {'room_id': room_id}, to=f'room_{room_id}')
        except Exception as e:
            logger.warning(f"pin_updated emit failed: room_id={room_id}, error={e}")

    def _emit_pin_system_message(room_id: int, actor_user_id: int, content: str):
        socketio_instance = _get_socketio()
        try:
            sys_msg = create_message(room_id, actor_user_id, content, 'system')
            if sys_msg and socketio_instance:
                socketio_instance.emit('new_message', sys_msg, to=f'room_{room_id}')
        except Exception as e:
            logger.warning(f"pin system message emit failed: room_id={room_id}, error={e}")

    def _get_max_upload_size() -> int:
        return int(app.config.get('MAX_CONTENT_LENGTH') or MAX_CONTENT_LENGTH or 16 * 1024 * 1024)

    def _public_config_payload():
        return {
            'upload': {
                'max_size_bytes': _get_max_upload_size(),
            },
            'rate_limits': {
                'login': '10/min',
                'register': '5/min',
                'upload': '10/min',
                'search_advanced': '30/min',
                'socket_send_message': f"{int(app.config.get('SOCKET_SEND_MESSAGE_PER_MINUTE', SOCKET_SEND_MESSAGE_PER_MINUTE))}/min",
                'socket_pin_updated': f"{int(app.config.get('SOCKET_PIN_UPDATED_PER_MINUTE', 30))}/min",
            },
            'features': {
                'oidc': bool(app.config.get('FEATURE_OIDC_ENABLED', FEATURE_OIDC_ENABLED)),
                'av': bool(app.config.get('FEATURE_AV_SCAN_ENABLED', FEATURE_AV_SCAN_ENABLED)),
                'redis': bool(app.config.get('FEATURE_REDIS_ENABLED', FEATURE_REDIS_ENABLED)),
            },
        }

    @app.route('/')
    def index():
        return render_template('index.html')
    
    @app.route('/api/me')
    def get_current_user():
        """현재 로그인된 사용자 정보 반환 (새로고침 시 세션 체크)"""
        if 'user_id' in session:
            user = get_user_by_id(session['user_id'])
            if user:
                return jsonify({'logged_in': True, 'user': user})
        return jsonify({'logged_in': False})

    @app.route('/api/config')
    def get_runtime_config():
        return jsonify(_public_config_payload())

    @app.route('/api/auth/providers')
    def auth_providers():
        providers = []
        if oidc_enabled(app):
            meta = get_provider_metadata(app)
            providers.append({
                'type': 'oidc',
                'provider': meta.get('provider', 'oidc'),
                'login_url': '/auth/oidc/login',
            })
        return jsonify({'providers': providers})

    @app.route('/auth/oidc/login')
    def oidc_login():
        if not oidc_enabled(app):
            return redirect('/')
        redirect_uri = app.config.get('OIDC_REDIRECT_URI') or url_for('oidc_callback', _external=True)
        try:
            return redirect(build_authorize_redirect(app, redirect_uri=redirect_uri))
        except Exception as exc:
            logger.error(f"OIDC login redirect build failed: {exc}")
            return redirect('/')

    @app.route('/auth/oidc/callback')
    def oidc_callback():
        if not oidc_enabled(app):
            return redirect('/')

        expected_state = session.pop('oidc_state', None)
        expected_nonce = session.pop('oidc_nonce', None)
        state = request.args.get('state')
        if not expected_state or not state or state != expected_state:
            logger.warning("OIDC callback state mismatch")
            return redirect('/')
        if not expected_nonce:
            logger.warning("OIDC callback nonce missing")
            return redirect('/')

        code = request.args.get('code')
        if not code:
            return redirect('/')

        redirect_uri = app.config.get('OIDC_REDIRECT_URI') or url_for('oidc_callback', _external=True)
        try:
            claims = exchange_code_for_userinfo(
                app,
                code=code,
                redirect_uri=redirect_uri,
                expected_nonce=expected_nonce,
            )
            provider = app.config.get('OIDC_PROVIDER_NAME', 'oidc')
            subject = (claims or {}).get('sub')
            if not subject:
                return redirect('/')

            user = get_or_create_oidc_user(
                provider=provider,
                subject=subject,
                email=(claims or {}).get('email'),
                preferred_username=(claims or {}).get('preferred_username'),
                nickname=(claims or {}).get('nickname'),
            )
            if not user:
                return redirect('/')

            session.clear()
            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['nickname'] = user.get('nickname', user['username'])
            session['session_token'] = user.get('session_token')
            log_access(user['id'], 'oidc_login', request.remote_addr, request.user_agent.string)
            return redirect('/')
        except Exception as exc:
            logger.error(f"OIDC callback failed: {exc}")
            return redirect('/')
    
    @app.route('/api/register', methods=['POST'])
    @csrf.exempt  # [v4.2] 회원가입은 비인증 상태이므로 CSRF 예외
    @limiter.limit("5 per minute")
    def register():
        data, error_response = parse_json_payload()
        if error_response:
            return error_response
        username = data.get('username', '').strip()
        password = data.get('password', '')
        nickname = data.get('nickname', '').strip() or username
        
        if not username or not password:
            return jsonify({'error': '아이디와 비밀번호를 입력해 주세요.'}), 400
        
        # [v4.15] 아이디 형식 검증
        from app.utils import validate_username, validate_password
        if not validate_username(username):
            return jsonify({'error': '아이디는 3-20자의 영문, 숫자, 밑줄만 사용할 수 있습니다.'}), 400
        
        # [v4.3] 비밀번호 강도 검증
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
    @csrf.exempt  # [v4.2] 로그인은 비인증 상태이므로 CSRF 예외
    @limiter.limit("10 per minute")
    def login():
        data, error_response = parse_json_payload()
        if error_response:
            return error_response
        user = authenticate_user(data.get('username', ''), data.get('password', ''))
        if user:
            # [v4.17] 세션 고정 공격 방지: 사용자 데이터만 교체하고 CSRF 토큰은 보존
            # session.clear()를 호출하면 CSRF 세션 토큰도 함께 제거되므로
            # 필요한 사용자 관련 데이터만 갱신하고 세션 ID는 새로 만든다.
            old_csrf = session.get('csrf_token')  # 기존 CSRF 토큰 백업
            session.clear()
            session.permanent = True  # 세션 영구화 (새로고침 시 유지)
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['nickname'] = user.get('nickname', user['username'])  # 성능 최적화용 캐시
            session['session_token'] = user.get('session_token')
            log_access(user['id'], 'login', request.remote_addr, request.user_agent.string)
            
            # [v4.17] 새 CSRF 토큰 생성은 session 설정 후 호출해야 세션에 반영된다.
            new_csrf_token = generate_csrf()
            
            return jsonify({
                'success': True, 
                'user': user,
                'csrf_token': new_csrf_token
            })
        return jsonify({'error': '아이디 또는 비밀번호가 올바르지 않습니다.'}), 401
    
    @app.route('/api/logout', methods=['POST'])
    @csrf.exempt  # [v4.2] 로그아웃은 세션 정리 작업이라 CSRF 예외
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
        include_members = str(request.args.get('include_members', '')).lower() in ('1', 'true', 'yes')
        rooms = get_user_rooms(session['user_id'], include_members=include_members)
        return jsonify(rooms)
    
    @app.route('/api/rooms', methods=['POST'])
    def create_room_route():
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        data, error_response = parse_json_payload()
        if error_response:
            return error_response
        has_members = 'members' in data
        has_member_ids = 'member_ids' in data
        if has_members:
            raw_members = data.get('members')
            if has_member_ids:
                logger.warning("Both members and member_ids were provided; members will be used.")
        else:
            raw_members = data.get('member_ids', [])

        if raw_members is None:
            raw_members = []
        if not isinstance(raw_members, list):
            return jsonify({'error': 'members 또는 member_ids는 배열이어야 합니다.'}), 400

        normalized_members = []
        seen = set()
        for value in raw_members:
            try:
                member_id = int(value)
            except (TypeError, ValueError):
                return jsonify({'error': '멤버 ID는 정수여야 합니다.'}), 400
            if member_id <= 0 or member_id in seen:
                continue
            seen.add(member_id)
            normalized_members.append(member_id)

        if session['user_id'] not in seen:
            normalized_members.append(session['user_id'])
            seen.add(session['user_id'])

        member_ids = [uid for uid in normalized_members if get_user_by_id(uid)]
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
        
        # 대화방 멤버 확인
        if not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '대화방 접근 권한이 없습니다.'}), 403
        
        try:
            before_id = request.args.get('before_id', type=int)
            limit = request.args.get('limit', type=int) or 50
            if limit < 1:
                limit = 1
            if limit > 200:
                limit = 200

            include_meta = str(request.args.get('include_meta', '1')).lower() in ('1', 'true', 'yes')

            messages = get_room_messages(room_id, before_id=before_id, limit=limit)
            members = get_room_members(room_id) if include_meta else None
            encryption_key = get_room_key(room_id) if include_meta else None
            
            # [v4.31] 읽음 상태 계산 최적화: O(n*m) -> O(n+m)
            if messages:
                if include_meta and members:
                    # members already includes last_read_message_id; reuse it
                    user_last_read = {}
                    last_read_ids = []
                    for m in members:
                        try:
                            uid = m.get('id')
                            v = m.get('last_read_message_id') or 0
                        except Exception:
                            continue
                        if uid is None:
                            continue
                        user_last_read[uid] = v
                        last_read_ids.append(v)
                else:
                    last_reads = get_room_last_reads(room_id)
                    user_last_read = {}
                    last_read_ids = []
                    for lr, uid in last_reads:
                        v = lr or 0
                        user_last_read[uid] = v
                        last_read_ids.append(v)
                last_read_ids.sort()
                from bisect import bisect_left
                
                # 읽지 않은 사용자 수 계산: O(n log m) (m=멤버 수)
                for msg in messages:
                    sender_id = msg['sender_id']
                    msg_id = msg['id']
                
                    unread = bisect_left(last_read_ids, msg_id)
                    sender_lr = user_last_read.get(sender_id, 0)
                    if sender_lr < msg_id:
                        unread -= 1
                    if unread < 0:
                        unread = 0
                    msg['unread_count'] = unread
            
            resp: dict[str, Any] = {'messages': messages}
            if include_meta:
                resp['members'] = members
                resp['encryption_key'] = encryption_key
            return jsonify(resp)
        except Exception as e:
            logger.error(f"메시지 로드 오류: {e}")
            return jsonify({'error': '메시지 로드 실패'}), 500
    
    @app.route('/api/rooms/<int:room_id>/members', methods=['POST'])
    def invite_member(room_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        # [v4.5] 멤버 확인: 방 멤버만 초대 가능
        if not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '대화방 접근 권한이 없습니다.'}), 403
        
        data, error_response = parse_json_payload()
        if error_response:
            return error_response
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
            _emit_room_members_updated(room_id)
            return jsonify({'success': True, 'added_count': added})
        return jsonify({'error': '이미 참여 중인 사용자입니다.'}), 400
    
    @app.route('/api/rooms/<int:room_id>/leave', methods=['POST'])
    def leave_room_route(room_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401

        user_id = session['user_id']
        if not is_room_member(room_id, user_id):
            return jsonify({'success': True, 'left': False, 'already_left': True})

        leave_room_db(room_id, user_id)
        _emit_room_members_updated(room_id)
        return jsonify({'success': True, 'left': True, 'already_left': False})
    
    @app.route('/api/rooms/<int:room_id>/members/<int:target_user_id>', methods=['DELETE'])
    def kick_member(room_id, target_user_id):        # [v4.9] 관리자 강퇴 처리
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        # 관리자 권한 확인
        if not is_room_admin(room_id, session['user_id']):
            return jsonify({'error': '관리자만 멤버를 강퇴할 수 있습니다.'}), 403
        
        # 자기 자신은 강퇴할 수 없음
        if target_user_id == session['user_id']:
            return jsonify({'error': '자신은 강퇴할 수 없습니다.'}), 400
        
        # [v4.10] 대상이 관리자인지 확인: 관리자는 강퇴 불가
        if is_room_admin(room_id, target_user_id):
            return jsonify({'error': '관리자는 강퇴할 수 없습니다.'}), 403
        
        # 대상이 해당 방의 멤버인지 확인
        if not is_room_member(room_id, target_user_id):
            return jsonify({'error': '해당 사용자는 대화방 멤버가 아닙니다.'}), 400
        
        leave_room_db(room_id, target_user_id)
        _emit_room_members_updated(room_id)
        log_admin_action(
            room_id=room_id,
            actor_user_id=session['user_id'],
            target_user_id=target_user_id,
            action='kick_member',
            metadata={'source': 'api'},
        )
        return jsonify({'success': True})
    
    @app.route('/api/rooms/<int:room_id>/name', methods=['PUT'])
    def update_room_name_route(room_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        # [v4.4] 멤버 및 관리자 권한 확인
        if not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '대화방 접근 권한이 없습니다.'}), 403
        if not is_room_admin(room_id, session['user_id']):
            return jsonify({'error': '관리자만 대화방 이름을 변경할 수 있습니다.'}), 403
        
        data, error_response = parse_json_payload()
        if error_response:
            return error_response
        new_name = sanitize_input(data.get('name', ''), max_length=50)
        if not new_name:
            return jsonify({'error': '대화방 이름을 입력해 주세요.'}), 400
        
        update_room_name(room_id, new_name)
        return jsonify({'success': True})
    
    # NOTE: /pin-room is the explicit alias; /pin is kept for backwards compatibility.
    @app.route('/api/rooms/<int:room_id>/pin-room', methods=['POST'])
    @app.route('/api/rooms/<int:room_id>/pin', methods=['POST'])
    def pin_room_route(room_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        # [v4.4] 멤버 확인
        if not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '대화방 접근 권한이 없습니다.'}), 403
        
        data, error_response = parse_json_payload()
        if error_response:
            return error_response
        pinned = data.get('pinned', True)
        if pin_room(session['user_id'], room_id, pinned):
            return jsonify({'success': True})
        return jsonify({'error': '설정 변경에 실패했습니다.'}), 400
    
    @app.route('/api/rooms/<int:room_id>/mute', methods=['POST'])
    def mute_room_route(room_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        # [v4.4] 멤버 확인
        if not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '대화방 접근 권한이 없습니다.'}), 403
        
        data, error_response = parse_json_payload()
        if error_response:
            return error_response
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
        
        data, error_response = parse_json_payload()
        if error_response:
            return error_response
        new_content = data.get('content', '')
        if not new_content:
            return jsonify({'error': '메시지 내용을 입력해 주세요.'}), 400
        
        success, error, room_id = edit_message(message_id, session['user_id'], new_content)
        if success:
            return jsonify({'success': True, 'room_id': room_id})
        return jsonify({'error': error}), 403
    
    @app.route('/api/rooms/<int:room_id>/info')
    def get_room_info(room_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        # [v4.8] 멤버 확인 추가
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
    
        query = request.args.get('q')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        file_only = str(request.args.get('file_only', '')).lower() in ('1', 'true', 'yes')
        room_id = request.args.get('room_id', type=int)
        offset = request.args.get('offset', type=int)
        limit = request.args.get('limit', type=int)
        offset = max(offset if offset is not None else 0, 0)
        limit = min(max(limit if limit is not None else 50, 1), 200)
    
        # If no filters, return empty list (frontend expects list)
        if (not query or not query.strip()) and not date_from and not date_to and not file_only:
            return jsonify([])
    
        q = (query or '').strip()
        if q and len(q) < 2:
            return jsonify([])
    
        results = advanced_search(
            user_id=session['user_id'],
            query=(q or None),
            room_id=room_id,
            date_from=(date_from or None),
            date_to=(date_to or None),
            file_only=file_only,
            limit=limit,
            offset=offset,
        )
        return jsonify(results.get('messages', []))
    
    @app.route('/api/upload', methods=['POST'])
    @limiter.limit(upload_rate_limit)
    def upload_file():
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        upload_folder = app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER)

        room_id = request.form.get('room_id', type=int)
        if not room_id:
            return jsonify({'error': 'room_id가 필요합니다.'}), 400
        if not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '대화방 접근 권한이 없습니다.'}), 403
        
        # [v4.2] 업로드 파일 크기 검증 (메모리 로드 전)
        max_size = _get_max_upload_size()
        if request.content_length and request.content_length > max_size:
            return jsonify({'error': f'파일 크기는 {max_size} bytes 이하여야 합니다.'}), 413
        
        if 'file' not in request.files:
            return jsonify({'error': '파일이 없습니다.'}), 400
        
        file = request.files['file']
        original_filename = file.filename or ''
        if original_filename == '':
            return jsonify({'error': '파일을 선택하지 않았습니다.'}), 400
        
        if file and allowed_file(original_filename):
            # [v4.3] 파일 내용 검증 (Magic Number)
            if not validate_file_header(file):
                logger.warning(f"File signature mismatch: {file.filename}")
                return jsonify({'error': '파일 내용이 확장자와 일치하지 않습니다.'}), 400

            filename = secure_filename(original_filename)
            # [v4.14] UUID 추가로 동시 업로드 시 파일명 충돌 방지
            unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}_{filename}"
            ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
            file_type = 'image' if ext in {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'ico'} else 'file'

            av_enabled = bool(is_scan_enabled(app))
            if av_enabled:
                quarantine_folder = app.config.get('UPLOAD_QUARANTINE_FOLDER') or os.path.join(upload_folder, 'quarantine')
                os.makedirs(quarantine_folder, exist_ok=True)

                temp_abs_path = os.path.join(quarantine_folder, unique_filename)
                file.save(temp_abs_path)
                file_size = os.path.getsize(temp_abs_path)

                temp_rel_path = os.path.relpath(temp_abs_path, upload_folder).replace('\\', '/')
                final_rel_path = unique_filename.replace('\\', '/')
                try:
                    job_id = create_scan_job(
                        user_id=session['user_id'],
                        room_id=room_id,
                        temp_path=temp_rel_path,
                        final_path=final_rel_path,
                        file_name=filename,
                        file_type=file_type,
                        file_size=file_size,
                    )
                except Exception as exc:
                    logger.error(f"Create upload scan job failed: {exc}")
                    try:
                        safe_file_delete(temp_abs_path)
                    except Exception:
                        pass
                    return jsonify({'error': '업로드 준비에 실패했습니다.'}), 500

                return jsonify({
                    'success': True,
                    'scan_status': 'pending',
                    'job_id': job_id,
                })

            file_path = os.path.join(upload_folder, unique_filename)
            file.save(file_path)
            file_size = os.path.getsize(file_path)
            ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
            file_type = 'image' if ext in {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'ico'} else 'file'
            upload_token = issue_upload_token(
                user_id=session['user_id'],
                room_id=room_id,
                file_path=unique_filename,
                file_name=filename,
                file_type=file_type,
                file_size=file_size,
            )
            return jsonify({
                'success': True,
                'scan_status': 'clean',
                'file_path': unique_filename,
                'file_name': filename,
                'upload_token': upload_token,
            })
        
        return jsonify({'error': '허용되지 않는 파일 형식입니다.'}), 400

    @app.route('/api/upload/jobs/<job_id>')
    def get_upload_job_status(job_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401

        job = get_scan_job(job_id)
        if not job:
            return jsonify({'error': '스캔 작업을 찾을 수 없습니다.'}), 404
        if int(job.get('user_id') or 0) != int(session['user_id']):
            return jsonify({'error': '접근 권한이 없습니다.'}), 403

        status = (job.get('status') or 'pending').lower()
        payload = {
            'job_id': job_id,
            'scan_status': status,
        }
        if status == 'clean':
            payload.update({
                'upload_token': job.get('token'),
                'file_path': job.get('final_path'),
                'file_name': job.get('file_name'),
            })
        elif status in ('infected', 'error'):
            payload.update({
                'error': job.get('result') or '스캔 실패',
            })
        return jsonify(payload)
    
    @app.route('/uploads/<path:filename>')
    def uploaded_file(filename):
        # 인증 확인
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        upload_folder = app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER)

        # 파일명 정규화
        safe_filename = secure_filename(os.path.basename(filename))

        # 하위 경로 검증 (profiles만 허용)
        is_profile = False
        if '/' in filename:
            subdir = os.path.dirname(filename)
            allowed_subdirs = ['profiles']
            if subdir not in allowed_subdirs:
                return jsonify({'error': '접근 권한이 없습니다.'}), 403
            safe_path = os.path.join(subdir, safe_filename)
            is_profile = (subdir == 'profiles')
        else:
            safe_path = safe_filename

        # 경로 검증
        upload_root = os.path.realpath(upload_folder)
        full_path = os.path.realpath(os.path.join(upload_folder, safe_path))
        try:
            within_root = os.path.commonpath([full_path, upload_root]) == upload_root
        except ValueError:
            within_root = False
        if not within_root:
            logger.warning(f"Path traversal attempt: {filename}")
            return jsonify({'error': '잘못된 요청입니다.'}), 400

        if not os.path.isfile(full_path):
            return jsonify({'error': '파일을 찾을 수 없습니다.'}), 404

        download_name = safe_filename
        if not is_profile:
            # room_files에서 소유 방을 확인해 접근을 제어한다.
            try:
                conn = get_db()
                cursor = conn.cursor()
                lookup_path = safe_path.replace('\\', '/')
                cursor.execute(
                    'SELECT room_id, file_name FROM room_files WHERE file_path = ? ORDER BY id DESC LIMIT 1',
                    (lookup_path,),
                )
                row = cursor.fetchone()
            except Exception as e:
                logger.warning(f"Upload auth lookup failed: {e}")
                row = None

            if not row:
                return jsonify({'error': '파일을 찾을 수 없습니다.'}), 404

            room_id = row['room_id']
            download_name = row['file_name'] or download_name
            if not is_room_member(room_id, session['user_id']):
                return jsonify({'error': '접근 권한이 없습니다.'}), 403

        # Content-Disposition: 이미지는 inline, 그 외 파일은 attachment
        ext = os.path.splitext(safe_filename)[1].lower().lstrip('.')
        inline_exts = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'ico'}
        as_attachment = (not is_profile) and (ext not in inline_exts)

        response = send_from_directory(
            os.path.dirname(full_path),
            os.path.basename(full_path),
            as_attachment=as_attachment,
            download_name=download_name if as_attachment else None,
        )

        # 인증 리소스 캐시 정책
        if is_profile:
            response.headers['Cache-Control'] = 'private, max-age=3600'
        else:
            response.headers['Cache-Control'] = 'private, no-store'
        response.headers['Vary'] = 'Accept-Encoding'
        if not as_attachment and ext in inline_exts:
            response.headers['Content-Disposition'] = 'inline'
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
        
        data, error_response = parse_json_payload()
        if error_response:
            return error_response
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
        upload_folder = app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER)
        
        if 'file' not in request.files:
            return jsonify({'error': '파일이 없습니다.'}), 400
        
        file = request.files['file']
        original_filename = file.filename or ''
        if original_filename == '':
            return jsonify({'error': '파일을 선택하지 않았습니다.'}), 400
        
        # 이미지 파일만 허용
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        ext = original_filename.rsplit('.', 1)[-1].lower() if '.' in original_filename else ''
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
        profile_folder = os.path.join(upload_folder, 'profiles')
        os.makedirs(profile_folder, exist_ok=True)
        
        # [v4.12] 기존 프로필 이미지 삭제 (디스크 공간 절약)
        user = get_user_by_id(session['user_id'])
        if user and user.get('profile_image'):
            try:
                old_image_path = os.path.join(upload_folder, user['profile_image'])
                # [v4.14] safe_file_delete 사용
                if safe_file_delete(old_image_path):
                    logger.debug(f"Old profile image deleted: {user['profile_image']}")
            except Exception as e:
                logger.warning(f"Old profile image deletion failed: {e}")
        
        # 파일 저장: [v4.14] UUID 추가로 동시 업로드 시 파일명 충돌 방지
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
        upload_folder = app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER)
        if user and user.get('profile_image'):
            try:
                old_image_path = os.path.join(upload_folder, user['profile_image'])
                # [v4.14] safe_file_delete 사용
                safe_file_delete(old_image_path)
            except Exception as e:
                logger.warning(f"Profile image file deletion failed: {e}")
        
        # DB에서 프로필 이미지 제거 (null 대신 빈 문자열)
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
        
        data, error_response = parse_json_payload()
        if error_response:
            return error_response
        message_id = data.get('message_id')
        content = sanitize_input(data.get('content', ''), max_length=500)
        
        if not message_id and not content:
            return jsonify({'error': '고정할 메시지 또는 내용을 입력해 주세요.'}), 400
        
        pin_id = pin_message(room_id, session['user_id'], message_id, content)
        if pin_id:
            nickname = session.get('nickname', 'User')
            _emit_pin_system_message(
                room_id,
                session['user_id'],
                f"{nickname} pinned a message.",
            )
            _emit_pin_updated(room_id)
            return jsonify({'success': True, 'pin_id': pin_id})
        return jsonify({'error': '공지 고정에 실패했습니다.'}), 500
    
    @app.route('/api/rooms/<int:room_id>/pins/<int:pin_id>', methods=['DELETE'])
    def delete_pin(room_id, pin_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        if not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '접근 권한이 없습니다.'}), 403
        
        # [v4.20] 모든 멤버가 공지 해제 가능 (관리자 제한 제거)
        
        success, error = unpin_message(pin_id, session['user_id'], room_id)
        if success:
            nickname = session.get('nickname', 'User')
            _emit_pin_system_message(
                room_id,
                session['user_id'],
                f"{nickname} removed a pinned message.",
            )
            _emit_pin_updated(room_id)
            return jsonify({'success': True})
        if error and '찾을 수 없습니다' in error:
            return jsonify({'error': error}), 404
        if error and '일치하지 않습니다' in error:
            return jsonify({'error': error}), 403
        return jsonify({'error': error or '공지 해제에 실패했습니다.'}), 400
    
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
        
        data, error_response = parse_json_payload()
        if error_response:
            return error_response
        question = sanitize_input(data.get('question', ''), max_length=200)
        options = data.get('options', [])
        multiple_choice = data.get('multiple_choice', False)
        anonymous = data.get('anonymous', False)
        ends_at = data.get('ends_at')  # [v4.8] ISO 형식 날짜/시간 문자열
        
        if not question:
            return jsonify({'error': '질문을 입력해 주세요.'}), 400
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
                # DB 저장 형식으로 변환 (UTC 정보 없는 문자열)
                ends_at = ends_at_dt.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                return jsonify({'error': '올바른 날짜/시간 형식이 아닙니다. (ISO 8601)'}), 400
        
        options = [sanitize_input(opt, max_length=100) for opt in options[:10]]
        
        poll_id = create_poll(room_id, session['user_id'], question, options, multiple_choice, anonymous, ends_at)
        if poll_id:
            poll = get_poll(poll_id)
            if poll:
                return jsonify({'success': True, 'poll': poll})
            logger.error(f"Poll created but lookup failed: poll_id={poll_id}")
            return jsonify({'error': '투표 생성 후 조회에 실패했습니다.'}), 500
        return jsonify({'error': '투표 생성에 실패했습니다.'}), 500
    
    @app.route('/api/polls/<int:poll_id>/vote', methods=['POST'])
    def vote_poll_route(poll_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        # [v4.6] 투표가 속한 방의 멤버인지 확인
        poll = get_poll(poll_id)
        if not poll:
            return jsonify({'error': '투표를 찾을 수 없습니다.'}), 404
        if not is_room_member(poll['room_id'], session['user_id']):
            return jsonify({'error': '접근 권한이 없습니다.'}), 403
        
        data, error_response = parse_json_payload()
        if error_response:
            return error_response
        option_id = data.get('option_id')
        
        if not option_id:
            return json_error('옵션을 선택해 주세요.', 400, 'missing_option_id')

        success, error = vote_poll(poll_id, option_id, session['user_id'])
        if success:
            poll = get_poll(poll_id)
            if not poll:
                return json_error('Poll reload failed.', 500, 'poll_reload_failed')
            poll['my_votes'] = get_user_votes(poll_id, session['user_id'])
            return jsonify({'success': True, 'poll': poll})
        return json_error(error or '투표 실패', 400, 'invalid_poll_option')
    
    @app.route('/api/polls/<int:poll_id>/close', methods=['POST'])
    def close_poll_route(poll_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        # [v4.5] 투표가 속한 방의 멤버인지 확인
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
        # [v4.9] room_id를 전달해 다른 방 파일 삭제를 방지
        success, file_path = delete_room_file(file_id, session['user_id'], room_id=room_id, is_admin=is_admin)
        if success:
            if is_admin:
                log_admin_action(
                    room_id=room_id,
                    actor_user_id=session['user_id'],
                    action='delete_file',
                    metadata={'file_id': file_id, 'file_path': file_path},
                )
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
        
        data, error_response = parse_json_payload()
        if error_response:
            return error_response
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
        
        data, error_response = parse_json_payload()
        if error_response:
            return error_response
        target_user_id = data.get('user_id')
        is_admin = data.get('is_admin', True)
        
        if not target_user_id:
            return jsonify({'error': '사용자를 선택해 주세요.'}), 400
        
        # [v4.13] 마지막 관리자 해제 방지
        if not is_admin:
            admins = get_room_admins(room_id)
            if len(admins) <= 1:
                return jsonify({'error': '최소 한 명의 관리자가 필요합니다.'}), 400
        
        if set_room_admin(room_id, target_user_id, is_admin):
            log_admin_action(
                room_id=room_id,
                actor_user_id=session['user_id'],
                target_user_id=target_user_id,
                action='set_admin' if is_admin else 'unset_admin',
                metadata={'source': 'api'},
            )
            return jsonify({'success': True})
        return jsonify({'error': '관리자 설정에 실패했습니다.'}), 500
    
    @app.route('/api/rooms/<int:room_id>/admin-check')
    def check_admin(room_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        # [v4.22] 멤버 확인 추가
        if not is_room_member(room_id, session['user_id']):
            return jsonify({'error': '접근 권한이 없습니다.'}), 403
        is_admin = is_room_admin(room_id, session['user_id'])
        return jsonify({'is_admin': is_admin})

    @app.route('/api/rooms/<int:room_id>/admin-audit-logs')
    def room_admin_audit_logs(room_id):
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        if not is_room_admin(room_id, session['user_id']):
            return jsonify({'error': '관리자 권한이 필요합니다.'}), 403

        output_format = (request.args.get('format') or 'json').lower()
        limit = request.args.get('limit', type=int) or 200
        offset = request.args.get('offset', type=int) or 0
        logs = get_admin_audit_logs(room_id=room_id, limit=limit, offset=offset)

        if output_format == 'csv':
            stream = io.StringIO()
            writer = csv.writer(stream)
            writer.writerow(['id', 'room_id', 'actor_user_id', 'actor_nickname', 'target_user_id', 'target_nickname', 'action', 'metadata', 'created_at'])
            for row in logs:
                writer.writerow([
                    row.get('id'),
                    row.get('room_id'),
                    row.get('actor_user_id'),
                    row.get('actor_nickname'),
                    row.get('target_user_id'),
                    row.get('target_nickname'),
                    row.get('action'),
                    row.get('metadata'),
                    row.get('created_at'),
                ])
            response = make_response(stream.getvalue())
            response.headers['Content-Type'] = 'text/csv; charset=utf-8'
            response.headers['Content-Disposition'] = f'attachment; filename=room_{room_id}_admin_audit_logs.csv'
            return response

        return jsonify({'logs': logs, 'limit': limit, 'offset': offset})
    
    # ============================================================================
    # 고급 검색 API
    # ============================================================================
    @app.route('/api/search/advanced', methods=['POST'])
    @limiter.limit(advanced_search_rate_limit)
    def advanced_search_route():
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        data, error_response = parse_json_payload()
        if error_response:
            return error_response
        limit, error_response = parse_int_from_json(data, 'limit', 50, minimum=1, maximum=200)
        if error_response:
            return error_response
        offset, error_response = parse_int_from_json(data, 'offset', 0, minimum=0)
        if error_response:
            return error_response
        results = advanced_search(
            user_id=session['user_id'],
            query=data.get('query'),
            room_id=data.get('room_id'),
            sender_id=data.get('sender_id'),
            date_from=data.get('date_from'),
            date_to=data.get('date_to'),
            file_only=data.get('file_only', False),
            limit=limit,
            offset=offset,
        )
        return jsonify(results)

    # ============================================================================
    # [v4.1] 계정 보안 API
    # ============================================================================
    @app.route('/api/me/password', methods=['PUT'])
    def update_password():
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
            
        data, error_response = parse_json_payload()
        if error_response:
            return error_response
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        
        if not current_password or not new_password:
            return jsonify({'error': '입력값이 부족합니다.'}), 400
            
        # [v4.3] 비밀번호 강도 검증
        from app.utils import validate_password
        is_valid, error_msg = validate_password(new_password)
        if not is_valid:
            return jsonify({'error': error_msg}), 400
            
        # [v4.21] 모든 세션 토큰과 함께 비밀번호 변경
        success, error, new_session_token = change_password(session['user_id'], current_password, new_password)
        
        if success:
            # 현재 세션의 새 토큰 반영 (다른 세션은 무효화됨)
            if new_session_token:
                session['session_token'] = new_session_token
            log_access(session['user_id'], 'change_password', request.remote_addr, request.user_agent.string)
            return jsonify({
                'success': True,
                'message': '비밀번호가 변경되었습니다. 다른 기기에서는 세션이 로그아웃됩니다.'
            })
        else:
            return jsonify({'error': error}), 400

    @app.route('/api/me', methods=['DELETE'])
    def delete_account():
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
            
        data, error_response = parse_json_payload()
        if error_response:
            return error_response
        password = data.get('password')
        
        if not password:
            return jsonify({'error': '비밀번호를 입력해 주세요.'}), 400
            
        success, error = delete_user(session['user_id'], password)
        
        if success:
            log_access(session['user_id'], 'delete_account', request.remote_addr, request.user_agent.string)
            session.clear()
            return jsonify({'success': True})
        else:
            return jsonify({'error': error}), 400
