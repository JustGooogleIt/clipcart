#!/usr/bin/env python3
"""Offline/live still → Perceptron detect (for geometry proof without tab share).

Usage (from repo root, with key in env or .env):
  .venv/bin/python experiments/youtube-capture/scripts/detect_still.py path/to.jpg
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT / "server"))

# Load .env like the server does.
env_path = REPO / ".env"
if env_path.is_file():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v

from app import _perceptron_detect  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: detect_still.py <image.jpg>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    raw = path.read_bytes()
    if not os.getenv("PERCEPTRON_API_KEY", "").strip():
        print(
            json.dumps(
                {
                    "error": "PERCEPTRON_API_KEY missing",
                    "blocker": "model_input / credentials",
                }
            )
        )
        return 2
    out = _perceptron_detect(raw)
    # Never include env; print detect result only.
    print(json.dumps(out, indent=2))
    return 0 if out.get("boxes") is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
