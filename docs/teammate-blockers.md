# Teammate blockers / waiting list

Updated: 2026-10-17 (catalog branch)

## Done without further input

- [x] Live product provider proof (SoleScout)
- [x] Normalized catalog adapters + fixtures + 8 evaluation cases
- [x] Provider access + evaluation docs
- [x] PR opened: https://github.com/JustGooogleIt/clipcart/pull/1
- [x] eBay adapter skeleton (fails closed without keys)
- [x] Catalog unit tests (offline)

## Blocked / waiting on humans or Claude

| Item | Waiting on | Why | What to bring back |
| --- | --- | --- | --- |
| Align adapter to frozen contracts | **Claude** interface commit | Canonical Pydantic/OpenAPI not in repo yet | Paths + commit hash of `contracts/` |
| Wire into shopping workers / UI | **Claude** | Integration owner; teammate must not edit UI/orchestration | Merge of this PR + tool wiring |
| eBay (or second) marketplace with direct PDPs | **Credentials** | SoleScout free tier hides many retailer names; eBay needs app keys | `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET` (or chosen alt) |
| Demo clip + target garment choice | **Ashwin / product** | Needed for end-to-end matching quality | Clip file/URL + which jacket/top/bag is the target |
| Photon inbound/outbound proof | **Photon provisioning** | Separate from catalog; needs SDK/account | Confirmed bot/webhook credentials + one message round-trip log |
| Perceptron / Grok runtime keys | **Ashwin** (not teammate catalog) | Runtime AI path | Confirm when live for integration testing |
| Atlas connection for acceptance | **Claude** | Persistence not teammate-owned | Working session reload |

## Not starting yet (per SRS)

- Solana / demo checkout
- Voice
- Affiliate commission tracking as earned revenue

## Fastest unblock order for you

1. Get Claude to freeze contracts + merge/wire this catalog PR.
2. Decide demo garment + clip.
3. If retailer redirect quality is weak on SoleScout, create eBay developer app keys and re-run smoke with `CATALOG_PROVIDER=ebay`.
4. Only after core shopping works: Photon proof.
