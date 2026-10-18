// Shared settings and pure helpers. Imported by the service worker and the extension pages.

export const DEFAULT_CLIPCART_URL = "http://127.0.0.1:8000";

// The upload contract on `integration` has no provenance fields yet (see HANDOFF.md, change B).
// Flip this once the backend accepts sourceUrl/sourceTitle on POST /api/media/uploads.
export const SEND_PROVENANCE = false;

/** Normalize a user-typed ClipCart URL to its origin, or throw with a readable message. */
export function normalizeBaseUrl(raw) {
  const text = String(raw ?? "").trim();
  if (!text) throw new Error("Enter the address where ClipCart runs.");
  let url;
  try {
    url = new URL(/^[a-z][a-z0-9+.-]*:\/\//i.test(text) ? text : `http://${text}`);
  } catch {
    throw new Error("That doesn't look like a web address.");
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") throw new Error("Use an http:// or https:// address.");
  if (url.username || url.password) throw new Error("Leave the username and password out of the address.");
  return url.origin;
}

/** Match pattern for chrome.permissions; host patterns cover every port on that host. */
export function originPattern(base) {
  const u = new URL(base);
  return `${u.protocol}//${u.hostname}/*`;
}

export async function getBaseUrl() {
  const { clipcartUrl } = await chrome.storage.sync.get("clipcartUrl");
  try {
    return normalizeBaseUrl(clipcartUrl || DEFAULT_CLIPCART_URL);
  } catch {
    return DEFAULT_CLIPCART_URL;
  }
}

const BLOCKED_SCHEMES = ["chrome:", "chrome-extension:", "chrome-untrusted:", "devtools:", "edge:", "about:", "view-source:", "data:", "javascript:"];
const BLOCKED_HOSTS = ["chromewebstore.google.com"];

/** Why Chrome won't let an extension capture this tab, or null when capture should work. */
export function unsupportedReason(url) {
  if (!url) return "ClipCart can't see this tab. Click the ClipCart button while the video tab is in front.";
  let u;
  try {
    u = new URL(url);
  } catch {
    return "Chrome doesn't let extensions capture this tab.";
  }
  if (BLOCKED_SCHEMES.includes(u.protocol)) return "Chrome doesn't let extensions capture its own pages. Open a video page and try again.";
  if (BLOCKED_HOSTS.includes(u.hostname) || (u.hostname === "chrome.google.com" && u.pathname.startsWith("/webstore")))
    return "Chrome doesn't let extensions capture the Web Store.";
  if (u.protocol === "file:") return "Local files can't be captured. Open the video in a web page instead.";
  if (u.protocol !== "http:" && u.protocol !== "https:") return "This kind of page can't be captured.";
  return null;
}

/**
 * Convert a selection drawn on the displayed preview into source-pixel coordinates.
 * `sel` is {x, y, w, h} in display pixels, `shown` is the displayed image size, `natural` the real size.
 * Returns null when the selection is too small to be a deliberate crop.
 */
export function selectionToSourceRect(sel, shown, natural, minSourcePx = 32) {
  if (!sel || !shown.width || !shown.height) return null;
  const sx = natural.width / shown.width;
  const sy = natural.height / shown.height;
  let x0 = Math.min(sel.x, sel.x + sel.w);
  let y0 = Math.min(sel.y, sel.y + sel.h);
  let x1 = Math.max(sel.x, sel.x + sel.w);
  let y1 = Math.max(sel.y, sel.y + sel.h);
  x0 = Math.max(0, Math.round(x0 * sx));
  y0 = Math.max(0, Math.round(y0 * sy));
  x1 = Math.min(natural.width, Math.round(x1 * sx));
  y1 = Math.min(natural.height, Math.round(y1 * sy));
  const w = x1 - x0;
  const h = y1 - y0;
  if (w < minSourcePx || h < minSourcePx) return null;
  return { x: x0, y: y0, width: w, height: h };
}

/** True when nearly every sampled pixel is black: protected (DRM) video usually captures this way. */
export function looksBlank(rgba, threshold = 12, share = 0.985) {
  let dark = 0;
  let n = 0;
  for (let i = 0; i < rgba.length; i += 16) {
    n++;
    if (rgba[i] < threshold && rgba[i + 1] < threshold && rgba[i + 2] < threshold) dark++;
  }
  return n > 0 && dark / n >= share;
}
