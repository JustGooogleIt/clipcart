# Style memory: end-to-end browser verification

Run on 2026-10-17 against a local merge of `integration` (a1741a8), PR #15 (`feat/style-memory` at 20e17e0) and PR #16 (`feat/style-panel-d7ch3n` at 1c87573). The merge was local only and was not pushed.

**Result: 27 of 27 checks passed across three phases,** with two server restarts on a real MongoDB. There were no page errors. Per-check detail is in `log-phase1.json`, `log-phase2.json` and `log-phase3.json`.

## Setup

| Item | Value |
| --- | --- |
| Database | MongoDB 8.0.4 Community (official macOS arm64 build, SHA-256 checked against MongoDB's published hash), on 127.0.0.1:27027. Health reported `database.mode = mongodb`. |
| Server | Combined tree on 127.0.0.1:8012, serving the built web app. `.env` was not loaded. |
| Flags | `FEATURE_STYLE_MEMORY=1`; the style reader was the default (`STYLE_MODEL_PROVIDER` unset, so `none`, the rule parser) |
| Data | Fixture perception and fixture catalog. Every card is labelled as fixture data. |
| Browser | Headless Chromium through Playwright 1.62.1, at 1440×900. Cookies were carried across restarts as a returning shopper. |
| Web build | `tsc -b` and `vite build` were clean against the regenerated `packages/contracts`. |

## What was checked

**Phase 1: first visit**
1. A search for a drawn "denim jacket" returned 2 fixture cards with no personalization.
2. **Save an item:** pressing Save on the brown Calvin Klein moto jacket changed it to "Saved ✓", and the item appeared under Saved items.
3. **Accept a preference:** the style note "I love brown, I hate orange" was read by the rule-based parser, labelled as such. It proposed "Likes brown" from "love brown" (the quote fix) and "Avoids orange". Nothing was saved until "Save selected". Only brown was kept, as a `stated` / `style_note` memory.
4. **Search again:** the brown jacket moved to the top with "✦ Your style · You said you like brown". The other card had no reason.

**Phase 2: after restarting the server**
1. The same memory ID, events, saved state and restored results with their reason came back, and a fresh search still personalized.
2. **Correct:** brown was corrected to green in the panel. Green became active and brown was marked removed. After re-searching, the brown reason was gone.
3. **Delete:** removing green left no active preferences and no liked colors in the profile, while the saved item was kept. After re-searching, no card had a reason.

**Phase 3: after a second restart**
1. The memory history was identical, with brown and green both removed and nothing active. The saved item and its "Saved ✓" state remained, search had no reasons, and the panel showed no brown or green preference.

The records were also read directly from MongoDB between phases, outside the app.

## Re-run

```sh
# 1. MongoDB on localhost (any 6.0+ server)
mongod --dbpath <dir> --bind_ip 127.0.0.1 --port 27027
# 2. API + built web app (from the repo root after `cd apps/web && npm run build`)
cd services/api && CLIPCART_SKIP_DOTENV=1 FEATURE_STYLE_MEMORY=1 \
  MONGODB_URI=mongodb://127.0.0.1:27027 MONGODB_DB=clipcart_style_verify \
  PERCEPTION_PROVIDER=fixture CATALOG_PROVIDER=fixture \
  uvicorn app.main:app --host 127.0.0.1 --port 8012
# 3. Browser phases; restart step 2 between phases
cd scripts/e2e/style-memory
VERIFY_DIR=<scratch dir with a shots/ folder> PLAYWRIGHT_MODULE=<path to playwright> node phase1.cjs
VERIFY_DIR=... node phase2.cjs
VERIFY_DIR=... node phase3.cjs
```

Each phase exits non-zero if any check fails. Use a fresh database name per run, because phase 1 expects no prior memories for the new browser owner.
