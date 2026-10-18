/**
 * Solana demo merchant checkout: API calls and the Phantom transfer.
 * Contracts: docs/contracts/solana-demo-checkout.md and docs/contracts/solana-cnft-receipts.md (PR #13 and #29).
 *
 * The server prices the order and verifies payment on devnet. Nothing the browser sends is proof: the signature and
 * wallet passed to verify are hints. Only the one controlled demo catalog item can be ordered; retailer listings
 * cannot.
 */
import type { DemoCatalogItem, DemoMerchantOrder, DemoReceipt, DemoTransferRequest } from "@contracts";
import { ApiError } from "./api";

export const DEVNET_RPC = "https://api.devnet.solana.com";
export const DEVNET_GENESIS = "EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG";
export const DEMO_LABEL = "Devnet · Test funds · No retailer fulfillment";

export type DemoOrder = DemoMerchantOrder;
export type ReceiptStatus = DemoMerchantOrder["receiptStatus"];
export type { DemoCatalogItem, DemoReceipt };

export interface OrderView {
  order: DemoOrder;
  transferRequest?: DemoTransferRequest;
  receipt?: DemoReceipt;
}

/** A refused verify still carries the order, so the page can show what the server now says. */
export class VerifyError extends ApiError {
  constructor(status: number, code: string, message: string, retryable: boolean, public order?: DemoOrder) {
    super(status, code, message, retryable);
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      credentials: "same-origin",
      headers: { ...(method !== "GET" ? { "X-ClipCart-Request": "1" } : {}), ...(body ? { "Content-Type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "network", "Can't reach the ClipCart server. Check that it's running.", true);
  }
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new VerifyError(res.status, data?.code ?? "error", data?.message ?? res.statusText, !!data?.retryable, data?.order);
  return data as T;
}

export const demoApi = {
  catalog: () => call<{ network: "devnet"; items: DemoCatalogItem[]; warnings: string[] }>("GET", "/api/demo-catalog"),
  // The body carries only the item id: amount, recipient and reference come from the server.
  create: (catalogItemId: string, idempotencyKey: string) => call<OrderView>("POST", "/api/demo-orders", { catalogItemId, idempotencyKey }),
  order: (id: string) => call<OrderView>("GET", `/api/demo-orders/${encodeURIComponent(id)}`),
  verify: (id: string, hints: { paymentSignature?: string; buyerWallet?: string }) =>
    call<OrderView>("POST", `/api/demo-orders/${encodeURIComponent(id)}/verify`, hints),
  mintReceipt: (id: string) => call<OrderView>("POST", `/api/demo-orders/${encodeURIComponent(id)}/receipt/mint`),
};

export const explorerTx = (sig: string) => `https://explorer.solana.com/tx/${sig}?cluster=devnet`;
export const explorerAddress = (a: string) => `https://explorer.solana.com/address/${a}?cluster=devnet`;
export const short = (a: string | null | undefined) => (!a ? "—" : a.length < 14 ? a : `${a.slice(0, 4)}…${a.slice(-4)}`);
export const sol = (lamports: string) => `${(Number(lamports) / 1e9).toLocaleString(undefined, { maximumFractionDigits: 9 })} SOL`;

// ---------------------------------------------------------------- Phantom

interface PhantomKey {
  toString(): string;
}
interface Phantom {
  isPhantom?: boolean;
  publicKey: PhantomKey | null;
  connect(opts?: { onlyIfTrusted?: boolean }): Promise<{ publicKey: PhantomKey }>;
  disconnect(): Promise<void>;
  signAndSendTransaction(tx: unknown, opts?: { skipPreflight?: boolean }): Promise<{ signature: string } | string>;
  on?(event: string, cb: (...args: unknown[]) => void): void;
  off?(event: string, cb: (...args: unknown[]) => void): void;
}

export function phantom(): Phantom | null {
  const w = window as unknown as { phantom?: { solana?: Phantom }; solana?: Phantom };
  const p = w.phantom?.solana ?? w.solana;
  return p?.isPhantom ? p : null;
}

// web3.js is only loaded on this page, and it needs Buffer in the browser.
async function web3() {
  const { Buffer } = await import("buffer");
  (globalThis as { Buffer?: unknown }).Buffer ??= Buffer;
  return import("@solana/web3.js");
}

export async function devnetBalance(wallet: string): Promise<number> {
  const { Connection, PublicKey } = await web3();
  return new Connection(DEVNET_RPC, "confirmed").getBalance(new PublicKey(wallet));
}

/**
 * Builds the Solana Pay native SOL transfer from the server's order and asks Phantom to approve it.
 * The blockhash comes from devnet after a genesis check, so a wallet on another cluster can't land it.
 * Resolves once Phantom returns a signature; rejects if the person cancels.
 */
export async function payWithPhantom(p: Phantom, order: DemoOrder, transfer: DemoTransferRequest): Promise<string> {
  const { Connection, PublicKey, SystemProgram, Transaction } = await web3();
  if (!p.publicKey) throw new Error("Connect Phantom first.");
  if (transfer.splToken) throw new Error("This order asks for a token transfer, which the demo checkout doesn't support.");
  if (transfer.recipient !== order.recipientWallet || transfer.reference !== order.paymentReference) {
    throw new Error("The payment request doesn't match the order. Nothing was sent.");
  }
  const conn = new Connection(DEVNET_RPC, "confirmed");
  if ((await conn.getGenesisHash()) !== DEVNET_GENESIS) throw new Error("The RPC isn't Solana devnet. Nothing was sent.");
  const from = new PublicKey(p.publicKey.toString());
  const ix = SystemProgram.transfer({ fromPubkey: from, toPubkey: new PublicKey(transfer.recipient), lamports: BigInt(order.amountAtomic) });
  ix.keys.push({ pubkey: new PublicKey(transfer.reference), isSigner: false, isWritable: false });
  const tx = new Transaction().add(ix);
  tx.feePayer = from;
  tx.recentBlockhash = (await conn.getLatestBlockhash("finalized")).blockhash;
  const sent = await p.signAndSendTransaction(tx, { skipPreflight: false });
  return typeof sent === "string" ? sent : sent.signature;
}

export const rejected = (e: unknown) => /user rejected|rejected the request|cancel/i.test(String((e as Error)?.message ?? e));

// ---------------------------------------------------------------- last order

const LAST = "clipcart.demoOrderId";
export const rememberOrder = (id: string | null) => {
  try {
    if (id) localStorage.setItem(LAST, id);
    else localStorage.removeItem(LAST);
  } catch {
    /* private mode: the order link still works */
  }
};
export const lastOrder = () => {
  try {
    return localStorage.getItem(LAST);
  } catch {
    return null;
  }
};
