# 🔒 사내 웹메신저 v4.15

Flask + Socket.IO + PyQt6 기반 **종단간 암호화(E2E)** 사내 메신저

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-2.3+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

---

## 📋 목차

- [주요 기능](#-주요-기능)
- [최신 업데이트](#-v415-업데이트-2026-01-11)
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

### 💬 메시징 기능
- **실시간 채팅**: Socket.IO 기반 양방향 통신
- **1:1 및 그룹 채팅**: 개인 대화 및 다중 사용자 그룹 채팅
- **읽음 확인 (Read Receipt)**: 메시지 읽음 상태 실시간 표시
- **타이핑 인디케이터**: 상대방 입력 상태 실시간 표시
- **메시지 답장**: 특정 메시지에 대한 답장 기능
- **메시지 반응**: 이모지 리액션 기능

### 📁 파일 및 미디어
- **파일 공유**: 드래그앤드롭 지원, 최대 16MB
- **안전한 파일명**: UUID 기반 파일명으로 보안 강화
- **프로필 이미지**: 사용자 프로필 사진 업로드 및 관리
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
- **메시지 삭제**: 본인 메시지 삭제 기능
- **데이터 무결성**: 사용자 삭제 시 관련 데이터 자동 정리
- **고아 데이터 방지**: 참조 무결성 보장

---

## 🆕 v4.15 업데이트 (2026-01-11)

### 🛡️ 보안 및 안전성 강화 (Major Update)
- **보안 헤더 및 CSRF 보호** - `Flask-WTF` 및 표준 보안 헤더(`X-Frame-Options` 등) 적용
- **API 레이트 리미팅** - `Flask-Limiter` 도입으로 무차별 대입 공격 및 DoS 방지
- **데이터 무결성 보장** - 사용자 삭제 시 관련 데이터(방, 투표, 파일)의 완벽한 정리 및 고아 데이터 방지
- **Username 유효성 검사** - 회원가입 시 아이디 형식 검증 강화

### 🛠️ 시스템 안정성 개선
- **DB 커넥션 관리 최적화** - `teardown_appcontext`를 통한 스레드 로컬 DB 연결 자동 정리 (OperationalError 해결)
- **메시지 삭제 원자성** - DB 트랜잭션과 파일 삭제 간의 정합성 보장 (파일 삭제 실패 시에도 DB 일관성 유지)
- **메모리 누수 방지** - 소켓 연결 해제 시 타이핑 인디케이터 등 임시 데이터 즉시 정리

### 🧪 테스트 인프라
- **Pytest 도입** - 단위/통합 테스트 슈트 구축 (24개 테스트 케이스)
- **검증된 안정성** - 전체 회귀 테스트 통과 (Exit Code 0)

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
.\venv\Scripts\Activate.ps1

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
- 서버 시작/중지 GUI 제어
- 실시간 통계 모니터링
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
dist/사내메신저v4.3/사내메신저v4.3.exe
```

#### 4. 배포

`dist/사내메신저v4.3/` 폴더 전체를 압축하여 배포합니다.

### 빌드 옵션 커스터마이징

`messenger.spec` 파일을 수정하여 다음을 변경할 수 있습니다:

- **아이콘**: `icon='icon.ico'` (145번째 줄)
- **실행 파일 이름**: `name='사내메신저v4.3'` (134번째 줄)
- **콘솔 표시**: `console=False` (139번째 줄)
- **UPX 압축**: `upx=True` (138번째 줄)

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
│   ├── models.py                # 데이터베이스 모델 및 쿼리
│   ├── utils.py                 # 유틸리티 함수 (보안, 검증 등)
│   ├── crypto_manager.py        # E2E 암호화 관리
│   ├── extensions.py            # Flask 확장 (Limiter, CSRF 등)
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
│   │   └── crypto-js.min.js     # Crypto-JS 라이브러리 (로컬)
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
├── backup/                      # 백업 파일
│
├── _cleanup_20260113/           # 정리된 테스트/디버그 파일
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
| **Gevent** | 23.0+ | 비동기 처리 (CLI 모드) |
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
| **QWebEngineView** | - | 내장 브라우저 (선택) |

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
- **검증**: 모든 POST/PUT/DELETE 요청

### 5. Rate Limiting
- **로그인**: 5회/분
- **회원가입**: 3회/시간
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

---

## 🚀 성능 최적화

### 1. 데이터베이스
- **WAL 모드**: 동시 읽기/쓰기 성능 향상
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
- **Gevent**: CLI 모드에서 고성능 비동기 처리
- **Threading**: GUI 모드에서 안정성 우선
- **이벤트 기반**: Socket.IO 이벤트 루프

### 4. 메모리 관리
- **타이핑 인디케이터**: 자동 정리
- **소켓 세션**: 연결 해제 시 즉시 정리
- **로그 로테이션**: 10MB, 5개 백업

---

## 🔍 문제 해결

### 1. 서버가 시작되지 않음

**증상**: `OSError: [WinError 10048] 포트가 이미 사용 중입니다`

**해결**:
```powershell
# 포트 사용 중인 프로세스 확인
netstat -ano | findstr :5000

# 프로세스 종료
taskkill /PID <PID> /F

# 또는 config.py에서 포트 변경
DEFAULT_PORT = 5001
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

### 3. PyQt6 GUI가 표시되지 않음

**증상**: GUI 윈도우가 나타나지 않음

**해결**:
```powershell
# PyQt6 재설치
pip uninstall PyQt6
pip install PyQt6

# 또는 CLI 모드로 실행
python server.py --cli
```

### 4. 데이터베이스 잠금 오류

**증상**: `sqlite3.OperationalError: database is locked`

**해결**:
```powershell
# 서버 완전 종료 후 재시작
# WAL 파일 삭제 (주의: 데이터 손실 가능)
del messenger.db-wal
del messenger.db-shm
```

### 5. 파일 업로드 실패

**증상**: 파일 업로드 시 오류 발생

**해결**:
```powershell
# uploads 폴더 권한 확인
# 폴더 수동 생성
mkdir uploads
mkdir uploads\profiles

# config.py에서 크기 제한 확인
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
```

### 6. SSL 인증서 오류

**증상**: HTTPS 접속 시 인증서 오류

**해결**:
```powershell
# HTTP 모드로 변경 (config.py)
USE_HTTPS = False

# 또는 인증서 재생성
python -c "from certs.generate_cert import generate_certificate; generate_certificate('certs/cert.pem', 'certs/key.pem')"
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
- **외부 CDN 의존성 0%**: 모든 JavaScript 라이브러리 로컬 번들
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

**Made with ❤️ for secure internal communication**
