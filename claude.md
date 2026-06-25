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
