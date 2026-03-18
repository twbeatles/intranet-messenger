# -*- coding: utf-8 -*-
"""
Compatibility shim for Socket.IO event registration.
"""

from __future__ import annotations

from app.socket_events import register_socket_events
from app.socket_events.state import cleanup_old_cache, get_user_room_ids, invalidate_user_cache

__all__ = [
    "register_socket_events",
    "cleanup_old_cache",
    "get_user_room_ids",
    "invalidate_user_cache",
]
