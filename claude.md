# CLAUDE.md

Project: `intranet-messenger`
Last updated: 2026-04-16

## Read First

1. `README.md`
2. `feature_risk_review_2026-04-16.md`
3. `docs/BACKUP_RUNBOOK.md`
4. `pyrightconfig.json`
5. `jsconfig.json`
6. `eslint.config.mjs`

## Current Baseline To Preserve

- Room key rotation is membership-sensitive.
  - Invites, leave, kick, and account deletion rotate the room key for the remaining members.
  - Newly invited users must not receive pre-invite history.
- `room_security_updated` is the canonical socket event for frontend key refresh.
- `room_name_updated` and `admin_updated` must come from the server, not optimistic client emits.
- Deleted attachment messages must stay hidden from chat history search results.
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

## Required Verification Flow

1. `npm run check:js`
2. `pytest tests -q`
3. `pytest tests/test_feature_risk_review_implementation.py tests/test_upload_tokens.py -q`
4. `pyright app gui`

If an environment dependency is missing, record the exact missing package and the affected command.

## Documentation Sync Rule

When contracts, build steps, or recovery expectations change, update the matching docs in the same change set:

- `README.md`
- `claude.md`
- `gemini.md`
- `docs/BACKUP_RUNBOOK.md`
- `feature_risk_review_2026-04-16.md`

## Build Spec Checkpoints

Review `messenger.spec` whenever runtime imports or packaged data change. The current spec should continue to include:

- `app.bootstrap.*`
- `app.http.*`
- `app.socket_events.*`
- `app.services.*`
- `app.models.*`
- `docs/BACKUP_RUNBOOK.md`

## Working Prompt Template

```text
Read README.md, feature_risk_review_2026-04-16.md, docs/BACKUP_RUNBOOK.md, pyrightconfig.json, jsconfig.json, and eslint.config.mjs first.
Preserve membership-scoped room security, authoritative socket payloads, and upload-token cleanup behavior.
Update tests and docs in the same change set, then run:
1) npm run check:js
2) pytest tests -q
3) pytest tests/test_feature_risk_review_implementation.py tests/test_upload_tokens.py -q
4) pyright app gui
Report changed files, verification results, and any environment gaps.
```
