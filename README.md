# 🔒 사내 웹메신저 v4.36

Flask + Socket.IO + PyQt6 기반 **종단간 암호화(E2E)** 사내 메신저

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-2.3+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

---

## 📋 목차

- [주요 기능](#-주요-기능)
- [AI 작업 가이드 파일](#-ai-작업-가이드-파일)
- [🆕 v4.36.3 업데이트 (2026-02-20)](#-v4363-업데이트-2026-02-20)
- [🆕 v4.36.1 업데이트 (2026-02-13)](#-v4361-업데이트-2026-02-13)
- [🆕 v4.36 업데이트 (2026-01-23)](#-v436-업데이트-2026-01-23)
- [📝 v4.34 업데이트 (2026-01-23)](#-v434-업데이트-2026-01-23)
- [시스템 요구사항](#-시스템-요구사항)
- [설치 방법](#-설치-방법)
- [실행 방법](#-실행-방법)
- [빌드 방법](#-빌드-방법)
- [프로젝트 구조](#-프로젝트-구조)
- [기술 스택](#-기술-스택)
- [보안 기능](#-보안-기능)
- [성능 최적화](#-성능-최적화)
- [문제 해결](#-문제-해결)
- [라이선스](#-라이선스)

---

## ✨ 주요 기능

### 🔐 보안 및 암호화
- **종단간 암호화 (E2E)**: AES-256 기반 클라이언트 간 메시지 암호화
- **CSRF 보호**: Flask-WTF를 통한 Cross-Site Request Forgery 방지
- **Rate Limiting**: Flask-Limiter로 무차별 대입 공격 및 DoS 방지
- **보안 헤더**: X-Frame-Options, CSP, X-Content-Type-Options 등 적용
- **안전한 세션 관리**: 서버 사이드 세션 + HttpOnly 쿠키
- **XSS 방지**: 모든 사용자 입력 이스케이프 처리

### 💬 메시징 기능
- **실시간 채팅**: Socket.IO 기반 양방향 통신
- **1:1 및 그룹 채팅**: 개인 대화 및 다중 사용자 그룹 채팅
- **읽음 확인 (Read Receipt)**: 메시지 읽음 상태 실시간 표시
- **타이핑 인디케이터**: 상대방 입력 상태 실시간 표시
- **메시지 답장**: 특정 메시지에 대한 답장 기능
- **메시지 리액션**: 이모지 리액션 기능
- **메시지 수정/삭제**: 본인 메시지 수정 및 삭제 기능

### 📁 파일 및 미디어
- **파일 공유**: 드래그앤드롭 지원, 최대 16MB
- **안전한 파일명**: UUID 기반 파일명으로 보안 강화
- **프로필 이미지**: 사용자 프로필 사진 업로드 및 관리
- **이미지 lazy loading**: IntersectionObserver 기반 지연 로딩
- **지원 파일 형식**: 이미지, 문서, 압축 파일 등 다양한 형식 지원

### 👥 사용자 관리
- **회원가입/로그인**: 안전한 bcrypt 기반 비밀번호 해싱
- **프로필 관리**: 닉네임, 상태 메시지, 프로필 이미지 설정
- **온라인 상태**: 실시간 사용자 접속 상태 표시
- **관리자 권한**: 방 관리자 지정, 권한 이양, 강퇴 기능

### 📊 그룹 기능
- **투표/설문**: 그룹 내 실시간 투표 및 의사결정 지원
- **공지사항**: 중요 메시지 공지 기능
- **방 설정**: 방 이름, 설명, 멤버 관리
- **초대 시스템**: 사용자 초대 및 참여 관리

### 🔍 고급 기능
- **메시지 검색**: 날짜, 작성자, 파일 필터링 검색
- **@멘션**: 특정 사용자 호출 기능
- **데이터 무결성**: 사용자 삭제 시 관련 데이터 자동 정리
- **고아 데이터 방지**: 참조 무결성 보장

---

## 🤖 AI 작업 가이드 파일

새 작업 세션에서도 프로젝트 맥락을 빠르게 복원할 수 있도록 루트에 운영 가이드 파일을 둡니다.

- `claude.md`: Claude 작업 세션용 실행 가이드/검증 체크리스트
- `gemini.md`: Gemini 작업 세션용 실행 가이드/검증 체크리스트
- `IMPLEMENTATION_AUDIT.md`: 점검 리스크와 반영 이력(기준선 + 재검증 결과)

권장: 새 세션 시작 시 위 3개 문서를 먼저 읽고 작업을 시작하세요.

---

## 🆕 v4.36.3 업데이트 (2026-02-20)

### ✅ 감사 문서(`IMPLEMENTATION_AUDIT.md`) 반영 완료
- **Poll 계약 정합화**: `create_poll()` 반환 계약을 `poll_id`로 통일하고 라우트 조회 흐름을 정리했습니다.
- **Pin 삭제 판정 수정**: tuple truthy 오판을 제거하고 실패 시 상태코드/메시지를 정확히 반환합니다.
- **파일 메시지 보안 강화**:
  - `/api/upload` 응답에 `upload_token`(TTL 5분, 1회성) 포함
  - 소켓 `send_message`에서 `type=file|image`는 `upload_token` 필수 검증
  - 클라이언트 `file_path`/`file_name` 직접 신뢰 경로 제거
- **방 생성 호환성 개선**: `members` 표준 유지 + `member_ids` 하위호환 수용(`members` 우선).
- **검색 파라미터 정책 강화**: `/api/search` `limit`은 `1..200`으로 clamp, `offset`은 `>=0` 보정.
- **인증 파일 캐시 정책 수정**:
  - 일반 파일: `Cache-Control: private, no-store`
  - 프로필 이미지: `Cache-Control: private, max-age=3600`
- **회원탈퇴 Poll 정합성 수정**: `polls.created_by = NULL` 업데이트 제거, 방 멤버 재할당(없으면 poll 삭제)으로 FK 충돌을 방지.
- **폐쇄망 정합성 보강**: `templates/index.html`의 Google Fonts 외부 링크 제거.
- **프론트 정합화**: 파일 업로드 UX 제한을 16MB로 통일하고 토큰 오류 메시지 처리를 보강.
- **테스트 체계 정리**:
  - `pytest.ini` 추가 (`testpaths = tests`, `norecursedirs = backup dist build`)
  - 계약 드리프트/보안 회귀 테스트 추가 및 기존 노후 테스트 정리

### 🧪 검증 결과
- `pytest tests -q` 통과: **64 passed**
- `pytest --maxfail=1` 통과: 기본 수집 오류 제거 확인

---

## 🆕 v4.36.1 업데이트 (2026-02-13)

### 🛡️ 보안/운영 (1차)
- **Control API 격리**: GUI용 `/control/*` 제어 API를 메인 포트에서 분리하여 `127.0.0.1:{CONTROL_PORT}` 에서만 서비스합니다. 모든 요청은 `X-Control-Token` 헤더가 필요하며, 토큰은 `.control_token` 파일로 관리됩니다.
- **Socket.IO CORS 강화**: `cors_allowed_origins="*"` 설정을 제거하고 기본 정책(동일 출처)을 사용합니다. 필요 시 `SOCKETIO_CORS_ALLOWED_ORIGINS`로 화이트리스트를 지정할 수 있습니다.
- **/uploads 접근 제어**: 로그인 없는 `/uploads/...` 접근을 차단하고, 방 파일은 해당 방 멤버만 다운로드 가능하도록 제한합니다(프로필 이미지는 로그인 사용자에게 허용).

### 🔐 암호화 (E2E)
- **v2 포맷 + 무결성(HMAC)**: 신규 메시지는 `v2:` prefix 포맷으로 전송/저장되며, 변조 감지 실패 시 클라이언트는 안전한 placeholder로 표시합니다.
- **v1 호환 유지**: 기존 DB의 v1 암호문은 그대로 복호화되어 표시됩니다.

### ⚡ 성능 최적화 (1차)
- **`GET /api/rooms` 최적화**: 쿼리/페이로드를 줄이고 `last_message_preview` 등을 제공해 방 목록 갱신 비용을 낮췄습니다. (그룹방 `members`는 기본 미포함, 필요 시 `?include_members=1`)
- **불필요한 재조회 감소**: 소켓 이벤트로 인한 `loadRooms()` 호출 폭발을 줄이고 throttle 기반 갱신을 사용합니다.
- **Lazy 복호화**: 방 입장 시 대량 메시지 복호화로 인한 UI 멈춤을 줄이기 위해, 화면에 보이는 메시지부터 점진적으로 복호화합니다.
- **서버 검색 개선**: 서버 메시지 검색에서 `encrypted=1` 메시지는 제외됩니다(서버에서 의미 있는 검색 불가).

## 🆕 v4.36 업데이트 (2026-01-23)

### 🛡️ 코드 안정성 대폭 향상
- **Socket Safety Refactoring**: `safeSocketEmit` 도입으로 네트워크 연결 불안정 시 크래시 방지
- **Robust Error Handling**: 파일 업로드 시 JSON 파싱 오류 처리 강화, DOM 요소 Null Check 추가
- **Code Consistency**: JavaScript 코드 스타일 및 소켓 이벤트 패턴 표준화

### 🎨 UI/UX 상호작용 개선
- **이모지 피커 수정**: 클릭 반응이 없던 버그 수정
- **메시지 컨텍스트 메뉴**: 우클릭 메뉴(답장, 삭제 등) 기능 복구 및 스타일 개선
- **답장 기능 개선**: 실시간 답장 표시 및 [삭제된 메시지] 상태 즉시 반영
- **읽음 상태 정확도**: 개별 메시지 읽음 처리 로직 최적화

---

## 📝 v4.34 업데이트 (2026-01-23)

### 🎨 UI/UX 대규모 개선
- **회원가입 단계 표시기**: 3단계(아이디→비밀번호→닉네임) 진행 상태 시각화
- **대화방 드래그앤드롭 정렬**: 대화방 순서를 드래그로 변경, 로컬 저장
- **연속 메시지 그룹화**: 같은 발신자의 3분 이내 메시지 그룹화 표시
- **코드 블록 구문 강조**: \`\`\`언어 형식 지원, 복사 버튼 포함
- **시간 툴팁**: 메시지 시간 호버 시 상세 날짜/시간 표시

### 📱 모바일 반응형 개선
- **스와이프 답장**: 모바일에서 메시지 스와이프로 빠른 답장
- **이모지 피커 개선**: 하단 고정, 터치 최적화
- **사이드바 오버레이**: 모바일 사이드바 슬라이드 애니메이션

### ♿ 접근성 향상
- **ARIA 레이블**: 모든 모달에 role="dialog" 추가
- **스킵 링크**: 메인 콘텐츠로 바로 이동
- **스크린 리더**: aria-live 영역 추가
- **모션 감소 모드**: prefers-reduced-motion 미디어 쿼리 지원

### ✨ 마이크로 인터랙션
- 타이핑 중 아바타 펄스 효과
- 메시지 전송 체크마크 애니메이션
- 리액션 팝 효과
- 새 메시지 뱃지 애니메이션

---

## 📝 v4.32 업데이트 (2026-01-23)

### 🛡️ 코드 안정성 및 보안 강화
- 메모리 누수 방지 (LazyLoadObserver 정리)
- 메시지 미리보기 개선 (암호화 감지)
- 기존 1:1 채팅 확인 (중복 생성 방지)
- 비밀번호 검증 강화 (영문+숫자 필수)
- 파일 업로드 MIME 타입 검증

---

## 📝 v4.3 업데이트 (2026-01-15)

### 🎨 UI/UX 리팩토링
- 마이크로 애니메이션 추가 (hover, bounce, ripple)
- 스켈레톤 로딩, 모달 애니메이션
- 접근성 강화 (focus-visible, reduced-motion, high contrast)

### ⚡ 성능 최적화
- DOM 배치 업데이트, 이벤트 위임
- 이미지 lazy loading
- gzip 압축, 사용자 캐시

---

## 📝 v4.2 업데이트 (2026-01-14)

### 🚀 GUI 고성능 모드 리팩토링 (Major Update)
- **Gevent 기반 Subprocess 아키텍처**: GUI와 서버 프로세스 분리로 안정성 및 성능 향상
- **HTTP 제어 API**: `/control/status`, `/control/stats`, `/control/logs`, `/control/shutdown` 엔드포인트 추가
- **자동 Gevent 감지**: `app/__init__.py`에서 monkey patching 자동 감지 및 gevent 모드 전환
- **독립 서버 실행**: `app/server_launcher.py`를 통한 독립적인 서버 프로세스 실행

### 🛡️ 보안 및 인증 개선
- **CSRF 예외 처리**: `/api/register`, `/api/login`, `/api/logout` 엔드포인트에 CSRF 예외 적용
  - 미인증 사용자의 회원가입/로그인 가능하도록 개선
  - 로그아웃 시 세션 삭제 작업으로 CSRF 위험 낮음
- **오류 메시지 개선**: 로그인/회원가입 실패 시 서버 오류 메시지 정확히 표시
  - "서버 연결 오류" 대신 "아이디 또는 비밀번호가 올바르지 않습니다" 등 구체적 메시지

### 💾 데이터베이스 최적화
- **DB 초기화 로직 개선**: `init_db()` 함수에서 직접 sqlite3 연결 생성으로 스레드 로컬 문제 해결
- **Busy Timeout 설정**: `PRAGMA busy_timeout=30000` 추가로 DB 잠금 문제 완화
- **중복 초기화 방지**: `_db_initialized` 플래그로 중복 초기화 방지
- **트랜잭션 안정성**: try-except-finally 블록으로 연결 관리 강화

### 🎨 UI/UX 개선
- **로그아웃 캐시 무효화**: 
  - `sessionStorage.clear()` 추가
  - 타임스탬프 URL (`/?_=timestamp`) 사용으로 캐시 방지
  - 상태 변수 초기화 (`currentUser = null` 등)
- **리액션 기능 수정**: `showReactionPicker` 함수가 event 객체 지원하도록 개선
- **메시지 오류 처리**: `err.message` 사용으로 정확한 오류 메시지 표시

### 🧪 테스트 및 안정성
- **Pytest 통과**: 전체 회귀 테스트 통과 (Exit Code 0)
- **Gevent 모드 검증**: `socketio.async_mode = 'gevent'` 확인
- **DB 테이블 생성 검증**: `users` 테이블 등 모든 필수 테이블 생성 확인

---

## 💻 시스템 요구사항

### 최소 요구사항
- **운영체제**: Windows 10/11, Linux, macOS
- **Python**: 3.9 이상
- **메모리**: 512MB RAM
- **디스크**: 200MB 여유 공간

### 권장 요구사항
- **운영체제**: Windows 11, Ubuntu 22.04+, macOS 12+
- **Python**: 3.11 이상
- **메모리**: 2GB RAM
- **디스크**: 1GB 여유 공간
- **네트워크**: 사내망 또는 로컬 네트워크

---

## 📦 설치 방법

### 1. 저장소 클론 또는 다운로드

```bash
# Git을 사용하는 경우
git clone <repository-url>
cd intranet-messenger-main

# 또는 ZIP 파일 다운로드 후 압축 해제
```

### 2. Python 가상환경 생성 (권장)

```powershell
# Windows PowerShell
python -m venv venv
.\\venv\\Scripts\\Activate.ps1

# Linux/macOS
python3 -m venv venv
source venv/bin/activate
```

### 3. 필수 패키지 설치

```powershell
pip install -r requirements.txt
```

### 4. 초기 설정 (선택사항)

`config.py` 파일에서 다음 설정을 조정할 수 있습니다:

- **포트 번호**: `DEFAULT_PORT = 5000`
- **Control API 포트**: `CONTROL_PORT = 5001` (제어 API는 `127.0.0.1` 바인딩)
- **Socket.IO CORS 허용 목록**: `SOCKETIO_CORS_ALLOWED_ORIGINS = None` (기본 동일 출처) 또는 `[...]`로 화이트리스트 지정
- **HTTPS 사용**: `USE_HTTPS = False`
- **세션 타임아웃**: `SESSION_TIMEOUT_HOURS = 72`
- **비동기 모드**: `ASYNC_MODE = 'threading'` (또는 'gevent')
- **최대 파일 크기**: `MAX_CONTENT_LENGTH = 16 * 1024 * 1024` (16MB)

---

## 🚀 실행 방법

### GUI 모드 (일반 사용자용)

시스템 트레이에 아이콘이 표시되며, 웹 브라우저를 통해 접속합니다.

```powershell
python server.py
```

**특징:**
- PyQt6 기반 시스템 트레이 인터페이스
- Gevent 고성능 모드 (subprocess 아키텍처)
- 서버 시작/중지 GUI 제어
- 실시간 통계 모니터링 (HTTP 제어 API)
- 자동 브라우저 실행

### CLI 모드 (서버/대규모 접속용)

고성능 gevent 모드로 실행되며, 수십~수백 명의 동시 접속을 지원합니다.

```powershell
python server.py --cli
```

**특징:**
- Gevent 비동기 처리 활성화
- 높은 동시 접속 처리 능력
- 서버 환경에 최적화
- 콘솔 로그 출력

### 접속 방법

서버 실행 후 웹 브라우저에서 다음 주소로 접속:

```
http://localhost:5000
```

또는 네트워크 내 다른 PC에서:

```
http://<서버-IP>:5000
```

---

## 🔨 빌드 방법

### PyInstaller를 사용한 실행 파일 생성

#### 1. PyInstaller 설치

```powershell
pip install pyinstaller
```

#### 2. 빌드 실행

```powershell
pyinstaller messenger.spec --clean
```

#### 3. 결과물 확인

빌드가 완료되면 다음 경로에 실행 파일이 생성됩니다:

```
dist/사내메신저v4.34/사내메신저v4.34.exe
```

#### 4. 배포

`dist/사내메신저v4.34/` 폴더 전체를 압축하여 배포합니다.

### 빌드 옵션 커스터마이징

`messenger.spec` 파일을 수정하여 다음을 변경할 수 있습니다:

- **아이콘**: `icon='icon.ico'`
- **실행 파일 이름**: `name='사내메신저v4.34'`
- **콘솔 표시**: `console=False`
- **UPX 압축**: `upx=True`

---

## 🗂️ 프로젝트 구조

```
intranet-messenger-main/
├── server.py                    # 메인 진입점 (GUI/CLI 모드 선택)
├── config.py                    # 통합 설정 파일
├── requirements.txt             # Python 의존성 패키지
├── messenger.spec               # PyInstaller 빌드 명세서
├── migrate_db.py                # 데이터베이스 마이그레이션 스크립트
│
├── app/                         # 백엔드 애플리케이션
│   ├── __init__.py              # Flask 앱 팩토리
│   ├── routes.py                # HTTP 라우트 (REST API)
│   ├── sockets.py               # Socket.IO 이벤트 핸들러
│   ├── models/                  # 데이터베이스 모델 (모듈화)
│   │   ├── __init__.py
│   │   ├── base.py              # DB 연결 및 초기화
│   │   ├── users.py             # 사용자 관련 모델
│   │   └── rooms.py             # 대화방 관련 모델
│   ├── utils.py                 # 유틸리티 함수 (보안, 검증 등)
│   ├── crypto_manager.py        # E2E 암호화 관리
│   ├── extensions.py            # Flask 확장 (Limiter, CSRF 등)
│   ├── control_api.py           # 제어 API (GUI 모드용)
│   ├── server_launcher.py       # 독립 서버 실행 모듈
│   └── run_server.py            # 멀티프로세스 서버 실행 모듈
│
├── gui/                         # PyQt6 데스크탑 UI
│   ├── __init__.py
│   └── server_window.py         # 서버 관리 GUI 윈도우
│
├── static/                      # 프론트엔드 정적 파일
│   ├── css/
│   │   └── style.css            # 메인 스타일시트
│   ├── js/
│   │   ├── app.js               # 메인 애플리케이션 로직
│   │   ├── socket.io.min.js     # Socket.IO 클라이언트 (로컬)
│   │   ├── crypto-js.min.js     # Crypto-JS 라이브러리 (로컬)
│   │   ├── storage.js           # 로컬 스토리지 관리
│   │   └── notification.js      # 알림 관리
│   └── uploads/                 # 업로드된 파일 저장소
│       └── profiles/            # 프로필 이미지
│
├── templates/                   # HTML 템플릿
│   └── index.html               # 메인 SPA 템플릿
│
├── certs/                       # SSL 인증서 (자동 생성)
│   ├── cert.pem
│   └── key.pem
│
├── flask_session/               # 서버 사이드 세션 저장소
│
├── tests/                       # Pytest 테스트 슈트
│   ├── conftest.py
│   ├── test_basic.py
│   └── test_routes.py
│
├── messenger.db                 # SQLite 데이터베이스
├── messenger.db-wal             # WAL 모드 로그
├── messenger.db-shm             # 공유 메모리
│
├── .secret_key                  # Flask SECRET_KEY (자동 생성)
├── .security_salt               # 비밀번호 솔트 (자동 생성)
├── .master_key                  # E2E 마스터 키 (자동 생성)
│
└── server.log                   # 서버 로그 (자동 로테이션)
```

---

## ⚙️ 기술 스택

### 백엔드
| 기술 | 버전 | 용도 |
|------|------|------|
| **Python** | 3.9+ | 메인 언어 |
| **Flask** | 2.3+ | 웹 프레임워크 |
| **Flask-SocketIO** | 5.3+ | 실시간 양방향 통신 |
| **SQLite3** | - | 데이터베이스 (WAL 모드) |
| **Gevent** | 23.0+ | 비동기 처리 (GUI/CLI 모드) |
| **PyCryptodome** | 3.18+ | 서버 측 암호화 |
| **Bcrypt** | 4.0+ | 비밀번호 해싱 |
| **Flask-Limiter** | 3.3+ | Rate Limiting |
| **Flask-WTF** | 1.1+ | CSRF 보호 |
| **Flask-Compress** | 1.13+ | Gzip 압축 |

### 프론트엔드
| 기술 | 용도 |
|------|------|
| **Vanilla JavaScript** | 메인 로직 (프레임워크 없음) |
| **Socket.IO Client** | 실시간 통신 (로컬 번들) |
| **Crypto-JS** | 클라이언트 측 E2E 암호화 (로컬 번들) |
| **CSS3** | 스타일링 |
| **HTML5** | 마크업 |

### 데스크탑 UI
| 기술 | 버전 | 용도 |
|------|------|------|
| **PyQt6** | 6.5+ | GUI 프레임워크 |
| **QSystemTrayIcon** | - | 시스템 트레이 |

### 개발 및 테스트
| 기술 | 버전 | 용도 |
|------|------|------|
| **Pytest** | 7.4+ | 단위/통합 테스트 |
| **Pytest-Flask** | 1.2+ | Flask 테스트 유틸리티 |
| **PyInstaller** | 5.13+ | 실행 파일 빌드 |

---

## 🔒 보안 기능

### 1. 종단간 암호화 (E2E)
- **알고리즘**: AES-256-CBC
- **키 교환**: 서버 중재 방식
- **구현**: 클라이언트 측 Crypto-JS, 서버 측 PyCryptodome
- **범위**: 모든 메시지 내용

### 2. 비밀번호 보안
- **해싱**: Bcrypt (비용 계수 12)
- **솔트**: 파일 기반 영구 솔트 (`.security_salt`)
- **저장**: 해시만 데이터베이스에 저장

### 3. 세션 관리
- **저장 방식**: 서버 사이드 파일 세션
- **쿠키 보안**: HttpOnly, SameSite=Lax
- **타임아웃**: 72시간 (설정 가능)
- **세션 고정 방지**: 로그인 시 세션 재생성

### 4. CSRF 보호
- **구현**: Flask-WTF
- **토큰**: 세션별 고유 토큰
- **검증**: 인증된 사용자의 POST/PUT/DELETE 요청
- **예외**: `/api/register`, `/api/login`, `/api/logout` (미인증 접근 허용)

### 5. Rate Limiting
- **로그인**: 10회/분
- **회원가입**: 5회/분
- **메시지 전송**: 100회/분
- **파일 업로드**: 10회/분

### 6. 보안 헤더
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `Content-Security-Policy: default-src 'self'; ...`
- `Referrer-Policy: strict-origin-when-cross-origin`

### 7. 파일 업로드 보안
- **파일명**: UUID 기반 랜덤 파일명
- **확장자 검증**: 화이트리스트 방식
- **크기 제한**: 16MB
- **경로 검증**: 디렉토리 트래버설 방지
- **업로드 토큰**: `/api/upload` 성공 시 1회용 `upload_token`(기본 TTL 5분) 발급 후 소켓 전송에서 검증

### 8. 업로드 파일 접근 제어
- 로그인 없는 `/uploads/...` 접근은 `401`로 차단됩니다.
- `profiles/`는 로그인 사용자에게만 허용됩니다.
- 방 파일은 DB 역조회 후 **해당 방 멤버만** 다운로드 가능하도록 제한됩니다.
- 인증 리소스 캐시 정책: 일반 파일 `private, no-store`, 프로필 이미지 `private, max-age=3600`

### 8-1. API 호환 정책
- `POST /api/rooms`: 표준 입력은 `members`, 하위 호환으로 `member_ids`도 허용합니다(`members` 우선).
- `GET /api/search`: `limit`는 `1..200` 범위로 강제되며 `offset`은 음수 입력 시 `0`으로 보정됩니다.
- `POST /api/upload`: `room_id`가 필수이며 응답에 `upload_token`이 포함됩니다.

### 9. Control API 격리 (localhost + token)
- 제어 API는 메인 서버 포트가 아니라 `127.0.0.1:{CONTROL_PORT}`에서만 서비스됩니다.
- 모든 `/control/*` 요청은 `X-Control-Token` 헤더가 필요합니다(토큰 파일: `.control_token`).

### 10. Socket.IO CORS 정책 강화
- 기본값은 동일 출처만 허용하며, 필요 시 `SOCKETIO_CORS_ALLOWED_ORIGINS`로 화이트리스트를 지정합니다.

---

## 🚀 성능 최적화

### 1. 데이터베이스
- **WAL 모드**: 동시 읽기/쓰기 성능 향상
- **Busy Timeout**: 30초 대기로 잠금 문제 완화
- **스레드 로컬 연결**: 커넥션 풀링
- **자동 정리**: `teardown_appcontext`로 연결 해제
- **인덱싱**: 주요 쿼리 최적화

### 2. 네트워크
- **Gzip 압축**: Flask-Compress로 응답 압축
- **Socket.IO 최적화**: 
  - Ping Timeout: 120초
  - Ping Interval: 25초
  - Max Buffer: 10MB

### 3. 비동기 처리
- **Gevent**: GUI/CLI 모드에서 고성능 비동기 처리
- **Subprocess 아키텍처**: GUI와 서버 프로세스 분리
- **이벤트 기반**: Socket.IO 이벤트 루프

### 4. 메모리 관리
- **타이핑 인디케이터**: 자동 정리
- **소켓 세션**: 연결 해제 시 즉시 정리
- **로그 로테이션**: 10MB, 5개 백업

### 5. v4.36.1 성능 패치
- `/api/rooms` 응답 페이로드 축소(그룹방 `members` 기본 미포함) + `last_message_preview` 제공
- 소켓 이벤트로 인한 `loadRooms()` 재호출 감소(throttle 적용)
- 암호화 메시지 Lazy 복호화로 렌더링 jank 완화
- 서버 메시지 검색에서 `encrypted=1` 제외

---

## 🔍 문제 해결

### 1. 서버가 시작되지 않음

**증상**: `OSError: [WinError 10048] 포트가 이미 사용 중입니다`

**해결**:
```powershell
# 포트 사용 중인 프로세스 확인
netstat -ano | findstr :5000

# Control API 포트 확인 (기본 5001)
netstat -ano | findstr :5001

# 프로세스 종료
taskkill /PID <PID> /F

# 또는 config.py에서 포트 변경
DEFAULT_PORT = 5001
# 주의: CONTROL_PORT 기본값이 5001이므로, DEFAULT_PORT를 5001로 바꾸면 Control API 포트와 충돌합니다.
```

### 2. Gevent 관련 오류

**증상**: `ImportError: No module named 'gevent'`

**해결**:
```powershell
# Gevent 설치
pip install gevent gevent-websocket

# 또는 config.py에서 비동기 모드 변경
ASYNC_MODE = 'threading'
```

### 3. 데이터베이스 잠금 오류

**증상**: `sqlite3.OperationalError: database is locked`

**해결**:
```powershell
# 서버 완전 종료 후 재시작
# WAL 파일 삭제 (주의: 데이터 손실 가능)
del messenger.db-wal
del messenger.db-shm
```

### 4. 회원가입/로그인 실패

**증상**: "서버 연결 오류" 또는 "CSRF 토큰 누락"

**해결**:
- 브라우저 캐시 삭제 (Ctrl+Shift+Delete)
- 하드 새로고침 (Ctrl+F5)
- InPrivate/Incognito 모드에서 테스트
- Rate limit 확인 (1분 대기 후 재시도)

### 5. 파일 업로드 실패

**증상**: 파일 업로드 시 오류 발생

**해결**:
```powershell
# uploads 폴더 권한 확인
# 폴더 수동 생성
mkdir uploads
mkdir uploads\\profiles

# config.py에서 크기 제한 확인
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
```

---

## 🧪 테스트

### 전체 테스트 실행

```powershell
# 환경 변수 설정 및 테스트 실행
$env:PYTHONPATH='.'; pytest tests -v

# 또는 Linux/macOS
PYTHONPATH=. pytest tests -v
```

### 특정 테스트 파일 실행

```powershell
pytest tests/test_routes.py -v
```

### 커버리지 확인

```powershell
pip install pytest-cov
pytest tests --cov=app --cov-report=html
```

---

## 📝 사용 가이드

### 첫 사용자 등록

1. 서버 실행 후 브라우저에서 `http://localhost:5000` 접속
2. "회원가입" 버튼 클릭
3. 아이디, 비밀번호, 닉네임 입력
4. 첫 번째 사용자는 자동으로 관리자 권한 부여

### 대화방 생성

1. 로그인 후 좌측 사이드바에서 "새 대화" 버튼 클릭
2. 대화 상대 선택 (1:1) 또는 여러 명 선택 (그룹)
3. 그룹인 경우 방 이름 입력
4. "대화 시작" 클릭

### 파일 전송

1. 대화방에서 파일 아이콘 클릭 또는 드래그앤드롭
2. 파일 선택 (최대 16MB)
3. 자동 업로드 및 전송

### 투표 생성

1. 그룹 대화방에서 투표 아이콘 클릭
2. 질문과 선택지 입력
3. "투표 생성" 클릭
4. 멤버들이 실시간으로 투표 가능

---

## 🔄 업데이트 및 마이그레이션

### 데이터베이스 마이그레이션

버전 업데이트 시 데이터베이스 스키마 변경이 필요한 경우:

```powershell
python migrate_db.py
```

### v4.36.1 추가 안내
- 첫 실행 시 `.control_token` 파일이 자동 생성될 수 있습니다(제어 API 인증 토큰).
- 일부 쿼리 최적화를 위해 DB 인덱스가 추가되었습니다. 기존 DB라도 실행 시 `init_db()`에서 `IF NOT EXISTS`로 생성됩니다.
- 서버 검색에서 암호화 메시지(`encrypted=1`)는 제외됩니다.

### 백업 및 복원

**백업**:
```powershell
# 데이터베이스 백업
copy messenger.db messenger_backup.db

# 업로드 파일 백업
xcopy /E /I uploads uploads_backup
```

**복원**:
```powershell
# 데이터베이스 복원
copy messenger_backup.db messenger.db

# 업로드 파일 복원
xcopy /E /I uploads_backup uploads
```

---

## 🌐 사내망 호환성

이 메신저는 **완전히 독립적으로 실행**되며, 외부 인터넷 연결이 필요하지 않습니다.

### ✅ 폐쇄망 운영 가능
- **외부 CDN/웹폰트 의존성 0%**: JS/CSS/폰트는 로컬 번들 또는 시스템 폰트 사용
- **외부 API 호출 없음**: 완전 자체 완결형
- **로컬 데이터베이스**: SQLite (별도 DB 서버 불필요)
- **내장 리소스**: Socket.IO, Crypto-JS 등 모두 내장

### 📦 포함된 로컬 라이브러리
- Socket.IO Client 4.x
- Crypto-JS 4.x
- 모든 CSS 및 이미지 리소스

---

## 📄 라이선스

MIT License

Copyright (c) 2026 사내 메신저 개발팀

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

## 🤝 기여

버그 리포트, 기능 제안, 풀 리퀘스트를 환영합니다!

---

## 📞 지원

문제가 발생하거나 질문이 있으시면 이슈를 등록해주세요.

---

## Performance Optimizations (v4.36.2)

- Room list rendering: switched to DOM reconcile updates to avoid full `innerHTML` rebuild on refresh.
- Read receipt UI: `read_updated` now updates only the affected message id range (binary search), avoiding scanning all sent messages.
- File-only search: added `idx_messages_file_name` index and optimized filename search to prefer prefix matches (contains match still supported).
- Fixed incremental room DOM update selector in `updateRoomListFromMessage` (previously could fail to find the room element).

**Made with ❤️ for secure internal communication**
