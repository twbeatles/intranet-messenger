# Intranet Messenger

Updated: 2026-04-27

Intranet Messenger is a Flask + Socket.IO chat application with a web UI, optional desktop packaging via PyInstaller, end-to-end message encryption support, and room/file/poll collaboration features.

## What Changed In The Current Baseline

- Room membership changes now rotate room encryption keys.
- Message visibility is scoped by the member's joined key version.
- Room name/admin updates are emitted as server-authoritative socket events.
- Deleting a pinned file now also refreshes the pin banner state.
- Deleted attachment messages are hidden from search results.
- Expired and unreferenced upload-token files are purged by maintenance workers.
- Frontend JavaScript now has repo-local lint and typecheck commands.
- Message-scoped APIs now consistently enforce per-member visibility for files, pins, reactions, replies, read receipts, downloads, and edit/delete actions.
- `room_name_updated` and `admin_updated` are server-emitted notification events only.

## Repository Layout

- `server.py`: runtime entry point for local server execution.
- `messenger_server.py`: compatibility shim only; do not add new runtime logic here.
- `app/factory.py`: Flask app factory.
- `app/bootstrap/`: runtime/bootstrap wiring.
- `app/http/`: HTTP routes and API handlers.
- `app/socket_events/`: Socket.IO event handlers.
- `app/services/`: shared runtime services and broadcast helpers.
- `app/models/`: database access and domain logic.
- `static/js/core/`, `static/js/services/`, `static/js/features/`, `static/js/bootstrap/`: primary frontend sources.
- `static/js/*.js`: compatibility exports for the runtime-split frontend.
- `templates/partials/`: HTML partials loaded by `templates/index.html`.
- `docs/BACKUP_RUNBOOK.md`: backup, restore, and recovery checks.
- `implementation_gap_review_2026-04-27.md`: implementation-focused follow-up for the April 27 visibility and authority gap review.

## Current Security And API Contracts

### 1. Membership-scoped room encryption

- `POST /api/rooms/<room_id>/members`, `POST /api/rooms/<room_id>/leave`, kick flows, and account deletion flows rotate the room key for surviving members.
- `GET /api/rooms/<room_id>/messages` now returns:
  - `encryption_key`
  - `encryption_keys`
  - `key_version`
  - `member_key_version`
- The `room_security_updated` socket event is the canonical frontend trigger for key refresh.
- Newly invited members must not see messages older than their `joined_key_version`.
- The same visibility rule applies to message-adjacent APIs, including room files, downloads, pins, reactions, replies, read receipts, and message edit/delete actions.

### 2. Authoritative room metadata updates

- Room name changes emit `room_name_updated` from the server.
- Admin changes emit `admin_updated` from the server.
- Frontend code should not forge these events optimistically.
- Socket clients cannot mutate room names or admin roles by emitting those notification event names.

### 3. File upload and deletion safety

- `POST /api/upload` issues one-time `upload_token` values.
- File and image messages must be sent through the validated upload-token path.
- `DELETE /api/rooms/<room_id>/files/<file_id>` removes the linked attachment message and emits the same deletion flow the chat UI already understands.
- If the deleted file was pinned, the server also emits `pin_updated`.

### 4. Search visibility rules

- Deleted attachment messages must not reappear in basic or advanced search.
- Search responses must also respect membership visibility rules tied to `key_version`.

## Local Setup

### Python dependencies

```bash
pip install -r requirements.txt
```

### Frontend tooling dependencies

```bash
npm install
```

### Run the app

```bash
python server.py --cli
```

Default local URL:

- `http://localhost:5000`

## Verification Commands

### Python checks

```bash
pytest tests -q
pytest tests/test_feature_risk_review_implementation.py tests/test_upload_tokens.py -q
pyright app gui
```

### Frontend checks

```bash
npm run lint:js
npm run typecheck:js
npm run check:js
```

Notes:

- `jsconfig.json` covers the shared frontend bridge/state files that are most sensitive to load-order and global exposure regressions.
- Vendor/minified assets are excluded from lint/typecheck.
- Experimental ES module files under `static/js/experimental/` are linted but excluded from the TypeScript-style `checkJs` pass.

## Packaging

Build with PyInstaller:

```bash
pyinstaller messenger.spec --clean
```

The reviewed `messenger.spec` already includes the runtime-split Python packages, socket broadcast helpers, upload-token helpers, and backup documentation needed by the current app layout. The April 27 remediation introduced no new packaged runtime modules or data files.

## Documentation Index

- `README.md`
- `claude.md`
- `gemini.md`
- `docs/BACKUP_RUNBOOK.md`
- `implementation_gap_review_2026-04-27.md`
- `pyrightconfig.json`
- `jsconfig.json`
- `eslint.config.mjs`
