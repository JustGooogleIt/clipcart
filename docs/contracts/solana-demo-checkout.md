# Contract: Solana demo merchant checkout (devnet)

Status: implemented on `feat/solana-demo-checkout` (payment + verification only). Bubblegum / compressed NFT minting is **out of scope** for this PR. After a verified payment, `receiptStatus` becomes `eligible` and stays there.

Flag `FEATURE_SOLANA` is **off by default**. While off, every demo route returns `404` with `code: "feature_disabled"` (including `GET /api/demo-catalog`).

External SoleScout / retailer listings keep the existing `/go/{token}` path. They cannot create demo orders. A paid demo order never claims retailer fulfillment, shipment, or affiliate revenue.

UI copy before signing: **Demo purchase on Solana devnet**, fixed amount, recipient, merchant label, test-funds warning, and no-fulfillment terms.

## Enums (SRS §12)

- `status`: `created` | `awaiting_payment` | `verifying` | `paid` | `expired` | `failed`
- `receiptStatus`: `ineligible` | `eligible` | `minting` | `confirmed` | `failed` | `needs_reconciliation`
- This PR only transitions `receiptStatus`: `ineligible` → `eligible` after independent payment verification. It does not mint.

## Env (names only)

```text
FEATURE_SOLANA=false
SOLANA_NETWORK=devnet
SOLANA_RPC_URL=https://api.devnet.solana.com
SOLANA_DEMO_MERCHANT_WALLET=     # public pubkey; required when flag is on
SOLANA_DEMO_AMOUNT_LAMPORTS=10000000
SOLANA_DEMO_ORDER_TTL_S=900
```

Do not put seed phrases or private keys in env files committed to git.

## `GET /api/demo-catalog`

Requires the owner cookie (created if missing). Flag must be on.

```json
{
  "network": "devnet",
  "featureEnabled": true,
  "items": [
    {
      "id": "demo_item_clipcart_jacket_01",
      "merchantId": "clipcart_demo",
      "merchantLabel": "ClipCart demo merchant",
      "title": "ClipCart Demo Jacket (devnet)",
      "description": "Participating ClipCart demo merchant item for a wallet-approved Solana Pay transfer on devnet. Not a SoleScout listing.",
      "amountAtomic": "10000000",
      "amountDisplay": "0.01 SOL",
      "assetMint": null,
      "network": "devnet",
      "fulfillmentTerms": "Demo only. No shipment or retailer fulfillment. Test SOL on Solana devnet. This is not a SoleScout or third-party retailer purchase.",
      "eligibleForCheckout": true
    }
  ],
  "warnings": [
    "Demo purchase on Solana devnet",
    "Uses test funds only",
    "Does not purchase or fulfill external retailer listings"
  ]
}
```

Flag off:

```json
{ "code": "feature_disabled", "message": "Solana demo checkout is turned off", "retryable": false, "requestId": "req_…" }
```

## `POST /api/demo-orders`

Headers: `X-ClipCart-Request: 1`, owner cookie. Body accepts **only** `catalogItemId` and optional `idempotencyKey`. Extra fields (amount, recipient, mint, listingId, recommendationId) are rejected (`422`).

```json
{ "catalogItemId": "demo_item_clipcart_jacket_01", "idempotencyKey": "uuid" }
```

### Created / awaiting payment

```json
{
  "order": {
    "id": "dmo_…",
    "catalogItemId": "demo_item_clipcart_jacket_01",
    "merchantId": "clipcart_demo",
    "merchantLabel": "ClipCart demo merchant",
    "recipientWallet": "<SOLANA_DEMO_MERCHANT_WALLET>",
    "buyerWallet": null,
    "network": "devnet",
    "assetMint": null,
    "amountAtomic": "10000000",
    "paymentReference": "<base58 reference pubkey>",
    "expiresAt": "2026-10-17T22:15:00Z",
    "status": "awaiting_payment",
    "paymentSignature": null,
    "receiptStatus": "ineligible",
    "receiptAssetId": null,
    "createdAt": "2026-10-17T22:00:00Z",
    "updatedAt": "2026-10-17T22:00:00Z",
    "fulfillmentTerms": "Demo only. No shipment or retailer fulfillment. …",
    "uiLabel": "Demo purchase on Solana devnet",
    "explorerPaymentUrl": null
  },
  "transferRequest": {
    "recipient": "<merchant>",
    "amount": "0.01",
    "splToken": null,
    "reference": "<same as paymentReference>",
    "label": "ClipCart demo merchant",
    "message": "ClipCart demo order dmo_…",
    "memo": null
  }
}
```

| HTTP | `code` | When |
| --- | --- | --- |
| 404 | `feature_disabled` | Flag off |
| 404 | `not_found` | Unknown `catalogItemId` |
| 503 | `solana_not_configured` | Merchant wallet / RPC / amount misconfigured |
| 429 | `rate_limited` | More than 10 creates / 10 minutes / owner |

## `GET /api/demo-orders/{id}`

Owner-scoped. Other owners get `404 not_found`. Pending orders include `transferRequest`.

### Expired

When `expiresAt` has passed and the order was not paid:

```json
{
  "order": {
    "id": "dmo_…",
    "status": "expired",
    "receiptStatus": "ineligible",
    "paymentSignature": null
  }
}
```

## `POST /api/demo-orders/{id}/verify`

Headers: `X-ClipCart-Request: 1`. Body fields are optional hints:

```json
{ "paymentSignature": "<base58>", "buyerWallet": "<base58>" }
```

Server checks `getGenesisHash` against Solana **devnet**, finds transactions by Solana Pay `paymentReference` (and optional signature hint), and independently confirms: successful confirmed/finalized tx, exact native SOL lamports, configured merchant recipient, reference account present, buyer source wallet, and order not expired. Client values are never treated as proof.

### Paid

```json
{
  "order": {
    "id": "dmo_…",
    "status": "paid",
    "buyerWallet": "<source>",
    "paymentSignature": "<sig>",
    "receiptStatus": "eligible",
    "receiptAssetId": null,
    "explorerPaymentUrl": "https://explorer.solana.com/tx/<sig>?cluster=devnet",
    "network": "devnet",
    "amountAtomic": "10000000",
    "uiLabel": "Demo purchase on Solana devnet"
  }
}
```

Repeating verify on an already-paid order returns the same paid order (`200`).

### Unconfirmed / missing (retryable)

```json
{
  "code": "payment_unconfirmed",
  "message": "payment not yet confirmed",
  "retryable": true,
  "requestId": "req_…",
  "order": { "id": "dmo_…", "status": "awaiting_payment", "receiptStatus": "ineligible" }
}
```

`payment_missing` and `rpc_unavailable` are also retryable; order stays `awaiting_payment`.

### Mismatch (not paid)

```json
{
  "code": "payment_mismatch",
  "message": "no native SOL transfer matching recipient and amount",
  "retryable": false,
  "requestId": "req_…",
  "order": { "id": "dmo_…", "status": "failed", "receiptStatus": "ineligible" }
}
```

### Signature reuse

```json
{
  "code": "signature_reused",
  "message": "This payment signature is already claimed by another order",
  "retryable": false,
  "requestId": "req_…"
}
```

One on-chain transaction cannot mark two orders paid.

## Wallet / UI notes

1. Connect a **devnet** wallet only after showing merchant, amount, network, and demo terms.
2. Build a Solana Pay transfer using `transferRequest` (native SOL, `splToken: null`, include `reference`).
3. After wallet approval, call verify with the signature as a hint; poll GET until `paid`, `expired`, or `failed`.
4. Do not show an NFT as minted in this PR. `receiptStatus: "eligible"` means minting may happen in a later PR.
