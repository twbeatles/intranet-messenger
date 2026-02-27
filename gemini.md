# GEMINI.md

프로젝트: `intranet-messenger-main`  
최종 업데이트: 2026-02-27

## 1) 문서 목표

새 세션에서 Gemini가 즉시 작업 가능한 수준으로 프로젝트 컨텍스트를 제공한다.  
특히 보안 계약, API 호환성, 테스트 기준선이 깨지지 않도록 가이드한다.

## 2) 시작 절차 (Session Bootstrap)

1. `README.md` 읽기  
2. `PROJECT_STRUCTURE_FEATURE_EXPANSION_ANALYSIS_2026-02-27.md` 읽기  
3. 본 문서(`gemini.md`) 기준으로 작업 계획 수립  
4. 변경 전 영향 파일/테스트 명시

## 3) 현재 상태 스냅샷

- 테스트 기준선:
  - `pytest tests -q` => `71 passed`
  - `pytest --maxfail=1` => `71 passed`
- 테스트 수집 안정화 완료:
  - `pytest.ini` (`testpaths = tests`, `norecursedirs = backup dist build`)
- 보안/계약 핵심 반영 완료:
  - `upload_token` 플로우 도입
  - `members` 표준 + `member_ids` 호환
  - `/api/search` limit/offset clamp
  - `/uploads` 인증 캐시 정책 강화

## 4) 절대 보존해야 할 계약

## 4.1 `POST /api/rooms`

- 표준: `members`
- 호환: `member_ids`
- 둘 다 전달 시 `members` 우선
- 멤버 ID는 정수/중복 제거/자기 자신 포함

## 4.2 파일 업로드/전송

- `POST /api/upload`:
  - `room_id` 필수
  - 응답: `upload_token` 포함
- `send_message` 소켓:
  - `file`/`image`는 `upload_token` 필수
  - 토큰 검증 실패 시 메시지 저장 금지 + 에러 emit
  - 클라이언트 `file_path`, `file_name` 신뢰 금지

## 4.3 검색

- `GET /api/search`
  - `limit`는 `1..200`으로 강제
  - `offset`은 `0` 미만 금지

## 4.4 Poll/Pin

- `create_poll` 반환은 `poll_id`
- pin 삭제는 `(success, error)` 구조분해로만 성공 판정

## 4.5 탈퇴 처리

- `polls.created_by`를 NULL로 두지 않음
- 재할당 우선순위: 관리자 > 일반 멤버
- 재할당 대상 없으면 poll 삭제

## 5) 보안 규칙

1. 권한 없는 경로 접근 방지 로직 제거 금지
2. 인증 리소스 캐시 완화 금지
   - 일반 파일: `private, no-store`
   - 프로필: `private, max-age=3600`
3. 업로드 토큰 우회 가능 코드(path 직접 신뢰) 재도입 금지

## 6) 구현 작업 포맷 (권장)

작업 시 항상 아래 순서 유지:

1. 변경 이유/영향 범위 명시
2. 파일 수정
3. 테스트 실행
4. 결과 요약(실패 시 원인 분리: 코드/테스트/문서)
5. README/감사문서 동기화 여부 확인

## 7) 권장 테스트 세트

- 전체:
  - `pytest tests -q`
  - `pytest --maxfail=1`
- 보안 회귀 우선:
  - `tests/test_socket_upload_token.py`
  - `tests/test_upload_tokens.py`
  - `tests/test_uploads_authz.py`
  - `tests/test_pins_delete_api.py`
  - `tests/test_search_limit_clamp.py`
  - `tests/test_rooms_member_ids_compat.py`

## 8) 문서 동기화 원칙

- 코드 계약 바뀌면 최소 다음 문서를 같이 수정:
  - `README.md`
  - `PROJECT_STRUCTURE_FEATURE_EXPANSION_ANALYSIS_2026-02-27.md`
  - `claude.md`
  - `gemini.md`
- 기존 내용 삭제 대신, "업데이트 섹션"을 추가해 이력 보존.

## 9) Gemini 세션 프롬프트 템플릿(권장)

새 세션 시작 시:

```
Read `gemini.md`, `claude.md`, `README.md`, and `PROJECT_STRUCTURE_FEATURE_EXPANSION_ANALYSIS_2026-02-27.md`.
Keep current security/API contracts intact.
When changing code, update docs and run:
1) pytest tests -q
2) pytest --maxfail=1
Then report changed files and test results.
```

## 10) 2026-02-25 정합성 동기화 메모

- README/API/구조 분석 문서 기준선 동기화 완료
- 테스트 기준선: `pytest -q` -> `71 passed`
- `.spec` 보강 반영:
  - 신규 모듈 hidden import: `app.state_store`, `app.upload_scan`, `app.oidc`, `app.models.admin_audit`
  - Redis 동적 import: `redis`, `redis.asyncio`
  - 런북 데이터 포함: `docs/BACKUP_RUNBOOK.md`

## 11) 2026-02-27 구조 리스크 개선 메모

- 실행 기준 경로: `server.py` 단일화, `messenger_server.py`는 deprecated shim
- 프론트 업로드 분리: `static/js/message-upload.js` 추가
- 세션 저장소: Flask-Session `cachelib` 백엔드 사용
- 인코딩 안정성: 서버 진입점 UTF-8 stdio 설정 적용
