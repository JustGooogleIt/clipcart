#!/usr/bin/env node
/**
 * ClipCart Bubblegum V2 worker CLI.
 * Speaks JSON on stdout. Secrets never printed.
 *
 * Commands:
 *   generate-authority --out <path>
 *   create-tree --rpc <url> --keypair <path> [--max-depth 5] [--max-buffer 8] [--canopy 3]
 *   build-sign-mint --rpc <url> --keypair <path> --tree <pubkey> --leaf-owner <pubkey> --name <str> --uri <str>
 *   send-signed --rpc <url> --keypair <path> --signed-tx <base64>
 *   confirm --rpc <url> --signature <sig>
 *   parse-leaf --rpc <url> --signature <sig>
 *   get-asset --das-rpc <url> --asset-id <pubkey>
 *   genesis --rpc <url>
 */
import { mkdirSync, writeFileSync, chmodSync } from "node:fs";
import { dirname } from "node:path";
import { generateSigner, none, sol } from "@metaplex-foundation/umi";
import {
  createTreeV2,
  mintV2,
  parseLeafFromMintV2Transaction,
} from "@metaplex-foundation/mpl-bubblegum";
import { dasApi } from "@metaplex-foundation/digital-asset-standard-api";
import bs58 from "bs58";
import { buildUmi, requireDevnet, DEVNET_GENESIS_HASH, publicKey } from "./umi.mjs";

function arg(name, fallback = undefined) {
  const i = process.argv.indexOf(`--${name}`);
  if (i === -1) return fallback;
  return process.argv[i + 1];
}

function out(obj) {
  process.stdout.write(JSON.stringify(obj) + "\n");
}

function fail(err) {
  out({ ok: false, error: String(err?.message || err) });
  process.exitCode = 1;
}

async function cmdGenerateAuthority() {
  const outPath = arg("out");
  if (!outPath) throw new Error("--out required");
  const umi = buildUmi({ rpcUrl: "https://api.devnet.solana.com" });
  const signer = generateSigner(umi);
  mkdirSync(dirname(outPath), { recursive: true });
  const secret = [...signer.secretKey];
  writeFileSync(outPath, JSON.stringify(secret), { encoding: "utf8", mode: 0o600 });
  chmodSync(outPath, 0o600);
  out({
    ok: true,
    publicKey: signer.publicKey,
    path: outPath,
    note: "Secret written with mode 0600. Never commit or log this file.",
  });
}

async function cmdGenesis() {
  const rpc = arg("rpc", "https://api.devnet.solana.com");
  const umi = buildUmi({ rpcUrl: rpc });
  const genesis = await requireDevnet(umi);
  out({ ok: true, genesis, expected: DEVNET_GENESIS_HASH, match: genesis === DEVNET_GENESIS_HASH });
}

async function cmdAirdrop() {
  const rpc = arg("rpc", "https://api.devnet.solana.com");
  const keypair = arg("keypair");
  const amount = Number(arg("sol", "2"));
  if (!keypair) throw new Error("--keypair required");
  const umi = buildUmi({ rpcUrl: rpc, authorityKeypairPath: keypair });
  await requireDevnet(umi);
  await umi.rpc.airdrop(umi.identity.publicKey, sol(amount), { commitment: "confirmed" });
  out({ ok: true, recipient: String(umi.identity.publicKey), sol: amount });
}

async function cmdCreateTree() {
  const rpc = arg("rpc", "https://api.devnet.solana.com");
  const keypair = arg("keypair");
  const maxDepth = Number(arg("max-depth", "5"));
  const maxBufferSize = Number(arg("max-buffer", "8"));
  const canopyDepth = Number(arg("canopy", "3"));
  if (!keypair) throw new Error("--keypair required");
  const umi = buildUmi({ rpcUrl: rpc, authorityKeypairPath: keypair });
  await requireDevnet(umi);
  const merkleTree = generateSigner(umi);
  const builder = await createTreeV2(umi, {
    merkleTree,
    maxDepth,
    maxBufferSize,
    canopyDepth,
    public: false,
  });
  const result = await builder.sendAndConfirm(umi, { confirm: { commitment: "finalized" } });
  out({
    ok: true,
    merkleTree: merkleTree.publicKey,
    treeCreator: umi.identity.publicKey,
    signature: bs58.encode(result.signature),
    maxDepth,
    maxBufferSize,
    canopyDepth,
    public: false,
    version: "bubblegum-v2",
  });
}

async function cmdBuildSignMint() {
  const rpc = arg("rpc", "https://api.devnet.solana.com");
  const keypair = arg("keypair");
  const tree = arg("tree");
  const leafOwner = arg("leaf-owner");
  const name = arg("name");
  const uri = arg("uri");
  const sellerFeeBasisPoints = Number(arg("seller-fee-bps", "0"));
  if (!keypair || !tree || !leafOwner || !name || !uri) {
    throw new Error("--keypair --tree --leaf-owner --name --uri required");
  }
  const umi = buildUmi({ rpcUrl: rpc, authorityKeypairPath: keypair });
  await requireDevnet(umi);
  const owner = publicKey(leafOwner);
  // Explicit leafOwner — never default to fee payer / identity.
  if (owner === umi.identity.publicKey) {
    // Allowed only if the buyer truly is the authority (not our demo case). Still explicit.
  }
  const builder = mintV2(umi, {
    leafOwner: owner,
    merkleTree: publicKey(tree),
    metadata: {
      name,
      uri,
      sellerFeeBasisPoints,
      collection: none(),
      creators: [],
    },
  });
  const signed = await builder.buildAndSign(umi);
  const bytes = umi.transactions.serialize(signed);
  const signature = bs58.encode(signed.signatures[0]);
  out({
    ok: true,
    signedTxBase64: Buffer.from(bytes).toString("base64"),
    signature,
    leafOwner: String(owner),
    merkleTree: tree,
    feePayer: String(umi.identity.publicKey),
    persistedBeforeBroadcast: true,
  });
}

async function cmdSendSigned() {
  const rpc = arg("rpc", "https://api.devnet.solana.com");
  const keypair = arg("keypair");
  const b64 = arg("signed-tx");
  if (!keypair || !b64) throw new Error("--keypair --signed-tx required");
  const umi = buildUmi({ rpcUrl: rpc, authorityKeypairPath: keypair });
  await requireDevnet(umi);
  const bytes = Buffer.from(b64, "base64");
  const tx = umi.transactions.deserialize(bytes);
  const sig = await umi.rpc.sendTransaction(tx, { skipPreflight: false });
  out({ ok: true, signature: bs58.encode(sig) });
}

async function cmdConfirm() {
  const rpc = arg("rpc", "https://api.devnet.solana.com");
  const signature = arg("signature");
  if (!signature) throw new Error("--signature required");
  const umi = buildUmi({ rpcUrl: rpc });
  await requireDevnet(umi);
  const sigBytes = bs58.decode(signature);
  const statuses = await umi.rpc.getSignatureStatuses([sigBytes], {
    searchTransactionHistory: true,
  });
  const st = statuses?.[0] || null;
  const confirmationStatus = st?.confirmationStatus || null;
  const err = st?.err ?? null;
  out({
    ok: true,
    signature,
    confirmationStatus,
    err,
    finalized: confirmationStatus === "finalized" && err == null,
  });
}

async function cmdParseLeaf() {
  const rpc = arg("rpc", "https://api.devnet.solana.com");
  const signature = arg("signature");
  if (!signature) throw new Error("--signature required");
  const umi = buildUmi({ rpcUrl: rpc });
  await requireDevnet(umi);
  const sigBytes = bs58.decode(signature);
  const leaf = await parseLeafFromMintV2Transaction(umi, sigBytes);
  out({
    ok: true,
    assetId: String(leaf.id),
    owner: String(leaf.owner),
    nonce: Number(leaf.nonce),
  });
}

async function cmdGetAsset() {
  const dasRpc = arg("das-rpc") || arg("rpc");
  const assetId = arg("asset-id");
  if (!dasRpc || !assetId) throw new Error("--das-rpc and --asset-id required");
  // DAS plugin is bundled with mplBubblegum in recent SDKs; also try explicit use.
  let umi = buildUmi({ rpcUrl: dasRpc });
  try {
    umi = umi.use(dasApi());
  } catch {
    /* already registered via mplBubblegum */
  }
  await requireDevnet(umi);
  const asset = await umi.rpc.getAsset(publicKey(assetId));
  out({
    ok: true,
    assetId,
    owner: asset?.ownership?.owner || asset?.owner || null,
    compression: asset?.compression || null,
    content: {
      name: asset?.content?.metadata?.name || asset?.content?.json_uri || null,
      jsonUri: asset?.content?.json_uri || null,
    },
    rawKeys: asset ? Object.keys(asset) : [],
  });
}

const cmd = process.argv[2];
const table = {
  "generate-authority": cmdGenerateAuthority,
  genesis: cmdGenesis,
  airdrop: cmdAirdrop,
  "create-tree": cmdCreateTree,
  "build-sign-mint": cmdBuildSignMint,
  "send-signed": cmdSendSigned,
  confirm: cmdConfirm,
  "parse-leaf": cmdParseLeaf,
  "get-asset": cmdGetAsset,
};

if (!cmd || !table[cmd]) {
  fail(new Error(`Unknown command. Use: ${Object.keys(table).join(" | ")}`));
} else {
  table[cmd]().catch(fail);
}
