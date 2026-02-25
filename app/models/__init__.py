# -*- coding: utf-8 -*-
"""
데이터베이스 모델 패키지

모든 모델 함수를 이 패키지에서 re-export하여 
기존 코드와의 호환성을 유지합니다.

사용법:
    from app.models import create_user, authenticate_user, ...
    또는
    from app.models.users import create_user
"""

# Base - DB 연결 및 초기화
from app.models.base import (
    get_db,
    close_thread_db,
    get_db_context,
    init_db,
    safe_file_delete,
    close_expired_polls,
    cleanup_old_access_logs,
    cleanup_empty_rooms,
    cleanup_retention_data,
)

# Users - 사용자 관리
from app.models.users import (
    create_user,
    authenticate_user,
    get_user_by_id,
    get_user_by_id_cached,
    invalidate_user_cache,
    get_all_users,
    update_user_status,
    update_user_profile,
    get_online_users,
    log_access,
    change_password,
    get_user_session_token,
    get_or_create_oidc_user,
    delete_user,
)

# Rooms - 대화방 관리
from app.models.rooms import (
    create_room,
    get_room_key,
    get_user_rooms,
    get_room_members,
    is_room_member,
    add_room_member,
    leave_room_db,
    update_room_name,
    get_room_by_id,
    pin_room,
    mute_room,
    kick_member,
    set_room_admin,
    is_room_admin,
    get_room_admins,
)

# Messages - 메시지 관리
from app.models.messages import (
    create_message,
    get_room_messages,
    update_last_read,
    get_unread_count,
    get_room_last_reads,
    get_message_room_id,
    delete_message,
    edit_message,
    search_messages,
    advanced_search,
    pin_message,
    unpin_message,
    get_pinned_messages,
    server_stats,
    update_server_stats,
    get_server_stats,
)

# Polls - 투표 관리
from app.models.polls import (
    create_poll,
    get_poll,
    get_room_polls,
    vote_poll,
    get_user_votes,
    close_poll,
)

# Files - 파일 저장소
from app.models.files import (
    add_room_file,
    get_room_files,
    delete_room_file,
)

# Reactions - 리액션 관리
from app.models.reactions import (
    add_reaction,
    remove_reaction,
    toggle_reaction,
    get_message_reactions,
    get_messages_reactions,
)

# Admin Audit Logs
from app.models.admin_audit import (
    log_admin_action,
    get_admin_audit_logs,
)

__all__ = [
    # Base
    'get_db', 'close_thread_db', 'get_db_context', 'init_db', 'safe_file_delete',
    'close_expired_polls', 'cleanup_old_access_logs', 'cleanup_empty_rooms', 'cleanup_retention_data',
    # Users
    'create_user', 'authenticate_user', 'get_user_by_id', 'get_user_by_id_cached',
    'invalidate_user_cache', 'get_all_users', 'update_user_status', 'update_user_profile',
    'get_online_users', 'log_access', 'change_password', 'get_user_session_token', 'get_or_create_oidc_user', 'delete_user',
    # Rooms
    'create_room', 'get_room_key', 'get_user_rooms', 'get_room_members',
    'is_room_member', 'add_room_member', 'leave_room_db', 'update_room_name',
    'get_room_by_id', 'pin_room', 'mute_room', 'kick_member',
    'set_room_admin', 'is_room_admin', 'get_room_admins',
    # Messages
    'create_message', 'get_room_messages', 'update_last_read', 'get_unread_count',
    'get_room_last_reads', 'get_message_room_id', 'delete_message', 'edit_message',
    'search_messages', 'advanced_search', 'pin_message', 'unpin_message', 'get_pinned_messages',
    'server_stats', 'update_server_stats', 'get_server_stats',
    # Polls
    'create_poll', 'get_poll', 'get_room_polls', 'vote_poll', 'get_user_votes', 'close_poll',
    # Files
    'add_room_file', 'get_room_files', 'delete_room_file',
    # Reactions
    'add_reaction', 'remove_reaction', 'toggle_reaction', 
    'get_message_reactions', 'get_messages_reactions',
    # Admin audit
    'log_admin_action', 'get_admin_audit_logs',
]
