# -*- coding: utf-8 -*-
"""Shared Flask extension instances.

Compression is optional and should not prevent application boot in minimal
environments (for example Windows ARM without brotli wheels).
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

try:
    from flask_compress import Compress
except Exception:  # pragma: no cover - exercised only in env without brotli
    class Compress:  # type: ignore[override]
        def init_app(self, app):
            app.logger.warning("Flask-Compress disabled: brotli dependency unavailable")


limiter = Limiter(key_func=get_remote_address)
csrf = CSRFProtect()
compress = Compress()
