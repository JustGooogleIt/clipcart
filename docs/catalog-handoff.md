# Catalog handoff for Claude (integration owner)

Branch: `feat/catalog-access`  
PR: https://github.com/JustGooogleIt/clipcart/pull/1  
Latest useful commits: catalog adapter + fixtures + provider docs

## What is ready to merge/wire

| Piece | Path | Status |
| --- | --- | --- |
| Live SoleScout search/detail | `services/api/app/providers/catalog/solescout.py` | Proven live |
| Fixture/demo catalog | `fixture_catalog.py` + `fixtures/catalog/` | Labeled `mode: fixture` |
| eBay Browse skeleton | `ebay.py` | Code ready; **blocked on credentials** |
| Factory | `factory.py` | `CATALOG_PROVIDER=solescout\|fixture\|ebay` |
| Smoke | `scripts/catalog_smoke.py` | Works |
| Evidence docs | `docs/provider-access.md`, `docs/evaluation.md` | Written |

## Interface freeze wait

This branch uses provisional TypedDicts in `providers/catalog/types.py` matching SRS §12 `Listing` / `Evidence`.

When Claude commits canonical Pydantic models under `services/api/app/contracts/`:

1. Point catalog normalization at those models (or generate from them).
2. Do **not** rewrite SoleScout field mapping unless the frozen schema differs.
3. Wire tools: `search_catalog`, `get_listing_details` (+ optional `search_by_image` → unsupported for SoleScout).
4. Preserve `mode`, `checkedAt`, `evidenceIds`, and warnings on every card.
5. Prefer eBay for direct item URLs **after** a successful credential smoke; keep SoleScout as fallback.

## Suggested integration snippet

```python
from app.providers.catalog import CatalogFilters, get_catalog_provider

provider = get_catalog_provider()  # env CATALOG_PROVIDER
result = provider.search("denim jacket", CatalogFilters(currency="USD"), limit=6)
# result.listings / result.evidence / result.mode
```

## Do not claim

- Affiliate revenue from SoleScout/eBay links
- Verified material composition from titles alone
- Fresh stock without a detail revalidation
- Photon or Solana from this PR
