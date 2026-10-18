# Contract: persistent style memory

Status: **implemented on `feat/style-memory` (draft PR #15)**, first published early so the UI lane could build against it. Backend owner: Claude. `apps/web/` is untouched by this branch. Flag: `FEATURE_STYLE_MEMORY`, default **false**. When it's off, every route below returns `404 {code: "feature_disabled"}` and search is unchanged.

Style memory is **owner-scoped**, keyed to the browser owner cookie like sessions. It persists across sessions for the same owner. One owner can never read, change or delete another owner's events or memories.

## Readiness (independent of Gemma)

| Capability | Status | Needs Gemma? |
| --- | --- | --- |
| Events, memories, correction, removal, profile, owner isolation | **Ready** behind the flag; covered by tests | No |
| Deterministic inference from saved, rejected and purchased items | **Ready** | No |
| Search personalization (hide rejected items, soft reorder, reasons) | **Ready** | No |
| `POST /api/style/notes` proposals | **Ready with the rule-based parser** (precision 1.00, recall 0.86 on the labelled set) | Optional. Gemma adds brands and phrasing variety. |
| Model-written explanation sentences | Off by default; templates are used | Yes, and **not available**: no local Gemma runtime |

The UI can ship everything above without Gemma. `styleModel.mode` tells it whether model proposals are in use.

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
| `retailer_click` | **Server only**, recorded when `/go/{token}` redirects | **Never a purchase.** It creates no memory. |
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
  "styleModel": { "mode": "unavailable", "model": "gemma4:e4b" }
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

`source` is one of `preferences_form`, `style_note`, `chat_refinement`, `saved_items`, `rejected_items` or `purchases`.

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
  "model": "gemma4:e4b",
  "proposals": [
    { "kind": "size", "value": { "raw": "M", "system": "alpha" }, "action": "set", "quote": "I'm a medium" },
    { "kind": "color_avoid", "value": "orange", "action": "add", "quote": "I hate orange" },
    { "kind": "material_avoid", "value": "leather", "action": "add", "quote": "I never wear leather" }
  ],
  "rejectedProposals": 0
}
```

`mode` is `model` (Gemma output validated in code) or `rule_based` (model unavailable or invalid). Every proposal's `quote` is checked as an exact substring of the input text. To save proposals, the UI posts each accepted one to `POST /api/style/memories` with `source: "style_note"`.

## Health

`GET /api/health` adds `features.styleMemory` and `providers.styleModel: {mode, configured, calls, failures, lastError, model, provider}`.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `FEATURE_STYLE_MEMORY` | `false` | Turns on every route and personalization |
| `STYLE_MODEL_PROVIDER` | `ollama` | Set `none` to always use the rule-based parser |
| `STYLE_MODEL` | `gemma4:e4b` | Ollama tag. Use `gemma4:e2b` if E4B is too slow (see the benchmark below) |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Local Ollama |
| `STYLE_MODEL_TIMEOUT_S` | `8` | Per-call read timeout. Connect timeout is 1.5 s. |
| `STYLE_MODEL_EXPLANATIONS` | `false` | Model-written personalization sentences. Off by default to keep search fast. |

When Ollama is down, `/api/style/notes` falls back to the rule-based parser. Measured with nothing listening on the port, that took 11 ms median and 45 ms max. Every other route never calls the model.

## Search personalization (when the flag is on)

- **Snapshot:** search takes a compact profile snapshot at job creation. Session preferences stay the source of truth for hard constraints. The profile never relaxes or adds a hard constraint silently.
- **Rejected products:** hidden, with an agent event "Hid N item(s) you rejected before". Matching uses provider + listing ID, so a search hit and its detail snapshot match.
- **Reordering:** stated likes and avoids reorder results within each section, after identity tier and before relevance. Weights are stated like +2, inferred like +1, stated avoid −3, inferred avoid −1.5. Sections and constraint checks never change, and quality gates such as the category, color-mismatch and budget filters still apply.
- **New field:** each `Recommendation` gains an optional `personalization: string[]`, for example `["You said you like black"]` or `["Matches brands from items you saved"]`.
- **Explanations:** these come from templates. A model explanation is used only when it passes validation, which allows no prices, numbers, stock or retailer claims.

## Model status (2026-10-18)

Ollama is **not installed** on the development machine, so `gemma4:e4b` and `e2b` have not been run or benchmarked. Run `scripts/experiments/style_model_bench.py --models gemma4:e4b gemma4:e2b` once they're pulled. It never pulls models itself.

Baseline for the rule-based fallback on the 10 labelled statements in that script:

| Precision | Recall | False positives | Misses |
| --- | --- | --- | --- |
| 1.00 | 0.86 | 0 | 2 (brands, which are left to the model by design) |

## Shared types (codegen plan)

`packages/contracts` is **not regenerated** on this branch. A preview regeneration (2026-10-18) showed:

- **Already stale on integration, before this PR:** the committed `index.ts` lacks the research types from merged PR #6. That's 7 interfaces and about 338 lines of diff.
- **Added by this PR, all additive:** `StyleEvent`, `StyleItem`, `StyleMemory`, `StyleProfileView`, `StyleProposal`, `ProfileEntry` and `OwnedItem`, plus optional `Recommendation.personalization?: string[]`. No existing field changes.

The plan is one regeneration commit on `integration`, after the UI lane confirms this contract, covering both the research drift and the style types:

```bash
services/api/.venv/bin/python scripts/gen_contracts.py && (cd apps/web && npm run gen:types)
```

### Hosted Gemma on Lambda (2026-10-18)

The owner authorized reusing the intentgraph Lambda vLLM endpoint for a bounded experiment, up to 20 inference calls. Result: **unavailable**.

| Check | Result |
| --- | --- |
| Configuration | All four intentgraph variables are set. The URL is `http://<loopback>:<port>/v1`, which is OpenAI-compatible by convention. Values were never printed or copied. |
| `GET /v1/models` | Connection error |
| TCP to the configured address | Refused twice, instantly |
| Diagnosis | The URL points at a local SSH tunnel to the A100 instance (intentgraph README: "reached over an authenticated tunnel"). No tunnel is running, and no instance address is recorded locally. |

As instructed, the instance was not started, resized or reconfigured, no tunnel was created, and intentgraph was not changed. **No inference calls were made (0 of 20)**, and no Lambda adapter was added, because the protocol and served model could not be confirmed live. If the tunnel is restored, the next step is an `openai_compatible` style-model provider using ClipCart-only variables (`STYLE_REMOTE_BASE_URL`, `STYLE_REMOTE_API_KEY`, `STYLE_REMOTE_MODEL`). It would be reported as "Gemma hosted on Lambda, not local" and marked `live` only after a real call succeeds.
