# Fit-check Shorts downloads

Local media for the 10 YouTube Shorts listed in [`fixtures/fit-checks/youtube_shorts.json`](../../fixtures/fit-checks/youtube_shorts.json).

Demo story and live results: [`docs/fit-checks.md`](../../docs/fit-checks.md).

**Tracked in git** — the `fc01_….mp4` … `fc10_….mp4` clips and `index.json` are committed (~26 MB) so anyone can clone and upload them in the product UI without re-downloading.

Re-download or refresh if a Short goes down:

```bash
# from repo root (uses services/api/.venv yt-dlp when present)
services/api/.venv/bin/python scripts/download_fit_checks.py
```

Source URLs stay in the fixture manifest. Prefer pasting the Short URL in the product YouTube path when the feature flag is on; uploading these MP4s is the offline fallback.
