# -*- coding: utf-8 -*-
"""
Socket.IO 이벤트 핸들러 (성능 최적화 버전)
"""

import logging
import re
import time
import traceback
from threading import Lock
from flask import session, request, current_app
from flask_socketio import emit, join_room, leave_room, disconnect

from app.models import (
    update_user_status, get_user_by_id, is_room_member, is_room_admin,
    create_message, update_last_read, get_unread_count, server_stats,
    get_user_rooms, edit_message, delete_message, get_user_session_token
)
from app.upload_tokens import consume_upload_token, get_upload_token_failure_reason
from app.state_store import state_store

logger = logging.getLogger(__name__)

_MOJIBAKE_HINT_TOKENS = (
    "濡쒓렇", "꾩슂", "뺤옣", "먯꽌", "룞", "몄씠", "⑸땲", "뒿", "媛뺥",
    "앹꽦", "怨듭", "뚯씪", "紐낆쓽", "쒖냼", "먮룞", "쒕쾭", "곗씠",
)
_MOJIBAKE_LATIN_RE = re.compile(r"[Ã-ÿ]{2,}")

# 온라인 사용자 관리
online_users = {}  # {sid: user_id}
user_sids = {}     # {user_id: [sid1, sid2, ...]} - 다중 세션 지원
online_users_lock = Lock()
stats_lock = Lock()

# 사용자별 캐시 (닉네임, 방 목록)
user_cache = {}  # {user_id: {'nickname': str, 'rooms': [int], 'updated': float}}
cache_lock = Lock()
MAX_CACHE_SIZE = 1000  # [v4.1] 최대 캐시 크기
CACHE_TTL = 300  # [v4.1] 캐시 유효 시간 (5분)

# [v4.14] 타이핑 이벤트 레이트 리미팅
typing_last_emit = {}  # {(user_id, room_id): timestamp}
typing_rate_lock = Lock()
TYPING_RATE_LIMIT = 1.0  # 최소 1초 간격


def cleanup_old_cache():
    """오래된 캐시 항목 정리 (메모리 누수 방지)"""
    current_time = time.time()
    expired_keys = []
    
    with cache_lock:
        # 10분 이상 된 캐시 항목 식별
        for user_id, data in user_cache.items():
            if current_time - data.get('updated', 0) > 600:  # 10분
                expired_keys.append(user_id)
        
        # 만료된 항목 삭제
        for key in expired_keys:
            del user_cache[key]
        
        # 캐시 크기 제한 (FIFO 방식)
        if len(user_cache) > MAX_CACHE_SIZE:
            sorted_items = sorted(user_cache.items(), key=lambda x: x[1].get('updated', 0))
            to_remove = len(user_cache) - MAX_CACHE_SIZE
            for i in range(to_remove):
                del user_cache[sorted_items[i][0]]
    
    if expired_keys:
        logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")


def get_user_room_ids(user_id):
    """사용자의 방 ID 목록 (캐시 사용)"""
    with cache_lock:
        cached = user_cache.get(user_id)
        # 캐시가 있고 TTL 이내면 사용
        if cached and (time.time() - cached.get('updated', 0)) < CACHE_TTL:
            return cached.get('rooms', [])
    
    # 캐시 없거나 만료되면 DB에서 조회
    try:
        rooms = get_user_rooms(user_id)
        room_ids = [r['id'] for r in rooms]
        
        with cache_lock:
            # 캐시 정리 (주기적으로)
            if len(user_cache) > MAX_CACHE_SIZE // 2:
                cleanup_old_cache()
            
            if user_id not in user_cache:
                user_cache[user_id] = {}
            user_cache[user_id]['rooms'] = room_ids
            user_cache[user_id]['updated'] = time.time()
        
        return room_ids
    except Exception as e:
        logger.error(f"Get user rooms error: {e}")
        return []


def invalidate_user_cache(user_id):
    """사용자 캐시 무효화"""
    with cache_lock:
        if user_id in user_cache:
            del user_cache[user_id]


def register_socket_events(socketio):
    """Socket.IO 이벤트 등록"""

    def _looks_like_mojibake(text: str) -> bool:
        if not isinstance(text, str) or not text:
            return False
        if any(token in text for token in _MOJIBAKE_HINT_TOKENS):
            return True
        if _MOJIBAKE_LATIN_RE.search(text):
            return True
        if text.count("?") >= 2 and any(ord(ch) > 127 for ch in text):
            return True
        return False

    def _sanitize_client_message(message: str, fallback: str = "요청 처리 중 오류가 발생했습니다.") -> str:
        if _looks_like_mojibake(message):
            return fallback
        return message

    def _emit_error(message: str, fallback: str = "요청 처리 중 오류가 발생했습니다."):
        emit("error", {"message": _sanitize_client_message(message, fallback)})

    def _is_session_token_valid() -> bool:
        if 'user_id' not in session:
            return False
        user_id = session.get('user_id')
        if not user_id:
            return False
        current_token = session.get('session_token')
        db_token = get_user_session_token(user_id)
        return bool(current_token and db_token and current_token == db_token)

    def _ensure_session_token(event_name: str):
        if _is_session_token_valid():
            return True
        logger.warning(f"Socket session invalidated during event: {event_name}")
        _emit_error('세션이 만료되었거나 다른 세션에서 무효화되었습니다.')
        try:
            disconnect()
        except Exception:
            pass
        return False

    def _check_send_message_rate_limit(user_id: int) -> bool:
        per_minute = int(current_app.config.get('SOCKET_SEND_MESSAGE_PER_MINUTE', 100))
        key = f"socket:send_message:{user_id}"
        count = state_store.incr(key, ttl_seconds=60)
        return count <= per_minute

    @socketio.on('connect')
    def handle_connect():
        if not _is_session_token_valid():
            return False

        if 'user_id' in session:
            user_id = session['user_id']
            
            with online_users_lock:
                online_users[request.sid] = user_id
                if user_id not in user_sids:
                    user_sids[user_id] = []
                user_sids[user_id].append(request.sid)
            was_offline = state_store.incr(f"presence:user:{user_id}") == 1
            
            # Join all my rooms so this client receives room events without polling.
            room_ids = get_user_room_ids(user_id)
            for room_id in room_ids:
                try:
                    join_room(f'room_{room_id}')
                except Exception:
                    pass

            # 첫 연결일 때만 상태 업데이트
            if was_offline:
                update_user_status(user_id, 'online')
                # 해당 사용자의 방에만 상태 전송 (broadcast 대신)
                for room_id in room_ids:
                    emit('user_status', {'user_id': user_id, 'status': 'online'}, 
                         room=f'room_{room_id}')
            
            with stats_lock:
                server_stats['total_connections'] += 1
                server_stats['active_connections'] += 1
                # [v4.22] 100개 연결마다 캐시 정리 (메모리 누수 방지)
                should_cleanup = server_stats['total_connections'] % 100 == 0
            
            if should_cleanup:
                cleanup_old_cache()
    
    @socketio.on('disconnect')
    def handle_disconnect():
        user_id = None
        still_online = False
        room_ids = []  # [v4.2] 락 내에서 미리 저장
        
        with online_users_lock:
            user_id = online_users.pop(request.sid, None)
            if user_id and user_id in user_sids:
                if request.sid in user_sids[user_id]:
                    user_sids[user_id].remove(request.sid)
                local_still_online = len(user_sids[user_id]) > 0
                if not local_still_online:
                    del user_sids[user_id]
                    # [v4.2] 락 내에서 방 목록 캐시 복사
                    if user_id in user_cache:
                        room_ids = user_cache[user_id].get('rooms', []).copy()
        if user_id:
            still_online = state_store.decr(f"presence:user:{user_id}") > 0
        
        # [v4.2] 락 해제 후 DB 작업 및 브로드캐스트 (락 내에서 가져온 정보 사용)
        if user_id and not still_online:
            update_user_status(user_id, 'offline')
            # 캐시가 없었으면 DB에서 조회
            if not room_ids:
                room_ids = get_user_room_ids(user_id)
            try:
                for room_id in room_ids:
                    emit('user_status', {'user_id': user_id, 'status': 'offline'}, 
                         room=f'room_{room_id}')
            except Exception as e:
                logger.error(f"Disconnect broadcast error: {e}")
            
            # [v4.15] 사용자의 타이핑 레이트 리밋 정보 정리 (메모리 누수 방지)
            with typing_rate_lock:
                keys_to_remove = [k for k in typing_last_emit if k[0] == user_id]
                for k in keys_to_remove:
                    del typing_last_emit[k]
        
        with stats_lock:
            server_stats['active_connections'] = max(0, server_stats['active_connections'] - 1)
    
    @socketio.on('subscribe_rooms')
    def handle_subscribe_rooms(data):
        try:
            if not _ensure_session_token('subscribe_rooms'):
                return

            room_ids = data.get('room_ids') if isinstance(data, dict) else None
            if not isinstance(room_ids, list):
                return

            room_ids = [rid for rid in room_ids if isinstance(rid, int) and rid > 0]
            if not room_ids:
                return

            user_id = session['user_id']
            allowed = set(get_user_room_ids(user_id))
            for rid in room_ids:
                if rid in allowed:
                    join_room(f'room_{rid}')
                    continue

                # Cache can be stale right after room creation/invite; fallback to DB check.
                if is_room_member(rid, user_id):
                    invalidate_user_cache(user_id)
                    join_room(f'room_{rid}')
        except Exception as e:
            logger.error(f"Subscribe rooms error: {e}")

    @socketio.on('join_room')
    def handle_join_room(data):
        try:
            if not _ensure_session_token('join_room'):
                return
            room_id = data.get('room_id')
            if room_id and 'user_id' in session:
                # 캐시된 방 목록으로 빠른 확인
                user_rooms = get_user_room_ids(session['user_id'])
                if room_id in user_rooms:
                    join_room(f'room_{room_id}')
                    emit('joined_room', {'room_id': room_id})
                else:
                    # 캐시에 없으면 DB 직접 확인 (새로 초대된 경우)
                    if is_room_member(room_id, session['user_id']):
                        invalidate_user_cache(session['user_id'])
                        join_room(f'room_{room_id}')
                        emit('joined_room', {'room_id': room_id})
                    else:
                        _emit_error('대화방 접근 권한이 없습니다.')
        except Exception as e:
            logger.error(f"Join room error: {e}")
    
    @socketio.on('leave_room')
    def handle_leave_room(data):
        try:
            if not _ensure_session_token('leave_room'):
                return
            room_id = data.get('room_id')
            if room_id:
                leave_room(f'room_{room_id}')
                # 캐시 무효화
                if 'user_id' in session:
                    invalidate_user_cache(session['user_id'])
        except Exception as e:
            logger.error(f"Leave room error: {e}")
    
    @socketio.on('send_message')
    def handle_send_message(data):
        try:
            if not _ensure_session_token('send_message'):
                return
            user_id = session['user_id']
            if not _check_send_message_rate_limit(user_id):
                _emit_error('메시지 전송 속도 제한을 초과했습니다.')
                return
            
            # [v4.2] 입력 유효성 검사 강화
            room_id = data.get('room_id')
            if not isinstance(room_id, int) or room_id <= 0:
                _emit_error('잘못된 대화방 ID입니다.')
                return
            
            content = data.get('content', '')
            if isinstance(content, str):
                content = content.strip()[:10000]  # 최대 10000자 제한
            else:
                content = ''
            
            message_type = data.get('type', 'text')
            # 허용된 메시지 타입만 사용
            allowed_types = {'text', 'file', 'image', 'system'}
            if message_type not in allowed_types:
                message_type = 'text'
            
            file_path = None
            file_name = None
            file_size = None
            reply_to = data.get('reply_to')
            if reply_to is not None and not isinstance(reply_to, int):
                reply_to = None
            encrypted = bool(data.get('encrypted', True))

            # 캐시된 방 목록으로 빠른 확인
            user_rooms = get_user_room_ids(user_id)
            if room_id not in user_rooms:
                if not is_room_member(room_id, user_id):
                    _emit_error('대화방 접근 권한이 없습니다.')
                    return

            if message_type in ('file', 'image'):
                token = data.get('upload_token')
                reason = get_upload_token_failure_reason(
                    token=token,
                    user_id=user_id,
                    room_id=room_id,
                    expected_type=message_type,
                )
                if reason:
                    _emit_error(reason)
                    return

                token_data = consume_upload_token(
                    token=token,
                    user_id=user_id,
                    room_id=room_id,
                    expected_type=message_type,
                )
                if not token_data:
                    _emit_error('업로드 토큰이 이미 사용되었거나 만료되었습니다.')
                    return

                file_path = token_data.get('file_path')
                file_name = token_data.get('file_name')
                file_size = token_data.get('file_size')
                encrypted = False
                content = file_name or content

            if not content and not file_path:
                return
            
            message = create_message(
                room_id, user_id, content, message_type, file_path, file_name, reply_to, encrypted
            )
            if message:
                message['unread_count'] = get_unread_count(room_id, message['id'], user_id)
                if message_type in ('file', 'image') and file_path:
                    from app.models import add_room_file

                    try:
                        add_room_file(room_id, user_id, file_path, file_name, file_size, message_type, message['id'])
                    except Exception as e:
                        logger.error(f"Failed to add room file record: {e}")
                        logger.warning(
                            f"Potential orphan upload file detected: room={room_id}, user={user_id}, path={file_path}"
                        )

                emit('new_message', message, room=f'room_{room_id}')
                # broadcast 대신 해당 방 멤버들의 모든 세션에 전송
                logger.debug(f"Message sent: room={room_id}, user={user_id}, type={message_type}")
            else:
                logger.warning(f"Message creation failed: room={room_id}, user={user_id}")
                if message_type in ('file', 'image') and file_path:
                    logger.warning(
                        f"Potential orphan upload file after message failure: room={room_id}, user={user_id}, path={file_path}"
                    )
                _emit_error('메시지 저장에 실패했습니다.')
        except Exception as e:
            logger.error(f"Send message error: {e}\n{traceback.format_exc()}")
            _emit_error('메시지 전송에 실패했습니다.')
    
    @socketio.on('message_read')
    def handle_message_read(data):
        try:
            if not _ensure_session_token('message_read'):
                return
            
            room_id = data.get('room_id')
            message_id = data.get('message_id')
            
            if room_id and message_id:
                # [v4.13] 멤버십 확인
                if not is_room_member(room_id, session['user_id']):
                    return
                
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
        try:
            if not _ensure_session_token('typing'):
                return
            
            room_id = data.get('room_id')
            if not room_id:
                return
            
            user_id = session['user_id']
            
            # [v4.21] 멤버십 검증
            if not is_room_member(room_id, user_id):
                return
            
            # [v4.14] 타이핑 레이트 리미팅
            current_time = time.time()
            rate_key = (user_id, room_id)
            with typing_rate_lock:
                last_emit = typing_last_emit.get(rate_key, 0)
                if current_time - last_emit < TYPING_RATE_LIMIT:
                    return  # 너무 빈번한 이벤트 무시
                typing_last_emit[rate_key] = current_time
                # 오래된 항목 정리 (5분 이상)
                if len(typing_last_emit) > 1000:
                    expired = [k for k, v in typing_last_emit.items() if current_time - v > 300]
                    for k in expired:
                        del typing_last_emit[k]
            
            is_typing = data.get('is_typing', False)
            # 세션에서 닉네임 가져오기 (없으면 DB 조회)
            nickname = session.get('nickname', '')
            if not nickname:
                user = get_user_by_id(user_id)
                nickname = user.get('nickname', '사용자') if user else '사용자'
            
            emit('user_typing', {
                'room_id': room_id,
                'user_id': user_id,
                'nickname': nickname,
                'is_typing': is_typing
            }, room=f'room_{room_id}', include_self=False)
        except Exception as e:
            logger.error(f"Typing event error: {e}")
    
    # 방 이름 변경 알림
    @socketio.on('room_name_updated')
    def handle_room_name_updated(data):
        try:
            if not _ensure_session_token('room_name_updated'):
                return
            room_id = data.get('room_id')
            new_name = data.get('name')
            if room_id and new_name and 'user_id' in session:
                # [v4.9] 관리자 권한 확인
                if not is_room_admin(room_id, session['user_id']):
                    _emit_error('관리자만 방 이름을 변경할 수 있습니다.')
                    return
                
                # 시스템 메시지 생성
                nickname = session.get('nickname', '사용자')
                content = f"{nickname}님이 방 이름을 '{new_name}'(으)로 변경했습니다."
                sys_msg = create_message(room_id, session['user_id'], content, 'system')
                
                # 시스템 메시지 전송
                if sys_msg:
                    emit('new_message', sys_msg, room=f'room_{room_id}')
                
                emit('room_name_updated', {'room_id': room_id, 'name': new_name}, room=f'room_{room_id}')
        except Exception as e:
            logger.error(f"Room name update broadcast error: {e}")
    
    # 멤버 변경 알림
    @socketio.on('room_members_updated')
    def handle_room_members_updated(data):
        try:
            # [v4.14] 세션 검증 추가
            if not _ensure_session_token('room_members_updated'):
                return
            
            room_id = data.get('room_id')
            if room_id:
                # 관련 사용자들의 캐시 무효화
                emit('room_members_updated', {'room_id': room_id}, room=f'room_{room_id}')
        except Exception as e:
            logger.error(f"Room members update broadcast error: {e}")
    
    # 프로필 업데이트 알림
    @socketio.on('profile_updated')
    def handle_profile_updated(data):
        try:
            if not _ensure_session_token('profile_updated'):
                return
            if 'user_id' in session:
                user_id = session['user_id']
                nickname = data.get('nickname')
                profile_image = data.get('profile_image')
                
                # 모든 클라이언트에게 브로드캐스트 (본인 제외)
                emit('user_profile_updated', {
                    'user_id': user_id,
                    'nickname': nickname,
                    'profile_image': profile_image
                }, broadcast=True, include_self=False)
                
                logger.info(f"Profile updated broadcast: user_id={user_id}, nickname={nickname}, image={profile_image}")
        except Exception as e:
            logger.error(f"Profile update broadcast error: {e}")

    # 메시지 수정
    @socketio.on('edit_message')
    def handle_edit_message(data):
        try:
            if not _ensure_session_token('edit_message'):
                return
            
            message_id = data.get('message_id')
            content = data.get('content', '').strip()[:10000]  # [v4.10] 최대 10000자 제한
            encrypted = data.get('encrypted', True)
            
            if not message_id or not content:
                _emit_error('잘못된 요청입니다.')
                return
            
            success, error_msg, room_id = edit_message(message_id, session['user_id'], content)
            if success:
                emit('message_edited', {
                    'message_id': message_id,
                    'content': content,
                    'encrypted': encrypted
                }, room=f'room_{room_id}')
            else:
                _emit_error(error_msg)
        except Exception as e:
            logger.error(f"Edit message error: {e}")
            _emit_error('메시지 수정에 실패했습니다.')

    # 메시지 삭제
    @socketio.on('delete_message')
    def handle_delete_message(data):
        try:
            if not _ensure_session_token('delete_message'):
                return
            
            message_id = data.get('message_id')
            
            if not message_id:
                _emit_error('잘못된 요청입니다.')
                return
            
            success, result = delete_message(message_id, session['user_id'])
            if success:
                room_id = result
                emit('message_deleted', {
                    'message_id': message_id
                }, room=f'room_{room_id}')
            else:
                _emit_error(result)
        except Exception as e:
            logger.error(f"Delete message error: {e}")
            _emit_error('메시지 삭제에 실패했습니다.')

    # ============================================================================
    # v4.0 추가 이벤트
    # ============================================================================
    
    # 리액션 업데이트
    @socketio.on('reaction_updated')
    def handle_reaction_updated(data):
        try:
            room_id = data.get('room_id')
            message_id = data.get('message_id')
            reactions = data.get('reactions', [])
            
            # [v4.21] 세션 및 멤버십 확인 강화
            if not _ensure_session_token('reaction_updated'):
                return
            if not room_id or not message_id:
                _emit_error('잘못된 요청입니다.')
                return
            if not is_room_member(room_id, session['user_id']):
                _emit_error('대화방 멤버만 리액션을 추가할 수 있습니다.')
                return
            
            emit('reaction_updated', {
                'message_id': message_id,
                'reactions': reactions
            }, room=f'room_{room_id}')
        except Exception as e:
            logger.error(f"Reaction update broadcast error: {e}")
    
    # 투표 업데이트
    @socketio.on('poll_updated')
    def handle_poll_updated(data):
        try:
            room_id = data.get('room_id')
            poll = data.get('poll')
            
            # [v4.21] 세션 및 멤버십 확인 강화
            if not _ensure_session_token('poll_updated'):
                return
            if not room_id or not poll:
                _emit_error('잘못된 요청입니다.')
                return
            if not is_room_member(room_id, session['user_id']):
                _emit_error('대화방 멤버만 투표를 업데이트할 수 있습니다.')
                return
            
            emit('poll_updated', {
                'poll': poll
            }, room=f'room_{room_id}')
        except Exception as e:
            logger.error(f"Poll update broadcast error: {e}")
    
    # 투표 생성
    @socketio.on('poll_created')
    def handle_poll_created(data):
        try:
            room_id = data.get('room_id')
            poll = data.get('poll')
            
            # [v4.21] 세션 및 멤버십 확인 강화
            if not _ensure_session_token('poll_created'):
                return
            if not room_id or not poll:
                _emit_error('잘못된 요청입니다.')
                return
            if not is_room_member(room_id, session['user_id']):
                _emit_error('대화방 멤버만 투표를 생성할 수 있습니다.')
                return
            
            emit('poll_created', {
                'poll': poll
            }, room=f'room_{room_id}')
        except Exception as e:
            logger.error(f"Poll created broadcast error: {e}")
    
    # 공지 업데이트
    @socketio.on('pin_updated')
    def handle_pin_updated(data):
        try:
            if not _ensure_session_token('pin_updated'):
                return
            room_id = data.get('room_id')
            pins = data.get('pins', [])
            
            if room_id and 'user_id' in session:
                # [v4.10] 모든 멤버가 공지 가능
                if not is_room_member(room_id, session['user_id']):
                    _emit_error('대화방 멤버만 공지를 수정할 수 있습니다.')
                    return
                
                # 시스템 메시지 생성
                nickname = session.get('nickname', '사용자')
                content = f"{nickname}님이 공지사항을 업데이트했습니다."
                sys_msg = create_message(room_id, session['user_id'], content, 'system')
                
                if sys_msg:
                    emit('new_message', sys_msg, room=f'room_{room_id}')
                
                emit('pin_updated', {
                    'room_id': room_id,
                    'pins': pins
                }, room=f'room_{room_id}')
        except Exception as e:
            logger.error(f"Pin update broadcast error: {e}")
    
    # 관리자 변경
    @socketio.on('admin_updated')
    def handle_admin_updated(data):
        try:
            if not _ensure_session_token('admin_updated'):
                return
            room_id = data.get('room_id')
            target_user_id = data.get('user_id')
            is_admin_flag = data.get('is_admin')
            
            # [v4.9] 관리자 권한 확인
            if room_id and target_user_id is not None and 'user_id' in session:
                if not is_room_admin(room_id, session['user_id']):
                    _emit_error('관리자만 권한을 변경할 수 있습니다.')
                    return
                emit('admin_updated', {
                    'room_id': room_id,
                    'user_id': target_user_id,
                    'is_admin': is_admin_flag
                }, room=f'room_{room_id}')
        except Exception as e:
            logger.error(f"Admin update broadcast error: {e}")

