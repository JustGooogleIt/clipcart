#!/usr/bin/env bash
# Builds the landing page's video previews and posters from the committed fit-check clips.
# Usage (from the repo root): bash apps/web/scripts/landing-media.sh
# Needs ffmpeg with libx264. Output: apps/web/src/assets/landing/
set -euo pipefail
SRC=downloads/fit-checks
OUT=apps/web/src/assets/landing
mkdir -p "$OUT"

# id  start(s)  length(s)  -- muted H.264 loops cut from the part of each clip where the outfit is clearest
LOOPS="
fc08 0 11
fc05 34 6
fc09 2 6
fc02 30 6
fc07 0 6
fc10 12 6
fc06 15 6
fc03 0 6
fc04 0 5.5
"

echo "$LOOPS" | while read -r id start len; do
  [ -z "$id" ] && continue
  src=$(ls "$SRC/${id}_"*.mp4)
  ffmpeg -v error -y -ss "$start" -t "$len" -i "$src" -an -vf "scale=360:-2,fps=30" \
    -c:v libx264 -preset slow -crf 30 -profile:v high -pix_fmt yuv420p -movflags +faststart "$OUT/$id-loop.mp4" </dev/null
  ffmpeg -v error -y -i "$OUT/$id-loop.mp4" -frames:v 1 -q:v 6 "$OUT/$id-poster.jpg" </dev/null
done

# The walkthrough plays the original fc01 clip unchanged (it is also the file "Try this video" uploads),
# so its timestamps match the source. Its poster is the walkthrough frame.
cp "$SRC"/fc01_*.mp4 "$OUT/fc01-sample.mp4"
ffmpeg -v error -y -ss 22 -i "$OUT/fc01-sample.mp4" -frames:v 1 -q:v 5 "$OUT/fc01-poster.jpg" </dev/null

ls -la "$OUT"
