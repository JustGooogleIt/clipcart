# Contract: persistent style memory

Status: **agreed with the UI lane (PR #16) and implemented on `feat/style-memory` (PR #15)**. Shared types are generated in `packages/contracts`. Backend owner: Claude. `apps/web/` is untouched by this branch. Flag: `FEATURE_STYLE_MEMORY`, default **false**. When it's off, every route below returns `404 {code: "feature_disabled"}` and search is unchanged.

Style memory is **owner-scoped**, keyed to the browser owner cookie like sessions. It persists across sessions for the same owner. One owner can never read, change or delete another owner's events or memories.

## Readiness (independent of Gemma)

| Capability | Status | Needs Gemma? |
| --- | --- | --- |
| Events, memories, correction, removal, profile, owner isolation | **Ready** behind the flag; covered by tests | No |
| Deterministic inference from saved, rejected and purchased items | **Ready** | No |
| Search personalization (hide rejected items, soft reorder, reasons) | **Ready** | No |
| `POST /api/style/notes` proposals | **Ready with the rule-based parser** (precision 0.94, recall 0.68 on the 18 labelled statements) | Optional. Hosted Gemma 12B was measured at precision 0.76, recall 0.73 (see below). |
| Model-written explanation sentences | Off by default; templates are used | Yes. Not run against hosted Gemma in this PR. |

The UI can ship everything above without Gemma. **The rule-based parser is the default** (`STYLE_MODEL_PROVIDER=none`), because it was more precise than hosted Gemma on the benchmark below. `styleModel` tells the UI which reader is in use.

## Agreed with the UI lane (answers to PR #16's questions)

1. **Panel corrections use `source: "style_panel"`.** It is a new, additive value; `preferences_form` stays valid for the preferences form.
2. **Correcting a like/avoid value is `POST` the new memory, then `DELETE` the old one.** Post first, so a failed delete leaves both visible rather than neither. For `size`, `fit` and `budget_max`, a `POST` alone is enough, because the newer stated memory overrides the older one (`overridden` lists it).
3. **`retailer_click` items now carry `domain`.** It is the host the shopper was sent to, falling back to the listing's URL host.
4. **Rule-parser quotes stop at the last matched word.** "I love brown, I hate orange" now quotes `love brown`, not `love brown, I`.
5. **`Recommendation.personalization` is in `packages/contracts`,** along with every style record and the two response shapes below. The UI should import these instead of its hand-written copies.

**Model honesty in the UI.** Describe the reader from `styleModel.label` and `styleModel.hosting`, not a hard-coded "local model". A `remote` reader is never "local" or "on-device". With the default configuration, `styleModel` is `{mode: "unavailable", provider: "none", label: "Rule-based parser only"}`.

## Concepts

- **Event:** an append-only fact about what the shopper did or said. Events are the history.
- **Memory:** a preference derived from events. It's either `stated` (the shopper said it) or `inferred` (derived by deterministic rules from saved, rejected or purchased items). Every memory keeps its `source`, its timestamps and the event IDs it came from.
- **Profile:** a compact summary built from active memories. It's what search uses, never the full event history.

### Event types

| `type` | How it's created | Notes |
| --- | --- | --- |
| `explicit_preference` | `POST /api/style/memories` | Also creates a `stated` memory |
| `saved_item` | `POST /api/style/events` with a result you saw | Server copies brand, title and domain from the stored listing. The client can't supply them. |
| `rejected_item` | `POST /api/style/events` | That listing's offer is hidden from your future results |
| `retailer_click` | **Server only**, recorded when `/go/{token}` redirects | **Never a purchase.** It creates no memory. `item.domain` is the host the shopper was sent to. |
| `user_confirmed_purchase` | `POST /api/style/events`, after the shopper confirms they bought it | A user statement. ClipCart doesn't verify it. |
| `verified_order` | **Server only**, from a verified ClipCart demo order | Can't be created through the API |

Posting `retailer_click` or `verified_order` to the API returns `422 {code: "event_type_not_allowed"}`.

### Memory kinds

| `kind` | `value` | Cardinality |
| --- | --- | --- |
| `size` | `{ "raw": "M", "system": "alpha" }` | One active |
| `fit` | `"womens"`, `"mens"` or `"unisex"` | One active |
| `budget_max` | `{ "amountMinor": 15000, "currency": "USD" }` | One active |
| `color_like` / `color_avoid` | color word, e.g. `"black"` | Many |
| `material_avoid` / `material_like` | e.g. `"leather"` | Many |
| `brand_like` / `brand_avoid` | brand name as listed | Many |

### Rules

1. **Stated overrides inferred.** A stated memory conflicting with an inferred one marks the inferred one `overridden`, for example stated `color_avoid: orange` over inferred `color_like: orange`. Inference never overrides a stated memory.
2. **Latest stated wins.** For one-active kinds, and for like/avoid pairs, a newer stated memory marks the older one `overridden` and sets `overriddenBy`.
3. **Removal is final for inference.** `DELETE` sets `status: "removed"`, and the same kind and value won't be inferred again from existing events. Re-stating it is allowed.
4. **Inference rules are deterministic and need repeated evidence.** A brand or color seen in 2 or more saved items becomes `*_like`, and in 2 or more rejected items becomes `*_avoid`. One confirmed purchase or verified order gives `brand_like`. Clicks never produce memories.
5. The model never writes memories. It may only *propose* updates from text, which code validates. The client then saves the ones the shopper accepts.

## Endpoints

All need the owner cookie. Mutations also need `X-ClipCart-Request: 1` and accept an optional `idempotencyKey`. Errors use the standard body `{code, message, retryable, requestId}`.

### `GET /api/style/profile`

The `profile` object is validated against `StyleProfileView` before it's returned.

```json
{
  "profile": {
    "size": { "value": { "raw": "M", "system": "alpha" }, "origin": "stated", "memoryId": "mem_…" },
    "fit": null,
    "budgetMax": { "value": { "amountMinor": 15000, "currency": "USD" }, "origin": "stated", "memoryId": "mem_…" },
    "colorsLike": [{ "value": "black", "origin": "inferred", "memoryId": "mem_…", "evidenceCount": 2 }],
    "colorsAvoid": [{ "value": "orange", "origin": "stated", "memoryId": "mem_…" }],
    "materialsAvoid": [{ "value": "leather", "origin": "stated", "memoryId": "mem_…" }],
    "materialsLike": [],
    "brandsLike": [{ "value": "Alpha Industries", "origin": "inferred", "memoryId": "mem_…", "evidenceCount": 1 }],
    "brandsAvoid": [],
    "recentlyOwned": [{ "title": "Alpha Industries MA-1 Bomber", "brand": "Alpha Industries", "source": "user_confirmed_purchase", "at": "2026-10-18T…Z" }],
    "rejectedOfferCount": 3,
    "updatedAt": "2026-10-18T…Z"
  },
  "styleModel": { "mode": "unavailable", "provider": "none", "model": null, "hosting": null, "label": "Rule-based parser only" }
}
```

Lists are capped at 5 items, and `recentlyOwned` at 5. `styleModel.mode` is one of `unavailable` (feature or provider off), `unverified` (configured, no successful call yet) or `live` (a real call succeeded since startup). The internal list of rejected product keys is never returned; only `rejectedOfferCount` is.

### `GET /api/style/memories?status=active|overridden|removed|all`

Defaults to `active`.

```json
{ "memories": [
  { "id": "mem_…", "kind": "color_avoid", "value": "orange", "origin": "stated", "source": "style_note",
    "status": "active", "sourceEventIds": ["sev_…"], "evidenceCount": 1, "overriddenBy": null,
    "createdAt": "2026-10-18T…Z", "updatedAt": "2026-10-18T…Z" }
] }
```

`source` is one of `preferences_form`, `style_panel`, `style_note`, `chat_refinement`, `saved_items`, `rejected_items` or `purchases`. Clients may post only the first four; the last three belong to inferred memories.

### `POST /api/style/memories` (explicit preference)

```json
{ "kind": "color_avoid", "value": "orange", "source": "style_note", "idempotencyKey": "uuid" }
```

Returns `201 {memory, overridden: [mem ids]}`. A value that isn't in the allowed vocabulary returns `422 invalid_memory`.

### `DELETE /api/style/memories/{id}`

Returns `{ "memory": { …, "status": "removed" } }`. Another owner's ID returns `404`.

### `POST /api/style/events`

```json
{ "type": "saved_item", "recommendationId": "rec_…", "idempotencyKey": "uuid" }
```

`type` is `saved_item`, `rejected_item` or `user_confirmed_purchase`. The server resolves the recommendation and its listing for this owner, otherwise `404`. It returns `201 {event, inferredChanges: {added: [...], updated: [...], removed: [...]}}`.

```json
{ "event": { "id": "sev_…", "type": "saved_item", "origin": "stated", "source": "result_card",
             "occurredAt": "2026-10-18T…Z",
             "item": { "recommendationId": "rec_…", "listingId": "lst_…", "offerKey": "solescout:…",
                       "title": "Black Nylon Bomber Jacket", "brand": "Acme", "domain": "solescout.ai" } },
  "inferredChanges": { "added": ["mem_…"], "updated": [], "removed": [] } }
```

### `GET /api/style/events?limit=50`

Newest first: `{ "events": [ … ] }`.

### `DELETE /api/style/events/{id}`

Removes the event and re-derives inferred memories. Stated memories created from it stay until deleted separately. Returns `{ "deleted": "sev_…", "inferredChanges": {…} }`.

### `POST /api/style/notes`

Proposes memory updates from text and **saves nothing**.

```json
{ "text": "I'm a medium, I hate orange and I never wear leather" }
```

```json
{
  "mode": "model",
  "model": "gaunernst/gemma-3-12b-it-int4-awq",
  "hosting": "remote",
  "provider": "Gemma hosted on Lambda (not local)",
  "proposals": [
    { "kind": "size", "value": { "raw": "M", "system": "alpha" }, "action": "set", "quote": "I'm a medium" },
    { "kind": "color_avoid", "value": "orange", "action": "add", "quote": "I hate orange" },
    { "kind": "material_avoid", "value": "leather", "action": "add", "quote": "I never wear leather" }
  ],
  "rejectedProposals": 0,
  "note": null,
  "usage": { "wallMs": 2176, "promptTokens": 357, "completionTokens": 95 }
}
```

`mode` is `model` (Gemma output validated in code) or `rule_based` (model unavailable or invalid). `hosting` is `local` (Ollama), `remote` (hosted endpoint) or `null` when the rule parser answered; the UI must not call a `remote` model "on-device" or "local". `provider` is a display label. `usage` is present only for model answers, and token counts only when the server reports them. Every proposal's `quote` is checked as an exact substring of the input text. To save proposals, the UI posts each accepted one to `POST /api/style/memories` with `source: "style_note"`.

## Health

`GET /api/health` adds `features.styleMemory` and `providers.styleModel: {mode, configured, calls, failures, lastError, model, provider, hosting, label}`. `provider` is `ollama`, `openai_compatible`, `none` or `null` (feature off). `hosting` is `local` or `remote`. `mode` turns `live` only after a real call succeeds.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `FEATURE_STYLE_MEMORY` | `false` | Turns on every route and personalization |
| `STYLE_MODEL_PROVIDER` | `none` | `none` (rule-based parser, the default), `ollama` (local) or `openai_compatible` (hosted, e.g. vLLM) |
| `STYLE_MODEL` | `gemma4:e4b` | Ollama tag. Use `gemma4:e2b` if E4B is too slow (see the benchmark below) |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Local Ollama |
| `STYLE_MODEL_TIMEOUT_S` | `8` | Per-call read timeout. Connect timeout is 1.5 s. |
| `STYLE_MODEL_EXPLANATIONS` | `false` | Model-written personalization sentences. Off by default to keep search fast. |
| `STYLE_REMOTE_BASE_URL` | unset | OpenAI-compatible base URL ending in `/v1`. Hosted provider only. |
| `STYLE_REMOTE_API_KEY` | unset | Bearer key for that endpoint. Process environment or untracked `.env` only. Without it the provider is `unavailable`. |
| `STYLE_REMOTE_MODEL` | unset | Served model id, e.g. `gaunernst/gemma-3-12b-it-int4-awq` |
| `STYLE_REMOTE_LABEL` | `Gemma hosted on Lambda (not local)` | Display label in health and note responses |
| `STYLE_REMOTE_JSON_MODE` | `prompt` | `prompt` asks for JSON and extracts it; `schema` sends `response_format` json_schema, for servers whose guided decoding works |
| `STYLE_REMOTE_MAX_TOKENS` | `300` | Output cap per call. The hosted read timeout is at least 20 s. |

When a configured model is down, `/api/style/notes` falls back to the rule-based parser. Measured with nothing listening on the port, that took 11 ms median and 45 ms max. Every other route never calls the model.

## Search personalization (when the flag is on)

- **Snapshot:** search takes a compact profile snapshot at job creation. Session preferences stay the source of truth for hard constraints. The profile never relaxes or adds a hard constraint silently.
- **Rejected products:** hidden, with an agent event "Hid N item(s) you rejected before". Matching uses provider + listing ID, so a search hit and its detail snapshot match.
- **Reordering:** stated likes and avoids reorder results within each section, after identity tier and before relevance. Weights are stated like +2, inferred like +1, stated avoid −3, inferred avoid −1.5. Sections and constraint checks never change, and quality gates such as the category, color-mismatch and budget filters still apply.
- **New field:** each `Recommendation` gains an optional `personalization: string[]`, for example `["You said you like black"]` or `["Matches brands from items you saved"]`.
- **Explanations:** these come from templates. A model explanation is used only when it passes validation, which allows no prices, numbers, stock or retailer claims.

## Model status (2026-10-18)

Ollama is **not installed** on the development machine, so `gemma4:e4b` and `e2b` have not been run locally. Run `scripts/experiments/style_model_bench.py --models gemma4:e4b gemma4:e2b` once they're pulled. It never pulls models itself.

Hosted Gemma 3 12B (AWQ int4 on a Lambda A10, vLLM 0.9.2) was measured on 18 labelled statements. Labels are (kind, value, action), written before any call, and the scores count only output that passed validation. Full setup, per-case output and reproduction commands are in `docs/experiments/hosted-gemma-a10/`.

| | Rule parser | Hosted Gemma 12B int4 |
| --- | --- | --- |
| Precision | 0.94 | 0.76 |
| Recall | 0.68 | 0.73 |
| False positives / misses | 1 / 7 | 5 / 6 |
| Malformed responses | n/a | 0 of 18 |
| Proposals rejected by validation | n/a | 8 |
| Median / p95 latency | under 1 ms | 1,017 / 3,910 ms |
| Tokens (prompt / completion) | | 6,366 / 1,012 |

The model's main error is reading an avoid ("I never wear leather") as a **remove** of that avoid, in 3 cases. Because notes only propose and the UI saves each accepted proposal explicitly, this cannot change memory on its own. The UI should still show `remove` proposals distinctly. Quote validation caught a prompt-echo answer (5 invented proposals) and an ambiguous size. Recommendation: keep the rule parser as the default; revisit hosted Gemma after rewording the action guidance in the prompt and re-running this benchmark.

## Shared types

`packages/contracts` was regenerated once on this branch, from `scripts/gen_contracts.py` and `npm run gen:types`. The TypeScript diff is purely additive: 572 lines added, none removed.

- **Research drift from PR #6:** `ResearchJob`, `ResearchSubmission` and their parts, which were already missing on `integration`.
- **Style records:** `StyleEvent`, `StyleItem`, `StyleMemory`, `StyleProfileView`, `StyleProposal`, `ProfileEntry`, `OwnedItem`.
- **Style responses:** `StyleModelInfo` (`profile.styleModel` and the reader fields of health) and `StyleNoteResult` with `StyleNoteUsage` (`POST /api/style/notes`). The routes build these through the Pydantic models, so the wire shape can't drift from the types.
- **Recommendation:** optional `personalization?: string[]`.

To regenerate after a contract change:

```bash
services/api/.venv/bin/python scripts/gen_contracts.py && (cd apps/web && npm run gen:types)
```

## Regression cases for a later model run

`scripts/experiments/style_regression_cases.json` holds Gemma's action-interpretation failures from the A10 run, with the raw output recorded, plus unrun variants of the same patterns. Run them with `style_model_bench.py --set regression` (or `--set all`). Validation checks grounding, not intent, so a misread `remove` passes it. A test replays the recorded output to keep that visible. The UI must therefore show `remove` proposals distinctly and save nothing without the shopper's choice.

## Hosted Gemma on Lambda (2026-10-18)

The intentgraph endpoint was unreachable, because its tunnel was down and its host key had changed, so it was not used. The owner then created a temporary Lambda A10 (24 GB) instance for this experiment, which the owner terminates after the run.

- **Served:** `gaunernst/gemma-3-12b-it-int4-awq` at revision `3b0c67b98eee8fb90633ef1bfbf3d39f43b9cf9d`. The server was vLLM 0.9.2 with Transformers pinned to 4.53.2, a 4,096-token context, one concurrent request, and an API key, bound to the instance's loopback and reached through a localhost SSH tunnel.
- **GPU verified:** the vLLM process held 20.7 GB of A10 memory, the server log showed about 43 generated tokens per second, and it counted 18 successful completions for the 18 benchmark calls.
- **Adapter:** `OpenAICompatibleStyleModel` in `app/style/model.py`, selected with `STYLE_MODEL_PROVIDER=openai_compatible`. Ollama and the rule-based fallback are unchanged, and every validation and purchase guard still applies to its output.
- **Smoke test:** an isolated ClipCart on its own port used the in-memory database, no `.env`, and environment set only in the process. Health showed `unverified` with hosting `remote` before the call. `POST /api/style/notes` returned 3 grounded proposals in 2.2 s, saved nothing, and health then showed `live`.
- **Call budget:** 19 of the 20 authorized calls were used, 18 for the benchmark and 1 for the smoke test.
