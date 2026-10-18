// Extension-owned preview. The screenshot was taken before this page opened, so the
// selection overlay lives only here and never appears in the captured image.

import { looksBlank, selectionToSourceRect } from "./config.js";

const $ = (id) => document.getElementById(id);
const stage = $("stage");
const shot = $("shot");
const selEl = $("sel");
const sendBtn = $("send");
const clearBtn = $("clear");
const statusEl = $("status");
const captureId = location.hash.slice(1);

let sel = null; // {x, y, w, h} in displayed pixels
let drag = null;
let busy = false;
let sent = false;

const { [`capture:${captureId}`]: cap } = captureId ? await chrome.storage.session.get(`capture:${captureId}`) : {};
if (!cap) {
  stage.hidden = true;
  $("missing").hidden = false;
  $("note").hidden = true;
} else {
  shot.src = cap.dataUrl;
  await shot.decode().catch(() => {});
  sendBtn.disabled = false;
  updateButtons();
  if (cap.sourceUrl) {
    const host = safeHost(cap.sourceUrl);
    $("source-text").textContent = cap.sourceTitle ? `${cap.sourceTitle} · ${host}` : host;
    $("source").title = cap.sourceUrl;
    $("source").hidden = false;
  }
  checkBlank();
}

function safeHost(url) {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

function checkBlank() {
  const c = document.createElement("canvas");
  c.width = 96;
  c.height = Math.max(1, Math.round((96 * shot.naturalHeight) / shot.naturalWidth));
  const ctx = c.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(shot, 0, 0, c.width, c.height);
  $("blank").hidden = !looksBlank(ctx.getImageData(0, 0, c.width, c.height).data);
}

// ---------------------------------------------------------------- selection
function point(e) {
  const r = shot.getBoundingClientRect();
  return { x: Math.min(Math.max(e.clientX - r.left, 0), r.width), y: Math.min(Math.max(e.clientY - r.top, 0), r.height) };
}

stage.addEventListener("pointerdown", (e) => {
  if (busy || sent || !cap || e.button !== 0) return;
  stage.setPointerCapture(e.pointerId);
  const p = point(e);
  drag = p;
  sel = { x: p.x, y: p.y, w: 0, h: 0 };
  draw();
});
stage.addEventListener("pointermove", (e) => {
  if (!drag) return;
  const p = point(e);
  sel = { x: drag.x, y: drag.y, w: p.x - drag.x, h: p.y - drag.y };
  draw();
});
stage.addEventListener("pointerup", () => {
  if (!drag) return;
  drag = null;
  if (!currentRect()) sel = null; // a click or a tiny drag isn't a crop
  draw();
});
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && sel && !busy && !sent) {
    sel = null;
    draw();
  }
});
window.addEventListener("resize", () => {
  sel = null; // display scale changed; ask for a fresh selection rather than guess
  draw();
});

function currentRect() {
  return selectionToSourceRect(
    sel,
    { width: shot.clientWidth, height: shot.clientHeight },
    { width: shot.naturalWidth, height: shot.naturalHeight },
  );
}

function draw() {
  if (!sel) {
    selEl.hidden = true;
    updateButtons();
    return;
  }
  const x = Math.min(sel.x, sel.x + sel.w);
  const y = Math.min(sel.y, sel.y + sel.h);
  Object.assign(selEl.style, { left: `${x}px`, top: `${y}px`, width: `${Math.abs(sel.w)}px`, height: `${Math.abs(sel.h)}px` });
  selEl.classList.toggle("top", y < 34);
  const r = currentRect();
  $("size").textContent = r ? `${r.width} × ${r.height}` : "drag further";
  selEl.hidden = false;
  updateButtons();
}

function updateButtons() {
  const hasCrop = !!(sel && currentRect());
  clearBtn.hidden = !hasCrop || sent;
  if (!busy && !sent) sendBtn.textContent = "Open in ClipCart";
  const r = hasCrop ? currentRect() : null;
  $("scope").textContent = r ? `Sending your crop (${r.width} × ${r.height}).` : "Sending the whole frame.";
}

clearBtn.addEventListener("click", () => {
  sel = null;
  draw();
});

// ---------------------------------------------------------------- actions
$("cancel").addEventListener("click", async () => {
  if (busy) return;
  if (cap && !sent) await chrome.runtime.sendMessage({ type: "discard", captureId });
  window.close();
});

function croppedDataUrl() {
  const r = currentRect();
  if (!r) return null; // whole frame: the worker uses the stored capture as-is
  const c = document.createElement("canvas");
  c.width = r.width;
  c.height = r.height;
  c.getContext("2d").drawImage(shot, r.x, r.y, r.width, r.height, 0, 0, r.width, r.height);
  return c.toDataURL("image/jpeg", 0.92);
}

function setStatus(kind, html, action) {
  statusEl.hidden = !html;
  statusEl.className = `notice ${kind}`;
  statusEl.innerHTML = "";
  if (!html) return;
  const row = document.createElement("div");
  row.className = "status-row";
  const text = document.createElement("span");
  text.textContent = html;
  row.append(text);
  if (action) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "btn btn-sm";
    b.textContent = action.label;
    b.addEventListener("click", action.run);
    row.append(b);
  }
  statusEl.append(row);
}

async function send() {
  if (busy) return; // duplicate clicks while one is in flight do nothing
  if (sent) {
    await chrome.runtime.sendMessage({ type: "send", captureId }); // focuses the ClipCart tab, no re-upload
    return;
  }
  busy = true;
  sendBtn.disabled = true;
  sendBtn.innerHTML = '<span class="spin" aria-hidden="true"></span> Sending…';
  setStatus("", "Sending the frame to ClipCart…");
  const res = await chrome.runtime
    .sendMessage({ type: "send", captureId, imageDataUrl: croppedDataUrl() })
    .catch((e) => ({ ok: false, code: "extension_error", message: String(e?.message ?? e) }));
  busy = false;
  sendBtn.disabled = false;
  if (res?.ok) {
    sent = true;
    sendBtn.textContent = "Go to ClipCart";
    clearBtn.hidden = true;
    $("cancel").textContent = "Close";
    $("note").hidden = true;
    setStatus("ok", "Opened in ClipCart. Detection runs there now; pick the garment in the studio.");
    return;
  }
  updateButtons();
  if (res?.code === "needs_permission") {
    setStatus("warn", res.message, { label: "Allow", run: () => allowAndRetry(res.base) });
  } else if (res?.code === "server_unavailable") {
    setStatus("err", res.message, { label: "Retry", run: send });
    appendSettingsLink();
  } else if (res?.code === "in_progress") {
    setStatus("", res.message);
  } else {
    setStatus("err", res?.message ?? "Something went wrong.", { label: "Retry", run: send });
  }
}

async function allowAndRetry(base) {
  const u = new URL(base);
  const granted = await chrome.permissions.request({ origins: [`${u.protocol}//${u.hostname}/*`] });
  if (granted) send();
  else setStatus("err", `Without access to ${base} the frame can't be handed over.`);
}

function appendSettingsLink() {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "link";
  b.textContent = "Change address";
  b.addEventListener("click", () => chrome.runtime.openOptionsPage());
  statusEl.querySelector(".status-row")?.append(b);
}

sendBtn.addEventListener("click", send);
