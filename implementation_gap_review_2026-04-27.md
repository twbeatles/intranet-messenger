# Implementation Gap Review

Date: 2026-04-27 (updated 2026-06-25)
References: `README.md`, `claude.md`, `gemini.md`, `PROJECT_AUDIT.md`

## Remediation Status

Implemented on 2026-06-25 (PROJECT_AUDIT follow-up).

- Made invite-time key rotation and member insert atomic via `invite_members_with_key_rotation`.
- Added Redis scaling warnings / optional `REQUIRE_REDIS_STATE` fail-fast.
- Added socket relay rate limits for `room_members_updated`, `poll_created`, and `poll_updated`.
- Refreshed pending message decryption after `room_security_updated`.
- Aligned experimental `openRoom` stale-request guard with production runtime.
- Fixed OIDC JWKS loading to use HTTP `_fetch_json` (tests use mock HTTPS JWKS).
- Tightened encoding hygiene excludes for non-git workspaces.
- Added `tests/test_project_audit_remediation.py`.

Implemented on 2026-04-27.

- Added shared message visibility enforcement for files, downloads, pins, reactions, replies, read receipts, and message edit/delete paths.
- Made `room_name_updated` and `admin_updated` server-emitted events only.
- Clamped admin audit log pagination.
- Allowed rapid room switching to let the latest room-open request win.
- Added regression coverage in `tests/test_implementation_gap_remediation.py`.

Verification:

- `npm run check:js`
- `python -m pytest tests/test_implementation_gap_remediation.py -q`
- `python -m pytest tests/test_feature_risk_review_implementation.py tests/test_feature_risk_review_plan.py -q`
- `python -m pytest tests -q`
- `python -m pytest tests/test_feature_risk_review_implementation.py tests/test_upload_tokens.py -q`
- `pyright app gui`

## Current Security Notes

- Message history, file lists, file downloads, pins, reactions, replies, read receipts, and message edit/delete paths now share the same member visibility rule: `messages.key_version >= room_members.joined_key_version`.
- Newly invited members cannot list or download files, view pins, react to messages, or reply to messages from before their invite.
- Users who leave a room cannot edit or delete their old messages through HTTP or Socket.IO.
- `room_name_updated` and `admin_updated` are server-emitted notification events only; clients cannot mutate room metadata by emitting those event names.

## Build And Packaging Review

- `messenger.spec` was reviewed for this remediation.
- No new Python runtime packages or hidden imports were introduced.
- The existing hidden imports still cover `app.http.*`, `app.socket_events.*`, `app.services.*`, and `app.models.*`.
- Packaged data remains unchanged: the backup runbook is still the only explicitly packaged markdown document.

## Documentation Sync

- `feature_risk_review_2026-04-16.md` has been retired and removed.
- `README.md`, `claude.md`, and `gemini.md` now point to this document as the current implementation-risk follow-up.
