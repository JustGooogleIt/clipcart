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

## v2 (additive, `feat/research-v2`)

All new fields are optional or have defaults, so v1 clients keep working.

### Providers (`RESEARCH_PROVIDER`)

| Provider | `mode` | What it does | Live status |
| --- | --- | --- | --- |
| `fixture` (default) | `fixture` | Labelled development submission | n/a |
| `solescout` | `live` (or `fixture` with the fixture catalog) | **Fallback.** Runs at most 2 catalog searches built from the observed attributes and shopper constraints, then at most 3 detail checks on the closest matches. Each **named store record** (URL, price and sizes all from that same record) becomes an offer. When SoleScout names no stores, the offer is its comparison page, with no price. | Retrieval verified live on 2026-10-17 (see below). **No independent-retailer coverage is claimed.** |
| `manual` | `manual` | Dispatches nothing. The job waits for the owner's import. | n/a |
| `grok_bot` | — | **Not implemented.** The callback round trip is unproven. See `docs/grok-bot-bridge.md`. | — |

A catalog failure fails the job with `catalog_unavailable` (retryable) instead of completing it with nothing. The existing SoleScout search (`POST /api/sessions/{id}/searches`) is unchanged and remains the main path.

### Job

- **`styleHints`:** set only when `FEATURE_STYLE_MEMORY` is on. Shape: `{colorsLike, colorsAvoid, brandsLike, brandsAvoid, materialsAvoid, tonesLike}`. These are **soft context for the researcher, never constraints.** `preferences` stays the only source of hard constraints.
- **`resultSource`:** `provider` or `manual_import`.
- **`mode`** may be `manual`, and **`provider`** may be `solescout` or `manual`.

### Submission fields (`SubmittedProduct`)

| Field | Validation |
| --- | --- |
| `imageUrl` | Kept only if it is HTTPS and passes the URL-safety check. The image is never fetched. |
| `brand` | Kept only when an `evidence` entry with `field: "brand"` contains it (`brandBasis: "page_text"`) or the source is the catalog (`"catalog_record"`). Otherwise it is dropped with a warning. Never inferred from appearance. |
| `condition` | `new`, `used`, `pre_owned` (stored as `used`) or `unknown`. Feeds the condition check. |
| `sellerKind` | `retailer`, `marketplace`, `resale` or `unknown` |
| `variants[]` | `{label, available: true|false|null, price?, priceExcerpt?}`. **Unavailable variants are kept** (`availability: "unavailable"`), never dropped. Only available ones count as in stock. A variant price needs its own excerpt. |
| `evidence[]` | `{field, excerpt}`, where `field` is title, price, availability, size, condition, brand, identifier or image. At most 12. |
| `identifiers` | `{gtin (8–14 digits), mpn, sku, styleCode, catalogRef}`. Used only for equivalence. |

### Product fields (`ResearchProduct`)

These are added: `source` (`agent`, `catalog` or `manual_import`, **set by the server, never by the submission**), `imageUrl`, `brand`, `brandBasis`, `condition`, `sellerKind`, `variants`, `evidence` and `offerGroup`. The first warning names the source, for example "From SoleScout's store record…" or "Imported manually…". Offers older than 24 h from a non-live source get a "Seen on <date>; price and stock may have changed" warning. The result limit is now 5 primary and 5 needs-checking.

### Offer comparison (`offerGroup`)

| `equivalence` | When | UI wording |
| --- | --- | --- |
| `identifier_match` | The offers share a GTIN, MPN, SKU, style code or catalog product | "Same product (`basis`)" |
| `approximate` | The same evidenced brand and a near-identical title (token Jaccard ≥ 0.75) | "Looks like the same product — not confirmed" |
| `single` | Neither | No comparison |

- **Lowest price:** `lowestConfirmedPrice` counts only offers whose price came with page text, in the shopper's currency. `isLowestConfirmed` marks that offer.
- **Uncertain prices:** `uncertainPriceCount` counts offers in the group with no confirmed price. They are shown as "Price not confirmed" and never ranked as cheapest.
- **Timing:** groups are computed before the result limit, so `offerCount` can exceed the offers shown.

### Sections for unpriced offers (answer to #26 question 7)

**An offer without a confirmed price is never Recommended (`primary`), with or without a budget.** "Confirmed" means a price that came with the page text showing it. That excludes comparison pages, prices without an excerpt, and offers with no price.

| Shopper budget | Check added | Section |
| --- | --- | --- |
| Set | `budget: unknown` ("No sourced price") | `needs_checking` |
| Not set | `price: unknown` ("Price not confirmed on the page") | `needs_checking` |

Such an offer never satisfies a budget, is never `isLowestConfirmed`, and counts toward `uncertainPriceCount`. Before this change, an unpriced offer with no budget landed in `primary`, as #26 observed with SoleScout comparison pages.

### Health mode (answer to #26 question 4)

`research.mode` in health is the mode jobs from the configured provider get:

| `RESEARCH_PROVIDER` | `mode` |
| --- | --- |
| `fixture` | `fixture` |
| `manual` | `manual` |
| `solescout` | `fixture` with `CATALOG_PROVIDER=fixture`, otherwise `live` |
| anything not implemented (`grok_bot` on integration) | `null`, because no job can start |

`mode` describes the data source. It says nothing about reachability: a `live` SoleScout job can still fail with `catalog_unavailable`.

### Typed fields (answers to #26 questions 5 and 6)

- **`ResearchJob.error`** is `JobError | null`, that is `{code, message, retryable}`.
- **`warningCodes`** (on `ResearchProduct` and on `Recommendation`) holds stable codes for the warnings ClipCart itself adds. In TypeScript the type is `NonNullable<Recommendation["warningCodes"]>[number]`, the same union as on `ResearchProduct`. The readable text stays in `warnings`.

  | Code | Where | Meaning |
  | --- | --- | --- |
  | `seller_claims_unverified` | both | Metal, stone or authenticity words are the seller's description |
  | `availability_unknown` | search | Availability unknown |
  | `fixture_data` | both | Fixture data, not a live result |
  | `price_without_page_text` | research | A price came without page text and was dropped |
  | `comparison_page` | research | A price-comparison page, not a retailer checkout |
  | `observation_stale` | research | Seen more than 24 h ago by a non-live source |
  | `brand_not_evidenced` | research | Brand not in the page evidence, so it was dropped |
  | `image_rejected` | research | Image link failed the URL check |
  | `exact_claim_unconfirmed` | research | The agent said exact match; not confirmed |

  The research product's first warning, which names the source, has no code: read `source` instead. Provider-supplied warning text, such as SoleScout disclaimers, has no code either.

### Manual import: `POST /api/research-jobs/{jobId}/import`

This is for the owner, with the `X-ClipCart-Request: 1` header and a limit of 10 per 10 minutes. The body is `{products: SubmittedProduct[] (≤20), notes?}`.

- **When it's allowed:** while the job is pending, which is how `manual` jobs wait, or **after a failed or expired job**, for example when a bridge callback failed.
- **Labelling:** products are labelled `source: "manual_import"` and `mode: "manual"`, the job gets `resultSource: "manual_import"`, and its summary starts with "Manually imported results."
- **Validation:** the same as for any submission.

| HTTP | `code` | When |
| --- | --- | --- |
| 404 | `not_found` | Not this owner's job |
| 409 | `already_completed` | The job already has results |
| 422 | `invalid_import` | Envelope invalid. The job is left as it was. |

### Rendering additions (UI)

1. **Source label:** show `source` as "From SoleScout's store record", "Found by research agent" or "Imported manually".
2. **Offer groups:** for `offerGroup.offerCount > 1`, show the group with the wording above. Mark the `isLowestConfirmed` offer "Lowest confirmed price". Never mark an offer whose `price` is null.
3. **Variants:** show unavailable variants struck through or labelled "Unavailable". Don't hide them.
4. **Brand and image:** show `brand` only when it's present, and add "(from the page)" or "(from SoleScout)" per `brandBasis`. Show `imageUrl` with `referrerpolicy="no-referrer"`.
5. **Import:** a manual import form, or a JSON paste, for failed, expired or `manual` jobs, clearly labelled "Manual import".

### Live retrieval check (2026-10-17, no key, no paid provider)

One run of the `solescout` provider covered a blue denim trucker jacket with a $300 budget. It made 5 SoleScout calls: 2 searches and 3 detail checks. All three detailed products reported **one hidden store and no named store records**, so the result was 3 SoleScout comparison-page offers. They're priced "not confirmed", labelled, and sorted into needs-checking. **On SoleScout's free tier, this run found no independent retailer offers.** Real multi-retailer and resale coverage needs a working research agent (`docs/grok-bot-bridge.md`) or eBay credentials (`docs/ebay-adapter.md`).
