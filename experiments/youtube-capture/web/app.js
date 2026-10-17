/* Primary path: URL → yt-dlp cache → ffmpeg frames → Perceptron */

const DEFAULT_URL = "https://www.youtube.com/watch?v=aqz-KE-bpKQ";

const els = {
  urlInput: document.getElementById("urlInput"),
  analyzeBtn: document.getElementById("analyzeBtn"),
  frameCount: document.getElementById("frameCount"),
  geometryOnly: document.getElementById("geometryOnly"),
  status: document.getElementById("status"),
  healthChip: document.getElementById("healthChip"),
  results: document.getElementById("results"),
  playerWrap: document.getElementById("playerWrap"),
};

els.urlInput.value = DEFAULT_URL;

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
    els.healthChip.title = data.primaryPath || "";
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
    new YT.Player("player", {
      videoId,
      playerVars: { playsinline: 1, rel: 0 },
    });
  };
  if (window.YT && window.YT.Player) mount();
  else window.onYouTubeIframeAPIReady = mount;
}

function drawBoxes(canvas, boxes) {
  const ctx = canvas.getContext("2d");
  ctx.lineWidth = Math.max(2, Math.round(canvas.width / 400));
  ctx.font = `${Math.max(12, Math.round(canvas.width / 45))}px sans-serif`;
  for (const b of boxes || []) {
    const [x0, y0, x1, y1] = b.box01;
    const left = x0 * canvas.width;
    const top = y0 * canvas.height;
    const w = (x1 - x0) * canvas.width;
    const h = (y1 - y0) * canvas.height;
    ctx.strokeStyle = "#00c853";
    ctx.fillStyle = "rgba(0,200,83,0.12)";
    ctx.fillRect(left, top, w, h);
    ctx.strokeRect(left, top, w, h);
    ctx.fillStyle = "#00c853";
    ctx.fillText(b.label || "garment", left + 4, Math.max(14, top - 6));
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
  const ctx = canvas.getContext("2d");
  ctx.drawImage(img, 0, 0);
  drawBoxes(canvas, (frame.detection && frame.detection.boxes) || []);

  const meta = document.createElement("div");
  meta.className = "meta";
  const det = frame.detection || {};
  meta.textContent = [
    `t=${Number(frame.timeSec).toFixed(2)}s · sample #${frame.index}`,
    `image ${frame.imageSize.width}×${frame.imageSize.height} · black=${frame.blackFrame}`,
    `detect=${det.mode || "?"} · model=${det.model || "—"} · boxes=${(det.boxes || []).length}`,
    det.requestId ? `requestId=${det.requestId}` : null,
    (det.boxes || [])
      .map((b) => `${b.label}: [${b.box01.map((n) => n.toFixed(3)).join(", ")}]`)
      .join("\n") || "no boxes",
  ]
    .filter(Boolean)
    .join("\n");

  card.appendChild(canvas);
  card.appendChild(meta);
  els.results.appendChild(card);
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
  loadPreview(videoId);
  setStatus("Downloading / using cache, extracting frames, running Perceptron…", "warn");

  try {
    const res = await fetch("/api/analyze-youtube", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        youtubeUrl,
        frameCount: Math.min(6, Math.max(1, Number(els.frameCount.value) || 3)),
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
    setStatus(
      `Done · videoId=${data.videoId} · cacheHit=${data.cacheHit} · frames=${data.frames?.length || 0} · ${data.elapsedMs}ms`,
      "ok",
    );
    for (const frame of data.frames || []) {
      try {
        await renderFrame(frame);
      } catch (err) {
        console.warn("render failed", err);
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
