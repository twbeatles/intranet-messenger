# -*- coding: utf-8 -*-
"""Shared Flask extension instances.

Compression is optional and should not prevent application boot in minimal
environments (for example Windows ARM without brotli wheels).
"""

from typing import Any, Protocol

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect


class _CompressLike(Protocol):
    def init_app(self, app: Any) -> None: ...


class _FallbackCompress:
    def init_app(self, app: Any) -> None:
        app.logger.warning("Flask-Compress disabled: brotli dependency unavailable")


try:
    from flask_compress import Compress as _CompressClass
except Exception:  # pragma: no cover - exercised only in env without brotli
    compress: _CompressLike = _FallbackCompress()
else:
    compress: _CompressLike = _CompressClass()


limiter = Limiter(key_func=get_remote_address)
csrf = CSRFProtect()
