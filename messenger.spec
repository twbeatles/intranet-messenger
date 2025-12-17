# -*- mode: python ; coding: utf-8 -*-
# ============================================================================
# 사내 메신저 v3.6 PyInstaller Spec 파일
# 
# 사용법:
#   pyinstaller messenger.spec
# 또는:
#   auto-py-to-exe에서 이 파일 선택
#
# v3.6 업데이트:
#   - 키보드 단축키 (Ctrl+K, Ctrl+N, Ctrl+F, ESC)
#   - 토스트 알림 개선 (스택형, 진행률)
#   - 대화 내 검색 기능
#   - 오프라인 지원 강화
#   - 메모리 누수 방지
#   - 접근성 개선
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
        'gevent._ssl',
        'gevent.resolver',
        'gevent.resolver.thread',
        'gevent.resolver.blocking',
        'geventwebsocket',
        'geventwebsocket.handler',
        'geventwebsocket.websocket',
        
        # ====================================
        # 암호화 라이브러리
        # ====================================
        'cryptography',
        'cryptography.hazmat.primitives.kdf.pbkdf2',
        'cryptography.hazmat.backends',
        'cryptography.hazmat.primitives.asymmetric',
        'cryptography.hazmat.primitives.asymmetric.rsa',
        'cryptography.x509',
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
        'werkzeug.security',
        'jinja2',
        'flask.json',
        'flask.sessions',
        
        # ====================================
        # PyQt6 GUI
        # ====================================
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtWidgets',
        'PyQt6.QtGui',
        'PyQt6.sip',
        
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
        'json',
        'time',
        'datetime',
        'os',
        'sys',
        'uuid',
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
        'PySide6',
        'cv2',
        'PIL',
        'IPython',
        'notebook',
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
    name='사내메신저v3.6',
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
    version=None,  # 버전 정보 파일: 'version_info.txt' 지정
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
    name='사내메신저v3.6',
)

# ============================================================================
# 빌드 참고 사항
# ============================================================================
# 1. 빌드 전 임시 파일 정리:
#    pyinstaller messenger.spec --clean
#
# 2. 빌드 후 확인 사항:
#    - dist/사내메신저v3.6/ 폴더의 static/, templates/ 확인
#    - 실행 파일 더블클릭으로 GUI 정상 동작 확인
#
# 3. 오류 발생 시:
#    - build/, dist/ 폴더 삭제 후 재빌드
#    - --debug all 옵션으로 상세 로그 확인
#
# 4. gevent 미설치 환경:
#    - hiddenimports에서 gevent 관련 항목 제거 가능
#    - threading 모드로 동작 (동시 접속 제한)
# ============================================================================
