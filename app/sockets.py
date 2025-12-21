# -*- coding: utf-8 -*-
"""
Socket.IO 이벤트 핸들러 (성능 최적화 버전)
"""

import logging
import time
import traceback
from threading import Lock
from flask import session, request
from flask_socketio import emit, join_room, leave_room

from app.models import (
    update_user_status, get_user_by_id, is_room_member,
    create_message, update_last_read, get_unread_count, server_stats,
    get_user_rooms, edit_message, delete_message
)

logger = logging.getLogger(__name__)

# 온라인 사용자 관리
online_users = {}  # {sid: user_id}
user_sids = {}     # {user_id: [sid1, sid2, ...]} - 다중 세션 지원
online_users_lock = Lock()
stats_lock = Lock()

# 사용자별 캐시 (닉네임, 방 목록)
user_cache = {}  # {user_id: {'nickname': str, 'rooms': [int], 'updated': float}}
cache_lock = Lock()


def get_user_room_ids(user_id):
    """사용자의 방 ID 목록 (캐시 사용)"""
    with cache_lock:
        cached = user_cache.get(user_id)
        # 캐시가 있고 5분 이내면 사용
        if cached and (time.time() - cached.get('updated', 0)) < 300:
            return cached.get('rooms', [])
    
    # 캐시 없거나 만료되면 DB에서 조회
    try:
        rooms = get_user_rooms(user_id)
        room_ids = [r['id'] for r in rooms]
        
        with cache_lock:
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
    
    @socketio.on('connect')
    def handle_connect():
        if 'user_id' in session:
            user_id = session['user_id']
            
            with online_users_lock:
                online_users[request.sid] = user_id
                if user_id not in user_sids:
                    user_sids[user_id] = []
                user_sids[user_id].append(request.sid)
                was_offline = len(user_sids[user_id]) == 1
            
            # 첫 연결일 때만 상태 업데이트
            if was_offline:
                update_user_status(user_id, 'online')
                # 해당 사용자의 방에만 상태 전송 (broadcast 대신)
                for room_id in get_user_room_ids(user_id):
                    emit('user_status', {'user_id': user_id, 'status': 'online'}, 
                         room=f'room_{room_id}')
            
            with stats_lock:
                server_stats['total_connections'] += 1
                server_stats['active_connections'] += 1
    
    @socketio.on('disconnect')
    def handle_disconnect():
        user_id = None
        still_online = False
        
        with online_users_lock:
            user_id = online_users.pop(request.sid, None)
            if user_id and user_id in user_sids:
                if request.sid in user_sids[user_id]:
                    user_sids[user_id].remove(request.sid)
                still_online = len(user_sids[user_id]) > 0
                if not still_online:
                    del user_sids[user_id]
        
        if user_id and not still_online:
            update_user_status(user_id, 'offline')
            # 해당 사용자의 방에만 상태 전송
            try:
                for room_id in get_user_room_ids(user_id):
                    emit('user_status', {'user_id': user_id, 'status': 'offline'}, 
                         room=f'room_{room_id}')
            except Exception as e:
                logger.error(f"Disconnect broadcast error: {e}")
        
        with stats_lock:
            server_stats['active_connections'] = max(0, server_stats['active_connections'] - 1)
    
    @socketio.on('join_room')
    def handle_join_room(data):
        try:
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
                        emit('error', {'message': '대화방 접근 권한이 없습니다.'})
        except Exception as e:
            logger.error(f"Join room error: {e}")
    
    @socketio.on('leave_room')
    def handle_leave_room(data):
        try:
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
            
            # 캐시된 방 목록으로 빠른 확인
            user_rooms = get_user_room_ids(session['user_id'])
            if room_id not in user_rooms:
                if not is_room_member(room_id, session['user_id']):
                    emit('error', {'message': '대화방 접근 권한이 없습니다.'})
                    return
            
            message = create_message(
                room_id, session['user_id'], content, message_type, file_path, file_name, reply_to, encrypted
            )
            if message:
                message['unread_count'] = get_unread_count(room_id, message['id'])
                emit('new_message', message, room=f'room_{room_id}')
                # broadcast 대신 해당 방 멤버들의 모든 세션에 전송
                emit('room_updated', {'room_id': room_id}, room=f'room_{room_id}')
                logger.debug(f"Message sent: room={room_id}, user={session['user_id']}, type={message_type}")
            else:
                logger.warning(f"Message creation failed: room={room_id}, user={session['user_id']}")
                emit('error', {'message': '메시지 저장에 실패했습니다.'})
        except Exception as e:
            logger.error(f"Send message error: {e}\n{traceback.format_exc()}")
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
        try:
            if 'user_id' not in session:
                return
            
            room_id = data.get('room_id')
            if not room_id:
                return
            
            is_typing = data.get('is_typing', False)
            # 세션에서 닉네임 가져오기 (DB 조회 제거)
            nickname = session.get('nickname', '')
            
            emit('user_typing', {
                'room_id': room_id,
                'user_id': session['user_id'],
                'nickname': nickname,
                'is_typing': is_typing
            }, room=f'room_{room_id}', include_self=False)
        except Exception as e:
            logger.error(f"Typing event error: {e}")
    
    # 방 이름 변경 알림
    @socketio.on('room_name_updated')
    def handle_room_name_updated(data):
        try:
            room_id = data.get('room_id')
            new_name = data.get('name')
            if room_id and new_name:
                emit('room_name_updated', {'room_id': room_id, 'name': new_name}, room=f'room_{room_id}')
        except Exception as e:
            logger.error(f"Room name update broadcast error: {e}")
    
    # 멤버 변경 알림
    @socketio.on('room_members_updated')
    def handle_room_members_updated(data):
        try:
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
            if 'user_id' not in session:
                return
            
            message_id = data.get('message_id')
            content = data.get('content', '').strip()
            encrypted = data.get('encrypted', True)
            
            if not message_id or not content:
                emit('error', {'message': '잘못된 요청입니다.'})
                return
            
            success, error_msg, room_id = edit_message(message_id, session['user_id'], content)
            if success:
                emit('message_edited', {
                    'message_id': message_id,
                    'content': content,
                    'encrypted': encrypted
                }, room=f'room_{room_id}')
            else:
                emit('error', {'message': error_msg})
        except Exception as e:
            logger.error(f"Edit message error: {e}")
            emit('error', {'message': '메시지 수정에 실패했습니다.'})

    # 메시지 삭제
    @socketio.on('delete_message')
    def handle_delete_message(data):
        try:
            if 'user_id' not in session:
                return
            
            message_id = data.get('message_id')
            
            if not message_id:
                emit('error', {'message': '잘못된 요청입니다.'})
                return
            
            success, result = delete_message(message_id, session['user_id'])
            if success:
                room_id = result
                emit('message_deleted', {
                    'message_id': message_id
                }, room=f'room_{room_id}')
            else:
                emit('error', {'message': result})
        except Exception as e:
            logger.error(f"Delete message error: {e}")
            emit('error', {'message': '메시지 삭제에 실패했습니다.'})
