/* Auto-scan: URL → cache → full local scan → Perceptron on best frames */

// Short jacket lookbook (~90s) — replace with a team-owned fashion URL when available.
const DEFAULT_URL = "https://www.youtube.com/watch?v=7-etsr5-Z8A";

const els = {
  urlInput: document.getElementById("urlInput"),
  analyzeBtn: document.getElementById("analyzeBtn"),
  geometryOnly: document.getElementById("geometryOnly"),
  status: document.getElementById("status"),
  healthChip: document.getElementById("healthChip"),
  results: document.getElementById("results"),
  playerWrap: document.getElementById("playerWrap"),
  scanMeta: document.getElementById("scanMeta"),
  defaultHint: document.getElementById("defaultHint"),
};

els.urlInput.value = DEFAULT_URL;
els.defaultHint.textContent =
  "Default: Winter coats & jackets lookbook (demo). Prefer a URL you own/have permission to use.";

function setStatus(text, tone) {
  els.status.textContent = text;
  if (tone) els.status.dataset.tone = tone;
  else delete els.status.dataset.tone;
}

async function refreshHealth() {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    els.healthChip.textContent = data.perceptronConfigured
      ? `Perceptron ready · ${data.model}`
      : "Perceptron key missing";
  } catch {
    els.healthChip.textContent = "server offline";
  }
}

function parseVideoId(raw) {
  try {
    const u = new URL(raw.trim());
    if (u.hostname.includes("youtu.be")) return u.pathname.slice(1) || null;
    if (u.searchParams.get("v")) return u.searchParams.get("v");
  } catch {
    return null;
  }
  return null;
}

function loadPreview(videoId) {
  if (!window.YT) {
    const tag = document.createElement("script");
    tag.src = "https://www.youtube.com/iframe_api";
    document.head.appendChild(tag);
  }
  els.playerWrap.hidden = false;
  const mount = () => {
    document.getElementById("player").innerHTML = "";
    // eslint-disable-next-line no-new
    new YT.Player("player", { videoId, playerVars: { playsinline: 1, rel: 0 } });
  };
  if (window.YT && window.YT.Player) mount();
  else window.onYouTubeIframeAPIReady = mount;
}

function shortLabel(raw) {
  const s = String(raw || "").toLowerCase();
  if (s.includes("coat") || s.includes("jacket") || s.includes("blazer")) return "coat/jacket";
  if (s.includes("sweater") || s.includes("hoodie") || s.includes("knit")) return "sweater";
  if (s.includes("shirt") || s.includes("blouse") || s.includes("top")) return "top";
  if (s.includes("dress") || s.includes("skirt")) return "dress/skirt";
  if (s.includes("pants") || s.includes("jeans") || s.includes("trousers")) return "pants";
  if (s.includes("bag") || s.includes("handbag") || s.includes("backpack")) return "bag";
  return raw || "garment";
}

function drawBoxes(canvas, boxes) {
  const ctx = canvas.getContext("2d");
  ctx.lineWidth = Math.max(2, Math.round(canvas.width / 400));
  ctx.font = `600 ${Math.max(13, Math.round(canvas.width / 42))}px "Avenir Next", sans-serif`;
  for (const b of boxes || []) {
    const [x0, y0, x1, y1] = b.box01;
    const left = x0 * canvas.width;
    const top = y0 * canvas.height;
    const w = (x1 - x0) * canvas.width;
    const h = (y1 - y0) * canvas.height;
    ctx.strokeStyle = "#0f6a56";
    ctx.fillStyle = "rgba(15,106,86,0.10)";
    ctx.fillRect(left, top, w, h);
    ctx.strokeRect(left, top, w, h);
    const label = shortLabel(b.label);
    const pad = 4;
    const tw = ctx.measureText(label).width + pad * 2;
    const th = Math.max(16, Math.round(canvas.width / 38));
    const ly = Math.max(th + 2, top - 4);
    ctx.fillStyle = "#0f6a56";
    ctx.fillRect(left, ly - th, tw, th);
    ctx.fillStyle = "#fff";
    ctx.fillText(label, left + pad, ly - 5);
  }
}

async function renderFrame(frame) {
  const card = document.createElement("article");
  card.className = "card";
  const img = new Image();
  img.src = "/" + frame.artifactPath.replace(/\\/g, "/");
  await new Promise((resolve, reject) => {
    img.onload = resolve;
    img.onerror = reject;
  });
  const canvas = document.createElement("canvas");
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  canvas.getContext("2d").drawImage(img, 0, 0);
  const boxes = (frame.detection && frame.detection.boxes) || [];
  drawBoxes(canvas, boxes);

  const meta = document.createElement("div");
  meta.className = "meta";
  const det = frame.detection || {};
  const labels = boxes.map((b) => shortLabel(b.label)).filter(Boolean);
  meta.textContent = [
    `t=${Number(frame.timeSec).toFixed(2)}s · score=${frame.score ?? "—"} · sharp=${frame.sharpness}`,
    labels.length ? `found: ${labels.join(" · ")}` : "no garments in this still",
  ].join("\n");

  card.appendChild(canvas);
  card.appendChild(meta);
  // Prefer frames with garments at the top
  if (boxes.length) els.results.prepend(card);
  else els.results.appendChild(card);
}

async function analyze() {
  const youtubeUrl = els.urlInput.value.trim();
  const videoId = parseVideoId(youtubeUrl);
  if (!videoId) {
    setStatus("Could not parse a YouTube video id.", "bad");
    return;
  }
  els.analyzeBtn.disabled = true;
  els.results.innerHTML = "";
  els.scanMeta.hidden = true;
  loadPreview(videoId);
  setStatus("Caching video, scanning the whole clip, then detecting garments…", "warn");

  try {
    const res = await fetch("/api/analyze-youtube", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        youtubeUrl,
        mode: els.geometryOnly.checked ? "geometry_only" : "live",
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = data.detail || data;
      setStatus(
        `Failed (${res.status}): ${typeof detail === "string" ? detail : JSON.stringify(detail)}`,
        "bad",
      );
      return;
    }

    const scan = data.scan || {};
    els.scanMeta.hidden = false;
    els.scanMeta.textContent = [
      `${data.title || "(unknown)"}`,
      `cache ${data.cacheHit ? "hit" : "miss"} · ${(data.elapsedMs / 1000).toFixed(1)}s total`,
      `scanned ${scan.candidateCount} stills across ${scan.durationS}s locally (${scan.sceneCutCount} scene cuts)`,
      `Perceptron on ${scan.selectedCount} best frames → ${data.garmentFrames} with clothes`,
    ].join("\n");

    const tone = (data.garmentFrames || 0) > 0 ? "ok" : "warn";
    setStatus(
      `Scan complete · ${data.garmentFrames || 0} frame(s) with garments · ${scan.selectedCount} model calls`,
      tone,
    );

    for (const frame of data.frames || []) {
      try {
        await renderFrame(frame);
      } catch (err) {
        console.warn(err);
      }
    }
  } catch (err) {
    setStatus(String(err.message || err), "bad");
  } finally {
    els.analyzeBtn.disabled = false;
  }
}

els.analyzeBtn.addEventListener("click", () => analyze());
refreshHealth();
setInterval(refreshHealth, 15000);
