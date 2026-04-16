# -*- mode: python ; coding: utf-8 -*-
# 사내 메신저 v4.36.3 PyInstaller 빌드 명세서
# 2026-04-14 runtime/path + room membership contract sync 반영
# 경량화 최적화 버전

import importlib.util

# Reviewed on 2026-04-16 for room-key rotation, upload-token cleanup, and
# frontend/doc tooling sync. The current hiddenimports and packaged data list
# already cover the active runtime-split modules used by this baseline.

block_cipher = None


def _has_module(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


OPTIONAL_HIDDENIMPORTS = [
    name for name in (
        'eventlet',
        'redis',
        'redis.asyncio',
    )
    if _has_module(name)
]

# 제외할 모듈 목록 (경량화)
EXCLUDES = [
    # GUI 라이브러리 (사용하지 않는 것)
    'tkinter', '_tkinter', 'Tkinter',
    
    # 과학/데이터 라이브러리
    'matplotlib', 'numpy', 'pandas', 'scipy', 'PIL', 'cv2',
    
    # 테스트/개발 도구
    'unittest', 'pytest', 'doctest', 'pydoc', 'lib2to3',
    'pip',
    
    # 불필요한 이메일/HTTP 테스트
    'email.test', 'http.test', 'test',
    
    # XML 파서 (불필요)
    'xml.dom', 'xml.sax', 'xml.sax.xmlreader', 'xml.sax.expatreader',
    
    # 불필요한 DB 드라이버 (SQLite만 사용)
    'pysqlite2', 'MySQLdb',
    
    # 기타 불필요한 모듈
    'IPython', 'jupyter',
]

a = Analysis(
    ['server.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('static', 'static'),
        ('templates', 'templates'),
        ('docs/BACKUP_RUNBOOK.md', 'docs'),
    ],
    hiddenimports=[
        # Gevent 관련
        'engineio.async_drivers.gevent',
        'gevent',
        'gevent.monkey',
        'gevent.ssl',
        'gevent.builtins',
        'gevent.resolver_thread',
        'gevent._socket3',
        'greenlet',

        # Eventlet 관련 (선택 async_mode)
        'engineio.async_drivers.eventlet',
        
        # Socket.IO 관련
        'engineio',
        'engineio.async_drivers.threading',
        'flask_socketio',
        'socketio',
        
        # Flask 관련
        'flask',
        'flask_session',
        'flask_limiter',
        'flask_wtf',
        'flask_compress',
        'cachelib',
        'cachelib.file',
        
        # 암호화 관련
        'Crypto',
        'Crypto.Cipher',
        'Crypto.Cipher.AES',
        'Crypto.Random',
        'Crypto.Util.Padding',
        
        # 앱 모듈
        'app',
        'app.factory',
        'app.routes',
        'app.sockets',
        'app.models',
        'app.utils',
        'app.extensions',
        'app.crypto_manager',
        'app.upload_tokens',
        'app.state_store',
        'app.upload_scan',
        'app.oidc',
        'app.control_api',
        'app.server_launcher',
        'app.bootstrap',
        'app.bootstrap.runtime',
        'app.bootstrap.socketio_config',
        'app.bootstrap.hooks',
        'app.bootstrap.workers',
        'app.http',
        'app.http.auth',
        'app.http.public',
        'app.http.rooms',
        'app.http.messages',
        'app.http.uploads',
        'app.http.profile',
        'app.http.collaboration',
        'app.http.common',
        'app.http.route_deps',
        'app.socket_events',
        'app.socket_events.register',
        'app.socket_events.shared',
        'app.socket_events.state',
        'app.socket_events.connection',
        'app.socket_events.messages',
        'app.socket_events.presence',
        'app.socket_events.rooms',
        'app.socket_events.features',
        'app.services',
        'app.services.runtime_config',
        'app.services.runtime_paths',
        'app.services.session_tokens',
        'app.services.socket_broadcasts',
        'app.services.text_hygiene',
        'app.services.uploads',
        'app.models.base',
        'app.models.users',
        'app.models.rooms',
        'app.models.messages',
        'app.models.polls',
        'app.models.files',
        'app.models.reactions',
        'app.models.admin_audit',
        'app.legacy.models_monolith',

        # Redis (optional runtime backend)
        # 인증서 생성 경로 (GUI/CLI 공용)
        'certs.generate_cert',
        'cryptography.x509',
        'cryptography.x509.oid',
        'cryptography.hazmat.backends',
        'cryptography.hazmat.primitives',
        'cryptography.hazmat.primitives.asymmetric',
        
        # GUI 모듈
        'gui',
        'gui.server_window',
        'gui.services',
        'gui.services.process_control',
        'gui.services.settings_service',
        'gui.widgets',
        'gui.widgets.toast',
        'gui.styles',
        'gui.styles.qss',
        'gui.window',
        'gui.window.main_window',
        
        # 이메일 관련 (계정 기능)
        'email.mime',
        'email.mime.text',
        'email.mime.multipart',
        
        # 기타 필수
        'simple_websocket',
        'wsproto',
        'bcrypt',
        'jwt',
        'jwt.algorithms',
        'jwt.api_jwk',
        'jwt.jwks_client',
        'jwt.exceptions',
        'werkzeug',
        'werkzeug.security',
        'jinja2',
        'markupsafe',
    ] + OPTIONAL_HIDDENIMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# 바이너리에서 불필요한 파일 제거 (경량화)
a.binaries = [x for x in a.binaries if not x[0].startswith('libopenblas')]
a.binaries = [x for x in a.binaries if not x[0].startswith('libblas')]
a.binaries = [x for x in a.binaries if not x[0].startswith('liblapack')]

# 데이터에서 불필요한 파일 제거
a.datas = [x for x in a.datas if not x[0].startswith('share/')]
a.datas = [x for x in a.datas if not x[0].endswith('.pyi')]
a.datas = [x for x in a.datas if 'test' not in x[0].lower() or 'static' in x[0].lower()]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='사내메신저v4.36.3',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,  # 심볼 제거 (Windows에서는 False 권장)
    upx=False,    # UPX 압축 비활성화 (UPX가 설치되지 않은 경우 오류 발생)
    upx_exclude=[
        'vcruntime140.dll',
        'python*.dll',
        'ucrtbase.dll',
    ],
    runtime_tmpdir=None,
    console=False,  # 콘솔 창 숨김
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 아이콘 파일이 있으면 'icon.ico' 지정
)
