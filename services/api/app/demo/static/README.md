# Solana demo checkout (isolated)

Browser UI for the controlled ClipCart demo-merchant payment. Not part of `apps/web/`.

## Build the bundle

```bash
cd services/api/app/demo/static
npm install
npm run build
```

`checkout.bundle.js` is produced by esbuild with the real [`buffer`](https://www.npmjs.com/package/buffer) package injected for `@solana/web3.js`. Do not polyfill Buffer by hand.

## Smoke server

Keep `FEATURE_SOLANA=false` in `.env`. Enable only in the process:

```bash
cd services/api
FEATURE_SOLANA=true ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8020
```

Open `http://127.0.0.1:8020/demo/solana-pay`.
