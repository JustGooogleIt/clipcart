import { getBaseUrl, unsupportedReason } from "./config.js";

const $ = (id) => document.getElementById(id);
const shop = $("shop");
const error = $("error");

function showError(text) {
  error.textContent = text;
  error.hidden = !text;
}

$("settings").addEventListener("click", () => chrome.runtime.openOptionsPage());

const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
const reason = tab ? unsupportedReason(tab.url) : "No tab to capture.";
if (reason) {
  shop.disabled = true;
  showError(reason);
}

shop.addEventListener("click", async () => {
  if (shop.disabled) return;
  shop.disabled = true;
  shop.innerHTML = '<span class="spin" aria-hidden="true"></span> Capturing…';
  showError("");
  const res = await chrome.runtime.sendMessage({ type: "capture", tabId: tab.id }).catch((e) => ({ ok: false, message: String(e?.message ?? e) }));
  if (res?.ok) {
    window.close(); // the crop preview opens in its own tab
    return;
  }
  shop.disabled = false;
  shop.textContent = "Shop this frame";
  showError(res?.message ?? "Capture failed. Try again.");
});

// Reachability only: GET /api/health starts no analysis and calls no model.
(async () => {
  const base = await getBaseUrl();
  const host = new URL(base).host;
  $("server").title = base;
  const dot = $("server-dot");
  const text = $("server-text");
  try {
    const ctrl = new AbortController();
    setTimeout(() => ctrl.abort(), 3000);
    const res = await fetch(`${base}/api/health`, { credentials: "omit", cache: "no-store", signal: ctrl.signal });
    const body = res.ok ? await res.json() : null;
    if (body?.api !== "ok") throw new Error("not clipcart");
    dot.className = "dot ok";
    text.textContent = `ClipCart ready · ${host}`;
  } catch {
    dot.className = "dot err";
    text.textContent = `ClipCart not reachable · ${host}`;
  }
})();
