# cNFT live-mint prerequisites (operator checklist)

**Status:** complete for the preserved paid order. Do **not** create another tree, payment, or mint.

See freeze handoff: [`docs/solana-integration-handoff.md`](../solana-integration-handoff.md)  
Evidence: [`solana-cnft-receipts-evidence.md`](./solana-cnft-receipts-evidence.md), [`solana-cnft-live-mint-evidence.json`](./solana-cnft-live-mint-evidence.json)

## Completed

- [x] Receipt authority funded on devnet (`7DYdA9NWaGS3QxGP4uBWve5KAML4s3yZjuKDeBkpaUUT`)
- [x] `SOLANA_DAS_RPC_URL` set locally; DAS `getAsset` responds
- [x] Public metadata URL (gist) reachable
- [x] One private Bubblegum V2 tree: `HaWhPiE6wEBENDnjWZh3KH3vS8R34cpmvui25itZ6aRD`
- [x] One receipt minted to buyer `8W3Rgm2MFFkA3SP1TcUuvVaHMAPhJshZ4rdgJw2QSwjo`
- [x] DAS buyer-ownership verified

## DAS smoke (local; do not commit the URL)

```bash
curl -sS "$SOLANA_DAS_RPC_URL" -H 'content-type: application/json' -d '{
  "jsonrpc":"2.0","id":1,"method":"getGenesisHash","params":[]
}'
# expect EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG

curl -sS "$SOLANA_DAS_RPC_URL" -H 'content-type: application/json' -d '{
  "jsonrpc":"2.0","id":1,"method":"getAsset",
  "params":{"id":"HEtzjRrzUzYrSo2AaQJJsb5UXAXRXb8phLBchW7KUEhq"}
}'
# expect ownership.owner == 8W3Rgm2MFFkA3SP1TcUuvVaHMAPhJshZ4rdgJw2QSwjo
```

## Metadata

Live mint URI:

`SOLANA_CNFT_METADATA_BASE_URL=https://gist.githubusercontent.com/JustGooogleIt/0d8fd0741788906da0165de7a7d6a98e/raw/cnft-receipt-demo-metadata.json`
