# ClipCart provider access (catalog)

Owner: teammate (Cursor) — ticket T03  
Branch: `feat/catalog-access`  
Checked: 2026-10-17T20:40:36Z (UTC)

## Selected live provider: SoleScout public API

SoleScout’s no-key public JSON API returns fashion product search hits and product detail for jackets/tops/bags (and sneakers). Docs: https://solescout.ai/for-ai

| Capability | Endpoint | Auth | Status |
| --- | --- | --- | --- |
| Keyword search | `GET https://solescout.ai/api/public/search?q=...&limit=N` | None | **Working** |
| Product detail | `GET https://solescout.ai/api/public/product?slug=...` | None | **Working** |
| Image search | n/a | — | **Unsupported** (adapter returns `unsupported_capability`) |

Rate limit (documented): 60 requests/minute per IP. No signup for read endpoints.

### Real query proof

Command:

```bash
python3 scripts/catalog_smoke.py --query "denim jacket" --limit 3
```

Observed live call (2026-10-17):

| Field | Observed |
| --- | --- |
| Query | `denim jacket` |
| HTTP | 200 |
| Retrieval time | ~1.8s (search) / ~70ms (cached-ish product detail) |
| Product URL | SoleScout product page, e.g. `https://solescout.ai/product/...` |
| Image | `https://solescout.ai/api/goat-image?slug=...` |
| Price | `lowest_price_usd` integer dollars (not minor units) |
| Currency | USD implied; no ISO currency field in response |
| Variants / sizes | `sizes_in_stock[]` with `{size, lowest_price_usd}` when present |
| Stock | Inferred from non-empty `sizes_in_stock` or visible `stores`; otherwise unknown |
| Retailer identity | Often **hidden** on free tier (`stores: []` + `hidden_stores`) |

Example product detail (hoodie, live):

- Title: `032c Oversized Graphic Printed Hoodie`
- Brand: `032c`
- Price: `$100` (`lowest_price_usd`)
- Sizes in stock: `XS` only
- One visible store URL: `https://off--season.com/products/032c-oversize-mask-hoodie` with `price_usd: null`
- Cheapest retailers: names withheld (`hidden_stores.count: 2`)

Raw captured responses: `fixtures/catalog/raw/`.

### What SoleScout actually supplies vs missing

| Needed for ClipCart Listing | Provided? | Notes |
| --- | --- | --- |
| Product / offer URL | Partial | Free tier requires linking SoleScout product URL; retailer URLs often hidden |
| Image URL | Yes | Proxy image URL |
| Price + currency | Partial | USD dollars only; no `currency` field; shipping/tax absent |
| Variants | Partial | Size list only; no color/material variant IDs |
| Size availability | Partial | `sizes_in_stock`; empty list ≠ confirmed OOS |
| Stock status | Partial | No explicit `in_stock` flag |
| Material text | **No** | Must stay `null` / unknown |
| Condition | **No** | Treat as `unknown` |
| Checked-at | Client-side | We stamp `checkedAt` at retrieval |
| Image search | **No** | Unsupported |

SoleScout disclaimer (must surface): prices change daily; SoleScout is not the retailer.

### Credentials

| Variable | Required? | Purpose |
| --- | --- | --- |
| `CATALOG_PROVIDER` | No (default `solescout`) | `solescout` \| `fixture` |
| `SOLESCOUT_BASE_URL` | No | Default `https://solescout.ai` |
| `SOLESCOUT_TIMEOUT_S` | No | Default `20` |
| `EBAY_CLIENT_ID` / `EBAY_CLIENT_SECRET` | Optional next | Browse API application token (not yet verified on this account) |

See `docs/catalog.env.example`.

## eBay Browse (candidate, not yet proven)

SRS cites eBay Browse as a documented marketplace API. This environment has **no** eBay app credentials, so live Browse calls were not attempted.

Setup for the team:

1. Create an app at https://developer.ebay.com/
2. Client-credentials grant with scope `https://api.ebay.com/oauth/api_scope/buy.browse`
3. `GET /buy/browse/v1/item_summary/search` with `X-EBAY-C-MARKETPLACE-ID: EBAY_US`

If eBay credentials land, prefer eBay for **direct retailer item URLs**; keep SoleScout as a working fallback labeled honestly.

## Fallback: labeled sourced demo catalog

When live mode is unavailable or for deterministic demos, use `CATALOG_PROVIDER=fixture` and `fixtures/catalog/demo_catalog.json`. Every fixture listing sets `mode: "fixture"` or `"catalog"` and includes evidence IDs. Fixtures must never be presented as live results.

## Adapter paths (this branch)

| Path | Role |
| --- | --- |
| `services/api/app/providers/catalog/` | SoleScout + fixture adapters |
| `scripts/catalog_smoke.py` | Live or fixture smoke check |
| `fixtures/catalog/` | Demo catalog, search examples, raw live captures |
| `docs/evaluation.md` | Eight fashion truth-set cases |

**Contract note:** Claude owns canonical Pydantic models under `services/api/app/contracts/`. This branch implements against the SRS logical `CatalogProvider` interface (Section 12). After Claude freezes contracts, align imports/types without changing shopping orchestration or UI.

## Limitations (do not overclaim)

- Free SoleScout often cannot open a named merchant PDP for the cheapest offer.
- Visible store rows may omit price.
- Size systems are raw strings (shoe-like sizes appear on some apparel/bags).
- No material composition → leather exclusions cannot be auto-satisfied from this provider alone.
- Image-based search is unsupported.
- No Photon work on this branch.

## Next integration step for Claude

Wire `SoleScoutCatalogProvider` / `FixtureCatalogProvider` into shopping tools (`search_catalog`, `get_listing_details`). Keep `mode` and evidence timestamps on every recommendation card. Do not invent affiliate revenue from SoleScout links.
