# Project Audit

감사 일자: 2026-06-25  
감사 범위: 기능 구현 관점 (보안·가시성·비동기·상태 흐름·테스트·문서 정합성)  
분석 방법: `README.md`, `CLAUDE.md` 선독 → CodeGraph MCP 구조/호출 관계 분석 → pytest·`npm run check:js`·pyright 보조 검증

## Remediation Status (2026-06-25)

| 항목 | 상태 |
|------|------|
| §3.1 초대 트랜잭션화 | ✅ `invite_members_with_key_rotation` |
| §3.2 Redis 스케일링 가이드/경고 | ✅ `REQUIRE_REDIS_STATE`, worker warnings |
| §3.3 experimental openRoom race | ✅ `currentOpenRequestId` |
| §3.4 room_security_updated UI | ✅ `refreshPendingMessageDecryption` |
| §3.5 socket relay rate limit | ✅ room_members + poll_* |
| §3.6 E2E 문서 정정 | ✅ README/CLAUDE/gemini |
| §3.7 테스트 환경 | ✅ encoding exclude, OIDC JWKS HTTP |
| §3.8 불필요 rotate rollback | ✅ 트랜잭션 rollback + 테스트 |
| §6 테스트 보강 | ✅ `tests/test_project_audit_remediation.py` |
| 레거시 격리 | ✅ `app/legacy/README.md` |
| Playwright E2E | ⏸️ 정적 JS 계약 테스트로 대체 (경량) |

---

## 1. Executive Summary

이 프로젝트는 Flask + Socket.IO 기반 사내 메신저로, 2026-04-27 기준 **멤버십 기반 방 키 로테이션·메시지 가시성·서버 권위 소켓 이벤트**가 핵심 계약으로 잘 정리되어 있고, 관련 회귀 테스트도 다수 존재합니다. CodeGraph와 pytest 결과를 종합하면 **핵심 보안 계약 대부분은 구현·테스트로 뒷받침**되고 있습니다.

다만 다음 영역은 실제 운영에서 기능 장애나 보안 경계 약화로 이어질 수 있습니다.

| 영역 | 요약 |
|------|------|
| **동시성** | 초대(`invite_member`) 시 키 로테이션과 멤버 추가가 단일 트랜잭션으로 묶이지 않아, 동시 초대 시 `joined_key_version` 불일치 가능 |
| **수평 확장** | 기본 `StateStore` in-memory + `MESSAGE_QUEUE=None` → 다중 프로세스/다중 인스턴스에서 업로드 토큰·레이트리밋·presence 불일치 |
| **프론트엔드 이중 경로** | 운영 UI(`static/js/features/`)는 방 전환 race guard가 있으나, experimental 모듈은 미적용 |
| **테스트 신뢰도** | 전체 107개 중 3개 실패(인코딩 hygiene, OIDC 2건). git 미사용 환경에서 hygiene 테스트가 `node_modules`까지 스캔 |
| **문서 vs 구현** | README의 “E2E 암호화” 표현은 서버가 평문 키를 보유·전달하는 실제 구조와 차이 있음 |

**감사 시점 위험도: Medium~High** → **2026-06-25 remediation 적용 후: Low~Medium** (단일 프로세스), **Medium** (Redis 없이 다중 워커)

---

## 2. Project Understanding

### 2.1 프로젝트 목적

- 사내용 실시간 채팅(방/파일/핀/리액션/투표/검색)
- 선택적 PyInstaller 데스크톱 패키징
- 멤버십 변경 시 방 암호화 키 로테이션으로 **초대 이전 히스토리 차단**
- 로컬 SQLite + 파일 업로드 기반 단일 서버 우선 설계

### 2.2 아키텍처 (CodeGraph 기준)

```
server.py / app/server_launcher.py
  └─ app.factory.build_app()
       ├─ app/bootstrap/runtime.py      # Flask 설정, StateStore, 경로
       ├─ app/bootstrap/socketio_config.py
       ├─ app/routes → app/http/*       # REST API
       ├─ app/sockets → app/socket_events/*
       │    ├─ connection.py           # 연결/세션
       │    ├─ messages.py             # send/edit/delete/reaction
       │    ├─ rooms.py                # room_members_updated relay
       │    ├─ features.py             # pin/poll relay
       │    └─ presence.py             # typing, profile_updated
       ├─ app/models/*                  # DB·도메인 (rooms, messages, users…)
       ├─ app/services/socket_broadcasts.py  # HTTP→Socket 권위 이벤트
       └─ app/bootstrap/workers.py      # maintenance, upload scan

Frontend (templates/partials/scripts.html)
  static/js/core|services|features|bootstrap → compatibility shims (rooms.js, messages.js…)
```

### 2.3 주요 실행 흐름

**A. 앱 기동**  
`server_launcher.run_server()` → `create_app()` → Socket.IO + Control API(127.0.0.1) + maintenance worker

**B. 메시지 전송**  
클라이언트 `send_message` → `app/socket_events/messages.py`  
→ 멤버십·rate limit·(파일 시) `consume_upload_token` → `create_message` → `new_message` broadcast

**C. 멤버십 변경 / 키 로테이션**  
`POST /api/rooms/<id>/members|leave|kick`, 계정 삭제  
→ `rotate_room_key()` (invite/leave/kick/delete 잔존 멤버)  
→ `emit_room_security_updated` (사용자별 keyring payload)  
→ 프론트 `handleRoomSecurityUpdated`가 in-memory 키 갱신

**D. 메시지 가시성**  
`messages.key_version >= room_members.joined_key_version`  
`can_user_see_message`, `get_room_messages`, 검색, 파일/핀/리액션/답장/다운로드 경로에서 공유

**E. 업로드**  
`POST /api/upload` → `issue_upload_token` (StateStore, TTL 300s)  
→ socket `send_message`에서 1회성 소비 → maintenance worker가 미참조 orphan 파일 purge

### 2.4 CodeGraph blast radius (변경 시 영향 큰 심볼)

| 심볼 | 위치 | 호출자(요약) | 테스트 커버리지(CodeGraph) |
|------|------|--------------|---------------------------|
| `rotate_room_key` | `app/models/rooms.py` | `app/http/rooms.py`, `app/models/users.py` | 직접 단위 테스트 없음(통합 테스트는 존재) |
| `can_user_see_message` | `app/models/messages.py` | HTTP/socket/upload 7+ 경로 | 직접 단위 테스트 없음 |
| `consume_upload_token` | `app/upload_tokens.py` | `app/socket_events/messages.py` | `tests/test_upload_tokens.py` |
| `sync_user_room_membership` | `app/services/socket_broadcasts.py` | auth/rooms HTTP | 직접 테스트 없음 |
| `openRoom` | `static/js/features/rooms/runtime.js` | chat/rooms UI | 프론트 테스트 없음 |

### 2.5 검증 실행 결과 (2026-06-25)

| 명령 | 결과 |
|------|------|
| `pytest tests -q` | **104 passed, 3 failed** |
| `npm run check:js` | **pass** |
| `pyright app gui` | **0 errors** |

실패 테스트:
- `tests/test_encoding_hygiene.py::test_tracked_text_files_do_not_contain_mojibake` — `node_modules/typescript/...` 스캔
- `tests/test_feature_risk_review_plan.py` — OIDC JWKS `file://` 스킴 미지원 (PyJWT)

---

## 3. High-Risk Issues

### 3.1 초대 API의 키 로테이션·멤버 추가 비원자성

* **위치:** `app/http/rooms.py` — `invite_member()`; `app/models/rooms.py` — `rotate_room_key()`, `add_room_member()`
* **문제:** 초대 시 `rotate_room_key()`가 **즉시 commit**된 뒤, 루프에서 `add_room_member()`를 별도 commit으로 수행합니다. `leave_room_db()`는 `BEGIN IMMEDIATE`를 쓰지만 초대 경로는 트랜잭션 경계가 없습니다.
* **영향:** 동시 초대 요청 시 키 버전이 연속 증가하면서 일부 초대 대상에게 **낮은 `joined_key_version`**이 기록될 수 있습니다. 의도보다 넓은 과거 메시지 가시성(키 버전 경계 약화) 가능.
* **근거:**

```174:181:app/http/rooms.py
    rotation = rotate_room_key(room_id)
    if not rotation:
        return jsonify({"error": "방 보안 갱신에 실패했습니다."}), 500

    added_user_ids: list[int] = []
    for invitee_id in candidate_user_ids:
        if add_room_member(room_id, invitee_id, joined_key_version=rotation["key_version"]):
```

```205:227:app/models/rooms.py
def rotate_room_key(room_id: int, conn=None):
    ...
    if own_conn:
        conn.commit()
    return {'room_id': room_id, 'key_version': next_version, 'encryption_key': raw_key}
```

* **권장 수정 방향:** `BEGIN IMMEDIATE` 트랜잭션 안에서 rotate + member insert + (필요 시) 감사 로그를 한 번에 commit. 동시 초대는 row-level 직렬화 또는 idempotency key 검토.
* **우선순위:** **Critical**

---

### 3.2 다중 프로세스 환경에서 StateStore·Socket.IO 단일 노드 가정

* **위치:** `app/state_store.py`, `config.py` (`MESSAGE_QUEUE`, `STATE_STORE_REDIS_URL`), `app/bootstrap/runtime.py`
* **문제:** Redis 미설정 시 upload token, socket rate limit, presence 카운터가 **프로세스 로컬 메모리**에 저장됩니다. `MESSAGE_QUEUE=None`이면 Socket.IO도 단일 프로세스 브로드캐스트를 가정합니다.
* **영향:** gevent worker 다중화, PyInstaller + 별도 프로세스, reverse proxy 뒤 다중 인스턴스 시 **토큰 검증 실패, 중복 메시지 처리, presence 오류, 이벤트 미전달**.
* **근거:** `config.py` 기본값 `MESSAGE_QUEUE = None`, `STATE_STORE_REDIS_URL` 빈 문자열 시 in-memory fallback (`app/state_store.py` 102-123행).
* **권장 수정 방향:** 다중 워커/인스턴스 배포 시 Redis(`STATE_STORE_REDIS_URL`, `MESSAGE_QUEUE`) 필수화 및 기동 시 경고/실패-fast. README에 운영 조건 명시.
* **우선순위:** **High**

---

### 3.3 Experimental 프론트엔드의 방 전환 race 미방어

* **위치:** `static/js/experimental/modules/chat.js` — `openRoom()`
* **문제:** 운영 경로(`static/js/features/rooms/runtime.js`)는 `currentOpenRequestId`로 stale 응답을 무시하지만, experimental 모듈은 **요청 ID 가드 없이** `currentRoom`과 메시지를 즉시 갱신합니다.
* **영향:** 빠른 방 전환 시 **이전 방 메시지/키가 현재 방 UI에 잠깐 또는 지속적으로 표시**될 수 있음. 잘못된 `message_read`, 캐시 오염 가능.
* **근거:**

```265:363:static/js/features/rooms/runtime.js
        var requestId = ++currentOpenRequestId;
        ...
            if (requestId !== currentOpenRequestId) {
                if (window.DEBUG) console.log('Ignoring stale openRoom response');
                return;
            }
```

```9:44:static/js/experimental/modules/chat.js
export async function openRoom(room) {
    ...
    state.currentRoom = room;
    ...
    const result = await RoomAPI.getMessages(room.id);
    state.currentRoomKey = result.encryption_key;
```

* **권장 수정 방향:** experimental 경로에 동일한 request token 패턴 적용, 또는 experimental을 비활성/제거하고 단일 런타임 유지.
* **우선순위:** **High** (experimental 경로를 실제로 로드하는 배포에서만; 기본 `scripts.html`은 features 경로 사용)

---

### 3.4 `room_security_updated` 수신 후 UI 복호화 재시도 없음

* **위치:** `static/js/services/socket/runtime.js` — `handleRoomSecurityUpdated()`
* **문제:** 키 갱신 시 `currentRoomKey`/`currentRoomKeys`만 갱신하고, 이미 렌더된 **lazy decrypt 대기 메시지 재처리나 메시지 리로드가 없음**.
* **영향:** 키 로테이션 직후 화면에 `[암호화된 메시지]` placeholder가 남거나, 신규 키로 보낸 메시지 복호화가 지연될 수 있음(스크롤/재입장 전까지).
* **근거:**

```844:851:static/js/services/socket/runtime.js
function handleRoomSecurityUpdated(data) {
    if (!data || !data.room_id) return;
    if (currentRoom && currentRoom.id === data.room_id) {
        currentRoomKey = data.encryption_key || currentRoomKey;
        currentRoomKeys = data.encryption_keys || currentRoomKeys || {};
        currentRoom.key_version = data.key_version || currentRoom.key_version;
    }
}
```

* **권장 수정 방향:** 키 갱신 후 `decryptPendingInMessageEl` 일괄 실행 또는 현재 방 메시지 부분 리렌더.
* **우선순위:** **Medium**

---

### 3.5 클라이언트 트리거 소켓 relay 이벤트의 DoS/스팸 여지

* **위치:** `app/socket_events/features.py` (`pin_updated`, `poll_created`, `poll_updated`), `app/socket_events/rooms.py` (`room_members_updated`)
* **문제:** 방 멤버가 소켓 emit → 서버 relay 패턴입니다. `pin_updated`만 rate limit이 있고, `room_members_updated`·poll relay는 **멤버십 검사 외 제한이 약함**.
* **영향:** 악의적/버그 클라이언트가 방 전체에 불필요한 refresh 이벤트를 유발 → 핀/투표/멤버 UI 반복 로드, 서버·클라이언트 부하.
* **근거:** `tests/test_feature_risk_review_plan.py`는 `pin_updated` rate limit을 검증하지만, `room_members_updated` 멤버 relay 스팸 테스트는 없음. `reaction_updated`/`poll_updated`는 DB canonical payload로 위조 방지됨(양호).
* **권장 수정 방향:** relay 이벤트는 HTTP 성공 후 **서버만 emit**하도록 점진 통일하거나, 모든 relay에 per-user rate limit 적용.
* **우선순위:** **Medium**

---

### 3.6 README “E2E 암호화”와 실제 키 관리 모델 불일치

* **위치:** `README.md`; `app/models/rooms.py` — `get_room_security_bundle()`; `app/http/messages.py` — `get_messages()`
* **문제:** 서버가 방 키를 DB에 저장하고 API/socket으로 **평문 키·keyring을 클라이언트에 전달**합니다. 진정한 E2E(서버가 평문을 모름)가 아닙니다.
* **영향:** 문서 기대치와 달리 **서버/DB 유출 시 메시지 복호화 가능**. 보안 검토·컴플라이언스 설명 오류.
* **근거:** `get_room_security_bundle`이 `encryption_key`, `encryption_keys` 반환; README “end-to-end message encryption support”.
* **권장 수정 방향:** 문서를 “전송 구간 TLS + 서버 관리형 방 키 기반 클라이언트 암호화”로 정정. E2E 목표 시 키를 서버 밖에서만 유도하도록 설계 변경(별도 프로젝트).
* **우선순위:** **Medium** (기능 버그라기보다 계약/기대치 문제)

---

### 3.7 테스트 스위트 환경 취약성

* **위치:** `tests/test_encoding_hygiene.py`; `tests/test_feature_risk_review_plan.py` (OIDC)
* **문제:**
  - git 미사용 시 `git ls-files` 실패 → repo 전체 `rglob`으로 **`node_modules`까지 스캔**하여 false positive
  - OIDC 테스트가 `file://` JWKS URI 사용 → 현재 PyJWT에서 실패
* **영향:** CI/로컬 검증 신뢰도 저하, 회귀 놓침.
* **근거:** 2026-06-25 pytest 3 failures; workspace가 git repo가 아님.
* **권장 수정 방향:** hygiene 스캔에 `node_modules`, `.codegraph`, `uploads` 등 exclude; OIDC 테스트는 mock JWKS HTTP 서버 사용.
* **우선순위:** **Medium**

---

### 3.8 초대 실패 시 불필요한 키 로테이션

* **위치:** `app/http/rooms.py` — `invite_member()`
* **문제:** `candidate_user_ids`가 있으면 무조건 rotate 후, `add_room_member`가 전부 실패해도(이론상 드묾) 이미 키는 증가합니다.
* **영향:** 잔존 멤버에게 **의미 없는 키 로테이션** → 클라이언트 keyring 갱신 부담, 감사/지원 혼란.
* **근거:** 174-187행 rotate 선행, `added_user_ids` 빈 경우 183-187에서 security emit만 수행.
* **권장 수정 방향:** 멤버 추가 확정 후 rotate, 또는 트랜잭션 롤백.
* **우선순위:** **Low~Medium**

---

## 4. Potential Functional Gaps

아래 항목 중 **(추정)** 표시는 코드에서 직접 재현하지 않았거나 요구사항 문맥이 불명확한 경우입니다.

### 4.1 확인된 갭

| 항목 | 설명 |
|------|------|
| 동시 초대 통합 테스트 부재 | leave/kick/invite 가시성 테스트는 있으나 **병렬 초대** 시나리오 없음 |
| 프론트엔드 자동화 테스트 부재 | `openRoom` stale guard, `handleRoomSecurityUpdated` 등 JS 핵심 로직은 eslint/tsc만 존재 |
| `handleRoomSecurityUpdated` 후 복호화 갱신 | §3.4 — 키 수신 후 UI 동기화 미완 |
| 다중 인스턴스 운영 가이드 | Redis/Message queue 설정은 config에 주석 수준 — **필수 조건이 강제되지 않음 (추정: 운영 문서 갭)** |

### 4.2 설계상 의도이나 문서화 필요

| 항목 | 설명 |
|------|------|
| `pin_updated` 클라이언트 relay | HTTP 후 클라이언트가 refresh 트리거 — `tests/test_feature_risk_review_plan.py`로 의도 확인됨. 다만 README의 “server-authoritative” 범위에 포함 여부 불명확 |
| `room_name_updated` 클라이언트 emit | 서버 핸들러 없음 → DB 변조 없음(테스트 확인). 다른 클라이언트에게 forged 이벤트 전달도 없음 — **문서는 “변조 불가”로 정확하나 “클라이언트 emit 무시” 표현이 더 명확 (추정)** |
| `editRoomName` 로컬 optimistic UI | HTTP 성공 시 로컬 이름 즉시 반영(`static/js/features/rooms/runtime.js`). socket 이벤트와 이중 경로 — 단일 사용자 UX는 양호, 다중 탭 간 불일치 가능 **(추정)** |

### 4.3 추가 기능 가능성 (추정)

| 항목 | 이유 |
|------|------|
| 초대/강퇴 **진행 중** UI 락 | `isOpeningRoom`은 있으나 초대 API in-flight 중 중복 클릭 방지는 제한적 **(추정)** |
| 업로드 AV 스캔 실패 시 사용자 복구 UX | quarantine/scan job 경로 존재 — job stuck 시 재시도/취소 API 노출 여부 미확인 **(추정)** |
| 메시지 편집 충돌 처리 | 동시 편집 시 last-write-wins — 버전 충돌 알림 없음 **(추정)** |
| 계정 삭제 후 파일/메시지 보존 정책 | `delete_user` + key rotate는 구현 — attachment 물리 삭제 범위는 운영 정책 의존 **(추정)** |

### 4.4 문서·구현 정합성 (양호한 부분)

- `room_security_updated` canonical 이벤트 — HTTP membership flow와 테스트 일치
- 삭제된 첨부 메시지 검색 제외 — `_HIDDEN_DELETED_ATTACHMENT_WHERE` 공유
- `reaction_updated` / `poll_updated` — 클라이언트 payload 무시, DB canonical 재방송 (테스트 존재)
- 업로드 토큰 1회성 소비 — `tests/test_upload_tokens.py`
- pyright·`npm run check:js` 통과

### 4.5 레거시·부채

- `app/legacy/models_monolith.py` 잔존 — CodeGraph가 `add_room_member` duplicate 정의 참조. 런타임은 `app/models/rooms.py` 사용하나 **유지보수 혼선 (추정)**
- `config.py`의 `PASSWORD_SALT` 하드코딩 — 실제 런타임은 `app/bootstrap/runtime.py`에서 파일 기반 salt 로드로 대체

---

## 5. Recommended Fix Plan

### 1단계 — 즉시 수정 (Critical / 운영 사고 예방)

1. **`invite_member` 트랜잭션화**  
   `rotate_room_key` + `add_room_member`(복수) + 실패 시 rollback을 `BEGIN IMMEDIATE`로 묶기.
2. **동시 초대 회귀 테스트 추가**  
   두 클라이언트가 동시에 서로 다른 사용자 초대 → 모든 신규 멤버의 `joined_key_version == rooms.key_version` 검증.
3. **배포 모드 명시**  
   단일 프로세스 전제를 README/운영 문서에 명시. 다중 워커 사용 시 Redis 필수 체크리스트 추가.

### 2단계 — 안정성 개선 (High / Medium)

1. **StateStore + Socket.IO Redis 경로 검증 테스트**  
   upload token cross-process, rate limit, broadcast 통합 테스트.
2. **`handleRoomSecurityUpdated` UI 동기화**  
   키 갱신 후 pending decrypt 재실행 또는 메시지 영역 soft refresh.
3. **소켓 relay 이벤트 rate limit 통일**  
   `room_members_updated`, `poll_*`에 per-user limit; 가능하면 서버 emit-only로 축소.
4. **테스트 환경 수정**  
   encoding hygiene exclude 목록; OIDC mock JWKS.
5. **experimental `openRoom` 가드**  
   features/runtime과 동일 패턴 이식 또는 experimental 비활성.

### 3단계 — 구조 개선 (Low / 장기)

1. **문서 정정**  
   “E2E” → “서버 관리형 방 키 + 클라이언트 암호화” 용어 통일 (`README.md`, `CLAUDE.md` 동기화 규칙 준수).
2. **레거시 monolith 제거 또는 격리**  
   `app/legacy/models_monolith.py` archive — import 경로 단일화.
3. **프론트엔드 통합 테스트 도입**  
   Playwright 등으로 방 전환·키 로테이션·핀 삭제 시나리오 smoke.
4. **초대 API idempotency**  
   동일 사용자 중복 초대 요청 시 불필요 rotate 방지.

---

## 6. Test Recommendations

### 6.1 반드시 추가할 테스트

| 테스트 | 목적 |
|--------|------|
| `test_concurrent_invites_assign_consistent_joined_key_version` | §3.1 race 재현/방지 |
| `test_invite_rotate_rolls_back_when_all_adds_fail` | §3.8 불필요 rotate 방지 |
| `test_upload_token_shared_across_threads_with_redis` | §3.2 다중 워커 토큰 일관성 (Redis fixture) |
| `test_room_security_updated_triggers_decrypt_refresh` | §3.4 프론트 (Playwright 또는 JS unit) |

### 6.2 기존 스위트 보강

| 영역 | 제안 |
|------|------|
| `can_user_see_message` | 파라미터화 단위 테스트 — file/pin/reaction/HTTP 403 경계 |
| `rotate_room_key` | 직접 단위 테스트 + conn 인자 공유 트랜잭션 |
| `purge_expired_upload_tokens` | referenced 파일·토큰 만료·mtime 경계 추가 케이스 |
| Socket relay | `room_members_updated` 멤버 스팸 rate limit |
| encoding hygiene | `EXCLUDE_DIRS = {"node_modules", ".git", "uploads", "backup"}` |
| OIDC | `pytest.mark.skipif` 또는 httpx mock JWKS |

### 6.3 회귀 유지 권장 (이미 양호)

- `tests/test_implementation_gap_remediation.py`
- `tests/test_feature_risk_review_implementation.py`
- `tests/test_upload_tokens.py`
- `tests/test_feature_risk_review_plan.py` (OIDC 제외 시)

### 6.4 검증 파이프라인 (CLAUDE.md 기준 유지)

```bash
npm run check:js
pytest tests -q
pytest tests/test_feature_risk_review_implementation.py tests/test_upload_tokens.py -q
pyright app gui
```

현재 환경 갭:
- **pytest 3건 실패** — 위 §3.7 수정 전까지 전체 green 아님
- **git 미초기화** — encoding hygiene false positive 유발

---

## 부록: 감사 시 참조한 핵심 파일

- 문서: `README.md`, `CLAUDE.md`, `implementation_gap_review_2026-04-27.md`
- 백엔드: `app/http/rooms.py`, `app/models/rooms.py`, `app/models/messages.py`, `app/socket_events/messages.py`, `app/socket_events/features.py`, `app/upload_tokens.py`, `app/state_store.py`
- 프론트: `static/js/features/rooms/runtime.js`, `static/js/services/socket/runtime.js`, `static/js/experimental/modules/chat.js`
- 테스트: `tests/test_implementation_gap_remediation.py`, `tests/test_feature_risk_review_implementation.py`, `tests/test_upload_tokens.py`, `tests/test_feature_risk_review_plan.py`