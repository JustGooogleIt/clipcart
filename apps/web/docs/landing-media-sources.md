# Landing media sources

The landing clips come from the fit-check YouTube Shorts in `downloads/fit-checks/index.json`.

## Why the committed sources are 360x640

`scripts/download_fit_checks.py` passes `--max-height 720`, which builds a `height<=720` filter. For portrait Shorts that caps the **height** at 720, so the 720x1280 and 1080x1920 renditions are excluded and 360x640 is chosen. The width was never the limit.

## Native renditions (checked 2026-10-18)

The format lists were read with ordinary public access (`yt-dlp -F`, no cookies or sign-in). For every clip a higher-resolution **H.264** rendition is available. The best one was downloaded as HTTPS DASH video plus the original-language AAC audio into **`downloads/fit-checks-hires/`**. That folder is separate, local and gitignored. The working files in `downloads/fit-checks/` are unchanged.

| Clip | Current (downloads/fit-checks) | Native rendition used | yt-dlp format | Duration current / native | SSIM at matched times (native scaled to 360x640) |
| --- | --- | --- | --- | --- | --- |
| fc01 | 360x640 14953/500 | 1080x1920 14953/250 | 299+140 (1080x1920, 60 fps; original en-US audio) | 35.861 / 35.875 s | 1.0s 0.875, 17.93s 0.81, 22.5s 0.86, 34.36s 0.831 |
| fc02 | 360x640 30/1 | 1080x1920 30/1 | 137+140 | 57.045 / 57.051 s | 1.0s 0.924, 28.52s 0.921, 30.5s 0.918, 55.55s 0.879 |
| fc03 | 360x640 30/1 | 720x1280 30/1 | 136+140 (720x1280 is the highest H.264 rendition) | 11.401 / 11.447 s | 0.5s 0.968, 1.0s 0.967, 5.7s 0.983, 9.9s 0.965 |
| fc04 | 360x640 30/1 | 1080x1920 30/1 | 137+140 | 5.573 / 5.619 s | 0.5s 0.984, 1.0s 0.983, 2.79s 0.978, 4.07s 0.972 |
| fc05 | 360x640 30/1 | 1080x1920 30/1 | 137+140 | 64.597 / 64.598 s | 1.0s 0.936, 32.3s 0.963, 34.5s 0.964, 63.1s 0.946 |
| fc06 | 360x640 30/1 | 1080x1920 30/1 | 137+140 | 65.295 / 65.225 s | 1.0s 0.956, 15.5s 0.931, 32.65s 0.952, 63.79s 0.974 |
| fc07 | 360x640 2997/100 | 1080x1920 60000/1001 | 299+140 (60 fps) | 45.79 / 45.836 s | 0.5s 0.961, 1.0s 0.967, 22.89s 0.965, 44.29s 0.969 |
| fc08 | 360x640 30/1 | 1080x1920 30/1 | 137+140 | 11.122 / 11.169 s | 0.5s 0.973, 1.0s 0.961, 5.56s 0.985, 9.62s 0.987 |
| fc09 | 360x640 30/1 | 1080x1920 30/1 | 137+140 | 13.12 / 13.119 s | 1.0s 0.974, 2.5s 0.976, 6.56s 0.979, 11.62s 0.98 |
| fc10 | 360x640 30/1 | 1080x1920 30/1 | 137+140 | 23.808 / 23.8 s | 1.0s 0.909, 11.9s 0.953, 12.5s 0.95, 22.31s 0.966 |

### Same clips, same timestamps

- **Durations:** each native file matches the current one within 0.07 s, which is container rounding. Both start at 0.
- **Frame similarity:** frames at matched timestamps (1 s, the middle, near the end, and each landing loop's start, or 22.5 s for fc01) have SSIM 0.81–0.99 after the native frame is scaled down to 360x640. The lower fc01 scores come from comparing its 60 fps rendition with a 30 fps one.
- **Timing alignment:** at fc01's 22.0 s walkthrough frame, SSIM peaks at offset 0 (0.867) and drops to about 0.64 one frame either way. fc08 also peaks within one frame of 0. The timelines line up, so the walkthrough's 22 s box frame is unchanged.

### How the landing assets are built from them

```
LANDING_SRC=downloads/fit-checks-hires bash apps/web/scripts/landing-media.sh
```

The caps already in the script are kept, and **nothing is upscaled**:
- **Hero (fc08):** up to 1080 wide. The native stream is copied when it's ≤1080 wide.
- **Gallery loops:** up to 720 wide, at CRF 23.
- **Posters:** taken from the source frames.
- **fc01 walkthrough and upload sample:** this uses **YouTube's native 480x854, 30 fps rendition** (format 135 plus original audio), copied byte-for-byte, 5.6 MB. It's chosen on measured loading (below), not repository size. It matches the 360p file's timeline: SSIM at 22.0 s peaks at offset 0 (0.875). The 720p60 and 1080p60 renditions are kept locally in `downloads/fit-checks-hires/extra/`. The script still copies a sample ≤720 wide unchanged, and only scales down a wider one, keeping its frame rate, timestamps and audio.

No generative enhancement or upscaling is used, so garment details are whatever the native rendition shows.

## Measured loading (2026-10-18)

These were measured in Chrome 155 with a cold cache, through ClipCart's own server. `FileResponse` answers `Range` requests with `206`.

**Transfer:**

| | Integration (360p) | #24 with 720p fc01 | #24 with 480p fc01 (shipped) |
| --- | --- | --- | --- |
| First view (hero, side cards, posters, metadata) | 2.13 MB | 8.76 MB | 8.76 MB |
| Offscreen gallery loops on first view | 0–64 KB each (load interrupted) | same | same |
| fc01 on first view | metadata only | 64 KB | 64 KB |
| Walkthrough scroll-in: fc01 range request | `bytes=1310720-` (1.35 MB) | `bytes=7929856-` (7.9 MB) | `bytes=2654208-` (2.9 MB) |

Chrome makes one range request starting just before 0:19. It keeps buffering to the end of the file even after the demo pauses at 0:22, so the clip's bitrate decides the cost.

**Timing** (phone viewport, 60 ms latency):

| | 10 Mbps: largest paint / hero moving / walkthrough at 0:22 | 4 Mbps: same |
| --- | --- | --- |
| Integration | 0.64 / 1.23 / 2.87 s | 1.26 / 2.47 / 5.08 s |
| #24, 720p fc01 | 1.06 / 2.41 / 6.56 s | 2.32 / 5.66 / **14.8 s** |
| #24, 480p fc01 (shipped) | 1.15 / 2.50 / 4.66 s | 2.32 / 5.63 / 9.96 s |
| Same, with a 720p hero (comparison only) | 1.08 / 2.27 / 4.80 s | 2.30 / 5.41 / 10.97 s |

**Conclusions:**
- **Hero:** the **1080p hero stays**. Its poster, which shows the same frame, still paints within 2.5 s at 4 Mbps. A 720p re-encode is barely smaller (3.9 MB against 4.7 MB) and changes the timings by about 0.2 s.
- **fc01:** the **720p60 file was a measured problem**. It took 14.8 s to reach the walkthrough frame at 4 Mbps, so fc01 uses the native 480p30 rendition.

### Reproduce the download

```
services/api/.venv/bin/yt-dlp --no-cookies --no-playlist \
  -f "bv*[vcodec^=avc1][height<=1920][protocol=https]+ba[ext=m4a][format_note*=original]/bv*[vcodec^=avc1][height<=1920][protocol=https]+ba[ext=m4a]" \
  --merge-output-format mp4 -o "downloads/fit-checks-hires/<id>_<videoId>.%(ext)s" "https://www.youtube.com/shorts/<videoId>"
```

These are the same ten Shorts the app already uses (`fixtures/fit-checks/youtube_shorts.json`), at a higher resolution. Using them carries the same terms as the existing committed fit-check clips. The repository doesn't document rights for them, so that question is unchanged by this PR and stays with the owner.
