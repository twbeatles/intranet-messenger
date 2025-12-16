# -*- mode: python ; coding: utf-8 -*-
# 사내 메신저 v3.0 PyInstaller Spec 파일
# auto-py-to-exe에서 사용하거나 직접 실행: pyinstaller messenger.spec

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
        # 번들에 포함될 리소스 (static, templates 등)
        ('static', 'static'),
        ('templates', 'templates'),
        ('app', 'app'),
        ('gui', 'gui'),
        ('certs', 'certs'),
        ('config.py', '.'),
    ],
    hiddenimports=[
        'engineio.async_drivers.threading',
        'simple_websocket',
        'flask_socketio',
        'socketio',
        'engineio',
        'cryptography',
        'cryptography.hazmat.primitives.kdf.pbkdf2',
        'cryptography.hazmat.backends',
        'pycryptodome',
        'Crypto',
        'Crypto.Cipher',
        'Crypto.Cipher.AES',
        'Crypto.Random',
        'Crypto.Util.Padding',
        'werkzeug',
        'werkzeug.routing',
        'jinja2',
        'flask.json',
    ],
    hookspath=['.'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='사내메신저v3',
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
    icon=None,  # 아이콘 파일이 있으면 경로 지정
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='사내메신저v3',
)
