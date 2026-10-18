#!/usr/bin/env bash
# Local run: build the web app and serve UI + API on http://127.0.0.1:8000
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null || { echo "ffmpeg/ffprobe required on PATH"; exit 1; }
if [ -f "$ROOT/.env" ]; then set -a; . "$ROOT/.env"; set +a; fi
cd "$ROOT/services/api"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
(cd "$ROOT/apps/web" && npm ci --no-audit --no-fund && npm run build)
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}"
