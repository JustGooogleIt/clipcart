import { DEFAULT_CLIPCART_URL, getBaseUrl, normalizeBaseUrl, originPattern } from "./config.js";

const input = document.getElementById("url");
const msg = document.getElementById("msg");
input.value = await getBaseUrl();

function say(kind, text) {
  msg.className = `notice ${kind}`;
  msg.textContent = text;
  msg.hidden = !text;
}

async function save(raw) {
  let base;
  try {
    base = normalizeBaseUrl(raw);
  } catch (err) {
    say("err", err.message);
    return;
  }
  // Must run inside the click handler: Chrome only shows the prompt for a user gesture.
  const granted = await chrome.permissions.request({ origins: [originPattern(base)] });
  if (!granted) {
    say("err", `Not saved. ClipCart needs access to ${base} to hand frames over.`);
    return;
  }
  await chrome.storage.sync.set({ clipcartUrl: base });
  input.value = base;
  say("ok", `Saved. Frames go to ${base}.`);
}

document.getElementById("form").addEventListener("submit", (e) => {
  e.preventDefault();
  save(input.value);
});
document.getElementById("reset").addEventListener("click", () => save(DEFAULT_CLIPCART_URL));
