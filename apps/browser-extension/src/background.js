// Service worker: captures the visible tab on request, owns the capture store, and hands the
// cropped image to ClipCart. It never talks to a model provider and holds no provider keys.

import { SEND_PROVENANCE, getBaseUrl, originPattern, unsupportedReason } from "./config.js";
import { uploadCaptureInPage } from "./handoff.js";

const HEALTH_TIMEOUT_MS = 4000;
const LOAD_TIMEOUT_MS = 15000;
const sending = new Set(); // captureIds with an upload in flight in this worker instance

const captureKey = (id) => `capture:${id}`;
const sendKey = (id) => `send:${id}`;
const tabKey = (tabId) => `cropTab:${tabId}`;

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  const handler = { capture, send, discard }[msg?.type];
  if (!handler) return false;
  handler(msg, sender).then(reply, (err) => reply({ ok: false, code: "internal", message: String(err?.message ?? err) }));
  return true;
});

// Closing the preview tab counts as cancelling: drop the screenshot.
chrome.tabs.onRemoved.addListener(async (tabId) => {
  const key = tabKey(tabId);
  const { [key]: captureId } = await chrome.storage.session.get(key);
  if (captureId) await chrome.storage.session.remove([key, captureKey(captureId)]);
});

/** Popup → "Shop this frame". Capture first; nothing is drawn on the page before or after. */
async function capture({ tabId }) {
  const tab = await chrome.tabs.get(tabId);
  const reason = unsupportedReason(tab.url);
  if (reason) return { ok: false, code: "unsupported_page", message: reason };
  // captureVisibleTab grabs whatever is showing in the window, so only capture the tab the user is on.
  if (!tab.active) return { ok: false, code: "tab_not_visible", message: "Switch back to the video tab and click ClipCart again." };
  let dataUrl;
  try {
    dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "jpeg", quality: 92 });
  } catch (err) {
    return { ok: false, code: "capture_failed", message: captureMessage(err) };
  }
  if (!dataUrl?.startsWith("data:image/")) return { ok: false, code: "capture_failed", message: "Chrome returned an empty screenshot. Try again." };

  const id = crypto.randomUUID();
  await chrome.storage.session.set({
    [captureKey(id)]: { id, dataUrl, sourceUrl: tab.url, sourceTitle: tab.title ?? "", capturedAt: new Date().toISOString() },
  });
  const preview = await chrome.tabs.create({
    url: chrome.runtime.getURL(`src/crop.html#${id}`),
    index: tab.index + 1,
    openerTabId: tab.id,
    windowId: tab.windowId,
  });
  await chrome.storage.session.set({ [tabKey(preview.id)]: id });
  return { ok: true, captureId: id };
}

function captureMessage(err) {
  const text = String(err?.message ?? err);
  if (/permission|activeTab|cannot access|not allowed/i.test(text))
    return "Chrome didn't allow a capture here. Click the ClipCart button on the video tab and try again.";
  if (/quota|MAX_CAPTURE/i.test(text)) return "Too many captures in a row. Wait a second and try again.";
  return `Capture failed: ${text}`;
}

/** Preview → "Cancel". */
async function discard({ captureId }, sender) {
  const keys = [captureKey(captureId), sendKey(captureId)];
  if (sender.tab?.id != null) keys.push(tabKey(sender.tab.id));
  await chrome.storage.session.remove(keys);
  return { ok: true };
}

/** Preview → "Open in ClipCart". One upload per capture, however many times it's clicked. */
async function send({ captureId, imageDataUrl }) {
  const { [sendKey(captureId)]: prior } = await chrome.storage.session.get(sendKey(captureId));
  if (prior?.status === "sent") {
    await focusTab(prior.clipcartTabId);
    return { ok: true, already: true, ...prior };
  }
  const stillSending = prior?.status === "sending" && Date.now() - prior.at < 60_000; // a worker restart can orphan this
  if (sending.has(captureId) || stillSending) return { ok: false, code: "in_progress", message: "Already sending this frame." };
  const { [captureKey(captureId)]: cap } = await chrome.storage.session.get(captureKey(captureId));
  if (!cap) return { ok: false, code: "capture_missing", message: "This capture expired. Capture the frame again." };

  sending.add(captureId);
  await chrome.storage.session.set({ [sendKey(captureId)]: { status: "sending", at: Date.now() } });
  let helperTab = null;
  try {
    const base = await getBaseUrl();
    if (!(await chrome.permissions.contains({ origins: [originPattern(base)] })))
      return { ok: false, code: "needs_permission", base, message: `ClipCart needs your OK to open ${base}.` };
    const health = await checkHealth(base);
    if (!health.ok) return { ok: false, code: "server_unavailable", base, message: health.message };

    // An inert same-origin page (JSON, not the app) so the app's own boot can't race the upload.
    helperTab = await chrome.tabs.create({ url: `${base}/api/health`, active: false });
    await waitForLoad(helperTab.id);
    const provenance = SEND_PROVENANCE ? { sourceUrl: cap.sourceUrl, sourceTitle: cap.sourceTitle } : null;
    const [{ result } = {}] = await chrome.scripting.executeScript({
      target: { tabId: helperTab.id },
      func: uploadCaptureInPage,
      args: [{ dataUrl: imageDataUrl || cap.dataUrl, provenance }],
    });
    if (!result?.ok) {
      await closeQuietly(helperTab.id);
      return { ok: false, code: result?.code ?? "upload_failed", status: result?.status, message: uploadMessage(result) };
    }
    // Now load the studio; it resumes the newest session, which holds this frame.
    await chrome.tabs.update(helperTab.id, { url: `${base}/`, active: true });
    const done = { status: "sent", clipcartTabId: helperTab.id, sessionId: result.sessionId, mediaId: result.mediaId, analysisId: result.analysisId };
    await chrome.storage.session.set({ [sendKey(captureId)]: done });
    return { ok: true, ...done };
  } catch (err) {
    if (helperTab) await closeQuietly(helperTab.id);
    return { ok: false, code: "handoff_failed", message: `Couldn't hand the frame to ClipCart: ${err?.message ?? err}` };
  } finally {
    sending.delete(captureId);
    const { [sendKey(captureId)]: now } = await chrome.storage.session.get(sendKey(captureId));
    if (now?.status === "sending") await chrome.storage.session.remove(sendKey(captureId));
  }
}

async function checkHealth(base) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), HEALTH_TIMEOUT_MS);
  try {
    const res = await fetch(`${base}/api/health`, { credentials: "omit", cache: "no-store", signal: ctrl.signal });
    if (!res.ok) return { ok: false, message: `ClipCart at ${base} answered ${res.status}. Is it the right address?` };
    const body = await res.json().catch(() => null);
    if (body?.api !== "ok") return { ok: false, message: `${base} doesn't look like a ClipCart server.` };
    return { ok: true };
  } catch {
    return { ok: false, message: `Can't reach ClipCart at ${base}. Start the server, or change the address in settings.` };
  } finally {
    clearTimeout(timer);
  }
}

function uploadMessage(r) {
  if (!r) return "ClipCart didn't answer the upload.";
  if (r.status === 401) return "ClipCart couldn't find your session. Open ClipCart once, then try again.";
  if (r.status === 413) return "This frame is too large for ClipCart. Crop a smaller area.";
  if (r.status === 429) return "ClipCart is rate-limiting uploads. Wait a minute and try again.";
  return r.message ? `ClipCart said: ${r.message}` : "The upload failed.";
}

function waitForLoad(tabId) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(onUpdated);
      reject(new Error("ClipCart took too long to load"));
    }, LOAD_TIMEOUT_MS);
    function onUpdated(id, info) {
      if (id === tabId && info.status === "complete") {
        clearTimeout(timer);
        chrome.tabs.onUpdated.removeListener(onUpdated);
        resolve();
      }
    }
    chrome.tabs.onUpdated.addListener(onUpdated);
    chrome.tabs.get(tabId).then((t) => t.status === "complete" && onUpdated(tabId, { status: "complete" }), () => {});
  });
}

async function focusTab(tabId) {
  try {
    const t = await chrome.tabs.update(tabId, { active: true });
    await chrome.windows.update(t.windowId, { focused: true });
  } catch {
    /* the ClipCart tab was closed; nothing to focus */
  }
}

async function closeQuietly(tabId) {
  try {
    await chrome.tabs.remove(tabId);
  } catch {
    /* already gone */
  }
}
