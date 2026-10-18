/**
 * ClipCart Solana demo checkout (browser). Bundled with esbuild + real `buffer`.
 * Orders are created only after the user clicks Create order; pay params come from the API.
 */
import {
  Connection,
  PublicKey,
  SystemProgram,
  Transaction,
  LAMPORTS_PER_SOL,
} from "@solana/web3.js";

const RPC = "https://api.devnet.solana.com";
const CATALOG_ITEM_ID = "demo_item_clipcart_jacket_01";
const EXPECTED_BUYER = "8W3Rgm2MFFkA3SP1TcUuvVaHMAPhJshZ4rdgJw2QSwjo";
const EXPECTED_LAMPORTS = 10_000_000;

/** @typedef {'connect'|'ready'|'awaiting_approval'|'submitted'|'verifying'|'paid'|'expired'|'failed'} UiState */

const state = {
  /** @type {UiState} */
  ui: "connect",
  provider: null,
  buyer: null,
  order: null,
  transfer: null,
  catalogItem: null,
  signature: null,
  creating: false,
  paying: false,
  verifying: false,
  countdownTimer: null,
  lastError: null,
  diagnostics: [],
};

function $(id) {
  return document.getElementById(id);
}

function logDiag(msg) {
  const line = `${new Date().toISOString()}  ${msg}`;
  state.diagnostics.unshift(line);
  state.diagnostics = state.diagnostics.slice(0, 40);
  const el = $("diagLog");
  if (el) el.textContent = state.diagnostics.join("\n");
}

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    credentials: "include",
    headers: {
      "X-ClipCart-Request": "1",
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.message || data.code || res.statusText);
    err.code = data.code;
    err.status = res.status;
    err.payload = data;
    throw err;
  }
  return data;
}

function setUi(next) {
  state.ui = next;
  document.body.dataset.state = next;
  $("stateLabel").textContent = labelFor(next);
  render();
}

function labelFor(s) {
  return (
    {
      connect: "Connect wallet",
      ready: "Ready to pay",
      awaiting_approval: "Awaiting Phantom approval",
      submitted: "Transaction submitted",
      verifying: "Verifying on server",
      paid: "Payment verified",
      expired: "Order expired",
      failed: "Payment failed",
    }[s] || s
  );
}

function shortAddr(a) {
  if (!a || a.length < 12) return a || "—";
  return `${a.slice(0, 4)}…${a.slice(-4)}`;
}

function isExpired(order) {
  if (!order?.expiresAt) return false;
  return Date.parse(order.expiresAt) <= Date.now();
}

function stopCountdown() {
  if (state.countdownTimer) {
    clearInterval(state.countdownTimer);
    state.countdownTimer = null;
  }
}

function startCountdown() {
  stopCountdown();
  const tick = () => {
    const el = $("countdown");
    if (!state.order) {
      el.textContent = "—";
      return;
    }
    const ms = Date.parse(state.order.expiresAt) - Date.now();
    if (ms <= 0) {
      el.textContent = "Expired";
      if (state.ui !== "paid" && state.ui !== "failed" && state.ui !== "verifying" && state.ui !== "submitted") {
        setUi("expired");
      } else if (state.ui === "awaiting_approval") {
        // Approval may still land; keep awaiting but mark countdown expired.
        el.textContent = "Expired during approval — wait for result or create a new order after verify fails";
        render();
      }
      stopCountdown();
      render();
      return;
    }
    const s = Math.floor(ms / 1000);
    const m = Math.floor(s / 60);
    const r = s % 60;
    el.textContent = `${m}:${String(r).padStart(2, "0")} left`;
  };
  tick();
  state.countdownTimer = setInterval(tick, 1000);
}

function render() {
  const o = state.order;
  const t = state.transfer;
  const expired = o ? isExpired(o) : false;

  $("itemTitle").textContent = state.catalogItem?.title || "ClipCart Demo Jacket (devnet)";
  $("itemDesc").textContent =
    state.catalogItem?.description ||
    "Participating ClipCart demo merchant item. Not a SoleScout or retailer purchase.";
  $("amountHero").textContent = t?.amount ? `${t.amount} SOL` : "0.01 SOL";
  $("orderId").textContent = o?.id || "—";
  $("orderStatus").textContent = o ? `${o.status} · receipt ${o.receiptStatus}` : "no order yet";
  $("recipientShort").textContent = t ? shortAddr(t.recipient) : "—";
  $("recipientFull").textContent = t?.recipient || "—";
  $("referenceFull").textContent = t?.reference || "—";
  $("lamportsFull").textContent = o?.amountAtomic || String(EXPECTED_LAMPORTS);
  $("expiresFull").textContent = o?.expiresAt || "—";
  $("buyerShort").textContent = state.buyer ? shortAddr(state.buyer) : "Not connected";
  $("buyerFull").textContent = state.buyer || "—";
  $("sigFull").textContent = state.signature || "—";
  $("explorerLink").href = state.signature
    ? `https://explorer.solana.com/tx/${state.signature}?cluster=devnet`
    : "#";
  $("explorerLink").style.display = state.signature ? "inline" : "none";

  const terms = o?.fulfillmentTerms || state.catalogItem?.fulfillmentTerms || "";
  $("terms").textContent = terms;

  // Only create when there is no active payable order (or after terminal states).
  const canCreate =
    !state.creating &&
    !state.paying &&
    !state.verifying &&
    state.ui !== "awaiting_approval" &&
    state.ui !== "submitted" &&
    state.ui !== "verifying" &&
    state.ui !== "ready" &&
    (!o || state.ui === "expired" || state.ui === "failed" || state.ui === "paid" || state.ui === "connect");

  const canPay =
    !!state.provider &&
    !!o &&
    !!t &&
    !expired &&
    !state.paying &&
    !state.verifying &&
    (state.ui === "ready" || state.ui === "failed") &&
    o.status === "awaiting_payment" &&
    !state.signature;

  $("btnConnect").disabled = !!state.provider;
  $("btnConnect").textContent = state.provider ? "Wallet connected" : "Connect Phantom";
  $("btnCreate").disabled = !canCreate || state.ui === "awaiting_approval" || state.ui === "submitted" || state.ui === "verifying";
  $("btnCreate").textContent =
    o && (state.ui === "expired" || state.ui === "failed" || state.ui === "paid")
      ? "Create new order"
      : state.creating
        ? "Creating…"
        : "Create order";
  $("btnPay").disabled = !canPay;
  $("btnPay").textContent = state.paying
    ? "Opening Phantom…"
    : state.verifying
      ? "Verifying…"
      : "Pay 0.01 SOL";

  $("banner").hidden = !state.lastError;
  $("bannerText").textContent = state.lastError || "";

  $("paidBanner").hidden = state.ui !== "paid";
  $("submittedBanner").hidden = state.ui !== "submitted" && state.ui !== "verifying";
}

async function ensureSession() {
  await api("POST", "/api/sessions");
}

async function loadCatalog() {
  const cat = await api("GET", "/api/demo-catalog");
  state.catalogItem = (cat.items && cat.items[0]) || null;
  render();
}

async function createOrder() {
  if (state.creating || state.paying || state.verifying) return;
  if (state.ui === "awaiting_approval" || state.ui === "submitted" || state.ui === "verifying") {
    state.lastError = "A payment is already in flight for this order. Wait for verification before creating another.";
    render();
    return;
  }
  state.creating = true;
  state.lastError = null;
  state.signature = null;
  render();
  try {
    await ensureSession();
    const idem = `checkout-${crypto.randomUUID()}`;
    const created = await api("POST", "/api/demo-orders", {
      catalogItemId: CATALOG_ITEM_ID,
      idempotencyKey: idem,
    });
    state.order = created.order;
    state.transfer = created.transferRequest;
    if (Number(state.order.amountAtomic) !== EXPECTED_LAMPORTS) {
      throw new Error("Server returned unexpected amount; refusing to proceed");
    }
    logDiag(`Created order ${state.order.id} ref=${state.transfer.reference}`);
    setUi("ready");
    startCountdown();
  } catch (e) {
    state.lastError = e.message || String(e);
    logDiag(`Create failed: ${state.lastError}`);
    setUi(state.order ? state.ui : "connect");
  } finally {
    state.creating = false;
    render();
  }
}

async function connectWallet() {
  state.lastError = null;
  try {
    const phantom = window.solana;
    if (!phantom?.isPhantom) {
      throw new Error("Phantom not found. Open this page in Chrome with the Phantom extension.");
    }
    state.provider = phantom;
    const resp = await phantom.connect();
    state.buyer = resp.publicKey.toString();
    logDiag(`Connected ${state.buyer}`);
    if (state.buyer !== EXPECTED_BUYER) {
      state.lastError = `Connected ${shortAddr(state.buyer)}. Prefer Demo Buyer ${shortAddr(EXPECTED_BUYER)} on Devnet.`;
    }
    const conn = new Connection(RPC, "confirmed");
    const lamports = await conn.getBalance(new PublicKey(state.buyer));
    $("buyerBal").textContent = `${(lamports / LAMPORTS_PER_SOL).toFixed(4)} SOL`;
    if (!state.order) setUi("connect");
    else if (state.ui === "connect") setUi("ready");
    render();
  } catch (e) {
    state.lastError = e.message || String(e);
    logDiag(`Connect failed: ${state.lastError}`);
    render();
  }
}

async function pay() {
  if (state.paying || state.verifying || state.signature) return;
  if (!state.provider || !state.order || !state.transfer) return;
  if (isExpired(state.order)) {
    setUi("expired");
    state.lastError = "Order expired before pay. Create a new order.";
    render();
    return;
  }

  state.paying = true;
  state.lastError = null;
  setUi("awaiting_approval");

  try {
    const from = state.provider.publicKey;
    const conn = new Connection(RPC, "confirmed");
    const recipient = new PublicKey(state.transfer.recipient);
    const reference = new PublicKey(state.transfer.reference);
    const lamports = EXPECTED_LAMPORTS;

    const ix = SystemProgram.transfer({ fromPubkey: from, toPubkey: recipient, lamports });
    ix.keys.push({ pubkey: reference, isSigner: false, isWritable: false });
    if (!ix.keys.some((k) => k.pubkey.equals(reference))) {
      throw new Error("Reference account missing from transfer instruction");
    }

    const tx = new Transaction().add(ix);
    tx.feePayer = from;
    tx.recentBlockhash = (await conn.getLatestBlockhash("finalized")).blockhash;

    logDiag(`Requesting Phantom signature; reference=${reference.toBase58()}`);
    const signed = await state.provider.signAndSendTransaction(tx, { skipPreflight: false });
    const sig = typeof signed === "string" ? signed : signed.signature;
    state.signature = sig;
    state.paying = false;
    setUi("submitted");
    logDiag(`Submitted ${sig}`);

    // If order expired while Phantom was open, still attempt verify once — do not silently replace.
    if (isExpired(state.order)) {
      state.lastError =
        "Order TTL elapsed during Phantom approval. Verifying this signature anyway; create a new order only if verification fails.";
      logDiag("Order expired during approval; continuing to verify submitted tx");
    }

    await verifyPayment(sig);
  } catch (e) {
    state.paying = false;
    const msg = e.message || String(e);
    logDiag(`Pay failed: ${msg}`);
    if (/User rejected|rejected the request|cancelled/i.test(msg)) {
      state.lastError = "Phantom approval cancelled. You can try Pay again for the same order while it is valid.";
      setUi(isExpired(state.order) ? "expired" : "ready");
    } else if (isExpired(state.order)) {
      state.lastError = msg;
      setUi("expired");
    } else {
      state.lastError = msg;
      setUi("failed");
    }
    render();
  }
}

async function verifyPayment(sig) {
  if (state.verifying) return;
  state.verifying = true;
  setUi("verifying");
  try {
    const body = {
      paymentSignature: sig,
      buyerWallet: state.buyer || undefined,
    };
    // Retry a few times for confirmation lag
    let lastErr = null;
    for (let i = 0; i < 8; i++) {
      try {
        const res = await fetch(`/api/demo-orders/${state.order.id}/verify`, {
          method: "POST",
          credentials: "include",
          headers: { "X-ClipCart-Request": "1", "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const data = await res.json();
        if (res.ok && data.order?.status === "paid") {
          state.order = data.order;
          state.transfer = data.transferRequest || state.transfer;
          state.verifying = false;
          state.lastError = null;
          setUi("paid");
          stopCountdown();
          logDiag(`Verified paid; receiptStatus=${data.order.receiptStatus}`);
          return;
        }
        if (data.order) state.order = data.order;
        if (data.retryable) {
          lastErr = data.message || data.code;
          logDiag(`Verify retryable (${i + 1}/8): ${lastErr}`);
          await new Promise((r) => setTimeout(r, 1500));
          continue;
        }
        lastErr = data.message || data.code || `HTTP ${res.status}`;
        break;
      } catch (e) {
        lastErr = e.message || String(e);
        await new Promise((r) => setTimeout(r, 1500));
      }
    }
    state.verifying = false;
    state.lastError = `Verification did not succeed: ${lastErr}. Diagnose this signature before creating another order.`;
    setUi("failed");
    logDiag(`Verify failed: ${lastErr}`);
  } catch (e) {
    state.verifying = false;
    state.lastError = e.message || String(e);
    setUi("failed");
  }
}

export async function boot() {
  $("btnConnect").addEventListener("click", () => connectWallet());
  $("btnCreate").addEventListener("click", () => createOrder());
  $("btnPay").addEventListener("click", () => pay());
  try {
    await ensureSession();
    await loadCatalog();
    setUi("connect");
    logDiag("Checkout ready. Create an order when you are ready to pay.");
  } catch (e) {
    state.lastError = e.message || String(e);
    logDiag(`Boot failed: ${state.lastError}`);
    render();
  }
}

boot();
