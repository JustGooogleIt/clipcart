# Contract: persistent style memory

Status: **proposed, published early** on `feat/style-memory` so the UI lane can build against it. Backend owner: Claude. `apps/web/` is untouched by this branch. Flag: `FEATURE_STYLE_MEMORY`, default **false**. When it's off, every route below returns `404 {code: "feature_disabled"}` and search is unchanged.

Style memory is **owner-scoped**, keyed to the browser owner cookie like sessions. It persists across sessions for the same owner. One owner can never read, change or delete another owner's events or memories.

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

Lists are capped at 5 items, and `recentlyOwned` at 5. `styleModel.mode` is one of `unavailable`, `unverified` or `live`.

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

## Search personalization (when the flag is on)

- **Snapshot:** search takes a compact profile snapshot at job creation. Session preferences stay the source of truth for hard constraints. The profile never relaxes or adds a hard constraint silently.
- **Rejected offers:** hidden, with an agent event "Hid N item(s) you rejected".
- **Reordering:** stated likes and avoids reorder results within each section. Inferred ones weigh less.
- **New field:** each `Recommendation` gains an optional `personalization: string[]`, for example `["You said you like black"]` or `["Matches brands from items you saved"]`.
- **Explanations:** these come from templates. A model explanation is used only when it passes validation, which allows no prices, numbers, stock or retailer claims.
