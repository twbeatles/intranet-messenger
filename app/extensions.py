# -*- coding: utf-8 -*-
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from flask_compress import Compress

# [v4.3] 보안 확장 인스턴스
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
csrf = CSRFProtect()

# [v4.4] 성능 최적화 확장
compress = Compress()
