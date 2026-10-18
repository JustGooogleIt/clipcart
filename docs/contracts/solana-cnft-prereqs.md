# cNFT live-mint prerequisites (PR #29)

## 1) Authority funding (exact)

**Authority:** `7DYdA9NWaGS3QxGP4uBWve5KAML4s3yZjuKDeBkpaUUT`  
**Current balance:** `0` lamports (`0 SOL`)

**Chosen tree (smallest suitable private Bubblegum V2):**

| Param | Value |
| --- | --- |
| maxDepth | 3 |
| maxBufferSize | 8 |
| canopyDepth | 3 |
| public | false |
| capacity | 8 leaves |

Costs measured from `createTreeV2` SystemProgram `createAccount` lamports + `getMinimumBalanceForRentExemption(96)` for TreeConfigV2 + fee buffer:

| Component | Lamports | SOL |
| --- | ---: | ---: |
| Merkle tree account rent (1752 bytes) | 9,550,400 | 0.009550400 |
| TreeConfigV2 rent (96 bytes) | 1,137,920 | 0.001137920 |
| Tx fee buffer (create + one mint + retries) | 100,000 | 0.000100000 |
| **Total required** | **10,788,320** | **0.010788320** |
| Authority balance | 0 | 0 |
| **Top-up required** | **10,788,320** | **0.010788320 SOL** |

Optional headroom if you prefer the Metaplex docs example (`maxDepth=5`, buffer 8, canopy 3, capacity 32): **0.013714400 SOL** total (top-up **0.013714400 SOL**).

Do **not** send 1 SOL unless you want spare gas; **~0.011 SOL** covers the depth-3 plan.

## 2) DAS-enabled devnet RPC (Bubblegum V2)

Public `https://api.devnet.solana.com` is **not** sufficient for cNFT reads (`getAsset` / proofs).

### Helius (recommended free tier)

1. Create an account at https://dashboard.helius.dev/
2. Create an API key.
3. Use the **devnet** RPC URL form:  
   `https://devnet.helius-rpc.com/?api-key=<YOUR_KEY>`
4. Put **only in local** `.env` (never commit):  
   `SOLANA_DAS_RPC_URL=https://devnet.helius-rpc.com/?api-key=<YOUR_KEY>`
5. Verify DAS methods (not just `getHealth`):

```bash
# Must return JSON result for getAsset (even if asset missing → structured DAS error/null)
curl -sS "$SOLANA_DAS_RPC_URL" -H 'content-type: application/json' -d '{
  "jsonrpc":"2.0","id":"das-1","method":"getAsset",
  "params":{"id":"11111111111111111111111111111111"}
}'

# Ordinary RPC still works on the same URL:
curl -sS "$SOLANA_DAS_RPC_URL" -H 'content-type: application/json' -d '{
  "jsonrpc":"2.0","id":1,"method":"getGenesisHash","params":[]
}'
```

A DAS-capable endpoint answers `getAsset` / `getAssetsByOwner` / `getAssetProof`. A plain Solana RPC returns `Method not found` for those.

Alternatives with DAS: Triton, Shyft, QuickNode DAS add-ons — same env var pattern.

## 3) Public metadata (private repo)

`raw.githubusercontent.com/.../clipcart/...` returns **404** while the repo is private.

**Public HTTPS host (gist; repo stays private):**

- Metadata: https://gist.githubusercontent.com/JustGooogleIt/0d8fd0741788906da0165de7a7d6a98e/raw/cnft-receipt-demo-metadata.json  
- Image: https://gist.githubusercontent.com/JustGooogleIt/0d8fd0741788906da0165de7a7d6a98e/raw/cnft-receipt-demo-mark.svg  

Both verified HTTP 200 without auth; metadata `image` points at the public SVG.

Set locally:

`SOLANA_CNFT_METADATA_BASE_URL=https://gist.githubusercontent.com/JustGooogleIt/0d8fd0741788906da0165de7a7d6a98e/raw/cnft-receipt-demo-metadata.json`

## Gate before tree/mint

- [ ] Authority balance ≥ 10,788,320 lamports  
- [ ] `SOLANA_DAS_RPC_URL` set and `getAsset` responds as DAS  
- [ ] Metadata + image URLs return 200 anonymously  
- [ ] No tree address already persisted (`SOLANA_CNFT_TREE_ADDRESS` empty; no successful `tree-create.json`)

Then: create **one** private V2 tree → persist address → mint **one** receipt to buyer `8W3Rgm2MFFkA3SP1TcUuvVaHMAPhJshZ4rdgJw2QSwjo` for preserved payment. Reconcile before any retry. No faucet retries from agents; no new checkout payment.
