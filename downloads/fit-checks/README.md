# Fit-check Shorts downloads

Local media for the 10 YouTube Shorts listed in [`fixtures/fit-checks/youtube_shorts.json`](../../fixtures/fit-checks/youtube_shorts.json).

Demo story and live results: [`docs/fit-checks.md`](../../docs/fit-checks.md).

**Not committed** — only this README is tracked. Run:

```bash
# from repo root (uses services/api/.venv yt-dlp when present)
services/api/.venv/bin/python scripts/download_fit_checks.py
```

Files land here as `fc01_<videoId>.mp4` … `fc10_….mp4` plus `index.json`.

Then upload a clip in the product UI, or paste the Short URL (product YouTube path).
