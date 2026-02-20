# 기능 구현 리스크 정밀 점검 보고서

- 작성일: 2026-02-20
- 대상 프로젝트: `d:\google antigravity\intranet-messenger-main`
- 기준 문서: `README.md`
- 비고: `claude.md`는 저장소 내에서 확인되지 않아 본 점검에서 제외
- 업데이트(반영 완료): 2026-02-20

## 0. 반영 상태 요약 (Post-Fix)

- 본 문서의 Critical/High/Medium 항목은 코드베이스에 반영 완료.
- `README.md`와 실제 구현의 폐쇄망/업로드/API 호환 정책 정합성을 재동기화 완료.
- 테스트 재검증 결과:
  - `pytest tests -q` → **64 passed**
  - `pytest --maxfail=1` → **64 passed** (기본 수집 오류 해소)

### 핵심 반영 체크리스트

- [x] C-01 Poll 생성 응답 계약 정합화
  - `app/models/polls.py` 반환 계약을 `poll_id`로 고정
  - `app/routes.py`에서 `poll_id` 조회 후 `poll` 응답 구성
- [x] C-02 Pin 삭제 tuple truthy 오판 제거
  - `app/routes.py`에서 `success, error` 구조분해 판정
  - `app/models/messages.py` room mismatch/미존재 오류 메시지 구분
- [x] C-03 파일 전송 보안(`upload_token`) 도입
  - 신규: `app/upload_tokens.py`
  - `/api/upload` 토큰 발급 + 소켓 `send_message` 토큰 필수 검증
  - 클라이언트 직접 `file_path` 신뢰 경로 제거
- [x] H-01 `/uploads` 캐시 정책 수정
  - 일반 파일 `private, no-store`
  - 프로필 이미지 `private, max-age=3600`
- [x] H-02 탈퇴 시 polls.created_by NULL 충돌 위험 제거
  - `app/models/users.py`에서 poll 소유자 재할당(관리자 우선) 또는 삭제
- [x] H-03 폐쇄망 주장과 외부 폰트 호출 불일치 해소
  - `templates/index.html` Google Fonts 링크 제거
- [x] H-04 업로드 제한값 정합화
  - 프론트 드래그앤드롭 제한 10MB → 16MB 반영
- [x] M-01~M-03 테스트/문서/구현 드리프트 정리
  - `pytest.ini` 추가로 기본 `pytest` 수집 안정화
  - 노후 테스트 재작성 및 보안 회귀 테스트 추가

## 1. 점검 범위/방법

- 코드 점검 범위
- `app/routes.py`
- `app/sockets.py`
- `app/models/*.py`
- `static/js/*.js`
- `templates/index.html`
- `README.md`

- 실행 검증 범위
- `pytest tests -q` 실행
- `pytest --maxfail=1` 실행

- 점검 기준
- 보안(권한 검증, 민감 리소스 접근, 캐시 정책)
- API 계약 일관성(응답 타입/필드, 파라미터 호환성)
- 문서-구현 정합성(README 주장 vs 실제 코드)
- 테스트 신뢰도(실패 원인 분류: 코드 버그/테스트 노후화/문서 불일치)

## 2. 핵심 요약 (Top 5 위험)

1. `POST /api/rooms/<room_id>/polls`의 응답 계약 결함으로 `poll`이 `None`이 될 수 있음.
2. `DELETE /api/rooms/<room_id>/pins/<pin_id>`가 실패 상황에서도 성공 응답으로 오판될 수 있음.
3. 소켓 `send_message`에서 `file_path`를 신뢰하여 파일 권한 우회 시나리오가 가능함.
4. 인증이 필요한 `/uploads` 응답에 `Cache-Control: public`이 설정되어 민감 파일 캐시 노출 위험이 있음.
5. README의 폐쇄망 100% 주장과 실제 `Google Fonts` 외부 호출이 상충함.

## 3. 상세 이슈 목록

### C-01 (Critical) Poll 생성 응답 계약 불일치

- 요약: 라우트는 `create_poll` 반환값을 `poll_id`로 가정하지만, 실제 모델은 `poll` 객체를 반환함.
- 근거
- `app/models/polls.py:28` (`return get_poll(poll_id)`)
- `app/routes.py:764` (`poll_id = create_poll(...)`)
- `app/routes.py:766` (`poll = get_poll(poll_id)`)
- 영향
- `get_poll()`에 dict가 전달되어 내부 쿼리 바인딩 오류 발생 가능.
- API 응답의 `poll`이 `None`이 되어 클라이언트가 `poll.id` 접근 시 예외.
- 관련 실패 테스트
- `tests/test_polls.py`의 `test_vote_poll`, `test_close_poll`
- 재현
- `pytest tests/test_polls.py -q`
- 개선안
- `create_poll` 반환 타입을 `poll_id`로 고정하거나, 라우트에서 dict 반환을 직접 처리하도록 계약을 통일.
- 타입 힌트와 단위테스트로 계약을 명시적으로 고정.
- 우선순위: 즉시 수정

### C-02 (Critical) Pin 삭제 성공 판정 로직 오류 (Tuple truthy 오판)

- 요약: `unpin_message()`가 `(False, "...")`를 반환해도 라우트 `if` 조건에서 truthy로 평가되어 성공 처리될 수 있음.
- 근거
- `app/routes.py:711`
- `app/models/messages.py:564` (`return False, "공지를 찾을 수 없습니다."`)
- `app/models/messages.py:568` (`return True, None`)
- 영향
- 존재하지 않는 pin 삭제 요청이 `{"success": true}`로 잘못 응답될 수 있음.
- 클라이언트 상태와 DB 상태 불일치 발생 가능.
- 재현
- 로그인 후 존재하지 않는 `pin_id`로 `DELETE /api/rooms/<room_id>/pins/<pin_id>` 호출.
- 개선안
- 라우트에서 `success, err = unpin_message(...)` 형태로 구조분해하여 bool만 판정.
- 실패 시 404/400 등 의미 있는 상태코드 반환.
- 우선순위: 즉시 수정

### C-03 (Critical) 소켓 `send_message`의 `file_path` 신뢰에 따른 권한 우회 가능성

- 요약: 소켓 이벤트에서 전달된 `file_path`가 서버측 업로드 세션과 강결합 검증 없이 DB에 기록됨.
- 근거
- `app/sockets.py:266` (`file_path = data.get('file_path')`)
- `app/sockets.py:283`~`app/sockets.py:297` (해당 path로 메시지/room_files 기록)
- `app/routes.py:508` (다운로드 권한 판별이 `room_files.file_path` 조회에 의존)
- 영향
- 악의적 클라이언트가 다른 파일 경로를 메시지에 연결해 권한 검증 흐름을 오염시킬 가능성.
- 다운로드 접근제어가 “파일 실체 + 업로드 세션 연계”가 아닌 “DB 레코드 존재”에 치우침.
- 재현 시나리오
- 소켓 클라이언트로 `send_message(type='file', file_path='<임의경로>', file_name='...')` 이벤트 전송.
- 이후 `/uploads/<해당경로>` 접근 시 room_files 기반 권한 로직 확인.
- 개선안
- 업로드 완료 시 서버가 발급한 `upload_token` 또는 임시 파일 ID만 소켓에서 수용.
- `send_message`에서 `file_path` 직접 입력 금지, 서버 측 화이트리스트 테이블과 매칭.
- `room_files` 삽입 전 파일 존재/소유/업로드 세션 검증 강제.
- 우선순위: 즉시 수정

### H-01 (High) 인증 파일 응답에 `Cache-Control: public`

- 요약: 인증된 사용자에게만 제공되는 `/uploads` 응답에 장기 public 캐시가 설정됨.
- 근거
- `app/routes.py:537` (`Cache-Control: public, max-age=31536000`)
- `app/routes.py:521` (인증 사용자 room membership로 접근 제어)
- 영향
- 프록시/공유 캐시 환경에서 민감 파일 보존/재사용 위험.
- 로그아웃 이후에도 캐시 재노출 가능성.
- 개선안
- `private, no-store` 또는 최소 `private, max-age=0, must-revalidate`로 전환.
- 프로필 이미지와 일반 파일의 캐시 정책 분리 적용.
- 우선순위: 단기 수정

### H-02 (High) 회원탈퇴 시 `polls.created_by NULL` 업데이트와 스키마 충돌 가능성

- 요약: 탈퇴 처리에서 `created_by = NULL` 업데이트를 수행하나, 테이블 정의는 `NOT NULL`.
- 근거
- `app/models/users.py:293`
- `app/models/base.py:240` (`created_by INTEGER NOT NULL`)
- 영향
- DB 무결성/트랜잭션 실패 가능성.
- 사용자 탈퇴 시 롤백으로 인해 데이터 정리 실패 가능.
- 개선안
- `polls.created_by`를 nullable로 마이그레이션하거나, “탈퇴 사용자 대체 계정” 전략 적용.
- FK 정책을 `ON DELETE SET NULL`로 바꾸려면 컬럼 nullable 전환이 선행되어야 함.
- 우선순위: 단기 수정

### H-03 (High) README 폐쇄망 주장과 외부 리소스 사용 불일치

- 요약: README는 외부 CDN 의존성 0%를 명시하나, 템플릿에서 Google Fonts를 직접 호출.
- 근거
- `README.md:718` (외부 CDN 의존성 0%)
- `templates/index.html:10`
- `templates/index.html:12`
- 영향
- 폐쇄망 환경에서 폰트 로딩 실패.
- 문서 신뢰성 저하 및 운영 환경 예측 실패.
- 개선안
- 폰트를 로컬 번들로 전환하거나 README에 외부 의존성을 명시.
- 우선순위: 단기 수정

### H-04 (High) 파일 업로드 제한값 불일치 (서버 16MB vs 프론트 10MB)

- 요약: 서버/README는 16MB인데 프론트 드래그앤드롭 경로는 10MB로 차단.
- 근거
- `config.py:30` (16MB)
- `app/routes.py:440` (16MB 검사)
- `README.md:50` (최대 16MB)
- `static/js/messages.js:1263` (10MB 제한)
- 영향
- 사용자 관점의 기능 불일치(문서대로 16MB 업로드 불가).
- 지원/운영 문의 증가.
- 개선안
- 프론트 제한을 서버 설정값과 동기화(예: `/api/config` 제공 또는 템플릿 주입).
- 우선순위: 단기 수정

### M-01 (Medium) 테스트/문서/구현 계약 드리프트

- 요약: `pytest tests -q` 결과 53개 중 10개 실패.
- 근거
- 실측 결과: `43 passed, 10 failed`
- 대표 실패 유형
- 코드 버그: Poll API 반환 계약, Pin 삭제 판정.
- 테스트 노후화: `member_ids` 사용(`tests/test_v432_features.py:88`) vs 실제 API는 `members` 사용(`app/routes.py:150`).
- 정책 변경 미반영: 반응 API 기대값(200/404)과 실제 권한응답(403) 차이.
- 개선안
- 실패 테스트를 원인별 라벨링(`bug`, `test-obsolete`, `contract-drift`).
- 릴리즈 전 “문서-테스트-API 계약 검증” 체크리스트 추가.
- 우선순위: 단기

### M-02 (Medium) 사용자명 정책(3자 이상)과 테스트 데이터 충돌

- 요약: 일부 테스트가 `u1`, `s1`, `f1` 등 2자 아이디를 사용.
- 근거
- 정책: `app/utils.py:127` (3~20자)
- 테스트 예시: `tests/test_messages_api_params.py:16`, `tests/test_uploads_authz.py:31`, `tests/test_search_excludes_encrypted.py:14`
- 영향
- 로그인/회원가입 단계에서 선행 실패가 연쇄적으로 다른 테스트를 오염.
- 개선안
- 테스트 사용자명 규칙 통일(예: 최소 3자).
- 픽스처 공통 헬퍼에서 사용자명 정책을 강제.
- 우선순위: 단기

### M-03 (Medium) 기본 `pytest` 실행 시 backup 산출물 수집 충돌

- 요약: 기본 `pytest --maxfail=1` 실행에서 `backup/**/test_output.txt` 수집 중 UnicodeDecodeError 발생.
- 근거
- `README.md:624`는 `pytest tests -v`를 안내하나, 일반 `pytest` 실행 시 오류 가능.
- 실제 오류 파일 예: `backup/cleanup_v434_20260123/test_output.txt`
- 영향
- 로컬/CI에서 표준 `pytest` 명령 사용 시 혼란 발생.
- 개선안
- `pytest.ini`에 `testpaths = tests` 설정 또는 `norecursedirs = backup dist` 설정.
- 우선순위: 단기

## 4. 공개 API/인터페이스 관련 핵심 변경 제안

### A-01 `POST /api/rooms/<room_id>/polls` 응답 계약 정합화

- 제안
- 옵션 1: `create_poll()`이 `poll_id: int` 반환.
- 옵션 2: 라우트에서 `create_poll()` 반환값을 `poll`로 직접 수용.
- 권장: 옵션 1 + 타입 고정(서버 내부 계층 분리 명확).

### A-02 `DELETE /api/rooms/<room_id>/pins/<pin_id>` 성공 판정 구조화

- 제안
- 모델 반환 타입을 `tuple[bool, str|None]`로 고정.
- 라우트에서 구조분해 후 상태코드 매핑(404/403/500).

### A-03 `POST /api/rooms` 입력 호환성 명확화

- 제안
- `members`를 표준으로 고정하고 `member_ids`는 호환 alias로 수용 여부를 명확히 결정.
- README와 테스트에서 단일 표준 키로 정렬.

### A-04 `/api/search`의 `limit` 상한 정책 강제

- 제안
- `GET /api/search`에서 `limit` 상한(예: 200) 및 최소값(예: 1) 강제.
- 너무 큰 `limit` 요청 시 clamp 후 응답 메타에 실제 적용값 포함 검토.

## 5. 테스트 및 검증 시나리오

### 재현 명령

- `pytest tests -q`
- 실측 결과: `53 collected`, `43 passed`, `10 failed`

- `pytest --maxfail=1`
- 실측 결과: `backup/.../test_output.txt` 수집 중 `UnicodeDecodeError`로 중단

### 결함별 재현 시나리오

- Poll 생성 결함
- `POST /api/rooms/<room_id>/polls` 호출 후 응답의 `poll`이 null인지 확인.
- 직후 클라이언트에서 `poll.id` 접근 시 예외 여부 확인.

- Pin 삭제 결함
- 존재하지 않는 `pin_id`에 `DELETE` 호출.
- 응답이 실패가 아닌 성공으로 오는지 확인.

- 파일 권한 우회 시나리오
- 인증된 소켓 클라이언트로 `send_message`에 임의 `file_path` 전송.
- `room_files` 기록 및 `/uploads/<path>` 접근 제어 결과 확인.

- 탈퇴 트랜잭션 충돌 시나리오
- poll 생성자 계정으로 데이터 생성 후 `/api/me` 삭제 호출.
- `polls.created_by` 업데이트가 스키마 제약과 충돌하는지 DB 에러 로그 확인.

### 회귀 기준

- 실패 테스트를 다음 3개 라벨로 분류하고 이력 관리.
- 코드 버그
- 테스트 노후화
- 문서 불일치

## 6. 추가 구현 제안 (보안/성능/운영/테스트 체계)

### 보안

- 파일 업로드 플로우에 `upload_token` 기반 서버 검증 도입.
- `/uploads` 캐시 정책을 인증 리소스에 맞게 `private/no-store`로 재정의.
- `send_message`에서 `file_path`를 클라이언트 입력값으로 받지 않도록 인터페이스 축소.

### 성능

- `/api/search`의 `limit` 상한 강제로 쿼리 폭주 완화.
- 메시지/파일 조회 API에 공통 페이지네이션 정책 도입.

### 운영

- README의 폐쇄망 항목과 실제 배포 아티팩트 정합성 자동 점검.
- 버전 표기 통합(`config.VERSION`, `README 헤더`, 변경이력 섹션) 체크 자동화.

### 테스트 체계

- `pytest.ini` 추가로 수집 경로를 `tests/`로 고정.
- 실패 테스트 정리 시 “실제 계약” 기준으로 기대값 갱신.
- 노후 테스트(실DB 의존/가정 기반)를 fixture 기반 통합테스트로 재작성.

## 7. 실행 로드맵

### 즉시 (0~1일)

- C-01 Poll 생성 계약 버그 수정.
- C-02 Pin 삭제 판정 버그 수정.
- C-03 `send_message` 파일 경로 검증 가드 추가.

### 단기 (1~3일)

- H-01 `/uploads` 캐시 정책 조정.
- H-02 탈퇴 로직/스키마 정합성 정리.
- H-03 README 폐쇄망 항목 정합화.
- H-04 파일 업로드 제한값 단일화.
- M-03 `pytest` 수집 경로 고정.

### 중기 (1~2주)

- API 계약 명세 문서화(OpenAPI 또는 내부 스펙 문서).
- 테스트 분류 체계 정착(`bug`, `obsolete`, `contract` 라벨 운영).
- 배포 전 계약/문서 정합성 자동 점검 파이프라인 도입.

## 8. 부록: 테스트 실행 결과 요약

- 실행 일시: 2026-02-20
- 명령 1: `pytest tests -q`
- 결과: 53개 중 10개 실패, 43개 통과

- 주요 실패 테스트
- `tests/test_create_room.py::TestCreateRoom::test_create_room_logic`
- `tests/test_messages_api_params.py::test_get_messages_limit_and_include_meta`
- `tests/test_polls.py::test_vote_poll`
- `tests/test_polls.py::test_close_poll`
- `tests/test_rooms_api_payload.py::test_rooms_payload_members_default_excluded_and_preview_present`
- `tests/test_search_excludes_encrypted.py::test_search_excludes_encrypted_text_messages`
- `tests/test_search_excludes_encrypted.py::test_file_only_search_uses_file_name`
- `tests/test_uploads_authz.py::test_uploads_room_member_only`
- `tests/test_uploads_authz.py::test_uploads_profiles_allowed_for_logged_in`
- `tests/test_v432_features.py::test_reaction_api`

- 명령 2: `pytest --maxfail=1`
- 결과: 테스트 수집 단계에서 `backup/.../test_output.txt` 디코딩 오류로 중단

## 9. 재검증 결과 (Patch 적용 후)

- 실행 일시: 2026-02-20 (동일일 재검증)
- 명령 1: `pytest tests -q`
- 결과: `64 passed`

- 명령 2: `pytest --maxfail=1`
- 결과: `64 passed`

- 비고
- 8장은 "점검 당시 기준선(Baseline)"을 보존한 기록입니다.
- 9장은 실제 코드 반영 이후의 최신 회귀 검증 결과입니다.
