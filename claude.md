# CLAUDE.md

Project: `intranet-messenger`
Last updated: 2026-06-25

## Read First

1. `README.md`
2. `implementation_gap_review_2026-04-27.md`
3. `PROJECT_AUDIT.md`
4. `docs/BACKUP_RUNBOOK.md`
5. `pyrightconfig.json`
6. `jsconfig.json`
7. `eslint.config.mjs`

## Current Baseline To Preserve

- Room keys are server-managed; clients encrypt/decrypt with member-scoped keyrings delivered by the server (not server-blind E2E).
- Room key rotation is membership-sensitive.
- `invite_members_with_key_rotation` must keep rotate + member insert atomic (`BEGIN IMMEDIATE`).
  - Invites, leave, kick, and account deletion rotate the room key for the remaining members.
  - Newly invited users must not receive pre-invite history.
- `room_security_updated` is the canonical socket event for frontend key refresh.
- `room_name_updated` and `admin_updated` must come from the server, not optimistic client emits.
- Deleted attachment messages must stay hidden from chat history search results.
- Message-scoped file, pin, reaction, reply, read receipt, download, and edit/delete paths must respect `joined_key_version` visibility.
- File deletion must keep pin state in sync through `pin_updated`.
- Upload token cleanup must remove expired, unreferenced files without touching referenced uploads.

## Frontend Structure Notes

- Source-of-truth runtime files live under:
  - `static/js/core/`
  - `static/js/services/`
  - `static/js/features/`
  - `static/js/bootstrap/`
- Root files like `static/js/rooms.js` and `static/js/messages.js` are compatibility exports and should stay thin.
- The script load order is defined in `templates/partials/scripts.html`.

## Backend Structure Notes

- Main runtime logic belongs in:
  - `app/bootstrap/`
  - `app/http/`
  - `app/socket_events/`
  - `app/services/`
  - `app/models/`
- `messenger_server.py` is a shim. Prefer `server.py` and the runtime-split packages.

## Deployment Notes

- Single-process default: in-memory `StateStore` and `MESSAGE_QUEUE=None` are OK.
- Multi-worker/multi-instance: set `STATE_STORE_REDIS_URL` and `MESSAGE_QUEUE`; optional `REQUIRE_REDIS_STATE=1` for fail-fast.

## Required Verification Flow

1. `npm run check:js`
2. `pytest tests -q`
3. `pytest tests/test_feature_risk_review_implementation.py tests/test_upload_tokens.py tests/test_project_audit_remediation.py -q`
4. `pyright app gui`

If an environment dependency is missing, record the exact missing package and the affected command.

## Documentation Sync Rule

When contracts, build steps, or recovery expectations change, update the matching docs in the same change set:

- `README.md`
- `claude.md`
- `gemini.md`
- `docs/BACKUP_RUNBOOK.md`
- `implementation_gap_review_2026-04-27.md`
- `PROJECT_AUDIT.md`

## Build Spec Checkpoints

Review `messenger.spec` whenever runtime imports or packaged data change. The current spec should continue to include:

- `app.bootstrap.*`
- `app.http.*`
- `app.socket_events.*`
- `app.services.*`
- `app.models.*`
- `docs/BACKUP_RUNBOOK.md`

The April 27 visibility remediation did not add new packaged runtime modules or data files.

## Working Prompt Template

```text
Read README.md, implementation_gap_review_2026-04-27.md, PROJECT_AUDIT.md, docs/BACKUP_RUNBOOK.md, pyrightconfig.json, jsconfig.json, and eslint.config.mjs first.
Preserve membership-scoped room security, authoritative socket payloads, invite_members_with_key_rotation atomicity, and upload-token cleanup behavior.
Update tests and docs in the same change set, then run:
1) npm run check:js
2) pytest tests -q
3) pytest tests/test_feature_risk_review_implementation.py tests/test_upload_tokens.py tests/test_project_audit_remediation.py -q
4) pyright app gui
Report changed files, verification results, and any environment gaps.
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
