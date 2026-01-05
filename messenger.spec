# -*- mode: python ; coding: utf-8 -*-
# ============================================================================
# 사내 메신저 v4.3 PyInstaller Spec (경량화 최적화)
# 
# 빌드: pyinstaller messenger.spec --clean
# 결과: dist/사내메신저v4.3/사내메신저v4.3.exe
# ============================================================================

import os
import sys

block_cipher = None
BASE_PATH = os.path.dirname(os.path.abspath(SPEC))

# ============================================================================
# Analysis - 파일 수집 및 의존성 분석
# ============================================================================
a = Analysis(
    ['server.py'],
    pathex=[BASE_PATH],
    binaries=[],
    datas=[
        # 필수 리소스만 포함 (경량화)
        ('static', 'static'),
        ('templates', 'templates'),
        ('app', 'app'),
        ('gui', 'gui'),
        ('config.py', '.'),
        # certs 폴더가 있는 경우에만 포함
    ],
    hiddenimports=[
        # ========================================
        # Socket.IO 필수
        # ========================================
        'engineio.async_drivers.threading',
        'simple_websocket',
        'flask_socketio',
        'socketio',
        'engineio',
        
        # ========================================
        # gevent (CLI 모드 고성능 처리)
        # ========================================
        'gevent',
        'gevent.monkey',
        'geventwebsocket',
        'geventwebsocket.handler',
        
        # ========================================
        # 암호화 (E2E)
        # ========================================
        'Crypto',
        'Crypto.Cipher',
        'Crypto.Cipher.AES',
        'Crypto.Random',
        'Crypto.Util.Padding',
        
        # ========================================
        # PyQt6 핵심 모듈만
        # ========================================
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtWidgets',
        'PyQt6.QtGui',
        'PyQt6.sip',
    ],
    hookspath=['.'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # ========================================
        # 대형 불필요 라이브러리 (★ 용량 절감 핵심)
        # ========================================
        'matplotlib', 'numpy', 'pandas', 'scipy', 'sklearn',
        'tensorflow', 'torch', 'keras',
        'tkinter', '_tkinter', 'tk', 'tcl',
        'cv2', 'PIL', 'pillow', 'Pillow',
        'IPython', 'notebook', 'jupyter', 'nbconvert', 'nbformat',
        'pytest', 'unittest', 'doctest', 'nose',
        'setuptools', 'pip', 'wheel',
        'sphinx', 'docutils', 'pygments',
        'xml.etree.ElementTree',
        'email', 'html', 'http.server',
        'multiprocessing.popen_spawn_win32',
        
        # ========================================
        # PyQt5/PySide (충돌 방지)
        # ========================================
        'PyQt5', 'PySide2', 'PySide6',
        
        # ========================================
        # PyQt6 미사용 모듈 (★ 경량화 핵심)
        # ========================================
        'PyQt6.Qt3DAnimation', 'PyQt6.Qt3DCore', 'PyQt6.Qt3DExtras',
        'PyQt6.Qt3DInput', 'PyQt6.Qt3DLogic', 'PyQt6.Qt3DRender',
        'PyQt6.QtBluetooth', 'PyQt6.QtCharts', 'PyQt6.QtDataVisualization',
        'PyQt6.QtDBus', 'PyQt6.QtDesigner', 'PyQt6.QtHelp',
        'PyQt6.QtMultimedia', 'PyQt6.QtMultimediaWidgets',
        'PyQt6.QtNetwork', 'PyQt6.QtNetworkAuth',
        'PyQt6.QtNfc', 'PyQt6.QtOpenGL', 'PyQt6.QtOpenGLWidgets',
        'PyQt6.QtPdf', 'PyQt6.QtPdfWidgets',
        'PyQt6.QtPositioning', 'PyQt6.QtPrintSupport',
        'PyQt6.QtQml', 'PyQt6.QtQuick', 'PyQt6.QtQuickWidgets', 'PyQt6.QtQuick3D',
        'PyQt6.QtRemoteObjects', 'PyQt6.QtSensors', 'PyQt6.QtSerialPort',
        'PyQt6.QtSpatialAudio', 'PyQt6.QtSql', 'PyQt6.QtSvg', 'PyQt6.QtSvgWidgets',
        'PyQt6.QtTest', 'PyQt6.QtTextToSpeech',
        'PyQt6.QtWebChannel', 'PyQt6.QtWebEngine', 'PyQt6.QtWebEngineCore',
        'PyQt6.QtWebEngineWidgets', 'PyQt6.QtWebSockets',
        'PyQt6.QtXml', 'PyQt6.QtVirtualKeyboard',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ============================================================================
# PYZ - Python 모듈 압축
# ============================================================================
pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

# ============================================================================
# EXE - 실행 파일 생성
# ============================================================================
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='사내메신저v4.3',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,  # Windows에서는 strip 비활성화
    upx=True,     # UPX 압축 활성화
    console=False,  # GUI 모드 (콘솔 숨김)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 아이콘 경로 지정 가능: 'icon.ico'
)

# ============================================================================
# COLLECT - 최종 배포 폴더 생성
# ============================================================================
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,  # Windows 호환
    upx=True,     # UPX 압축
    upx_exclude=[
        # UPX 압축 제외 (호환성 문제 방지)
        'vcruntime140.dll',
        'vcruntime140_1.dll',
        'python*.dll',
        'Qt*.dll',
        'VCRUNTIME*.dll',
        'MSVCP*.dll',
        'api-ms-*.dll',
        'ucrtbase.dll',
        '_ssl.pyd',
        '_hashlib.pyd',
    ],
    name='사내메신저v4.3',
)
