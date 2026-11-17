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
# Admin Audit Logs
from app.models.admin_audit import (
    get_admin_audit_logs,
    log_admin_action,
)
from app.models.base import (
    cleanup_empty_rooms,
    cleanup_old_access_logs,
    cleanup_retention_data,
    close_expired_polls,
    close_thread_db,
    get_db,
    get_db_context,
    init_db,
    safe_file_delete,
)

# Files - 파일 저장소
from app.models.files import (
    add_room_file,
    delete_room_file,
    get_room_files,
)

# Messages - 메시지 관리
from app.models.messages import (
    advanced_search,
    can_user_see_message,
    create_message,
    delete_message,
    edit_message,
    get_message_room_id,
    get_pinned_messages,
    get_room_last_reads,
    get_room_messages,
    get_server_stats,
    get_unread_count,
    pin_message,
    search_messages,
    server_stats,
    unpin_message,
    update_last_read,
    update_server_stats,
)

# Polls - 투표 관리
from app.models.polls import (
    close_poll,
    create_poll,
    get_poll,
    get_room_polls,
    get_user_votes,
    vote_poll,
)

# Reactions - 리액션 관리
from app.models.reactions import (
    add_reaction,
    get_message_reactions,
    get_messages_reactions,
    remove_reaction,
    toggle_reaction,
)

# Rooms - 대화방 관리
from app.models.rooms import (
    add_room_member,
    create_room,
    get_room_admins,
    get_room_by_id,
    get_room_key,
    get_room_keyring,
    get_room_member_key_version,
    get_room_members,
    get_room_security_bundle,
    get_user_rooms,
    invite_members_with_key_rotation,
    is_room_admin,
    is_room_member,
    kick_member,
    leave_room_db,
    mute_room,
    pin_room,
    rotate_room_key,
    set_room_admin,
    update_room_name,
)

# Users - 사용자 관리
from app.models.users import (
    authenticate_user,
    change_password,
    create_user,
    delete_user,
    get_all_users,
    get_online_users,
    get_or_create_oidc_user,
    get_user_by_id,
    get_user_by_id_cached,
    get_user_session_token,
    invalidate_user_cache,
    log_access,
    update_user_profile,
    update_user_status,
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
    'create_room', 'get_room_key', 'get_room_keyring', 'get_room_member_key_version', 'get_room_security_bundle',
    'get_user_rooms', 'get_room_members',
    'is_room_member', 'add_room_member', 'invite_members_with_key_rotation', 'leave_room_db', 'rotate_room_key', 'update_room_name',
    'get_room_by_id', 'pin_room', 'mute_room', 'kick_member',
    'set_room_admin', 'is_room_admin', 'get_room_admins',
    # Messages
    'create_message', 'get_room_messages', 'update_last_read', 'get_unread_count',
    'get_room_last_reads', 'get_message_room_id', 'can_user_see_message', 'delete_message', 'edit_message',
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
