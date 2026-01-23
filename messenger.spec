# -*- mode: python ; coding: utf-8 -*-
# 사내 메신저 v4.34 PyInstaller 빌드 명세서
# 경량화 최적화 버전

block_cipher = None

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
    'xml.dom', 'xml.sax',
    
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
        'cachelib.file',
        
        # 암호화 관련
        'Crypto',
        'Crypto.Cipher',
        'Crypto.Cipher.AES',
        'Crypto.Random',
        'Crypto.Util.Padding',
        
        # 앱 모듈
        'app',
        'app.routes',
        'app.sockets',
        'app.models',
        'app.utils',
        'app.extensions',
        'app.crypto_manager',
        'app.control_api',
        'app.server_launcher',
        
        # GUI 모듈
        'gui',
        'gui.server_window',
        
        # 이메일 관련 (계정 기능)
        'email.mime',
        'email.mime.text',
        'email.mime.multipart',
        
        # 기타 필수
        'simple_websocket',
        'wsproto',
        'bcrypt',
        'werkzeug',
        'werkzeug.security',
        'jinja2',
        'markupsafe',
    ],
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
    name='사내메신저v4.34',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,  # 심볼 제거 (경량화)
    upx=True,    # UPX 압축 활성화
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
