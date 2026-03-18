# -*- coding: utf-8 -*-
"""
Socket.IO shared mutable state and cache helpers.
"""

from __future__ import annotations

import logging
import time
from threading import Lock

from app.models import get_user_rooms

logger = logging.getLogger(__name__)

online_users = {}
user_sids = {}
online_users_lock = Lock()
stats_lock = Lock()

user_cache = {}
cache_lock = Lock()
MAX_CACHE_SIZE = 1000
CACHE_TTL = 300

typing_last_emit = {}
typing_rate_lock = Lock()
TYPING_RATE_LIMIT = 1.0


def cleanup_old_cache():
    current_time = time.time()
    expired_keys = []
    with cache_lock:
        for user_id, data in user_cache.items():
            if current_time - data.get("updated", 0) > 600:
                expired_keys.append(user_id)
        for key in expired_keys:
            del user_cache[key]
        if len(user_cache) > MAX_CACHE_SIZE:
            sorted_items = sorted(user_cache.items(), key=lambda item: item[1].get("updated", 0))
            to_remove = len(user_cache) - MAX_CACHE_SIZE
            for index in range(to_remove):
                del user_cache[sorted_items[index][0]]
    if expired_keys:
        logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")


def get_user_room_ids(user_id):
    with cache_lock:
        cached = user_cache.get(user_id)
        if cached and (time.time() - cached.get("updated", 0)) < CACHE_TTL:
            return cached.get("rooms", [])

    try:
        rooms = get_user_rooms(user_id)
        room_ids = [room["id"] for room in rooms]
        with cache_lock:
            if len(user_cache) > MAX_CACHE_SIZE // 2:
                cleanup_old_cache()
            user_cache.setdefault(user_id, {})
            user_cache[user_id]["rooms"] = room_ids
            user_cache[user_id]["updated"] = time.time()
        return room_ids
    except Exception as exc:
        logger.error(f"Get user rooms error: {exc}")
        return []


def invalidate_user_cache(user_id):
    with cache_lock:
        if user_id in user_cache:
            del user_cache[user_id]

