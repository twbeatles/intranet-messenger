# Intranet Messenger

내부망 전용 메신저 서버(Flask + Socket.IO)입니다.

- 기준일: 2026-02-28
- 기준 브랜치: `main`
- 최신 검증: `pytest -q` -> `84 passed`

## 1. 프로젝트 상태

이번 주기에서 보안/구조 개선 항목을 반영했습니다.

- R-01 ~ R-11 대응 코드 반영
- OIDC(옵션), AV 스캔 파이프라인(옵션), Redis state store(옵션) 반영
- 관리자 감사로그 API 반영
- `/api/config` 기반 프론트-서버 계약 단일화
- 로컬 수동 백업/복구/검증 스크립트 + 런북 추가

## 2. 핵심 기능

- 실시간 채팅: Socket.IO 이벤트 기반 메시지 전송
- 1:1/그룹 방, 읽음 상태, 리액션, 고정 메시지, 투표
- 파일 업로드 및 다운로드 권한 제어
- 세션 토큰 검증(HTTP + Socket) 기반 세션 무효화
- 레이트리밋(로그인/가입/업로드/고급검색/소켓 전송)
- 관리자 감사로그(JSON/CSV 조회)

## 3. 시스템 구성

- 백엔드: Flask, Flask-SocketIO, SQLite
- 프론트: Vanilla JS
- 옵션 백엔드:
  - Redis: 레이트리밋 저장소 + 상태 저장소
  - OIDC: 사내 SSO 연동
  - ClamAV: 업로드 파일 비동기 스캔

## 4. 요구사항

- Python 3.9+
- 권장: Python 3.11+
- 설치:

```bash
pip install -r requirements.txt
```

## 5. 실행

개발/로컬 실행:

```bash
python server.py --cli
```

실행 기준 경로:

- 표준 진입점: `server.py`
- 레거시 호환 파일: `messenger_server.py` (deprecated shim, 신규 로직 추가 금지)

브라우저 접속:

- `http://localhost:5000`

## 6. 주요 설정값

`config.py` 및 환경변수로 제어합니다.

- 서버
  - `DEFAULT_PORT` (기본 5000)
  - `SESSION_TIMEOUT_HOURS` (기본 72)
- 업로드
  - `MAX_CONTENT_LENGTH` (기본 16MB)
  - `UPLOAD_FOLDER`
- 레이트리밋/상태 저장
  - `RATE_LIMIT_STORAGE_URI` (기본 `memory://`)
  - `STATE_STORE_REDIS_URL` (기본 공백)
  - `SOCKET_SEND_MESSAGE_PER_MINUTE` (기본 100)
  - `SOCKET_PIN_UPDATED_PER_MINUTE` (기본 30)
- OIDC(옵션)
  - `FEATURE_OIDC_ENABLED`
  - `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_ISSUER_URL` 등
  - `OIDC_JWKS_URL` (기본 공백, 미설정 시 well-known `jwks_uri` 사용)
  - `OIDC_JWKS_CACHE_SECONDS` (기본 300)
- AV 스캔(옵션)
  - `FEATURE_AV_SCAN_ENABLED`
  - `AV_CLAMD_HOST`, `AV_CLAMD_PORT`, `AV_SCAN_TIMEOUT_SECONDS`
- 보존 정책
  - `RETENTION_DAYS` (기본 0 = 비활성)

## 7. 공개 API 계약(핵심)

### 7.1 런타임 설정

- `GET /api/config`
- 응답 필드:
  - `upload.max_size_bytes`
  - `rate_limits.{login,register,upload,search_advanced,socket_send_message,socket_pin_updated}`
  - `features.{oidc,av,redis}`

### 7.2 파일 업로드

- `POST /api/upload`
- 필수: `file`, `room_id`
- AV 비활성:
  - `scan_status=clean`
  - `upload_token`, `file_path`, `file_name`
- AV 활성:
  - `scan_status=pending`
  - `job_id`

- `GET /api/upload/jobs/<job_id>`
- 상태: `pending|clean|infected|error`
- `clean` 상태에서만 `upload_token` 반환

### 7.3 투표 무결성

- `POST /api/polls/<poll_id>/vote`
- `option_id`가 해당 `poll_id` 소속이 아니면 `400`
- 표준 오류 필드: `error`, `code`

### 7.4 OIDC

- `GET /api/auth/providers`
- `GET /auth/oidc/login`
- `GET /auth/oidc/callback`
- 정책: 첫 로그인 시 로컬 계정 자동 프로비저닝
- 검증: `id_token` 서명(JWKS), `iss`, `aud`, `exp`, `nonce` 검증 실패 시 로그인 거부

### 7.5 관리자 감사로그

- `GET /api/rooms/<room_id>/admin-audit-logs?format=json|csv`

## 8. 레이트리밋 정책

- `POST /api/login`: `10/min`
- `POST /api/register`: `5/min`
- `POST /api/upload`: `10/min`
- `POST /api/search/advanced`: `30/min`
- Socket `send_message`: 사용자 기준 `100/min` (기본)
- Socket `pin_updated`: 사용자 기준 `30/min` (기본)

고급검색 입력 정책:
- `POST /api/search/advanced`에서 `limit`/`offset`이 정수가 아니면 `400`
- 오류 코드: `invalid_limit`, `invalid_offset`

방 나가기 API 응답:
- `POST /api/rooms/<room_id>/leave`
- 공통: `success: true`
- 상태 필드:
  - `left: true`, `already_left: false` (실제 나감)
  - `left: false`, `already_left: true` (이미 비멤버)

## 9. 보안/운영 메모

- 세션 무효화
  - 비밀번호 변경 시 DB `session_token` 갱신
  - HTTP(`before_request`) + Socket(`connect`/핵심 이벤트) 검증
- 업로드 토큰
  - 1회성 토큰, TTL 기반 검증
- 상태 저장소 강등
  - Redis 장애 시 메모리 저장소로 자동 강등

## 10. 백업/복구/검증

상세 절차는 [docs/BACKUP_RUNBOOK.md](docs/BACKUP_RUNBOOK.md)를 참고합니다.

- 백업

```bash
python scripts/backup_local.py --label before_release
```

- 복구

```bash
python scripts/restore_local.py <backup_dir> --yes
```

- 복구 검증

```bash
python scripts/verify_restore.py
```

## 11. 테스트

전체 테스트:

```bash
pytest -q
```

현재 기준선:

- `84 passed` (2026-02-28)

## 12. PyInstaller 빌드

`messenger.spec` 기준으로 빌드합니다.

```bash
pyinstaller messenger.spec --clean
```

이번 갱신에서 `.spec`에 아래 누락 위험을 반영했습니다.

- 신규 모듈 hidden import 추가:
  - `app.state_store`, `app.upload_scan`, `app.oidc`, `app.models.admin_audit`
- Redis 동적 import 반영:
  - `redis`, `redis.asyncio`
- OIDC/JWKS 검증 경로 반영:
  - `jwt`, `jwt.algorithms`, `jwt.api_jwk`, `jwt.jwks_client`, `jwt.exceptions`
- 런북 파일 포함:
  - `docs/BACKUP_RUNBOOK.md`

## 13. 관련 문서

- [claude.md](claude.md)
- [gemini.md](gemini.md)
- [docs/BACKUP_RUNBOOK.md](docs/BACKUP_RUNBOOK.md)
- [PROJECT_STRUCTURE_FEATURE_EXPANSION_ANALYSIS_2026-02-27.md](PROJECT_STRUCTURE_FEATURE_EXPANSION_ANALYSIS_2026-02-27.md)
- [FEATURE_RISK_REVIEW_2026-02-28.md](FEATURE_RISK_REVIEW_2026-02-28.md)

## 14. 2026-02-25 변경 요약

- 리스크 R-01~R-11 대응 구현 반영
- 추가 기능 7개(옵션 기반) 구현 반영
- 테스트/문서/운영 런북 동기화 완료

## 15. 2026-02-27 정합성 업데이트

- 구조 리스크 개선 반영:
  - `messenger_server.py` deprecated shim 전환(실행 기준 `server.py` 단일화)
  - 파일 업로드 책임 분리(`static/js/message-upload.js`)
  - 서버 진입점 UTF-8 stdio 고정 + 소켓 오류 메시지 정규화
  - Flask-Session deprecation 대응(`cachelib` 백엔드 전환)
- `.spec` 점검 결과:
  - `static` 디렉터리 포함으로 신규 프론트 파일(`message-upload.js`)은 추가 설정 없이 패키징 포함
  - `cachelib.file` hidden import 이미 반영됨(유지)

## 16. 2026-02-28 기능 리스크 반영 업데이트

- 서버 authoritative 소켓 계약 강화:
  - `room_members_updated`: room 정수/멤버십 검증 필수
  - `profile_updated`, `reaction_updated`, `poll_created`, `poll_updated`: 클라이언트 payload 위조값 무시, DB canonical 데이터 기준 브로드캐스트
  - `pin_updated`: 시스템 메시지 생성 제거, 멤버십 검증 + rate limit 적용, room 신호만 브로드캐스트
- 핀 생성/삭제 경로 정리:
  - 시스템 메시지 생성은 `/api/rooms/<room_id>/pins` 생성/삭제 성공 경로에서만 수행
  - 서버가 `new_message`, `pin_updated`를 직접 emit
- HTTP 하드닝:
  - `/api/search/advanced`의 `limit`, `offset` 타입 오류를 `400 + code`로 표준화
  - `/uploads/<path>` 경로 검증을 `os.path.commonpath` 기반으로 강화
  - `/api/rooms/<room_id>/leave` idempotent 응답 필드(`left`, `already_left`) 추가
- OIDC strict 검증:
  - `id_token` 필수
  - JWKS 서명 검증 + `iss`, `aud`, `exp`, `nonce` 검증
  - callback에서 `state`, `nonce` one-time pop 처리
