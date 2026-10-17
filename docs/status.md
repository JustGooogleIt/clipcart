# ClipCart status

Updated 2026-10-17 by Claude (integration owner). Branch `integration`.

## Working flow (verified locally in headless Chrome and with offline tests)

The flow runs on http://127.0.0.1:8000 via `scripts/dev.sh`:

1. Upload a JPEG/PNG or MP4/MOV. A photo and a 4 s clip were tested, at desktop and phone widths.
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
| SoleScout catalog | Live (real calls succeed) | Already live, no key needed |
| Perceptron | Not configured | `PERCEPTRON_API_KEY` set **and** one successful call; the app shows "Key set, not yet verified" until then |
| Grok (xAI) | Not configured, so rule-based workers | `XAI_API_KEY` set and one successful call |
| MongoDB | `local_memory` (mongomock, in process) | `MONGODB_URI` for Atlas; not Atlas-track complete until then |

## Latest good commit

See `git log integration`. Tests: `services/api/.venv/bin/python -m pytest services/api/tests -q` reports 132 passed and 1 skipped. The skip is the live Perceptron check.

## Known blockers

- No `PERCEPTRON_API_KEY`: AT03 (real Perceptron call) is not met.
- No `XAI_API_KEY`: AT06 (Grok workers doing real tool calls) is met only by a scripted-client test, not live.
- No `MONGODB_URI`: Atlas persistence (AT16 on Atlas) is unverified. The same pymongo code paths run on mongomock.
- SoleScout free tier hides the cheapest sellers. Cards say so and never attach the aggregate price to a named store.
- SoleScout gives no material composition, so any material exclusion leaves results in "Needs checking".

## Deferred behind flags (off)

`FEATURE_PHOTON`, `FEATURE_VOICE` and `FEATURE_SOLANA` are all false. Those features are not built.

## Active owners

- Claude: integration, UI, API, contracts, workers, verification, redirects.
- Perception lane: `app/media`, `app/providers/perceptron`, and their tests. Follow-ups are listed in the PR #2 review comment.
- Teammate: catalog adapter. The adapter fix is described in `docs/decisions.md`.

## Next

1. Add keys to `.env` and rerun the live checks in the README.
2. Set the Atlas URI and confirm reload after a server restart.
3. Build the truth set (AT19) on real clips once Perceptron is live.
