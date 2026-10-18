# eBay Browse adapter: status and gaps

`services/api/app/providers/catalog/ebay.py` is a **skeleton that has never run live.** No eBay results have been retrieved, so ClipCart claims no eBay coverage.

## Credentials (owner)

1. **Developer account:** an eBay Developers Program account and a **Production** keyset (App ID and Cert ID).
   - **Activation:** eBay requires production keysets to handle Marketplace Account Deletion notifications. Activating them means either subscribing to that notification with an endpoint, or applying for the exemption that applies when no eBay user data is stored. ClipCart stores no eBay user data.
   - **Scope:** the Browse API's `item_summary/search` uses an application token from the client-credentials grant with scope `https://api.ebay.com/oauth/api_scope/buy.browse`.
2. **Environment:** set `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET` and optionally `EBAY_MARKETPLACE_ID` (default `EBAY_US`) in the untracked root `.env`. None of these is set today.

## Implementation gaps

| Gap | Effect |
| --- | --- |
| **Condition never mapped** (always `unknown`) | Browse's `condition` / `conditionId` is ignored, so new-versus-used constraints can't be checked, which matters for resale |
| **Shipping ignored** | `shippingOptions[].shippingCost` isn't mapped |
| **Availability, sizes and variants** | `estimatedAvailabilities`, `localizedAspects` (Size) and item groups (`itemGroupHref`) aren't read, so size constraints stay unknown |
| **Category filter unset** | Category IDs aren't mapped. Clothing and jewelry/watch categories should be passed as `category_ids`. |
| **Brand** | Search summaries don't carry brand. Item details carry it in `localizedAspects`, which isn't read. |
| **Price evidence** | The evidence for the price claim has no excerpt |
| **`_from_item` reuses the summary mapper** | Item-detail fields are missed |
| **Image search not wired** | `search_image` raises `unsupported_capability` |
| **Not combinable** | eBay can only replace SoleScout (`CATALOG_PROVIDER=ebay`). It can't run beside it. To feed research, it should run as an extra source through the research `catalog` path with `sellerKind: "marketplace"` / `"resale"`. |

## Smallest live check once credentials exist

1. One token request.
2. One `item_summary/search` for a common item, for example "denim trucker jacket", with `limit=5`.
3. One `item/{id}` detail call.

Confirm the mapping of price, condition, URL and image before claiming any eBay coverage. The Browse API has no per-call fee, but it does have rate limits.
