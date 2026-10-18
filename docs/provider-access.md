# ClipCart provider access (catalog)

Owner: teammate (Cursor) — ticket T03  
Branch: `feat/catalog-honest-destinations` (base: `integration`)  
Checked: 2026-10-17 (honesty rules + Farfetch demo offer)

## Selected live provider: SoleScout public API

SoleScout’s no-key public JSON API returns fashion product search hits and product detail for jackets/tops/bags (and sneakers). Docs: https://solescout.ai/for-ai

| Capability | Endpoint | Auth | Status |
| --- | --- | --- | --- |
| Keyword search | `GET https://solescout.ai/api/public/search?q=...&limit=N` | None | **Working** |
| Product detail | `GET https://solescout.ai/api/public/product?slug=...` | None | **Working** |
| Image search | n/a | — | **Unsupported** (adapter returns `unsupported_capability`) |

Rate limit (documented): 60 requests/minute per IP. No signup for read endpoints.

### Purchase destination honesty

SoleScout often exposes an aggregate `lowest_price_usd` from **hidden** retailers while only showing a different store’s link (sometimes with `price_usd: null`).

| `destinationKind` | When | `canonicalUrl` | `price` |
| --- | --- | --- | --- |
| `retailer_offer` | Same visible `stores[]` row has `url` + `price_usd` (+ requested size if any) | That store URL | That store’s `price_usd` |
| `comparison` | Otherwise (search hits, hidden-only lowest, unpriced visible store) | SoleScout product page | Aggregate lowest (labeled); **not** checkout |

Never pair hidden/aggregate lowest with a different store URL. Never label a SoleScout product page as retailer checkout.

### Demo: real direct retailer link (top)

```bash
python3 scripts/catalog_smoke.py \
  --detail 3-pack-classic-slim-crew-tee-nscnp3whd --variant M
```

| Field | Value |
| --- | --- |
| Demo query | `polo ralph lauren t-shirt` (then `get_details` on the slim tee slug) |
| Slug | `3-pack-classic-slim-crew-tee-nscnp3whd` |
| Destination kind | `retailer_offer` |
| Retailer | `Grp-Ff` (Farfetch) |
| Destination URL | `https://www.farfetch.com/us/shopping/men/polo-ralph-lauren-slim-fit-3-pack-t-shirts-set-of-three-item-39280997.aspx` |
| Store price | **$74** (Farfetch) |
| Aggregate lowest | $55 from **hidden** retailers — must not be shown as the Farfetch price |

Meta: `fixtures/catalog/demo_direct_retailer.json`.  
Raw: `fixtures/catalog/raw/product_3-pack-classic-slim-crew-tee-nscnp3whd.json`.

### Counter-example (comparison only)

`032c` hoodie: visible Offseason URL has `price_usd: null` → adapter returns `destinationKind: comparison` to the SoleScout page, not Offseason checkout.

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
| `CATALOG_PROVIDER` | No (default `solescout`) | `solescout` \| `fixture` \| `ebay` |
| `SOLESCOUT_BASE_URL` | No | Default `https://solescout.ai` |
| `SOLESCOUT_TIMEOUT_S` | No | Default `20` |
| `EBAY_CLIENT_ID` / `EBAY_CLIENT_SECRET` | Required for `ebay` | Browse API application token (**not yet verified**) |

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
