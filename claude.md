# CLAUDE.md

?꾨줈?앺듃: `intranet-messenger-main`  
理쒖쥌 ?낅뜲?댄듃: 2026-02-28

## 1) 紐⑹쟻

???묒뾽 ?몄뀡?먯꽌 Claude媛 ???뚯씪 ?섎굹濡??꾨줈?앺듃???꾩옱 ?곹깭, ?꾩닔 洹쒖튃, 寃利?湲곗???鍮좊Ⅴ寃??뚯븙?섎룄濡??섍린 ?꾪븳 ?댁쁺 臾몄꽌.

## 2) ?몄뀡 ?쒖옉 ???꾩닔 ?뺤씤

1. `README.md`  
2. `PROJECT_STRUCTURE_FEATURE_EXPANSION_ANALYSIS_2026-02-27.md`  
3. 理쒓렐 蹂寃??뚯씪:
   - `app/routes.py`
   - `app/sockets.py`
   - `app/upload_tokens.py`
   - `app/models/users.py`
   - `app/models/messages.py`
   - `app/models/polls.py`

## 3) ?꾩옱 湲곗???Baseline)

- 踰꾩쟾 臾몄꽌 湲곗?: `v4.36.3 (2026-02-20)`
- ?뚭? ?뚯뒪??湲곗?:
  - `pytest tests -q` => `84 passed`
  - `pytest --maxfail=1` => `84 passed`
- `pytest.ini` 議댁옱:
  - `testpaths = tests`
  - `norecursedirs = backup dist build`

## 4) ?듭떖 API/蹂댁븞 怨꾩빟 (?덈? 源⑥?硫?????

### 4.1 諛??앹꽦 API

- ?붾뱶?ъ씤?? `POST /api/rooms`
- ?쒖? ?낅젰 ?? `members`
- ?명솚 ?낅젰 ?? `member_ids` (?섏쐞 ?명솚)
- ?숈떆 ?낅젰 ?? `members` ?곗꽑, `member_ids` 臾댁떆(寃쎄퀬 濡쒓렇)
- 硫ㅻ쾭 ?뺢퇋??
  - ?뺤닔 蹂??
  - 以묐났 ?쒓굅
  - ?먭린 ?먯떊 ?먮룞 ?ы븿

### 4.2 ?낅줈???뚯씪 硫붿떆吏 蹂댁븞

- ?낅줈?? `POST /api/upload`
  - `room_id` ?꾩닔
  - ?깃났 ?묐떟??`upload_token` ?ы븿
- ?뚯폆: `send_message`
  - `type in ('file','image')`?대㈃ `upload_token` ?꾩닔
  - ?쒕쾭???대씪?댁뼵??`file_path`/`file_name`???좊ː?섏? ?딆쓬
  - ?좏겙 寃利? user/room/type/留뚮즺/1?뚯꽦 ?뚮퉬
- ?좏겙 ??μ냼: `app/upload_tokens.py`
  - 湲곕낯 TTL 5遺?
  - thread-safe lock
  - one-time consume

### 4.3 ?뚯씪 ?ㅼ슫濡쒕뱶 罹먯떆 ?뺤콉

- ?붾뱶?ъ씤?? `GET /uploads/<path>`
- ?쇰컲 ?뚯씪: `Cache-Control: private, no-store`
- ?꾨줈???대?吏: `Cache-Control: private, max-age=3600`

### 4.4 寃??API ?뺤콉

- ?붾뱶?ъ씤?? `GET /api/search`
- `limit` clamp: `1..200`
- `offset`: ?뚯닔 諛⑹?(`>=0`)

### 4.5 Poll/Pin 怨꾩빟

- Poll ?앹꽦 紐⑤뜽 怨꾩빟:
  - `create_poll(...) -> poll_id | None`
- Poll ?앹꽦 ?쇱슦??
  - `poll_id` ?앹꽦 ??`get_poll(poll_id)` 議고쉶?섏뿬 ?묐떟
- Pin ??젣:
  - `success, error = unpin_message(...)`濡??먯젙
  - tuple truthy ?ㅽ뙋 湲덉?
- Pin ?쒖뒪??硫붿떆吏:
  - `pin_updated` ?뚯폆 ?대깽??寃쎈줈?먯꽌 ?앹꽦 湲덉?
  - `/api/rooms/<room_id>/pins` ?앹꽦/??젣 ?깃났 寃쎈줈?먯꽌留??앹꽦

### 4.7 Socket authoritative 怨꾩빟

- ?뚯폆 釉뚮줈?쒖틦?ㅽ듃 payload???쒕쾭 DB ?ъ“??媛믪씠 湲곗?
- `profile_updated`, `reaction_updated`, `poll_updated`, `poll_created`???대씪?댁뼵??payload瑜??좊ː?섏? ?딆쓬
- `room_members_updated`??emit 二쇱껜??room 硫ㅻ쾭??寃利??꾩닔

### 4.6 ?뚯썝?덊눜 臾닿껐??

- `polls.created_by = NULL` ?낅뜲?댄듃 湲덉? (`NOT NULL` ?쒖빟)
- ?덊눜 ?ъ슜?먭? 留뚮뱺 poll 泥섎━:
  - 媛숈? 諛⑹쓽 ?ㅻⅨ 硫ㅻ쾭?먭쾶 ?ы븷??愿由ъ옄 ?곗꽑)
  - ????놁쑝硫?poll ??젣

## 5) ?묒뾽 ?먯튃

1. `app/models.py`(紐⑤?由ъ떇)蹂대떎 `app/models/*` 紐⑤뱢 寃쎈줈瑜??곗꽑 ?ъ슜.
2. API 怨꾩빟 蹂寃???
   - ?쇱슦??+ ?꾨줎??+ ?뚯뒪??+ README瑜??숈떆 媛깆떊.
3. ?뚯씪 ?꾩넚 寃쎈줈?먯꽌 ?대씪?댁뼵???낅젰 寃쎈줈 ?좊ː 湲덉?.
4. ??蹂댁븞 濡쒖쭅 異붽? ???뚭? ?뚯뒪?몃? 諛섎뱶??異붽?.
5. README???먯뇙留??⑸웾/API ?ㅻ챸怨?援ы쁽????긽 ?쇱튂?쒗궗 寃?

## 6) 蹂寃???寃利?猷⑦떞

1. `pytest tests -q`
2. `pytest --maxfail=1`
3. ?ㅼ쓬???섎룞 ?먭?:
   - `/api/upload` ?묐떟??`upload_token` 議댁옱
   - ?좏겙 ?놁씠 ?뚯씪 ?뚯폆 ?꾩넚 ???먮윭 emit
   - `/api/search?limit=9999&offset=-1` clamp ?숈옉
   - `/uploads` 罹먯떆 ?ㅻ뜑 ?뺤콉 遺꾧린
   - `pin_updated` ?뚯폆 ?곗냽 ?몄텧 ??rate limit ?숈옉
   - OIDC callback?먯꽌 nonce/state one-time pop + 寃利??ㅽ뙣 濡쒓렇??嫄곕?

## 7) PR/而ㅻ컠 泥댄겕由ъ뒪??

- [ ] 怨꾩빟 蹂寃쎌씠 README/臾몄꽌??諛섏쁺?섏뿀?붽?
- [ ] ?뚯뒪??異붽?/?섏젙???숇컲?섏뿀?붽?
- [ ] 湲곗〈 ?뚯뒪???꾩껜 ?듦낵 ?щ? ?뺤씤?덈뒗媛
- [ ] 蹂댁븞 愿???뚭?(?좏겙 ?고쉶, 沅뚰븳 ?고쉶) 耳?댁뒪瑜?寃利앺뻽?붽?

## 8) Claude ?몄뀡 ?꾨＼?꾪듃 ?쒗뵆由?沅뚯옣)

?꾨옒瑜????몄뀡 泥?硫붿떆吏濡??ъ슜:

```
Read `claude.md`, `README.md`, and `PROJECT_STRUCTURE_FEATURE_EXPANSION_ANALYSIS_2026-02-27.md` first.
Then summarize:
1) current baseline (tests/contracts),
2) risks if we change this area,
3) exact files to edit,
and execute changes with verification (`pytest tests -q`, `pytest --maxfail=1`).
```

## 9) 2026-02-25 湲곗????낅뜲?댄듃 (Full Remediation)

- 肄붾뱶 湲곗???  - 由ъ뒪??留ㅽ븨 R-01~R-11 諛섏쁺 ?꾨즺
  - 異붽? 湲곕뒫(?듭뀡): OIDC, AV ?ㅼ틪 ?? Redis state_store, 愿由ъ옄 媛먯궗濡쒓렇, 蹂댁〈?뺤콉, 諛깆뾽/蹂듦뎄 ?곕턿

- ??蹂寃?二쇱슂 ?뚯씪
  - `app/state_store.py`
  - `app/upload_scan.py`
  - `app/oidc.py`
  - `app/models/admin_audit.py`
  - `app/legacy/models_monolith.py`
  - `scripts/backup_local.py`
  - `scripts/restore_local.py`
  - `scripts/verify_restore.py`
  - `docs/BACKUP_RUNBOOK.md`

- 怨듦컻 API 湲곗???  - `GET /api/config`
  - `GET /api/upload/jobs/<job_id>`
  - `GET /api/auth/providers`
  - `GET /auth/oidc/login`
  - `GET /auth/oidc/callback`
  - `GET /api/rooms/<room_id>/admin-audit-logs?format=json|csv`

- ?뚯뒪??湲곗???  - `pytest -q` => `84 passed`

- ?묒뾽 ???좎쓽?ы빆
  - ?몄뀡 臾댄슚?붾뒗 HTTP(`before_request`) + Socket(`connect`/?듭떖 ?대깽?? 紐⑤몢 ?좎?
  - ?뚯씪 硫붿떆吏??`upload_token` 寃利?寃쎈줈瑜??고쉶?섏? ?딅룄濡??좎?
  - `state_store`??Redis ?μ븷 ??硫붾え由?媛뺣벑 ?숈옉???좎?

## 10) 2026-02-25 ?뺥빀???숆린??硫붾え

- README/API 怨꾩빟/援ъ“ 遺꾩꽍 臾몄꽌 媛?湲곗????숆린???꾨즺
- ?뚯뒪??湲곗??? `pytest -q` -> `84 passed`
- `.spec` ?먭? 寃곌낵 諛섏쁺:
  - `app.state_store`, `app.upload_scan`, `app.oidc`, `app.models.admin_audit`
  - `redis`, `redis.asyncio`
  - `docs/BACKUP_RUNBOOK.md` ?곗씠???ы븿

## 11) 2026-02-27 援ъ“ 由ъ뒪??媛쒖꽑 諛섏쁺

- `messenger_server.py`??deprecated shim?쇰줈 ?좎??섍퀬 ?좉퇋 濡쒖쭅 異붽? 湲덉?
- ?꾨줎???낅줈??梨낆엫? `static/js/message-upload.js`濡?遺꾨━
- ?몄뀡 ??μ냼??`cachelib` 諛깆뿏??湲곗??쇰줈 ?좎?
- ?몄퐫???덉젙?? ?쒕쾭 吏꾩엯??UTF-8 stdio ?ㅼ젙 ?좎?

### API 怨꾩빟 怨좎젙媛?- `GET /api/config`
- `POST /api/upload` + `GET /api/upload/jobs/<job_id>`
- `POST /api/polls/<poll_id>/vote` (`error`, `code`)
- `GET /api/auth/providers`, `GET /auth/oidc/login`, `GET /auth/oidc/callback`
- `GET /api/rooms/<room_id>/admin-audit-logs?format=json|csv`


## 12) 2026-02-28 Feature Risk Review Sync

- Socket authoritative policy is now enforced for `room_members_updated`, `profile_updated`, `reaction_updated`, `poll_created`, `poll_updated`, and `pin_updated`.
- `pin_updated` socket event no longer creates system messages. System messages are created only in HTTP pin create/delete success paths.
- OIDC callback uses one-time `state`/`nonce` pop, and login is denied when `id_token` or nonce verification fails.
- OIDC `id_token` verification is strict: JWKS signature validation + `iss`, `aud`, `exp`, `nonce` checks.
- API contracts updated:
  - `POST /api/search/advanced`: invalid `limit`/`offset` returns `400` with `invalid_limit`/`invalid_offset`.
  - `POST /api/rooms/<room_id>/leave`: idempotent success with `left` and `already_left` flags.
- Test baseline: `pytest -q` => `84 passed` (2026-02-28).


