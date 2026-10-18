/**
 * Demo checkout: the ClipCart demo merchant's one controlled item, paid with test SOL on Solana devnet.
 * Contracts: docs/contracts/solana-demo-checkout.md and docs/contracts/solana-cnft-receipts.md.
 *
 * Honesty rules this page keeps:
 * - Always labelled Devnet · Test funds · No retailer fulfillment. Retailer search results are never sold here.
 * - The server prices the order. Paid means the server verified the transfer on devnet, not that Phantom signed.
 * - A receipt is "mint confirmed on-chain" at most; nothing here says a wallet shows it.
 * - Orders are read through the owner-scoped API only. This page never makes up an order or a receipt.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, key } from "../api";
import {
  DEMO_LABEL,
  demoApi,
  devnetBalance,
  explorerAddress,
  explorerTx,
  lastOrder,
  payWithPhantom,
  phantom,
  rejected,
  rememberOrder,
  rememberSignature,
  sentSignature,
  short,
  sol,
  VerifyError,
  wrongNetwork,
  type DemoCatalogItem,
  type DemoReceipt,
  type OrderView,
  type ReceiptStatus,
} from "../demo";
import "../checkout.css";

/** Local steps sit between the server's awaiting_payment and paid; the server's status wins once it moves. */
type Step = "awaiting_approval" | "submitted" | "verifying";
type Phase = "ready" | Step | "paid" | "expired" | "failed";

const STEPS: { id: Phase; label: string }[] = [
  { id: "ready", label: "Order created" },
  { id: "awaiting_approval", label: "Awaiting approval" },
  { id: "submitted", label: "Submitted" },
  { id: "verifying", label: "Verifying" },
  { id: "paid", label: "Paid" },
];

const PHASE_TEXT: Record<Phase, string> = {
  ready: "Waiting for payment",
  awaiting_approval: "Awaiting your approval in Phantom",
  submitted: "Transaction submitted to devnet",
  verifying: "ClipCart is verifying the payment on devnet",
  paid: "Payment verified by ClipCart on devnet",
  expired: "Order expired",
  failed: "Payment not verified",
};

const RECEIPT_TEXT: Record<ReceiptStatus, string> = {
  ineligible: "A receipt can be minted once the payment is verified.",
  eligible: "Payment verified. No receipt has been minted yet.",
  minting: "Minting the compressed receipt on devnet.",
  confirmed: "Mint confirmed on-chain.",
  failed: "The receipt mint failed. The payment is still verified.",
  needs_reconciliation: "The mint's outcome is being checked. ClipCart won't mint again until it's settled.",
};

const INDEXING_TEXT: Record<DemoReceipt["indexingStatus"], string> = {
  ready: "Indexer returned the asset and its owner, tree and metadata checked out.",
  pending: "Indexing pending: the indexer hasn't returned the asset yet.",
  unavailable: "Indexer not reachable from this server, so the asset hasn't been looked up.",
};

/** Verify polling: back off so a slow confirmation stays under the server's 30 verifies per 10 minutes. */
const BACKOFF = [2500, 5000, 10000, 20000, 30000];
const MIN_LEFT_MS = 60_000; // don't open Phantom with less than this left: the transfer might land after expiry

const MINT_ERRORS: Record<string, string> = {
  feature_disabled: "Receipt minting is turned off on this server.",
  receipt_ineligible: "This order isn't eligible for a receipt yet.",
  cnft_not_configured: "Receipt minting isn't set up on this server.",
  cnft_durable_required: "Receipt minting needs durable storage, which this server doesn't have.",
  receipt_mint_in_progress: "The mint is still in progress. Check the receipt again in a moment.",
  not_found: "This order isn't available to this browser, so no receipt was minted.",
};

function errText(e: unknown, fallback: string) {
  if (e instanceof ApiError) return e.code === "network" ? e.message : `${e.message || fallback}`;
  return (e as Error)?.message || fallback;
}

function useCountdown(expiresAt: string | null) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!expiresAt) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [expiresAt]);
  if (!expiresAt) return { left: null as number | null };
  return { left: Math.max(0, Date.parse(expiresAt) - now) };
}

const clock = (ms: number) => {
  const s = Math.ceil(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

function Field({ label, value, href, mono = true }: { label: string; value: string | null | undefined; href?: string | null; mono?: boolean }) {
  return (
    <div className="co-field">
      <dt>{label}</dt>
      <dd className={mono ? "co-mono" : undefined} title={value ?? undefined}>
        {value && href ? (
          <a href={href} target="_blank" rel="noreferrer">
            {short(value)} <span aria-hidden>↗</span>
          </a>
        ) : value ? (
          mono ? short(value) : value
        ) : (
          "—"
        )}
      </dd>
    </div>
  );
}

export default function DemoCheckout({ orderId: routeOrderId, receiptsEnabled }: { orderId: string | null; receiptsEnabled: boolean }) {
  const [item, setItem] = useState<DemoCatalogItem | null>(null);
  const [off, setOff] = useState<string | null>(null);
  const [view, setView] = useState<OrderView | null>(null);
  const [step, setStep] = useState<Step | null>(null);
  const [signature, setSignature] = useState<string | null>(null);
  const [wallet, setWallet] = useState<string | null>(null);
  const [balance, setBalance] = useState<number | null>(null);
  const [busy, setBusy] = useState<"create" | "connect" | "mint" | "check" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mintError, setMintError] = useState<string | null>(null);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true; // StrictMode remounts: set again after the dev-only unmount
    return () => void (alive.current = false);
  }, []);

  const order = view?.order ?? null;
  const transfer = view?.transferRequest ?? null;
  const receipt = view?.receipt ?? null;
  const { left } = useCountdown(order && (order.status === "awaiting_payment" || order.status === "created") ? order.expiresAt : null);
  const provider = phantom();

  // Boot: the catalog item, then the order in the link or the last one this browser created.
  useEffect(() => {
    demoApi
      .catalog()
      .then((c) => setItem(c.items.find((i) => i.eligibleForCheckout) ?? null))
      .catch((e) => setOff(e instanceof ApiError && e.code === "feature_disabled" ? "Demo checkout is turned off on this server." : errText(e, "Couldn't load the demo item.")));
    const id = routeOrderId ?? lastOrder();
    if (!id) return;
    demoApi
      .order(id)
      .then((v) => {
        setView(v);
        setSignature(sentSignature(v.order.id));
      })
      .catch((e) => {
        // Another owner's order or an old id: the server says not_found, and this page shows nothing for it.
        if (e instanceof ApiError && e.status === 404) {
          if (!routeOrderId) rememberOrder(null);
          else setError("That order isn't available to this browser. Orders open only for the browser that created them.");
        } else setError(errText(e, "Couldn't load the order."));
      });
  }, [routeOrderId]);

  // Reconnect silently if Phantom already trusts this site.
  useEffect(() => {
    if (!provider) return;
    provider
      .connect({ onlyIfTrusted: true })
      .then((r) => setWallet(r.publicKey.toString()))
      .catch(() => {});
    const onChange = (...args: unknown[]) => setWallet(args[0] ? String(args[0]) : null);
    provider.on?.("accountChanged", onChange);
    return () => provider.off?.("accountChanged", onChange);
  }, [provider]);

  useEffect(() => {
    setBalance(null);
    if (!wallet) return;
    devnetBalance(wallet)
      .then((b) => alive.current && setBalance(b))
      .catch(() => {});
  }, [wallet, order?.status]);

  // While a receipt is minting or being reconciled, re-read the order. GET never mints or reconciles: only
  // "Check receipt" (a repeat POST …/receipt/mint, which the server treats as idempotent) moves a stuck attempt on.
  const receiptBusy = receipt?.status === "minting" || receipt?.status === "needs_reconciliation" || order?.receiptStatus === "minting";
  useEffect(() => {
    if (!order || !receiptBusy) return;
    let n = 0;
    const t = setInterval(() => {
      if (++n > 24) return clearInterval(t);
      demoApi.order(order.id).then((v) => alive.current && setView(v)).catch(() => {});
    }, 5000);
    return () => clearInterval(t);
  }, [order?.id, receiptBusy]);

  const serverPhase: Phase | null = !order
    ? null
    : order.status === "paid"
      ? "paid"
      : order.status === "failed"
        ? "failed"
        : order.status === "expired"
          ? "expired"
          : order.status === "verifying"
            ? "verifying"
            : "ready";
  // A local step shows only while the server still says the order is open.
  const phase: Phase | null = serverPhase === "ready" || serverPhase === "verifying" ? (step ?? serverPhase) : serverPhase;
  const expiredHere = phase === "ready" && left === 0;

  const create = async () => {
    if (!item) return;
    setBusy("create");
    setError(null);
    setStep(null);
    setSignature(null);
    try {
      const v = await demoApi.create(item.id, `demo-checkout-${key()}`);
      if (v.order.amountAtomic !== item.amountAtomic) throw new Error("The server's order price doesn't match the demo item. Nothing was sent.");
      setView(v);
      rememberOrder(v.order.id);
      history.replaceState(null, "", `#/demo-checkout/${v.order.id}`);
    } catch (e) {
      setError(e instanceof ApiError && e.code === "rate_limited" ? "Too many demo orders in the last 10 minutes. Try again shortly." : errText(e, "Couldn't create the order."));
    } finally {
      setBusy(null);
    }
  };

  const connect = async () => {
    if (!provider) return;
    setBusy("connect");
    setError(null);
    try {
      const r = await provider.connect();
      setWallet(r.publicKey.toString());
    } catch (e) {
      setError(rejected(e) ? "Phantom connection cancelled." : errText(e, "Couldn't connect Phantom."));
    } finally {
      setBusy(null);
    }
  };

  // Ask the server to verify. The signature and wallet are hints; retryable answers are polled, with backoff, until the
  // order closes. A call straight after Phantom keeps "Submitted" on screen until the server's first answer.
  const verify = useCallback(
    async (orderId: string, expiresAt: string, hints: { paymentSignature?: string; buyerWallet?: string }, first: Step = "verifying") => {
      setStep(first);
      const until = Date.parse(expiresAt) + 120_000; // a transfer that landed in time can confirm a little later
      for (let attempt = 0; ; attempt++) {
        let wait = BACKOFF[Math.min(attempt, BACKOFF.length - 1)];
        try {
          const v = await demoApi.verify(orderId, hints);
          if (!alive.current) return;
          setView(v);
          if (v.order.status !== "awaiting_payment" && v.order.status !== "created" && v.order.status !== "verifying") break;
        } catch (e) {
          if (!alive.current) return;
          const order = e instanceof VerifyError ? e.order : undefined;
          if (order) setView((v) => (v ? { ...v, order: { ...v.order, ...order } } : v));
          const limited = e instanceof ApiError && e.code === "rate_limited";
          if (limited) wait = 60_000;
          const retry = e instanceof ApiError && (e.retryable || limited) && Date.now() < until;
          if (!retry) {
            setError(
              e instanceof ApiError && e.code === "signature_reused"
                ? "That payment is already claimed by another order."
                : e instanceof ApiError && e.code === "payment_mismatch"
                  ? "The transaction didn't match this order's amount and recipient, so it isn't paid."
                  : e instanceof ApiError && (e.retryable || limited)
                    ? "ClipCart couldn't confirm the payment yet. Check again in a moment; don't pay a second time."
                    : errText(e, "Couldn't verify the payment."),
            );
            break;
          }
        }
        setStep("verifying");
        await new Promise((r) => setTimeout(r, wait));
      }
      if (alive.current) setStep(null);
    },
    [],
  );

  const pay = async () => {
    if (!provider || !order || !transfer || !wallet || orderProblem) return;
    if (Date.parse(order.expiresAt) - Date.now() < MIN_LEFT_MS) {
      setError("Less than a minute is left on this order, so the payment might land after it expires. Start a new demo order instead.");
      return;
    }
    setError(null);
    setStep("awaiting_approval");
    let sig: string;
    try {
      sig = await payWithPhantom(provider, order, transfer);
    } catch (e) {
      setStep(null);
      setError(
        rejected(e)
          ? "Approval cancelled in Phantom. Nothing was sent."
          : wrongNetwork(e)
            ? "Phantom is on another network. Switch Phantom to Devnet and try again. Nothing was sent."
            : errText(e, "Phantom couldn't send the transaction."),
      );
      return;
    }
    setSignature(sig);
    rememberSignature(order.id, sig);
    await verify(order.id, order.expiresAt, { paymentSignature: sig, buyerWallet: wallet }, "submitted");
  };

  const checkAgain = async () => {
    if (!order) return;
    setBusy("check");
    setError(null);
    await verify(order.id, order.expiresAt, { ...(signature ? { paymentSignature: signature } : {}), ...(wallet ? { buyerWallet: wallet } : {}) });
    setBusy(null);
  };

  // One mint request at a time: a second POST while one is open could start a second attempt.
  const minting = useRef(false);
  const mint = async () => {
    if (!order || minting.current) return;
    minting.current = true;
    setBusy("mint");
    setMintError(null);
    try {
      setView(await demoApi.mintReceipt(order.id));
    } catch (e) {
      setMintError(e instanceof ApiError ? (MINT_ERRORS[e.code] ?? errText(e, "Couldn't mint the receipt.")) : errText(e, "Couldn't mint the receipt."));
      demoApi.order(order.id).then((v) => alive.current && setView(v)).catch(() => {});
    } finally {
      minting.current = false;
      setBusy(null);
    }
  };

  const startOver = () => {
    setView(null);
    setStep(null);
    setSignature(null);
    setError(null);
    setMintError(null);
    rememberOrder(null);
    history.replaceState(null, "", "#/demo-checkout");
  };

  const open = phase === "ready" && !expiredHere;
  const inFlight = phase === "awaiting_approval" || phase === "submitted" || phase === "verifying";
  const stepIndex = phase ? STEPS.findIndex((s) => s.id === phase) : -1;
  const price = order ? sol(order.amountAtomic) : (item?.amountDisplay ?? "");
  const receiptStatus = receipt?.status ?? order?.receiptStatus ?? null;
  // Resumed orders are checked too: only a devnet order at the demo item's server price can be paid here.
  const orderProblem =
    !!order && (order.network !== "devnet" || (!!item && order.amountAtomic !== item.amountAtomic))
      ? "This order doesn't match the devnet demo item, so it can't be paid here."
      : null;
  // A sent transaction the server hasn't credited: the person must keep the signature and not pay again.
  const stranded = !!signature && !!order && order.status !== "paid" && (phase === "expired" || phase === "failed" || expiredHere);

  return (
    <div className="co">
      <p className="co-back">
        <a href="#/">← Back to ClipCart</a>
      </p>
      <header className="co-head">
        <div>
          <p className="co-kicker">ClipCart demo merchant</p>
          <h1>Demo checkout</h1>
        </div>
        <p className="co-label" role="note">
          <span className="co-label-dot" aria-hidden />
          {DEMO_LABEL}
        </p>
      </header>
      <p className="co-scope">
        One controlled demo item, paid with test SOL on Solana devnet. Nothing ships. Search results on ClipCart are retailer links and can't
        be bought here.
      </p>

      {off ? (
        <p className="banner banner-error">{off}</p>
      ) : (
        <div className="co-grid">
          <section className="co-card co-item" aria-labelledby="co-item-title">
            <p className="co-tag">Demo item · not a retailer listing</p>
            <h2 id="co-item-title">{item?.title ?? "Loading the demo item…"}</h2>
            {item && <p className="muted">{item.description}</p>}
            <p className="co-price">
              {price}
              <span>Price set by the server · devnet test SOL</span>
            </p>
            {item && <p className="co-terms">{order?.fulfillmentTerms || item.fulfillmentTerms}</p>}
            <dl className="co-fields">
              <Field label="Merchant" value={item?.merchantLabel ?? null} mono={false} />
              <Field label="Network" value="Solana devnet" mono={false} />
            </dl>
          </section>

          <section className="co-card co-pay" aria-labelledby="co-pay-title" aria-live="polite">
            <h2 id="co-pay-title">Payment</h2>

            <div className="co-wallet">
              {!provider ? (
                <p className="muted">Phantom isn't installed in this browser. Open this page in a browser with the Phantom extension, set to devnet.</p>
              ) : wallet ? (
                <p>
                  <span className="co-dot co-dot-ok" aria-hidden /> Phantom <span className="co-mono">{short(wallet)}</span>
                  {balance !== null && <span className="muted"> · {(balance / 1e9).toFixed(4)} devnet SOL</span>}
                </p>
              ) : (
                <button type="button" className="btn" onClick={connect} disabled={busy === "connect"}>
                  {busy === "connect" ? "Connecting…" : "Connect Phantom"}
                </button>
              )}
            </div>

            {!order ? (
              <>
                <p className="muted">Create an order to get the server's price, recipient and payment reference. Nothing is charged until you approve in Phantom.</p>
                <button type="button" className="btn btn-primary co-cta" onClick={create} disabled={!item || busy === "create"}>
                  {busy === "create" ? "Creating order…" : "Create demo order"}
                </button>
              </>
            ) : (
              <>
                <ol className="co-steps" aria-label="Payment progress">
                  {STEPS.map((s, i) => (
                    <li
                      key={s.id}
                      className={phase === "paid" || i < stepIndex ? "co-step-done" : i === stepIndex ? "co-step-now" : ""}
                      aria-current={i === stepIndex ? "step" : undefined}
                    >
                      <span className="co-step-n">{phase === "paid" || i < stepIndex ? "✓" : i + 1}</span>
                      {s.label}
                    </li>
                  ))}
                </ol>
                <p className={`co-state co-state-${expiredHere ? "expired" : phase}`}>
                  {inFlight && <span className="co-spin" aria-hidden />}
                  {expiredHere ? "Order expired" : phase && PHASE_TEXT[phase]}
                  {open && left !== null && <span className="co-timer"> · expires in {clock(left)}</span>}
                </p>
                {phase === "awaiting_approval" && <p className="muted">Check the Phantom window. It should show {price} to the ClipCart demo merchant on devnet.</p>}
                {phase === "submitted" && <p className="muted">Phantom returned a signature. ClipCart will now check devnet for it.</p>}
                {phase === "verifying" && <p className="muted">Checking amount, recipient, reference and time window on devnet. Don't pay again.</p>}
                {stranded ? (
                  <p className="banner banner-error co-error" role="alert">
                    Your transaction was sent but ClipCart couldn't credit it to this order. Don't pay again. Keep this signature:
                    <span className="co-mono co-sig">{signature}</span>
                  </p>
                ) : (
                  (phase === "expired" || expiredHere) && <p className="muted">This order can't be paid any more. Create a new one to try again.</p>
                )}
                {orderProblem && <p className="banner banner-error co-error">{orderProblem}</p>}

                <dl className="co-fields">
                  <Field label="Order" value={order.id} />
                  <Field label="Amount" value={sol(order.amountAtomic)} mono={false} />
                  <Field label="Recipient" value={order.recipientWallet} href={explorerAddress(order.recipientWallet)} />
                  <Field label="Reference" value={order.paymentReference} />
                  {order.buyerWallet && <Field label="Paid from" value={order.buyerWallet} href={explorerAddress(order.buyerWallet)} />}
                  {/* Linked only once the server verified it; a signature Phantom returned stays plain text until then. */}
                  {order.paymentSignature ? (
                    <Field label="Payment tx" value={order.paymentSignature} href={order.explorerPaymentUrl ?? null} />
                  ) : (
                    signature && <Field label="Sent tx · not verified" value={signature} />
                  )}
                </dl>

                {open && !inFlight && !signature && (
                  <>
                    <button type="button" className="btn btn-primary co-cta" onClick={pay} disabled={!wallet || !transfer || !!orderProblem}>
                      {wallet ? `Approve ${price} in Phantom` : "Connect Phantom to pay"}
                    </button>
                    <p className="co-hint">Set Phantom to Devnet first. A wallet on another network can't send this.</p>
                  </>
                )}
                {(phase === "ready" || stranded) && !inFlight && (signature || error) && (
                  <button type="button" className="btn co-cta-2" onClick={checkAgain} disabled={busy === "check"}>
                    Check payment again
                  </button>
                )}
                {(phase === "expired" || phase === "failed" || expiredHere || phase === "paid") && !stranded && (
                  <button type="button" className="btn co-cta-2" onClick={startOver}>
                    Start a new demo order
                  </button>
                )}
              </>
            )}
            {error && <p className="banner banner-error co-error">{error}</p>}
          </section>

          {order && (phase === "paid" || receipt) && (
            <section className="co-card co-receipt" aria-labelledby="co-receipt-title" aria-live="polite">
              <p className="co-tag">Compressed NFT receipt · devnet</p>
              <h2 id="co-receipt-title">Receipt</h2>
              <p className={`co-receipt-state co-receipt-${receiptStatus}`}>
                {(receiptStatus === "minting" || busy === "mint") && <span className="co-spin" aria-hidden />}
                {busy === "mint"
                  ? "Minting the compressed receipt on devnet."
                  : receiptStatus === "eligible" && !receiptsEnabled
                    ? "Payment verified. Receipts are off on this server."
                    : receiptStatus && RECEIPT_TEXT[receiptStatus]}
              </p>
              {receipt?.status === "confirmed" && <p className="muted">{INDEXING_TEXT[receipt.indexingStatus]}</p>}
              <dl className="co-fields">
                <Field label="Status" value={receiptStatus?.replace(/_/g, " ") ?? null} mono={false} />
                <Field label="Asset ID" value={receipt?.assetId ?? order.receiptAssetId} href={receipt?.assetId ? explorerAddress(receipt.assetId) : null} />
                <Field label="Mint tx" value={receipt?.mintSignature ?? null} href={receipt?.explorerMintUrl ?? (receipt?.mintSignature ? explorerTx(receipt.mintSignature) : null)} />
                {receipt?.merkleTree && <Field label="Tree" value={receipt.merkleTree} href={explorerAddress(receipt.merkleTree)} />}
                {receipt?.buyerWallet && (
                  <Field label={receipt.status === "confirmed" ? "Owner" : "Buyer wallet"} value={receipt.buyerWallet} href={explorerAddress(receipt.buyerWallet)} />
                )}
              </dl>
              {receiptsEnabled && (receiptStatus === "eligible" || receiptStatus === "minting" || receiptStatus === "needs_reconciliation") && (
                <button type="button" className="btn co-cta-2" onClick={mint} disabled={busy === "mint"}>
                  {busy === "mint" ? "Working…" : receiptStatus === "eligible" ? "Mint demo receipt" : "Check receipt"}
                </button>
              )}
              {mintError && <p className="banner banner-error co-error">{mintError}</p>}
              <p className="co-fine">{receipt?.label ?? "ClipCart demo receipt · Devnet · No retailer fulfillment."} Wallet display of the receipt hasn't been tested.</p>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
