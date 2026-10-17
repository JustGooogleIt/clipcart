/* ClipCart YouTube tab-capture spike (browser-only capture; no downloader). */

const DEFAULT_URL = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"; // Big Buck Bunny (CC)

const els = {
  urlInput: document.getElementById("urlInput"),
  loadBtn: document.getElementById("loadBtn"),
  shareBtn: document.getElementById("shareBtn"),
  stopShareBtn: document.getElementById("stopShareBtn"),
  sampleBtn: document.getElementById("sampleBtn"),
  preview: document.getElementById("preview"),
  results: document.getElementById("results"),
  playerStatus: document.getElementById("playerStatus"),
  shareStatus: document.getElementById("shareStatus"),
  sampleStatus: document.getElementById("sampleStatus"),
  healthChip: document.getElementById("healthChip"),
  frameCount: document.getElementById("frameCount"),
  gapMs: document.getElementById("gapMs"),
  geometryOnly: document.getElementById("geometryOnly"),
  playerWrap: document.getElementById("playerWrap"),
};

els.urlInput.value = DEFAULT_URL;

let ytPlayer = null;
let ytReady = false;
let videoId = null;
let youtubeUrl = null;
let captureStream = null;
let captureVideoTrack = null;

function setStatus(el, text, tone) {
  el.textContent = text;
  if (tone) el.dataset.tone = tone;
  else delete el.dataset.tone;
}

function parseVideoId(raw) {
  try {
    const u = new URL(raw.trim());
    if (u.hostname.includes("youtu.be")) return u.pathname.slice(1) || null;
    if (u.searchParams.get("v")) return u.searchParams.get("v");
    const parts = u.pathname.split("/").filter(Boolean);
    const embed = parts.indexOf("embed");
    if (embed >= 0 && parts[embed + 1]) return parts[embed + 1];
    const shorts = parts.indexOf("shorts");
    if (shorts >= 0 && parts[shorts + 1]) return parts[shorts + 1];
  } catch {
    return null;
  }
  return null;
}

function loadYoutubeApi() {
  return new Promise((resolve, reject) => {
    if (window.YT && window.YT.Player) {
      resolve();
      return;
    }
    const tag = document.createElement("script");
    tag.src = "https://www.youtube.com/iframe_api";
    tag.onerror = () => reject(new Error("Failed to load YouTube IFrame API"));
    window.onYouTubeIframeAPIReady = () => resolve();
    document.head.appendChild(tag);
  });
}

async function refreshHealth() {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    const label = data.perceptronConfigured
      ? `Perceptron ready · ${data.model}`
      : "Perceptron key missing";
    els.healthChip.textContent = label;
    els.healthChip.title = JSON.stringify(data);
  } catch (err) {
    els.healthChip.textContent = "server offline";
  }
}

async function loadPlayer() {
  const url = els.urlInput.value.trim();
  const id = parseVideoId(url);
  if (!id) {
    setStatus(els.playerStatus, "Could not parse a YouTube video id from that URL.", "bad");
    return;
  }
  youtubeUrl = url;
  videoId = id;
  setStatus(els.playerStatus, "Loading YouTube IFrame API…");
  await loadYoutubeApi();
  if (ytPlayer) {
    ytPlayer.destroy();
    ytPlayer = null;
  }
  document.getElementById("player").innerHTML = "";
  ytReady = false;
  ytPlayer = new YT.Player("player", {
    videoId: id,
    playerVars: {
      playsinline: 1,
      rel: 0,
      modestbranding: 1,
    },
    events: {
      onReady: () => {
        ytReady = true;
        els.shareBtn.disabled = false;
        setStatus(
          els.playerStatus,
          `Player ready for ${id}. Press play, then share this tab.`,
          "ok",
        );
      },
      onError: (e) => {
        setStatus(els.playerStatus, `YouTube player error: ${e.data}`, "bad");
      },
    },
  });
}

function onShareEnded() {
  captureStream = null;
  captureVideoTrack = null;
  els.preview.srcObject = null;
  els.stopShareBtn.disabled = true;
  els.sampleBtn.disabled = true;
  setStatus(els.shareStatus, "Tab share ended or was stopped.", "warn");
}

async function startShare() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
    setStatus(
      els.shareStatus,
      "getDisplayMedia is not supported in this browser. Use Chrome/Chromium on desktop.",
      "bad",
    );
    return;
  }
  try {
    // preferCurrentTab is Chromium; ignored elsewhere.
    captureStream = await navigator.mediaDevices.getDisplayMedia({
      video: {
        displaySurface: "browser",
        frameRate: { ideal: 15, max: 30 },
      },
      audio: false,
      preferCurrentTab: true,
      selfBrowserSurface: "include",
      surfaceSwitching: "exclude",
      systemAudio: "exclude",
    });
  } catch (err) {
    const name = err && err.name ? err.name : "Error";
    if (name === "NotAllowedError") {
      setStatus(els.shareStatus, "Share denied or dismissed. No frames captured.", "bad");
    } else {
      setStatus(els.shareStatus, `Share failed: ${name} — ${err.message || err}`, "bad");
    }
    return;
  }

  captureVideoTrack = captureStream.getVideoTracks()[0] || null;
  if (captureVideoTrack) {
    captureVideoTrack.addEventListener("ended", onShareEnded);
  }
  els.preview.srcObject = captureStream;
  await els.preview.play().catch(() => {});
  els.stopShareBtn.disabled = false;
  els.sampleBtn.disabled = false;

  const settings = captureVideoTrack ? captureVideoTrack.getSettings() : {};
  setStatus(
    els.shareStatus,
    `Sharing · surface=${settings.displaySurface || "unknown"} · ${settings.width || "?"}×${settings.height || "?"} · stop sharing when finished.`,
    "ok",
  );
}

function stopShare() {
  if (captureStream) {
    for (const track of captureStream.getTracks()) track.stop();
  }
  onShareEnded();
  setStatus(els.shareStatus, "Share stopped; stream discarded.", "warn");
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function grabFrameBitmap() {
  const video = els.preview;
  if (!video.videoWidth || !video.videoHeight) {
    throw new Error("Capture preview has no video pixels yet");
  }
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas;
}

function playerRect() {
  const iframe = els.playerWrap.querySelector("iframe");
  if (!iframe) return { width: 0, height: 0 };
  const r = iframe.getBoundingClientRect();
  return { width: Math.round(r.width), height: Math.round(r.height) };
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
    ctx.fillStyle = "rgba(0,200,83,0.15)";
    ctx.fillRect(left, top, w, h);
    ctx.strokeRect(left, top, w, h);
    ctx.fillStyle = "#00c853";
    ctx.fillText(b.label || "garment", left + 4, Math.max(14, top - 6));
  }
}

function renderResultCard(payload, bitmapCanvas) {
  const card = document.createElement("article");
  card.className = "card";
  const out = document.createElement("canvas");
  out.width = bitmapCanvas.width;
  out.height = bitmapCanvas.height;
  out.getContext("2d").drawImage(bitmapCanvas, 0, 0);
  const boxes = (payload.detection && payload.detection.boxes) || [];
  drawBoxes(out, boxes);

  const meta = document.createElement("div");
  meta.className = "meta";
  const det = payload.detection || {};
  meta.textContent = [
    `t=${payload.playerTimeSec.toFixed(2)}s · sample #${payload.sampleIndex}`,
    `capture ${payload.captureSize.width}×${payload.captureSize.height} · image ${payload.imageSize.width}×${payload.imageSize.height} · player ${payload.playerSize.width}×${payload.playerSize.height}`,
    `luminance mean=${payload.luminance.mean} black=${payload.blackFrame}`,
    `detect mode=${det.mode || "?"} · model=${det.model || "—"} · boxes=${(det.boxes || []).length}`,
    det.requestId ? `requestId=${det.requestId}` : null,
    (det.boxes || [])
      .map((b) => `${b.label}: [${b.box01.map((n) => n.toFixed(3)).join(", ")}]`)
      .join("\n") || "no boxes",
  ]
    .filter(Boolean)
    .join("\n");

  card.appendChild(out);
  card.appendChild(meta);
  els.results.prepend(card);
}

async function sampleAndDetect() {
  if (!captureStream || !ytPlayer || !ytReady) {
    setStatus(els.sampleStatus, "Need an active tab share and a ready player.", "bad");
    return;
  }
  const n = Math.min(6, Math.max(1, Number(els.frameCount.value) || 1));
  const gap = Math.max(200, Number(els.gapMs.value) || 800);
  const mode = els.geometryOnly.checked ? "geometry_only" : "live";
  els.results.innerHTML = "";
  els.sampleBtn.disabled = true;

  try {
    if (ytPlayer.playVideo) ytPlayer.playVideo();
  } catch {
    /* ignore */
  }

  for (let i = 0; i < n; i++) {
    if (!captureStream || captureVideoTrack?.readyState !== "live") {
      setStatus(els.sampleStatus, `Share ended before sample ${i}.`, "bad");
      break;
    }
    let playerTimeSec = 0;
    try {
      playerTimeSec = ytPlayer.getCurrentTime() || 0;
    } catch {
      playerTimeSec = 0;
    }

    let canvas;
    try {
      canvas = grabFrameBitmap();
    } catch (err) {
      setStatus(els.sampleStatus, String(err.message || err), "bad");
      break;
    }

    setStatus(els.sampleStatus, `Uploading sample ${i + 1}/${n} at t=${playerTimeSec.toFixed(2)}s…`);

    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
    const rect = playerRect();
    const fd = new FormData();
    fd.append("file", blob, `frame_${i}.jpg`);
    fd.append("youtubeUrl", youtubeUrl || "");
    fd.append("videoId", videoId || "");
    fd.append("playerTimeSec", String(playerTimeSec));
    fd.append("sampleIndex", String(i));
    fd.append("captureWidth", String(canvas.width));
    fd.append("captureHeight", String(canvas.height));
    fd.append("playerWidth", String(rect.width));
    fd.append("playerHeight", String(rect.height));
    fd.append("mode", mode);

    const res = await fetch("/api/detect-frame", { method: "POST", body: fd });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = payload.detail || payload;
      setStatus(
        els.sampleStatus,
        `Detect failed (${res.status}): ${typeof detail === "string" ? detail : JSON.stringify(detail)}`,
        "bad",
      );
      // Still show the captured frame without boxes.
      renderResultCard(
        {
          playerTimeSec,
          sampleIndex: i,
          captureSize: { width: canvas.width, height: canvas.height },
          imageSize: { width: canvas.width, height: canvas.height },
          playerSize: rect,
          luminance: { mean: "?", min: "?", max: "?" },
          blackFrame: false,
          detection: { mode: "error", boxes: [] },
        },
        canvas,
      );
      break;
    }
    renderResultCard(payload, canvas);
    setStatus(
      els.sampleStatus,
      `Sample ${i + 1}/${n} done · detect=${payload.detection?.mode} · boxes=${payload.detection?.boxes?.length ?? 0}`,
      payload.blackFrame ? "warn" : "ok",
    );
    if (i < n - 1) await sleep(gap);
  }

  stopShare();
  setStatus(
    els.sampleStatus,
    `${els.sampleStatus.textContent} · capture stream discarded.`,
    els.sampleStatus.dataset.tone || "ok",
  );
  els.sampleBtn.disabled = true;
}

els.loadBtn.addEventListener("click", () => loadPlayer().catch((e) => setStatus(els.playerStatus, String(e), "bad")));
els.shareBtn.addEventListener("click", () => startShare());
els.stopShareBtn.addEventListener("click", () => stopShare());
els.sampleBtn.addEventListener("click", () => sampleAndDetect().catch((e) => setStatus(els.sampleStatus, String(e), "bad")));

refreshHealth();
setInterval(refreshHealth, 15000);
