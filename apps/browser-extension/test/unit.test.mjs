import assert from "node:assert/strict";
import { test } from "node:test";
import { looksBlank, normalizeBaseUrl, originPattern, selectionToSourceRect, unsupportedReason } from "../src/config.js";

test("normalizeBaseUrl keeps only the origin and adds a scheme", () => {
  assert.equal(normalizeBaseUrl("127.0.0.1:8000"), "http://127.0.0.1:8000");
  assert.equal(normalizeBaseUrl(" http://localhost:5173/#/studio "), "http://localhost:5173");
  assert.equal(normalizeBaseUrl("https://clipcart.example.com/app"), "https://clipcart.example.com");
  assert.throws(() => normalizeBaseUrl(""), /Enter the address/);
  assert.throws(() => normalizeBaseUrl("ftp://x"), /http/);
  assert.throws(() => normalizeBaseUrl("http://u:p@host"), /username/);
});

test("originPattern covers every port on the host", () => {
  assert.equal(originPattern("http://127.0.0.1:8000"), "http://127.0.0.1/*");
  assert.equal(originPattern("https://shop.example.com"), "https://shop.example.com/*");
});

test("unsupportedReason blocks browser pages, the Web Store and files", () => {
  assert.equal(unsupportedReason("https://www.youtube.com/watch?v=x"), null);
  assert.equal(unsupportedReason("http://127.0.0.1:8765/video.html"), null);
  for (const url of ["chrome://newtab/", "chrome-extension://abc/x.html", "about:blank", "view-source:https://a.com", "edge://settings",
    "https://chromewebstore.google.com/detail/x", "https://chrome.google.com/webstore/detail/x", "file:///Users/a/v.mp4", undefined, "not a url"]) {
    assert.ok(unsupportedReason(url), `expected ${url} to be unsupported`);
  }
});

test("selectionToSourceRect scales display pixels to source pixels and clamps", () => {
  const shown = { width: 640, height: 360 };
  const natural = { width: 1920, height: 1080 };
  assert.deepEqual(selectionToSourceRect({ x: 100, y: 50, w: 200, h: 100 }, shown, natural), { x: 300, y: 150, width: 600, height: 300 });
  // dragged up-left, past the edge
  assert.deepEqual(selectionToSourceRect({ x: 50, y: 40, w: -80, h: -60 }, shown, natural), { x: 0, y: 0, width: 150, height: 120 });
  // too small to be a deliberate crop
  assert.equal(selectionToSourceRect({ x: 10, y: 10, w: 5, h: 5 }, shown, natural), null);
  assert.equal(selectionToSourceRect(null, shown, natural), null);
});

test("looksBlank flags an all-black frame only", () => {
  const black = new Uint8ClampedArray(4 * 1000);
  assert.equal(looksBlank(black), true);
  const scene = black.map((_, i) => (i % 4 === 3 ? 255 : (i * 37) % 256));
  assert.equal(looksBlank(scene), false);
});
