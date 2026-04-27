# GEMINI.md

Project: `intranet-messenger`
Last updated: 2026-04-27

## Session Bootstrap

Read these files before changing code:

1. `README.md`
2. `claude.md`
3. `implementation_gap_review_2026-04-27.md`
4. `docs/BACKUP_RUNBOOK.md`
5. `pyrightconfig.json`
6. `jsconfig.json`
7. `eslint.config.mjs`

## Must-Keep Contracts

### Room security

- Membership changes rotate room keys.
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

## Prompt Template

```text
Read README.md, claude.md, implementation_gap_review_2026-04-27.md, docs/BACKUP_RUNBOOK.md, pyrightconfig.json, jsconfig.json, and eslint.config.mjs.
Keep room-security rotation, authoritative socket events, upload-token cleanup, and search-visibility rules intact.
When you change code, update tests and docs in the same patch set and run:
1) npm run check:js
2) pytest tests -q
3) pytest tests/test_feature_risk_review_implementation.py tests/test_upload_tokens.py -q
4) pyright app gui
Then summarize file changes, test results, and any remaining environment issues.
```
