# Intranet Messenger 프로젝트 구조 분석 및 기능 확장 가이드

- 작성일: 2026-02-27
- 최종 업데이트: 2026-03-15
- 대상 경로: `C:\twbeatles-repos\intranet-messenger`
- 목적: 현재 구조를 기준으로 기능 확장과 유지보수 시 영향 범위와 우선순위를 빠르게 파악하기 위한 문서

## 1. 현재 기준선

- 표준 실행 진입점: `server.py`
- 앱 팩토리: `app.create_app() -> (app, socketio)`
- 타입 기준선: `pyright` -> `0 errors, 0 warnings`
- 테스트 기준선: `pytest -q` -> `86 passed`
- 문서 기준 세트
  - `README.md`
  - `claude.md`
  - `gemini.md`
  - `docs/BACKUP_RUNBOOK.md`

## 2. 최상위 구조

- `server.py`
  - CLI/GUI 실행 진입점
  - HTTPS 인증서 생성 fallback 호출
- `config.py`
  - 런타임 설정, 기능 플래그, 경로 상수
- `app/`
  - Flask 앱 팩토리, 라우트, 소켓 이벤트, 모델, 보조 유틸리티
- `static/`, `templates/`
  - 프런트엔드 리소스 및 단일 페이지 템플릿
- `tests/`
  - 회귀 테스트와 운영/보안 계약 검증
- `scripts/`
  - 로컬 백업/복구/검증 스크립트
- `docs/`
  - 운영 문서
- `messenger.spec`
  - PyInstaller 빌드 명세
- `pyrightconfig.json`
  - 리포지토리 로컬 타입체크 기준선

## 3. 백엔드 구조

### 3.1 앱 초기화

- `app/__init__.py`
  - Flask 설정 로드
  - Session / CSRF / Compress / Limiter 초기화
  - Socket.IO async mode 선택
  - maintenance worker 시작

### 3.2 HTTP API

- `app/routes.py`
  - 인증, 방, 메시지, 업로드, 프로필, 핀, 투표, 관리자 API 담당
  - JSON payload 파싱과 공통 에러 응답이 집중된 파일

### 3.3 Socket 이벤트

- `app/sockets.py`
  - 실시간 메시지, 리액션, 프로필, 투표, 방 멤버십 이벤트 담당
  - authoritative payload 원칙 적용

### 3.4 데이터 계층

- `app/models/base.py`
  - DB 연결, 마이그레이션성 초기화, 공용 쿼리 유틸
- `app/models/*`
  - 도메인별 쿼리 분리
  - `users`, `rooms`, `messages`, `polls`, `files`, `reactions`, `admin_audit`
- `app/legacy/models_monolith.py`
  - 레거시 호환용 모놀리식 계층
  - 신규 구현보다 유지보수/비교 기준 용도에 가깝다

## 4. 프런트 구조

- `static/js/app.js`, `static/js/rooms.js`, `static/js/messages.js`
  - 기존 메인 동작 흐름 담당
- `static/js/message-upload.js`
  - 파일 업로드 전담 분리 모듈
- `static/js/modules/*`
  - 일부 기능의 점진적 모듈화 경로

## 5. 운영/보안 핵심 계약

- 방 생성은 `members`를 표준 입력으로 사용하고 `member_ids`를 호환 입력으로 허용한다
- 파일 메시지는 `upload_token` 검증이 선행되어야 한다
- 세션 무효화는 HTTP와 Socket 양쪽에서 검증한다
- 소켓 payload는 서버 DB 조회 결과를 기준으로 한다
- `/uploads/<path>`는 경로 검증과 접근 권한 검증을 통과해야 한다
- Poll/Pin 계약은 README와 `claude.md` 기준을 따른다

## 6. 확장 시 우선 확인할 영향 범위

### 6.1 API 계약 변경

- 수정 파일
  - `app/routes.py`
  - 관련 `app/models/*`
  - 관련 `static/js/*`
  - 관련 `tests/*`
  - `README.md`, `claude.md`, `gemini.md`

### 6.2 Socket 이벤트 변경

- 수정 파일
  - `app/sockets.py`
  - 필요 시 `app/routes.py`
  - 관련 프런트 핸들러
  - 관련 보안/회귀 테스트

### 6.3 업로드/보안 로직 변경

- 수정 파일
  - `app/routes.py`
  - `app/upload_tokens.py`
  - `app/upload_scan.py`
  - `static/js/message-upload.js`
  - 업로드/권한/토큰 관련 테스트

### 6.4 패키징/배포 경로 변경

- 수정 파일
  - `messenger.spec`
  - 필요 시 `server.py`, `gui/server_window.py`
  - 운영 문서와 README

## 7. 현재 구조의 강점

- 실행 진입점이 `server.py`로 정리되어 있다
- 업로드, OIDC, Redis state store, 감사 로그처럼 옵션 기능의 경계가 비교적 명확하다
- `app/models/*` 분리가 진행되어 있어 도메인 단위 수정이 가능하다
- 타입 체크와 인코딩 hygiene 회귀 검증이 자동화되었다

## 8. 현재 구조의 주의 지점

- `app/routes.py`와 `app/sockets.py`는 여전히 크고 영향 범위가 넓다
- `app/__init__.py`는 초기화 책임이 많아 async mode/세션/확장 초기화 변경 시 회귀 위험이 있다
- 레거시 `app/legacy/models_monolith.py`와 분리 모델 계층이 공존한다
- GUI, CLI, PyInstaller 경로가 모두 살아 있어 진입점 변경 시 패키징 영향 확인이 필요하다

## 9. 권장 후속 개선

1. Socket event schema를 별도 문서로 분리해 프런트/백엔드 계약을 명확히 유지한다.
2. `app/routes.py`와 `app/sockets.py`를 도메인별 서브모듈로 점진 분리한다.
3. PyInstaller smoke test를 자동화해 optional import 누락을 조기에 잡는다.
4. 문서 기준선과 테스트 기준선을 릴리스 단위로 고정해 업데이트한다.

## 10. 2026-03-15 정합성 업데이트

- Pylance/Pyright 기준선을 `pyrightconfig.json`으로 고정했다
- UTF-8 BOM 제거와 깨진 한글 복구를 반영했다
- `tests/test_encoding_hygiene.py`를 추가했다
- `messenger.spec`에 eventlet 및 인증서 생성 경로 hidden import를 보강했다
- 활성 문서 세트 기준으로 README/운영 문서/세션 가이드를 다시 동기화했다
