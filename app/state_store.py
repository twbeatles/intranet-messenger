# -*- coding: utf-8 -*-
"""
Shared state store with optional Redis backend and in-memory fallback.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


class _InMemoryStateStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._data: dict[str, tuple[Any, float | None]] = {}

    def _purge_if_expired(self, key: str):
        value = self._data.get(key)
        if not value:
            return
        _, expires_at = value
        if expires_at is not None and expires_at <= time.time():
            self._data.pop(key, None)

    def set(self, key: str, value: Any, ttl_seconds: int | None = None):
        expires_at = None
        if ttl_seconds is not None and ttl_seconds > 0:
            expires_at = time.time() + ttl_seconds
        with self._lock:
            self._data[key] = (value, expires_at)

    def get(self, key: str):
        with self._lock:
            self._purge_if_expired(key)
            item = self._data.get(key)
            return item[0] if item else None

    def getdel(self, key: str):
        with self._lock:
            self._purge_if_expired(key)
            item = self._data.pop(key, None)
            return item[0] if item else None

    def delete(self, key: str):
        with self._lock:
            self._data.pop(key, None)

    def incr(self, key: str, ttl_seconds: int | None = None) -> int:
        with self._lock:
            self._purge_if_expired(key)
            current = self._data.get(key)
            now = time.time()
            value = 1
            expires_at = None
            if current:
                value = int(current[0]) + 1
                expires_at = current[1]
            elif ttl_seconds and ttl_seconds > 0:
                expires_at = now + ttl_seconds
            self._data[key] = (value, expires_at)
            return value

    def decr(self, key: str) -> int:
        with self._lock:
            self._purge_if_expired(key)
            current = self._data.get(key)
            if not current:
                return 0
            value = max(0, int(current[0]) - 1)
            if value == 0:
                self._data.pop(key, None)
                return 0
            self._data[key] = (value, current[1])
            return value


class StateStore:
    def __init__(self):
        self._backend = _InMemoryStateStore()
        self._redis = None
        self._namespace = "im"
        self._redis_degraded = False

    def init_app(self, redis_url: str | None = None, namespace: str = "im"):
        self._namespace = namespace
        self._redis_degraded = False
        if not redis_url:
            logger.info("StateStore using in-memory backend")
            self._redis = None
            self._backend = _InMemoryStateStore()
            return

        try:
            import redis  # type: ignore

            client = redis.Redis.from_url(redis_url, decode_responses=True)
            client.ping()
            self._redis = client
            logger.info("StateStore using redis backend")
        except Exception as exc:
            logger.warning(f"StateStore redis unavailable, falling back to memory: {exc}")
            self._redis = None
            self._backend = _InMemoryStateStore()
            self._redis_degraded = True

    @property
    def redis_enabled(self) -> bool:
        return self._redis is not None

    def _k(self, key: str) -> str:
        return f"{self._namespace}:{key}"

    def _degrade_redis(self, exc: Exception):
        if self._redis is not None:
            logger.warning(f"StateStore redis operation failed, degrading to memory backend: {exc}")
        self._redis = None
        self._redis_degraded = True

    def set_json(self, key: str, value: dict[str, Any], ttl_seconds: int | None = None):
        payload = json.dumps(value, ensure_ascii=False)
        self.set_value(key, payload, ttl_seconds=ttl_seconds)

    def get_json(self, key: str) -> dict[str, Any] | None:
        payload = self.get_value(key)
        if not payload:
            return None
        try:
            return json.loads(payload)
        except Exception:
            return None

    def getdel_json(self, key: str) -> dict[str, Any] | None:
        payload = self.getdel_value(key)
        if not payload:
            return None
        try:
            return json.loads(payload)
        except Exception:
            return None

    def set_value(self, key: str, value: str, ttl_seconds: int | None = None):
        store_key = self._k(key)
        if self._redis is not None:
            try:
                if ttl_seconds and ttl_seconds > 0:
                    self._redis.setex(store_key, ttl_seconds, value)
                else:
                    self._redis.set(store_key, value)
                return
            except Exception as exc:
                self._degrade_redis(exc)
        self._backend.set(store_key, value, ttl_seconds=ttl_seconds)

    def get_value(self, key: str) -> str | None:
        store_key = self._k(key)
        if self._redis is not None:
            try:
                return self._redis.get(store_key)
            except Exception as exc:
                self._degrade_redis(exc)
        return self._backend.get(store_key)

    def getdel_value(self, key: str) -> str | None:
        store_key = self._k(key)
        if self._redis is not None:
            try:
                return self._redis.getdel(store_key)
            except Exception as exc:
                try:
                    current = self._redis.get(store_key)
                    self._redis.delete(store_key)
                    return current
                except Exception as inner_exc:
                    self._degrade_redis(inner_exc)
                self._degrade_redis(exc)
        return self._backend.getdel(store_key)

    def delete(self, key: str):
        store_key = self._k(key)
        if self._redis is not None:
            try:
                self._redis.delete(store_key)
                return
            except Exception as exc:
                self._degrade_redis(exc)
        self._backend.delete(store_key)

    def incr(self, key: str, ttl_seconds: int | None = None) -> int:
        store_key = self._k(key)
        if self._redis is not None:
            try:
                value = int(self._redis.incr(store_key))
                if ttl_seconds and value == 1:
                    self._redis.expire(store_key, ttl_seconds)
                return value
            except Exception as exc:
                self._degrade_redis(exc)
        return self._backend.incr(store_key, ttl_seconds=ttl_seconds)

    def decr(self, key: str) -> int:
        store_key = self._k(key)
        if self._redis is not None:
            try:
                value = int(self._redis.decr(store_key))
                if value <= 0:
                    self._redis.delete(store_key)
                    return 0
                return value
            except Exception as exc:
                self._degrade_redis(exc)
        return self._backend.decr(store_key)


state_store = StateStore()
