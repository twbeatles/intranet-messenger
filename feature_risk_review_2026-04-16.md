# Feature Implementation Risk Review

Date: 2026-04-16  
Reference docs: `README.md`, `claude.md`, `gemini.md`

## Scope

This document tracks the implementation follow-up for the April 16 feature-risk review and the matching documentation/tooling work that was added afterward.

## Implemented Changes

### 1. Membership-scoped room security

- Added room key versioning and per-member visibility checks.
- Introduced key rotation for:
  - member invite
  - member leave
  - member kick
  - account deletion
- Added canonical security payloads so the frontend can refresh active-room keys without a full reload.

### 2. Server-authoritative realtime events

- Room name changes now emit canonical `room_name_updated`.
- Admin permission changes now emit canonical `admin_updated`.
- Client-side forged admin update emission was removed.

### 3. File deletion and search consistency

- Deleting a room file now removes the linked attachment message through the standard deletion flow.
- If that file was pinned, the server also emits `pin_updated`.
- Hidden/deleted attachment messages are excluded from search results.

### 4. Upload-token cleanup

- Added maintenance cleanup for expired and unreferenced upload-token artifacts.
- Wired the cleanup into the background maintenance worker.

### 5. Tooling and documentation sync

- Added repo-local JavaScript lint/typecheck commands.
- Added `eslint.config.mjs`, `jsconfig.json`, and frontend ambient declarations.
- Updated README, agent guidance docs, and the backup runbook to match the current contracts.
- Reviewed `messenger.spec` against the runtime-split layout and current packaged modules.

## Primary Files

- `app/models/base.py`
- `app/models/rooms.py`
- `app/models/messages.py`
- `app/http/rooms.py`
- `app/http/messages.py`
- `app/http/auth.py`
- `app/http/uploads.py`
- `app/services/socket_broadcasts.py`
- `app/socket_events/messages.py`
- `app/upload_tokens.py`
- `static/js/features/rooms/runtime.js`
- `static/js/features/messages/runtime.js`
- `static/js/services/socket/runtime.js`
- `package.json`
- `eslint.config.mjs`
- `jsconfig.json`
- `types/frontend-globals.d.ts`

## Verification Results

- `npm run check:js`
- `python -m pytest tests/test_feature_risk_review_implementation.py tests/test_upload_tokens.py -q`
  - `7 passed`
- `python -m pytest tests -q`
  - `102 passed`
- `npx --yes pyright app gui`
  - `0 errors, 0 warnings`

## Notes

- `feature_risk_review_2026-04-14.md` was already removed from the worktree before this update. This document is the current replacement baseline for the new implementation pass.
