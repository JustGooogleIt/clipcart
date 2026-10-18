import { readFileSync } from "node:fs";
import { createUmi } from "@metaplex-foundation/umi-bundle-defaults";
import { mplBubblegum } from "@metaplex-foundation/mpl-bubblegum";
import {
  createSignerFromKeypair,
  keypairIdentity,
  publicKey,
} from "@metaplex-foundation/umi";

/** Official Solana devnet genesis (Anza / getGenesisHash). */
export const DEVNET_GENESIS_HASH = "EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG";

export async function requireDevnet(umi) {
  const genesis = await umi.rpc.getGenesisHash();
  if (genesis !== DEVNET_GENESIS_HASH) {
    throw new Error(`Refusing non-devnet RPC (genesis ${String(genesis).slice(0, 12)}…)`);
  }
  return genesis;
}

/**
 * Load a Solana JSON keypair file (array of 64 bytes) with restrictive local perms.
 * Never log the secret.
 */
export function loadKeypairSigner(umi, keypairPath) {
  const raw = JSON.parse(readFileSync(keypairPath, "utf8"));
  if (!Array.isArray(raw) || raw.length < 64) {
    throw new Error("Authority keypair file must be a Solana JSON secret key array");
  }
  const secretKey = Uint8Array.from(raw.slice(0, 64));
  const kp = umi.eddsa.createKeypairFromSecretKey(secretKey);
  return createSignerFromKeypair(umi, kp);
}

export function buildUmi({ rpcUrl, authorityKeypairPath }) {
  const umi = createUmi(rpcUrl).use(mplBubblegum());
  if (authorityKeypairPath) {
    const signer = loadKeypairSigner(umi, authorityKeypairPath);
    umi.use(keypairIdentity(signer));
  }
  return umi;
}

export { publicKey };
