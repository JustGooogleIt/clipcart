# ClipCart status

Updated 2026-10-17. YouTube product ingest lands on `feat/youtube-product` (based on `integration`).

## Working flow (verified locally in headless Chrome and with offline tests)

The flow runs on http://127.0.0.1:8000 via `scripts/dev.sh`:

1. Upload a JPEG/PNG or MP4/MOV, **or paste a YouTube URL** (`POST /api/sessions/{id}/youtube-analyze` — temporary yt-dlp download, ranked local scan, then the same analysis job). A photo and a 4 s clip were tested; YouTube path has offline fixture tests.
2. Frames are extracted with decoder timestamps. Without a Perceptron key, detection reports "not configured" and the shopper draws a box (manual crop fallback).
3. Select the garment, then set budget, size, colors, excluded materials and condition.
4. Two bounded workers search **live SoleScout**. Without `XAI_API_KEY` they run rule-based queries, labeled "Rule-based".
5. A deterministic verifier filters and ranks results into Recommended, Needs checking, and Possible original over budget.
6. Text refinement ("leather is fine, under $300") patches only the named fields and supersedes the running search.
7. `/go/{token}` opens the stored SoleScout or store page and records the referral.
8. A reload restores the session, results and preferences. A second browser cannot read them.

## Provider modes

| Provider | Mode now | What makes it live |
| --- | --- | --- |
| SoleScout catalog | Live (real calls succeed). PR #3 destinations are integrated | Already live, no key needed |
| Perceptron | **Live**, verified 2026-10-17 with `perceptron-mk1.5` (set in `.env`). The smoke check gave request `be94e617…`, one jacket box, and visible attributes. The web flow worked on a photo (desktop) and a 6-frame clip (phone): 13 paid calls, 0 failures | Already live |
| Grok (xAI) | Not configured: `XAI_API_KEY` is empty. Search uses rule-based workers | Key set, then `--only grok` shows `groundedInCatalog: true` |
| MongoDB | `local_memory` by default. Restore after restart was verified on a real MongoDB 8.0 server (local binary, not Atlas) | `MONGODB_URI` (Atlas), then `--only atlas` succeeds |

## Spend bounds for live Perceptron

Each upload makes at most `PERCEPTION_MAX_FRAMES` (6) detect calls and `PERCEPTION_MAX_ATTRIBUTE_CALLS` (3) attribute calls. `PERCEPTRON_MAX_TOKENS` is 1200. The live check makes at most one detect call and one attribute call.

## Latest good commit

See `git log integration`. Tests: `services/api/.venv/bin/python -m pytest services/api/tests -q` reports 142 passed and 1 skipped. The skip is the live Perceptron check.

## Known blockers

- AT03 is met: a real Perceptron call produced a displayed garment tied to its frame and request ID.
- The live garment label shows only a color when the representative crop got an attribute call (3 per upload). Grouping and labels belong to the perception lane.
- The UI detection chip refreshes only after a search finishes. That's a note for the UI polish session.
- `XAI_API_KEY` is empty, so AT06 is met only by a scripted-client test.
- `MONGODB_URI` is empty, so Atlas itself is unverified. The same code passed a restart-restore check on a real MongoDB server.
- `feat/ui-polish` hasn't landed, so the post-UI desktop and phone verification is still pending.
- SoleScout free tier hides most cheapest sellers. Material composition is never provided, so material exclusions leave results in "Needs checking".

## Deferred behind flags (off)

`FEATURE_PHOTON`, `FEATURE_VOICE` and `FEATURE_SOLANA` are all false. Those features are not built.

## Active owners

- Claude: integration, UI, API, contracts, workers, verification, redirects.
- Perception lane: `app/media`, `app/providers/perceptron`, and their tests. Follow-ups are listed in the PR #2 review comment.
- Teammate: catalog adapter. The adapter fix is described in `docs/decisions.md`.

## Next

1. Fill `PERCEPTRON_API_KEY` (and optionally `XAI_API_KEY`, `MONGODB_URI`) in the root `.env`, then run `services/api/.venv/bin/python scripts/live_checks.py --image <garment photo>`.
2. Set the Atlas URI and confirm reload after a server restart.
3. Build the truth set (AT19) on real clips once Perceptron is live.
