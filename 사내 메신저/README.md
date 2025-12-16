# 🔒 사내 웹메신저 v3.0

Flask + Socket.IO + PyQt6 기반의 **종단간 암호화(E2E)** 사내 웹 메신저 시스템입니다.

## ✨ v3.0 업데이트

- 🔐 **HTTPS 지원**: 자체 서명 SSL 인증서 생성 및 보안 연결
- 🔔 **데스크톱 알림**: Web Notification API로 새 메시지 알림
- 💾 **오프라인 캐싱**: IndexedDB를 통한 메시지 로컬 저장
- 🏗️ **코드 모듈화**: 유지보수가 쉬운 구조로 리팩토링
- 🏢 **사내망 호환**: 외부 인터넷 없이 완전 독립 동작

## 🔒 사내망/폐쇄망 호환성

이 애플리케이션은 **외부 인터넷 연결 없이** 완전히 독립적으로 동작합니다:

- ✅ Socket.IO 라이브러리 로컬 포함 (`/static/js/socket.io.min.js`)
- ✅ CryptoJS 라이브러리 로컬 포함 (`/static/js/crypto-js.min.js`)
- ✅ 시스템 폰트만 사용 (외부 웹폰트 없음)
- ✅ 외부 CDN, API 호출 없음
- ✅ SQLite 로컬 데이터베이스

## 주요 기능

### 보안
- **종단간 암호화 (E2E)** - AES-256으로 서버 관리자도 메시지 확인 불가
- **HTTPS** - SSL/TLS 암호화 통신
- **비밀번호 솔트 해싱**

### 채팅
- **1:1 / 그룹 대화**
- **읽음 확인**
- **파일/이미지 첨부**
- **이모지**

### 알림
- **데스크톱 알림** - 새 메시지 수신 시 브라우저 알림
- **오프라인 캐싱** - 서버 재시작 시에도 최근 메시지 유지

### 서버 관리 (PyQt6 GUI)
- **시스템 트레이**
- **HTTPS 활성화/비활성화**
- **SSL 인증서 생성**
- **실시간 통계**

## 📦 설치

```powershell
pip install flask flask-socketio simple-websocket pycryptodome pyqt6 cryptography
```

## 🚀 실행

### GUI 모드 (권장)
```powershell
python server.py
```

### CLI 모드
```powershell
python server.py --cli
```

### 기존 버전 실행
```powershell
python messenger_server.py
```

## 📱 접속

- **로컬 (HTTP)**: http://localhost:5000
- **로컬 (HTTPS)**: https://localhost:5000
- **네트워크**: https://<서버IP>:5000

> ⚠️ HTTPS 사용 시 자체 서명 인증서이므로 브라우저에서 보안 경고가 표시됩니다.
> "고급" → "안전하지 않음 진행"을 클릭하여 접속하세요.

## 🗂️ 파일 구조

```
사내 메신저/
├── server.py                # 새 메인 진입점 (v3.0)
├── messenger_server.py      # 기존 단일 파일 버전 (v2.5)
├── config.py                # 설정 파일
├── app/
│   ├── __init__.py          # Flask 앱 팩토리
│   ├── routes.py            # HTTP 라우트
│   ├── sockets.py           # Socket.IO 이벤트
│   ├── models.py            # 데이터베이스
│   └── utils.py             # 유틸리티
├── gui/
│   └── server_window.py     # PyQt6 GUI
├── certs/
│   ├── generate_cert.py     # 인증서 생성
│   ├── cert.pem             # SSL 인증서 (자동 생성)
│   └── key.pem              # 개인키 (자동 생성)
├── static/
│   ├── css/style.css        # 스타일시트
│   ├── js/
│   │   ├── app.js           # 메인 앱 로직
│   │   ├── notification.js  # 알림 모듈
│   │   ├── storage.js       # 로컬 저장소
│   │   ├── socket.io.min.js # Socket.IO (로컬)
│   │   └── crypto-js.min.js # CryptoJS (로컬)
│   └── sw.js                # Service Worker
├── templates/
│   └── index.html           # HTML 템플릿
├── uploads/                 # 파일 업로드 (자동 생성)
├── messenger.db             # SQLite DB (자동 생성)
└── server.log               # 서버 로그 (자동 생성)
```

## 🔑 SSL 인증서 생성

GUI에서 "인증서 생성" 버튼을 클릭하거나:

```powershell
cd "d:\google antigravity\사내 메신저"
python certs/generate_cert.py
```

## 📦 AUTO-PY-TO-EXE 패키징

### 1. 사전 준비

```powershell
pip install auto-py-to-exe
```

### 2. 실행

```powershell
auto-py-to-exe
```

### 3. 기본 설정

| 설정 항목 | 값 |
|-----------|-----|
| Script Location | `server.py` 선택 |
| Onefile/One Directory | **One Directory** 선택 |
| Console Window | **Window Based (No Console)** 선택 |

### 4. Additional Files 추가 ⚠️ 중요

`Add Folder` 버튼으로 다음 폴더들을 추가:

| 소스 폴더 | 대상 경로 |
|-----------|----------|
| `static/` | `static/` |
| `templates/` | `templates/` |
| `app/` | `app/` |
| `gui/` | `gui/` |
| `certs/` | `certs/` |

`Add Files` 버튼으로 다음 파일 추가:

| 소스 파일 | 대상 경로 |
|-----------|----------|
| `config.py` | `.` |

### 5. Advanced 탭 - Hidden Imports 추가 ⚠️ 필수

```
engineio.async_drivers.threading
simple_websocket
flask_socketio
socketio
engineio
cryptography
cryptography.hazmat.primitives.kdf.pbkdf2
cryptography.hazmat.backends
Crypto
Crypto.Cipher
Crypto.Cipher.AES
Crypto.Random
Crypto.Util.Padding
werkzeug
werkzeug.routing
jinja2
flask.json
```

### 6. 패키징 실행

`CONVERT .PY TO .EXE` 버튼 클릭

### 7. 결과물 확인

```
output/
└── 사내메신저v3/
    ├── 사내메신저v3.exe    # 실행 파일
    ├── static/             # 웹 리소스
    ├── templates/          # HTML 템플릿
    ├── app/                # 백엔드 모듈
    ├── gui/                # GUI 모듈
    ├── certs/              # SSL 인증서
    └── config.py           # 설정 파일
```

### 대안: spec 파일 직접 사용

```powershell
cd "d:\google antigravity\사내 메신저"
pyinstaller messenger.spec
```

## ⚠️ 패키징 주의사항

1. **폴더 구조 유지**: `static/`, `templates/`, `app/`, `gui/`, `certs/` 폴더 반드시 포함
2. **Hidden Imports**: Socket.IO, Crypto, Flask 관련 모듈 누락 시 실행 오류 발생
3. **config.py**: 루트에 반드시 포함 (패키징 후 설정 변경 가능)
4. **One Directory 권장**: One File은 리소스 접근 문제 발생 가능
5. **오류 시**: `build/`, `dist/` 폴더 삭제 후 `pyinstaller messenger.spec --clean` 실행

## ⚠️ 기타 주의사항

- 첫 실행 시 `messenger.db`, `uploads/`, `server.log`가 자동 생성됩니다
- HTTPS 사용 시 SSL 인증서가 자동 생성됩니다 (cryptography 라이브러리 필요)
- **사내망에서 외부 인터넷 없이 완전히 독립 동작합니다**
- **기존 v2.5 사용자**: `messenger.db`를 삭제하고 새로 시작해야 합니다 (비밀번호 해시 호환성)
