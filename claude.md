# CLAUDE.md

프로젝트: `intranet-messenger-main`  
최종 업데이트: 2026-02-20

## 1) 목적

새 작업 세션에서 Claude가 이 파일 하나로 프로젝트의 현재 상태, 필수 규칙, 검증 기준을 빠르게 파악하도록 하기 위한 운영 문서.

## 2) 세션 시작 시 필수 확인

1. `README.md`  
2. `IMPLEMENTATION_AUDIT.md`  
3. 최근 변경 파일:
   - `app/routes.py`
   - `app/sockets.py`
   - `app/upload_tokens.py`
   - `app/models/users.py`
   - `app/models/messages.py`
   - `app/models/polls.py`

## 3) 현재 기준선(Baseline)

- 버전 문서 기준: `v4.36.3 (2026-02-20)`
- 회귀 테스트 기준:
  - `pytest tests -q` => `64 passed`
  - `pytest --maxfail=1` => `64 passed`
- `pytest.ini` 존재:
  - `testpaths = tests`
  - `norecursedirs = backup dist build`

## 4) 핵심 API/보안 계약 (절대 깨지면 안 됨)

### 4.1 방 생성 API

- 엔드포인트: `POST /api/rooms`
- 표준 입력 키: `members`
- 호환 입력 키: `member_ids` (하위 호환)
- 동시 입력 시: `members` 우선, `member_ids` 무시(경고 로그)
- 멤버 정규화:
  - 정수 변환
  - 중복 제거
  - 자기 자신 자동 포함

### 4.2 업로드/파일 메시지 보안

- 업로드: `POST /api/upload`
  - `room_id` 필수
  - 성공 응답에 `upload_token` 포함
- 소켓: `send_message`
  - `type in ('file','image')`이면 `upload_token` 필수
  - 서버는 클라이언트 `file_path`/`file_name`을 신뢰하지 않음
  - 토큰 검증: user/room/type/만료/1회성 소비
- 토큰 저장소: `app/upload_tokens.py`
  - 기본 TTL 5분
  - thread-safe lock
  - one-time consume

### 4.3 파일 다운로드 캐시 정책

- 엔드포인트: `GET /uploads/<path>`
- 일반 파일: `Cache-Control: private, no-store`
- 프로필 이미지: `Cache-Control: private, max-age=3600`

### 4.4 검색 API 정책

- 엔드포인트: `GET /api/search`
- `limit` clamp: `1..200`
- `offset`: 음수 방지(`>=0`)

### 4.5 Poll/Pin 계약

- Poll 생성 모델 계약:
  - `create_poll(...) -> poll_id | None`
- Poll 생성 라우트:
  - `poll_id` 생성 후 `get_poll(poll_id)` 조회하여 응답
- Pin 삭제:
  - `success, error = unpin_message(...)`로 판정
  - tuple truthy 오판 금지

### 4.6 회원탈퇴 무결성

- `polls.created_by = NULL` 업데이트 금지 (`NOT NULL` 제약)
- 탈퇴 사용자가 만든 poll 처리:
  - 같은 방의 다른 멤버에게 재할당(관리자 우선)
  - 대상 없으면 poll 삭제

## 5) 작업 원칙

1. `app/models.py`(모놀리식)보다 `app/models/*` 모듈 경로를 우선 사용.
2. API 계약 변경 시:
   - 라우트 + 프론트 + 테스트 + README를 동시 갱신.
3. 파일 전송 경로에서 클라이언트 입력 경로 신뢰 금지.
4. 새 보안 로직 추가 시 회귀 테스트를 반드시 추가.
5. README의 폐쇄망/용량/API 설명과 구현을 항상 일치시킬 것.

## 6) 변경 후 검증 루틴

1. `pytest tests -q`
2. `pytest --maxfail=1`
3. 다음을 수동 점검:
   - `/api/upload` 응답에 `upload_token` 존재
   - 토큰 없이 파일 소켓 전송 시 에러 emit
   - `/api/search?limit=9999&offset=-1` clamp 동작
   - `/uploads` 캐시 헤더 정책 분기

## 7) PR/커밋 체크리스트

- [ ] 계약 변경이 README/문서에 반영되었는가
- [ ] 테스트 추가/수정이 동반되었는가
- [ ] 기존 테스트 전체 통과 여부 확인했는가
- [ ] 보안 관련 회귀(토큰 우회, 권한 우회) 케이스를 검증했는가

## 8) Claude 세션 프롬프트 템플릿(권장)

아래를 새 세션 첫 메시지로 사용:

```
Read `claude.md`, `README.md`, and `IMPLEMENTATION_AUDIT.md` first.
Then summarize:
1) current baseline (tests/contracts),
2) risks if we change this area,
3) exact files to edit,
and execute changes with verification (`pytest tests -q`, `pytest --maxfail=1`).
```

## 9) 2026-02-25 기준선 업데이트 (Full Remediation)

- 코드 기준선
  - 리스크 매핑 R-01~R-11 반영 완료
  - 추가 기능(옵션): OIDC, AV 스캔 큐, Redis state_store, 관리자 감사로그, 보존정책, 백업/복구 런북

- 새/변경 주요 파일
  - `app/state_store.py`
  - `app/upload_scan.py`
  - `app/oidc.py`
  - `app/models/admin_audit.py`
  - `app/legacy/models_monolith.py`
  - `scripts/backup_local.py`
  - `scripts/restore_local.py`
  - `scripts/verify_restore.py`
  - `docs/BACKUP_RUNBOOK.md`

- 공개 API 기준선
  - `GET /api/config`
  - `GET /api/upload/jobs/<job_id>`
  - `GET /api/auth/providers`
  - `GET /auth/oidc/login`
  - `GET /auth/oidc/callback`
  - `GET /api/rooms/<room_id>/admin-audit-logs?format=json|csv`

- 테스트 기준선
  - `pytest -q` => `71 passed`

- 작업 시 유의사항
  - 세션 무효화는 HTTP(`before_request`) + Socket(`connect`/핵심 이벤트) 모두 유지
  - 파일 메시지는 `upload_token` 검증 경로를 우회하지 않도록 유지
  - `state_store`는 Redis 장애 시 메모리 강등 동작을 유지

## 10) 2026-02-25 정합성 동기화 메모

- README/API 계약/감사 문서/리스크 문서 간 기준선 동기화 완료
- 테스트 기준선: `pytest -q` -> `71 passed`
- `.spec` 점검 결과 반영:
  - `app.state_store`, `app.upload_scan`, `app.oidc`, `app.models.admin_audit`
  - `redis`, `redis.asyncio`
  - `docs/BACKUP_RUNBOOK.md` 데이터 포함

### API 계약 고정값
- `GET /api/config`
- `POST /api/upload` + `GET /api/upload/jobs/<job_id>`
- `POST /api/polls/<poll_id>/vote` (`error`, `code`)
- `GET /api/auth/providers`, `GET /auth/oidc/login`, `GET /auth/oidc/callback`
- `GET /api/rooms/<room_id>/admin-audit-logs?format=json|csv`
