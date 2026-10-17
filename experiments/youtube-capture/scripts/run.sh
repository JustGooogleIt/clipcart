#!/usr/bin/env bash
# Run the isolated YouTube tab-capture spike (does not start ClipCart main API).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
cd "$REPO"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export PERCEPTRON_MODEL="${PERCEPTRON_MODEL:-perceptron-mk1.5}"
# YouTube often bot-checks yt-dlp; Chrome cookies usually unblock local demos.
export YOUTUBE_COOKIES_FROM_BROWSER="${YOUTUBE_COOKIES_FROM_BROWSER:-chrome}"
PORT="${YOUTUBE_CAPTURE_PORT:-8765}"

echo "Starting YouTube download-cache spike on http://127.0.0.1:${PORT}"
if [[ -n "${PERCEPTRON_API_KEY:-}" ]]; then
  echo "Perceptron configured: yes (key not printed)"
else
  echo "Perceptron configured: no — set PERCEPTRON_API_KEY or repo .env"
fi
echo "yt-dlp cookies-from-browser: ${YOUTUBE_COOKIES_FROM_BROWSER}"

cd "$ROOT/server"
exec python -m uvicorn app:app --host 127.0.0.1 --port "$PORT"
