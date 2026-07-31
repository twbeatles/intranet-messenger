# GEMINI.md

Project: `intranet-messenger`
Last updated: 2026-06-25

## Session Bootstrap

Read these files before changing code:

1. `README.md`
2. `claude.md`
3. `implementation_gap_review_2026-04-27.md`
4. `PROJECT_AUDIT.md`
5. `docs/BACKUP_RUNBOOK.md`
6. `pyrightconfig.json`
7. `jsconfig.json`
8. `eslint.config.mjs`

## Must-Keep Contracts

### Room security

- Room keys are server-managed; clients encrypt with member-scoped keyrings from the server (not server-blind E2E).
- Membership changes rotate room keys.
- `invite_members_with_key_rotation` keeps invite-time rotate + member insert atomic.
- Message visibility depends on `key_version` and `joined_key_version`.
- Message-adjacent APIs for files, pins, reactions, replies, read receipts, downloads, and edit/delete actions must use the same visibility rule.
- `GET /api/rooms/<room_id>/messages` is expected to return room key metadata for the active member.
- `room_security_updated` is the authoritative realtime refresh path.

### Room metadata

- Server emits canonical `room_name_updated`.
- Server emits canonical `admin_updated`.
- Frontend should not simulate these events locally.
- Clients must not mutate room metadata by emitting those notification event names.

### File lifecycle

- Uploads must flow through `upload_token`.
- File deletion removes the linked attachment message.
- Pin state must refresh when a pinned file is deleted.
- Expired, unused upload-token files must be purged by maintenance code.

### Search behavior

- Hidden/deleted attachment messages stay out of search.
- Search results must respect per-member history visibility.

## Frontend Tooling Expectations

- `npm run lint:js` checks first-party frontend scripts.
- `npm run typecheck:js` runs `checkJs`-style validation for the shared frontend bridge/state files.
- Vendor/minified assets are excluded.
- Experimental ES module files are not part of the `checkJs` pass unless that scope is intentionally expanded.

## Change Routine

1. State the change scope and affected contracts.
2. Update code.
3. Update tests.
4. Update docs if runtime, API, packaging, or recovery guidance changed.
5. Run verification:
   - `npm run check:js`
   - `pytest tests -q`
   - `pytest tests/test_feature_risk_review_implementation.py tests/test_upload_tokens.py -q`
   - `pyright app gui`
6. Record exact blockers if the environment is missing dependencies.

## Files Worth Checking First

- `app/models/rooms.py`
- `app/models/messages.py`
- `app/http/rooms.py`
- `app/http/messages.py`
- `app/http/uploads.py`
- `app/services/socket_broadcasts.py`
- `app/upload_tokens.py`
- `static/js/features/rooms/runtime.js`
- `static/js/features/messages/runtime.js`
- `static/js/services/socket/runtime.js`
- `templates/partials/scripts.html`
- `messenger.spec`
- `implementation_gap_review_2026-04-27.md`
- `PROJECT_AUDIT.md`

## Prompt Template

```text
Read README.md, claude.md, implementation_gap_review_2026-04-27.md, PROJECT_AUDIT.md, docs/BACKUP_RUNBOOK.md, pyrightconfig.json, jsconfig.json, and eslint.config.mjs.
Keep room-security rotation, invite_members_with_key_rotation atomicity, authoritative socket events, upload-token cleanup, and search-visibility rules intact.
When you change code, update tests and docs in the same patch set and run:
1) npm run check:js
2) pytest tests -q
3) pytest tests/test_feature_risk_review_implementation.py tests/test_upload_tokens.py tests/test_project_audit_remediation.py -q
4) pyright app gui
Then summarize file changes, test results, and any remaining environment issues.
```

<!-- SPECKIT-AGENT-GUIDE:START -->

## Spec Kit / Spec-Driven Development (AI 에이전트 필독)

> 이 블록은 GitHub Spec Kit 활성화 및 기능 명세 작업 결과를 AI 에이전트가 바로 쓰도록 정리한 안내입니다.
> 수정 시 마커 주석을 유지하세요. 스크립트/후속 세션이 이 구간을 갱신합니다.

### 이 저장소 상태

- **프로젝트**: `intranet-messenger`
- **Spec Kit 초기화**: `.specify/ 있음`
- **에이전트 스킬**: Grok=True, Claude=True, Codex/Agy(.agents)=True
- **활성 기능**: 아직 `specs/` 기능 명세 없음 — `.specify/` 만 준비된 상태

### 에이전트가 먼저 읽을 파일

1. `.specify/` 및 `.grok/skills` / `.claude/skills` / `.agents/skills` 의 `speckit-*`
2. 기능 작업 시작 시 `/speckit-specify` 로 `specs/00N-...` 생성

### 권장 워크플로 (스킬 / 슬래시 커맨드)

| 단계 | 커맨드 (Grok/Claude 등) | 산출 |
|------|-------------------------|------|
| 원칙 | `/speckit-constitution` | `.specify/memory/constitution.md` |
| 명세 | `/speckit-specify` | `specs/<id>/spec.md` |
| 계획 | `/speckit-plan` | `plan.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md` |
| 작업 | `/speckit-tasks` | `tasks.md` |
| 구현 | `/speckit-implement` | 코드 (tasks 순서) |
| 갭점검 | `/speckit-converge` | `tasks.md` 에 Phase Convergence **append-only** |

- Codex skills 모드: `$speckit-specify` 형태일 수 있음
- 스킬 파일: `.grok/skills/speckit-*/SKILL.md`, `.claude/skills/speckit-*/SKILL.md`

### 작업 규칙 (에이전트)

1. **새 기능/큰 변경 전** 활성 `spec.md`·`tasks.md` 를 읽고, 없으면 specify→plan→tasks 순으로 만든다.
2. **구현은 tasks.md 체크리스트**를 따른다. 완료 시 `- [ ]` → `- [x]`.
3. **`/speckit-converge` 는 tasks.md 를 rewrite 하지 않는다** — 잔여 갭만 하단 Phase 로 append.
4. brownfield 프로젝트는 상당 기능이 이미 있을 수 있다. 중복 구현 전에 코드·`[x]` 태스크를 확인한다.
5. 웹/데스크톱 패리티 등 **out-of-scope Assumptions** 는 새 feature 로 분리하는 것을 선호한다.
6. 기본 integration 은 **grok** 이며, 동일 레포에 claude / codex / agy 스킬도 multi-install 되어 있을 수 있다.

### 관련 링크

- Spec Kit: https://github.com/github/spec-kit
- 로컬 CLI: `specify` (uv tool, 버전은 `specify version`)

<!-- SPECKIT-AGENT-GUIDE:END -->
