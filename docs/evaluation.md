# ClipCart evaluation truth set (catalog / product evidence)

Owner: teammate (Cursor) — ticket T03  
Provider mode for live rows: SoleScout public API (captured 2026-10-17)  
Media clips for perception are owned separately; this file focuses on **listing evidence** cases.

Every case records whether identity is known, what the provider returned, and what remains unknown. Empty or uncertain results are valid outcomes.

## Cases

| ID | Intent | Query / seed | Expected shopping behavior | Evidence source | Identity known? |
| --- | --- | --- | --- | --- | --- |
| E01 | Exact / strong brand listing | `white cotton t-shirt` → Polo Ralph Lauren slim tee | Useful top result with price + image + URL | Live SoleScout search + detail `3-pack-classic-slim-crew-tee-nscnp3whd` | Brand/title yes; SKU-style code yes; not creator-linked verified match |
| E02 | Over-budget original | `black nylon bomber jacket` → CECILIE BAHNSEN bomber `$1810` | May appear as “original found / over budget”, not in ≤$120 set | Live SoleScout | Likely brand match only |
| E03 | Unavailable / missing size | `032c hoodie` detail: sizes_in_stock = `XS` only | User size `M` → size **unknown/violated**, not silently OK | Live product detail | Brand yes |
| E04 | Visually similar, different item | Denim jacket C2H4 vs Our Legacy bomber vs Prada Re-Nylon | Alternatives worker may return similar; must not label verified identical | Live search `denim jacket` / `black nylon bomber jacket` | No cross-item identity |
| E05 | Bag under budget | `canvas tote bag` → adidas Y-3 canvas tote ~`$93` | Qualifying similar option if constraints allow | Live SoleScout | Brand yes |
| E06 | Material exclusion (leather) | `about:blank leather jacket` | Title implies leather → exclude when user says “no leather”; picture alone insufficient for “not leather” | Live detail `about-blank-leather-jacket-ss26036brn` | Material from title text only (weak) |
| E07 | Empty / weak size+stock | `amiri canvas tote` / quilted handbag with `sizes_in_stock: []` | Availability **unknown**; do not claim in stock | Live SoleScout | Brand maybe; stock unknown |
| E08 | No useful match for absurd query | `neon holographic scuba tuxedo jacket size zzz` (fixture scenario) | `no_match` or empty normalized list; no invented URLs | Fixture `search_examples.json` | n/a |

## Held-out checks (do not tune prompts against these)

1. Unfamiliar query: `quilted black handbag` — sparse results (`total: 6`); some price nulls.
2. Faux-leather moto: Calvin Klein Jeans faux leather moto `$209`, size `XXS` only — tests material wording + size miss.

## Acceptance mapping

| SRS AT | Catalog contribution |
| --- | --- |
| AT08 | Verified-match only with creator link / SKU evidence / human confirm — SoleScout brand+title alone → **likely/similar** |
| AT09 | Over-budget and leather-title cases in E02/E06 |
| AT10 | Missing size/stock labeled unknown in E03/E07 |
| AT14 | Prices/URLs tied to captured evidence + `checkedAt` |
| AT19 | Eight cases above + two held-outs |

## Machine-readable examples

See `fixtures/catalog/search_examples.json` and `fixtures/catalog/demo_catalog.json` (`mode` labeled `fixture` / `catalog`).

## Outcomes log (fill during integration)

| Case | Date | Mode | Result summary | Pass? |
| --- | --- | --- | --- | --- |
| E01 | 2026-10-17 | live | Search returned Polo tee @ $55 with image + SoleScout URL | pending UI |
| E02 | 2026-10-17 | live | Bomber @ $1810 observed | pending UI |
| E03 | 2026-10-17 | live | Hoodie XS-only observed | pending UI |
| E04–E08 | 2026-10-17 | live/fixture | Captured / authored | pending UI |
