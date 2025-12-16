# -*- mode: python ; coding: utf-8 -*-
# ============================================================================
# 사내 메신저 v3.4 PyInstaller Spec 파일
# 
# 사용법:
#   pyinstaller messenger.spec
# 또는:
#   auto-py-to-exe에서 이 파일 선택
# ============================================================================

import os
import sys

block_cipher = None

# 현재 디렉토리 기준 경로
BASE_PATH = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    ['server.py'],
    pathex=[BASE_PATH],
    binaries=[],
    datas=[
        # ====================================
        # 리소스 파일 (static, templates 등)
        # ====================================
        ('static', 'static'),
        ('templates', 'templates'),
        ('app', 'app'),
        ('gui', 'gui'),
        ('certs', 'certs'),
        ('config.py', '.'),
    ],
    hiddenimports=[
        # ====================================
        # Socket.IO / Engine.IO
        # ====================================
        'engineio.async_drivers.threading',
        'engineio.async_drivers.gevent',
        'engineio.async_drivers.gevent_uwsgi',
        'engineio.async_drivers.eventlet',
        'simple_websocket',
        'flask_socketio',
        'socketio',
        'engineio',
        
        # ====================================
        # gevent (고성능 동시 접속)
        # ====================================
        'gevent',
        'gevent.monkey',
        'gevent.pywsgi',
        'gevent.socket',
        'gevent.ssl',
        'gevent.local',
        'gevent.queue',
        'gevent.event',
        'gevent.lock',
        'gevent.pool',
        'gevent.hub',
        'gevent.greenlet',
        'geventwebsocket',
        'geventwebsocket.handler',
        'geventwebsocket.websocket',
        
        # ====================================
        # 암호화 라이브러리
        # ====================================
        'cryptography',
        'cryptography.hazmat.primitives.kdf.pbkdf2',
        'cryptography.hazmat.backends',
        'pycryptodome',
        'Crypto',
        'Crypto.Cipher',
        'Crypto.Cipher.AES',
        'Crypto.Random',
        'Crypto.Util.Padding',
        
        # ====================================
        # Flask / Werkzeug / Jinja2
        # ====================================
        'werkzeug',
        'werkzeug.routing',
        'werkzeug.serving',
        'werkzeug.utils',
        'jinja2',
        'flask.json',
        'flask.sessions',
        
        # ====================================
        # 기타 의존성
        # ====================================
        'sqlite3',
        'hashlib',
        'secrets',
        'logging',
        'threading',
        'contextlib',
        'base64',
        're',
    ],
    hookspath=['.'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 불필요한 모듈 제외
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'tkinter',
        'PyQt5',
        'PySide2',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ============================================================================
# 실행 파일 설정
# ============================================================================
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='사내메신저v3.3',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI 모드 (콘솔 숨김)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 아이콘 파일: 'icon.ico' 경로 지정
)

# ============================================================================
# 배포 폴더 생성
# ============================================================================
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='사내메신저v3.4',
)
