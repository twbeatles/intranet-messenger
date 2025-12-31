# -*- mode: python ; coding: utf-8 -*-
# ============================================================================
# 사내 메신저 v4.1 PyInstaller Spec (경량화)
# 
# 빌드: pyinstaller messenger.spec --clean
# ============================================================================

import os
block_cipher = None
BASE_PATH = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    ['server.py'],
    pathex=[BASE_PATH],
    binaries=[],
    datas=[
        ('static', 'static'),
        ('templates', 'templates'),
        ('app', 'app'),
        ('gui', 'gui'),
        ('certs', 'certs'),
        ('config.py', '.'),
    ],
    hiddenimports=[
        # Socket.IO 필수
        'engineio.async_drivers.threading',
        'simple_websocket', 'flask_socketio', 'socketio', 'engineio',
        # gevent (CLI 모드용)
        'gevent', 'gevent.monkey', 'geventwebsocket', 'geventwebsocket.handler',
        # 암호화
        'Crypto', 'Crypto.Cipher', 'Crypto.Cipher.AES', 'Crypto.Random', 'Crypto.Util.Padding',
        # PyQt6
        'PyQt6', 'PyQt6.QtCore', 'PyQt6.QtWidgets', 'PyQt6.QtGui', 'PyQt6.sip',
    ],
    hookspath=['.'],
    excludes=[
        # 대형 불필요 모듈 제외
        'matplotlib', 'numpy', 'pandas', 'scipy', 'tkinter', '_tkinter',
        'PyQt5', 'PySide2', 'PySide6', 'cv2', 'PIL', 'pillow',
        'IPython', 'notebook', 'jupyter', 'pytest', 'unittest',
        'setuptools', 'pip', 'wheel',
        # PyQt6 불필요 모듈
        'PyQt6.QtBluetooth', 'PyQt6.QtDBus', 'PyQt6.QtDesigner', 'PyQt6.QtHelp',
        'PyQt6.QtMultimedia', 'PyQt6.QtNetwork', 'PyQt6.QtNfc', 'PyQt6.QtOpenGL',
        'PyQt6.QtPositioning', 'PyQt6.QtPrintSupport', 'PyQt6.QtQml', 'PyQt6.QtQuick',
        'PyQt6.QtRemoteObjects', 'PyQt6.QtSensors', 'PyQt6.QtSerialPort', 'PyQt6.QtSql',
        'PyQt6.QtSvg', 'PyQt6.QtTest', 'PyQt6.QtWebChannel', 'PyQt6.QtWebEngine',
        'PyQt6.QtWebSockets', 'PyQt6.QtXml',
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='사내메신저v4.1',
    debug=False,
    strip=False,  # Windows에서는 strip 도구 없음
    upx=True,
    console=False,
    icon=None,
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False,  # Windows에서는 strip 비활성화
    upx=True,
    upx_exclude=['vcruntime140.dll', 'python*.dll', 'Qt*.dll', 'VCRUNTIME*.dll', 'MSVCP*.dll'],
    name='사내메신저v4.1',
)
