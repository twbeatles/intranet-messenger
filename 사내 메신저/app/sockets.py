# -*- coding: utf-8 -*-
"""
Socket.IO 이벤트 핸들러
"""

import logging
from threading import Lock
from flask import session, request
from flask_socketio import emit, join_room, leave_room

from app.models import (
    update_user_status, get_user_by_id, is_room_member,
    create_message, update_last_read, get_unread_count, server_stats
)

logger = logging.getLogger(__name__)

# 온라인 사용자 관리
online_users = {}
online_users_lock = Lock()
stats_lock = Lock()


def register_socket_events(socketio):
    """Socket.IO 이벤트 등록"""
    
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
            
            if not is_room_member(room_id, session['user_id']):
                emit('error', {'message': '대화방 접근 권한이 없습니다.'})
                return
            
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
        try:
            if 'user_id' not in session:
                return
            
            room_id = data.get('room_id')
            if not room_id:
                return
                
            is_typing = data.get('is_typing', False)
            user = get_user_by_id(session['user_id'])
            
            if user:
                emit('user_typing', {
                    'room_id': room_id,
                    'user_id': session['user_id'],
                    'nickname': user.get('nickname', ''),
                    'is_typing': is_typing
                }, room=f'room_{room_id}', include_self=False)
        except Exception as e:
            logger.error(f"Typing event error: {e}")
    
    # 방 이름 변경 알림
    @socketio.on('room_name_updated')
    def handle_room_name_updated(data):
        room_id = data.get('room_id')
        new_name = data.get('name')
        if room_id and new_name:
            emit('room_name_updated', {'room_id': room_id, 'name': new_name}, room=f'room_{room_id}')
    
    # 멤버 변경 알림
    @socketio.on('room_members_updated')
    def handle_room_members_updated(data):
        room_id = data.get('room_id')
        if room_id:
            emit('room_members_updated', {'room_id': room_id}, room=f'room_{room_id}')
