#!/usr/bin/env python3
"""Download the fit-check YouTube Shorts truth set into downloads/fit-checks/.

Usage (from repo root):
  services/api/.venv/bin/python scripts/download_fit_checks.py
  # or: python3 scripts/download_fit_checks.py   (needs yt-dlp on PATH/venv)

Media is written under downloads/fit-checks/ (gitignored). Re-run is safe —
existing files are skipped unless --force.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "fixtures" / "fit-checks" / "youtube_shorts.json"
DEFAULT_OUT = ROOT / "downloads" / "fit-checks"


def _yt_dlp_bin() -> list[str]:
    api_yt = ROOT / "services" / "api" / ".venv" / "bin" / "yt-dlp"
    if api_yt.is_file():
        return [str(api_yt)]
    root_yt = ROOT / ".venv" / "bin" / "yt-dlp"
    if root_yt.is_file():
        return [str(root_yt)]
    return [sys.executable, "-m", "yt_dlp"]


def download_one(url: str, out_tmpl: Path, *, force: bool, max_height: int) -> tuple[bool, str]:
    existing = list(out_tmpl.parent.glob(out_tmpl.name.replace("%(ext)s", "*")))
    # Also match after yt-dlp fills extension
    stem = out_tmpl.name.replace(".%(ext)s", "")
    hits = [p for p in out_tmpl.parent.glob(f"{stem}.*") if p.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}]
    if hits and not force:
        return True, f"skip (exists): {hits[0].name}"

    fmt = (
        f"bv*[height<={max_height}][ext=mp4]+ba[ext=m4a]/"
        f"b[height<={max_height}][ext=mp4]/"
        f"b[height<={max_height}]/best"
    )
    cmd = [
        *_yt_dlp_bin(),
        "--no-playlist",
        "--no-warnings",
        "--extractor-args",
        "youtube:player_client=android",
        "-f",
        fmt,
        "--merge-output-format",
        "mp4",
        "-o",
        str(out_tmpl),
        "--print",
        "after_move:%(title)s\t%(duration)s\t%(filepath)s",
        url,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
    except FileNotFoundError:
        return False, "yt-dlp missing — install services/api requirements or pip install yt-dlp"
    except subprocess.TimeoutExpired:
        return False, "timeout (>180s)"

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "yt-dlp failed")[-500:]
        return False, err.strip()

    line = (proc.stdout or "").strip().splitlines()[-1] if (proc.stdout or "").strip() else "ok"
    return True, line


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-download even if file exists")
    ap.add_argument("--max-height", type=int, default=720)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    ap.add_argument("--only", nargs="*", help="optional fc01..fc10 ids to download")
    args = ap.parse_args()

    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    clips = data["clips"]
    if args.only:
        want = set(args.only)
        clips = [c for c in clips if c["id"] in want]
        if not clips:
            print("No matching clip ids.", file=sys.stderr)
            return 2

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / ".gitkeep").write_text("", encoding="utf-8")

    ok = fail = 0
    index: list[dict] = []
    print(f"Downloading {len(clips)} Shorts → {out_dir}")
    for c in clips:
        stem = f"{c['id']}_{c['videoId']}"
        out_tmpl = out_dir / f"{stem}.%(ext)s"
        success, detail = download_one(c["url"], out_tmpl, force=args.force, max_height=args.max_height)
        status = "ok" if success else "FAIL"
        print(f"  [{status}] {c['id']} {c['label']}: {detail[:160]}")
        if success:
            ok += 1
            files = sorted(out_dir.glob(f"{stem}.*"))
            media = next((p for p in files if p.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}), None)
            index.append({**c, "path": media.name if media else None, "download": detail})
        else:
            fail += 1
            index.append({**c, "path": None, "error": detail[:800]})

    index_path = out_dir / "index.json"
    index_path.write_text(json.dumps({"clips": index, "ok": ok, "fail": fail}, indent=2), encoding="utf-8")
    print(f"Done: {ok} ok, {fail} failed. Index: {index_path}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
