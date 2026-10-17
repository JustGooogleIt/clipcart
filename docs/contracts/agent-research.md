# Contract: shopping research jobs (provider-neutral)

Status: **proposed** on `feat/grok-bot-research`. The UI owner must confirm before any `apps/web/` change. Flag `FEATURE_AGENT_RESEARCH` is off by default. The only provider today is `fixture`, which returns development data built from captured SoleScout records. The Grok Bot bridge is not proven; see `docs/grok-bot-bridge.md`.

This runs alongside, not instead of, the existing search (`POST /api/sessions/{id}/searches`), which is unchanged.

## Rendering rules

1. Show `identityTier` (`likely` or `similar`), never "verified". `matchClaim: "exact"` is what the agent said; label it "Agent says exact match (not confirmed)".
2. Show a price only when `priceBasis == "agent_observed"`, with "seen by the agent on <observedAt date>". Otherwise show "Price not confirmed".
3. Every product has `verification: "url_checked_page_not_fetched"`. ClipCart checked the link but did not open the page.
4. `mode: "fixture"` must be visibly labelled as development data.
5. Links go through `/go/{token}` like search results. `aggregator_product_page` is a comparison page, not a checkout.
6. `section: "excluded"` products have no links. Show them only as counts or reasons, if at all.

## `POST /api/sessions/{sessionId}/research-jobs`

Headers: `X-ClipCart-Request: 1`, plus the owner cookie. The body uses the session's selected garment and current preferences.

```json
{ "idempotencyKey": "uuid" }
```

Errors:

| HTTP | `code` | When |
| --- | --- | --- |
| 404 | `feature_disabled` | Flag off |
| 422 | `no_selection` | No garment selected |
| 503 | `provider_not_available` | `RESEARCH_PROVIDER` names an unimplemented provider |
| 429 | `rate_limited` | More than 10 jobs per 10 minutes |

Error body, as for all routes:

```json
{ "code": "no_selection", "message": "Select a garment first", "retryable": false, "requestId": "req_…" }
```

Pending response:

```json
{
  "job": {
    "id": "rsj_…", "sessionId": "ses_…", "provider": "fixture", "mode": "fixture", "status": "pending",
    "garment": { "garmentId": "gar_…", "garmentSource": "media", "category": "jacket", "description": "black bomber",
                 "colors": ["black"], "pattern": [], "cut": [], "details": [], "visibleText": [], "timestampMs": 2000,
                 "cropAssetId": "crp_…" },
    "preferences": { "country": "US", "currency": "USD", "maxItemPriceMinor": 15000,
                     "size": { "raw": "M", "system": "alpha" }, "colors": [], "excludedMaterials": [], "condition": "any" },
    "createdAt": "2026-10-17T22:00:00Z", "expiresAt": "2026-10-17T22:15:00Z", "finishedAt": null,
    "products": [], "rejected": [], "agentNotes": null, "error": null, "summary": null
  }
}
```

## `GET /api/research-jobs/{jobId}`

Poll until `status` is `completed`, `failed` or `expired`. A job past `expiresAt` reports `expired`, and later results are refused.

Completed response (fixture, selected garment category `top`, $150 budget, size M), with only `products[0]` shown. For a jacket, the same fixture T-shirt is rejected as `not a jacket (…)`.

```json
{
  "job": {
    "id": "rsj_…", "status": "completed", "mode": "fixture",
    "summary": "1 recommended, 1 need checking; 3 item(s) rejected",
    "products": [
      {
        "id": "rp_…", "jobId": "rsj_…", "section": "primary",
        "retailer": "Farfetch (listed by SoleScout as Grp-Ff)", "domain": "farfetch.com",
        "title": "Polo Ralph Lauren Slim Fit Cotton T-shirt White",
        "matchClaim": "similar", "identityTier": "similar",
        "price": { "amountMinor": 7400, "currency": "USD" }, "priceBasis": "agent_observed",
        "priceExcerpt": "store.price_usd=74 (SoleScout store record)",
        "availability": "in_stock", "sizesAvailable": ["XS", "S", "M", "L", "XL"],
        "constraintChecks": [
          { "constraint": "budget", "state": "satisfied", "detail": "Agent-observed price $74 within $150 budget (excludes shipping and tax)", "evidenceIds": [] },
          { "constraint": "size", "state": "satisfied", "detail": "M shown as available by the agent", "evidenceIds": [] }
        ],
        "observedAt": "2026-10-17T21:17:33Z", "validatedAt": "2026-10-17T22:00:02Z",
        "verification": "url_checked_page_not_fetched",
        "uncertainty": "Captured snapshot; price and sizes may have changed.",
        "warnings": ["Found by a research agent; ClipCart checked the link but did not open the page.",
                     "Development fixture: not live research output."],
        "links": [{ "token": "lk_…", "kind": "retailer_product_page",
                    "label": "View at Farfetch (listed by SoleScout as Grp-Ff)", "retailer": "Farfetch (listed by SoleScout as Grp-Ff)",
                    "priceNote": "$74 seen by the agent on 2026-10-17" }],
        "mode": "fixture"
      }
    ],
    "rejected": [
      { "index": 2, "reason": "product_url rejected: not https", "domain": null },
      { "index": 3, "reason": "duplicate product URL", "domain": "farfetch.com" },
      { "index": 4, "reason": "invalid productUrl: Field required", "domain": null }
    ]
  }
}
```

Failed response:

```json
{ "job": { "id": "rsj_…", "status": "failed", "products": [],
           "error": { "code": "dispatch_failed", "message": "webhook returned 401", "retryable": false } } }
```

Expired response: `status: "expired"`, `products: []`, and `summary: "No research results arrived before the job expired."`.

## Health

`GET /api/health` adds `features.agentResearch` and `research: { provider, mode }`. Both are `null` when the flag is off.
