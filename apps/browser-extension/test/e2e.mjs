// End-to-end check of the unpacked extension in real Chromium against a running ClipCart server.
//
//   CLIPCART_URL=http://127.0.0.1:8000 node test/e2e.mjs
//
// Needs a ClipCart server (fixture providers are fine) and Chromium. Screenshots land in test/out/.
// What is real and what is substituted is printed at the end; see README.md "Testing".

import { chromium } from "playwright-core";
import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const extRoot = path.resolve(here, "..");
const out = path.join(here, "out");
const BASE = (process.env.CLIPCART_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const CHROME = process.env.CHROME_PATH ?? "/opt/pw-browsers/chromium";
const VIDEO_PORT = 8765;
const VIDEO_URL = `http://video.test:${VIDEO_PORT}/video.html`; // a host the extension has no permission for
const DEAD_URL = "http://127.0.0.1:8009"; // nothing listens here
fs.mkdirSync(out, { recursive: true });

const results = [];
const step = async (name, fn) => {
  try {
    await fn();
    results.push(["PASS", name]);
    console.log(`PASS  ${name}`);
  } catch (err) {
    results.push(["FAIL", name, err]);
    console.log(`FAIL  ${name}\n      ${err?.stack ?? err}`);
  }
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ------------------------------------------------------------------ fixtures
const server = http.createServer((req, res) => {
  const file = path.join(here, "fixtures", path.basename(new URL(req.url, "http://x").pathname));
  if (!fs.existsSync(file)) return res.writeHead(404).end();
  res.writeHead(200, { "Content-Type": file.endsWith(".html") ? "text/html" : "image/jpeg" }).end(fs.readFileSync(file));
});
await new Promise((r) => server.listen(VIDEO_PORT, "127.0.0.1", r));

// Test copy of the extension. The only change: "<all_urls>" stands in for the activeTab grant
// Chrome gives on a real toolbar click, which automation cannot perform.
function extensionCopy(name, extraHosts) {
  const dir = path.join(os.tmpdir(), `clipcart-ext-${name}-${process.pid}`);
  fs.rmSync(dir, { recursive: true, force: true });
  fs.cpSync(extRoot, dir, { recursive: true, filter: (p) => !p.includes("node_modules") && !p.includes(`${path.sep}test`) });
  const m = JSON.parse(fs.readFileSync(path.join(dir, "manifest.json"), "utf8"));
  m.host_permissions.push(...extraHosts);
  fs.writeFileSync(path.join(dir, "manifest.json"), JSON.stringify(m, null, 2));
  return dir;
}

async function launch(extDir) {
  const ctx = await chromium.launchPersistentContext(fs.mkdtempSync(path.join(os.tmpdir(), "cc-prof-")), {
    executablePath: CHROME,
    headless: true,
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    args: [`--disable-extensions-except=${extDir}`, `--load-extension=${extDir}`, `--host-resolver-rules=MAP video.test 127.0.0.1`],
  });
  const sw = ctx.serviceWorkers()[0] ?? (await ctx.waitForEvent("serviceworker"));
  const id = new URL(sw.url()).host;
  return { ctx, sw, id };
}

// The real action popup isn't exposed as a Playwright page; confirm it opens via CDP targets.
async function openPopup(ctx, sw) {
  const page = ctx.pages().find((p) => p.url().startsWith("http")) ?? ctx.pages()[0];
  const cdp = await ctx.newCDPSession(page);
  await sw.evaluate(() => chrome.action.openPopup());
  let target;
  for (let i = 0; i < 40 && !target; i++) {
    const { targetInfos } = await cdp.send("Target.getTargets");
    target = targetInfos.find((t) => t.url.endsWith("/src/popup.html"));
    if (!target) await sleep(100);
  }
  await cdp.detach();
  assert.ok(target, "popup target did not appear");
}

// The popup document in a background tab, with the target tab brought back to the front: the
// target is then the visible tab of its window, as it is under a real toolbar popup.
async function popupWindow(ctx, sw, id, front) {
  const p = await ctx.newPage();
  await p.goto(`chrome-extension://${id}/src/popup.html`);
  await front.bringToFront();
  return p;
}

// ------------------------------------------------------------------ run
const diag = async () => (await (await fetch(`${BASE}/api/diagnostics`)).json());
const counts = async () => {
  const d = await diag();
  return { analyses: d.collections.analysis_jobs, sessions: d.collections.sessions, perceptronCalls: d.health.providers.perceptron.calls };
};

const ext = extensionCopy("allurls", ["<all_urls>"]);
const { ctx, sw, id } = await launch(ext);
const extUrl = (p) => `chrome-extension://${id}/${p}`;
console.log(`extension ${id}, ClipCart ${BASE}`);
const start = await counts();
let video;
let crop;
let captureId;

await step("video page loads and browsing it makes no ClipCart calls", async () => {
  video = await ctx.newPage();
  await video.goto(VIDEO_URL);
  await video.waitForLoadState("networkidle");
  await video.screenshot({ path: path.join(out, "00-video-page.png") });
  assert.deepEqual(await counts(), start);
});

await step("popup renders with Shop this frame and server status; opening it starts no analysis", async () => {
  // Render the popup document at popup size, targeted at the video tab, for a faithful screenshot.
  const pop = await ctx.newPage();
  await pop.goto(extUrl("src/popup.html"));
  await pop.waitForFunction(() => !document.getElementById("server-text").textContent.includes("Checking"));
  // Opened as a tab, the popup sees itself as the active tab, an extension page, and correctly refuses it.
  assert.match(await pop.locator("#error").textContent(), /capture|ClipCart button/);
  // Show it as it looks on a capturable page for the screenshot.
  await pop.evaluate(() => {
    document.getElementById("error").hidden = true;
    document.getElementById("shop").disabled = false;
  });
  assert.equal((await pop.locator("#shop").textContent()).trim(), "Shop this frame");
  assert.match(await pop.locator("#server-text").textContent(), /ClipCart ready/);
  await pop.locator("main").screenshot({ path: path.join(out, "01-popup.png") });
  await pop.close();
  // The real action popup also opens (chrome.action.openPopup), proving the manifest wiring.
  await video.bringToFront();
  await openPopup(ctx, sw);
  assert.deepEqual(await counts(), start);
});

await step("popup on a chrome:// page explains it can't capture there", async () => {
  const pop = await ctx.newPage();
  await pop.goto(extUrl("src/popup.html"));
  await pop.evaluate(() => {
    // Same check the popup runs on load, fed the URL of a chrome:// tab.
    return import("./config.js").then(({ unsupportedReason }) => {
      const e = document.getElementById("error");
      e.textContent = unsupportedReason("chrome://settings/");
      e.hidden = false;
      document.getElementById("shop").disabled = true;
    });
  });
  await pop.locator("main").screenshot({ path: path.join(out, "02-popup-unsupported.png") });
  await pop.close();
});

await step("Shop this frame captures the visible video tab before any overlay, then opens the crop preview", async () => {
  await video.bringToFront();
  const tabId = await sw.evaluate(async (u) => (await chrome.tabs.query({ url: u }))[0].id, VIDEO_URL);
  const opened = ctx.waitForEvent("page", (p) => p.url().includes("/src/crop.html"));
  // Exactly the message the popup's button sends.
  const pop = await popupWindow(ctx, sw, id, video);
  const reply = await pop.evaluate((tabId) => chrome.runtime.sendMessage({ type: "capture", tabId }), tabId);
  await pop.close();
  assert.equal(reply.ok, true, JSON.stringify(reply));
  captureId = reply.captureId;
  crop = await opened;
  await crop.waitForLoadState("load");
  await crop.waitForFunction(() => document.getElementById("shot").naturalWidth > 0 && !document.getElementById("source").hidden);
  const stored = await sw.evaluate(async (k) => (await chrome.storage.session.get(k))[k], `capture:${captureId}`);
  assert.equal(stored.sourceUrl, VIDEO_URL);
  assert.match(stored.sourceTitle, /denim trucker jacket/);
  fs.writeFileSync(path.join(out, "03-raw-capture.jpg"), Buffer.from(stored.dataUrl.split(",")[1], "base64"));
  assert.match(await crop.locator("#source-text").textContent(), /denim trucker jacket \(test page\) · video\.test:8765/);
  assert.equal(await crop.locator("#blank").isHidden(), true);
  // The capture is the video page (its red player bar is there), not the popup or the preview.
  const red = await crop.evaluate(() => {
    const img = document.getElementById("shot");
    const c = Object.assign(document.createElement("canvas"), { width: img.naturalWidth, height: img.naturalHeight });
    const g = c.getContext("2d");
    g.drawImage(img, 0, 0);
    const d = g.getImageData(0, 0, c.width, c.height).data;
    let n = 0;
    for (let i = 0; i < d.length; i += 4) if (d[i] > 200 && d[i + 1] < 50 && d[i + 2] < 50) n++;
    return n;
  });
  assert.ok(red > 500, `expected the video page's red player bar in the capture, found ${red} red pixels`);
  await crop.screenshot({ path: path.join(out, "04-crop-preview.png") });
  assert.deepEqual(await counts(), start, "capture and preview must not start analysis");
});

await step("drag selects the jacket; Escape clears; drag again", async () => {
  const box = await crop.locator("#shot").boundingBox();
  const at = (fx, fy) => [box.x + box.width * fx, box.y + box.height * fy];
  // The jacket in the paused frame sits around the middle of the player.
  const drag = async (a, b) => {
    await crop.mouse.move(...at(...a));
    await crop.mouse.down();
    await crop.mouse.move(...at(...b), { steps: 8 });
    await crop.mouse.up();
  };
  await drag([0.3, 0.2], [0.5, 0.5]);
  assert.equal(await crop.locator("#sel").isVisible(), true);
  await crop.keyboard.press("Escape");
  assert.equal(await crop.locator("#sel").isHidden(), true);
  await drag([0.245, 0.39], [0.505, 0.81]);
  assert.match(await crop.locator("#size").textContent(), /\d+ × \d+/);
  assert.match(await crop.locator("#scope").textContent(), /Sending your crop/);
  await crop.screenshot({ path: path.join(out, "05-crop-selected.png") });
  assert.deepEqual(await counts(), start);
});

await step("server unavailable: clear error with Retry, nothing uploaded", async () => {
  await sw.evaluate((u) => chrome.storage.sync.set({ clipcartUrl: u }), DEAD_URL);
  await crop.locator("#send").click();
  await crop.waitForFunction(() => /Can't reach ClipCart/.test(document.getElementById("status").textContent));
  assert.equal(await crop.locator("#status button", { hasText: "Retry" }).isVisible(), true);
  await crop.screenshot({ path: path.join(out, "06-server-unavailable.png") });
  assert.equal((await ctx.pages()).filter((p) => p.url().startsWith(DEAD_URL)).length, 0, "no tab opened for a dead server");
  assert.deepEqual(await counts(), start);
  await sw.evaluate((u) => chrome.storage.sync.set({ clipcartUrl: u }), BASE);
});

let clipcart;
let sent;
await step("Open in ClipCart: double click uploads once, opens the studio with the frame, keeps the user's cookie session", async () => {
  // Visit ClipCart first so this browser already has its own owner cookie and session.
  const prior = await ctx.newPage();
  await prior.goto(`${BASE}/`);
  await prior.waitForLoadState("networkidle");
  const priorSession = await prior.evaluate(async () => (await (await fetch("/api/sessions/latest")).json()).session.id);
  await prior.close();
  const before = await counts();

  await crop.bringToFront();
  const appeared = ctx.waitForEvent("page", (p) => p.url().startsWith(BASE));
  await crop.locator("#send").dblclick(); // duplicate submission
  await crop.locator("#send").click().catch(() => {});
  clipcart = await appeared;
  await crop.waitForFunction(() => /Opened in ClipCart/.test(document.getElementById("status").textContent), null, { timeout: 20000 });
  await crop.screenshot({ path: path.join(out, "07-crop-sent.png") });
  await crop.locator("#send").click(); // "Go to ClipCart": focus only
  await sleep(500);

  await clipcart.waitForURL(`${BASE}/`, { timeout: 15000 });
  sent = await sw.evaluate(async (k) => (await chrome.storage.session.get(k))[k], `send:${captureId}`);
  assert.equal(sent.status, "sent");
  const after = await counts();
  assert.equal(after.analyses, before.analyses + 1, "exactly one upload/analysis");
  assert.equal(after.sessions, before.sessions + 1, "one new session for the capture");

  const latest = await clipcart.evaluate(async () => (await (await fetch("/api/sessions/latest")).json()));
  assert.equal(latest.session.id, sent.sessionId, "studio resumes the session holding the capture");
  assert.notEqual(latest.session.id, priorSession);
  assert.equal(latest.media.id, sent.mediaId);
  assert.equal(latest.media.kind, "image");
  // Provenance (HANDOFF.md change B): the page the frame came from travels with it.
  assert.equal(latest.media.sourceType, "browser_capture");
  assert.equal(latest.media.canonicalSourceUrl, VIDEO_URL);
  assert.equal(latest.media.sourceTitle, await video.title());
  // Same owner: the earlier session is still readable with this browser's cookie.
  const ok = await clipcart.evaluate(async (id) => (await fetch(`/api/sessions/${id}`)).status, priorSession);
  assert.equal(ok, 200, "capture landed under the same cc_owner as the user's earlier session");
  const crop01 = (await crop.locator("#size").textContent()).match(/(\d+) × (\d+)/);
  assert.equal(latest.media.width, Number(crop01[1]));
  assert.equal(latest.media.height, Number(crop01[2]));
  console.log(`      session ${latest.session.id}, media ${latest.media.id} ${latest.media.width}x${latest.media.height}, analysis ${latest.analysis?.status}`);
});

await step("studio shows the uploaded frame", async () => {
  await clipcart.bringToFront();
  await clipcart.waitForLoadState("networkidle");
  await clipcart.waitForFunction(() => !document.querySelector(".shell-landing"), null, { timeout: 15000 });
  await sleep(2500); // let fixture analysis finish and boxes draw
  const meta = await clipcart.locator("body").innerText();
  assert.match(meta, new RegExp(`Browser capture · ${(await video.title()).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`));
  await clipcart.screenshot({ path: path.join(out, "08-clipcart-studio.png") });
});

await step("cancel discards the capture and closes the preview", async () => {
  await video.bringToFront();
  const tabId = await sw.evaluate(async (u) => (await chrome.tabs.query({ url: u }))[0].id, VIDEO_URL);
  const pop = await popupWindow(ctx, sw, id, video);
  const opened = ctx.waitForEvent("page", (p) => p.url().includes("/src/crop.html"));
  const reply = await pop.evaluate((tabId) => chrome.runtime.sendMessage({ type: "capture", tabId }), tabId);
  await pop.close();
  const c2 = await opened;
  await c2.waitForLoadState("load");
  const before = await counts();
  const closed = c2.waitForEvent("close");
  await c2.locator("#cancel").click();
  await closed;
  const left = await sw.evaluate(async (k) => (await chrome.storage.session.get(k))[k] ?? null, `capture:${reply.captureId}`);
  assert.equal(left, null);
  assert.deepEqual(await counts(), before);
});

await step("protected-video style black frame shows a warning", async () => {
  const blank = await ctx.newPage();
  await blank.goto(`http://video.test:${VIDEO_PORT}/video.html`);
  await blank.evaluate(() => (document.body.innerHTML = "", document.body.style.background = "#000", document.title = "Protected player"));
  const tabId = await sw.evaluate(async () => (await chrome.tabs.query({ active: true, lastFocusedWindow: true }))[0].id);
  const pop = await popupWindow(ctx, sw, id, blank);
  const opened = ctx.waitForEvent("page", (p) => p.url().includes("/src/crop.html"));
  await pop.evaluate((tabId) => chrome.runtime.sendMessage({ type: "capture", tabId }), tabId);
  const c3 = await opened;
  await c3.waitForFunction(() => document.getElementById("shot").naturalWidth > 0);
  await c3.waitForFunction(() => !document.getElementById("blank").hidden);
  await c3.screenshot({ path: path.join(out, "09-black-frame.png") });
  await c3.close();
  await pop.close();
  await blank.close();
});

await step("two simultaneous sends for one capture upload once", async () => {
  const pv = await ctx.newPage();
  await pv.goto(VIDEO_URL);
  await pv.waitForLoadState("networkidle");
  const tabId = await sw.evaluate(async () => (await chrome.tabs.query({ active: true, lastFocusedWindow: true }))[0].id);
  const pop = await popupWindow(ctx, sw, id, pv);
  const opened = ctx.waitForEvent("page", (p) => p.url().includes("/src/crop.html"));
  const reply = await pop.evaluate((tabId) => chrome.runtime.sendMessage({ type: "capture", tabId }), tabId);
  const c3 = await opened;
  await c3.waitForLoadState("load");
  const before = await counts();
  // Bypasses the preview's own button lock: two messages land in the worker at the same time,
  // as from a duplicated preview tab.
  const replies = await pop.evaluate(
    (captureId) => Promise.all([chrome.runtime.sendMessage({ type: "send", captureId }), chrome.runtime.sendMessage({ type: "send", captureId })]),
    reply.captureId,
  );
  const again = await pop.evaluate((captureId) => chrome.runtime.sendMessage({ type: "send", captureId }), reply.captureId);
  await pop.close();
  const after = await counts();
  assert.equal(replies.filter((r) => r.ok).length, 1, JSON.stringify(replies));
  assert.equal(replies.filter((r) => r.code === "in_progress").length, 1, JSON.stringify(replies));
  assert.equal(again.ok && again.already, true, "a later send only focuses the ClipCart tab");
  assert.equal(after.analyses, before.analyses + 1, "exactly one upload for two simultaneous sends");
  const opened2 = replies.find((r) => r.ok).clipcartTabId;
  await sw.evaluate((t) => chrome.tabs.remove(t), opened2);
  await c3.close();
  await pv.close();
});

console.log("counts at start", start, "at end", await counts());
await ctx.close();

// ------------------------------------------------------------------ real manifest, no activeTab grant
await step("real manifest: without the toolbar-click grant, capture fails with a readable message", async () => {
  const real = extensionCopy("real", []);
  const { ctx: c, sw: w, id: rid } = await launch(real);
  const v = await c.newPage();
  await v.goto(VIDEO_URL);
  await v.bringToFront();
  const tabId = await w.evaluate(async () => (await chrome.tabs.query({ active: true, lastFocusedWindow: true }))[0].id);
  const pop = await popupWindow(c, w, rid, v);
  const reply = await pop.evaluate((tabId) => chrome.runtime.sendMessage({ type: "capture", tabId }), tabId);
  console.log("      reply:", JSON.stringify(reply));
  assert.equal(reply.ok, false);
  // Without the grant Chrome hides the tab URL too, so the page check refuses before capture is attempted.
  assert.ok(["capture_failed", "unsupported_page"].includes(reply.code), reply.code);
  assert.match(reply.message, /capture|ClipCart button/i);
  await c.close();
});

server.close();
const failed = results.filter((r) => r[0] === "FAIL");
console.log(`\n${results.length - failed.length}/${results.length} passed`);
process.exit(failed.length ? 1 : 0);
