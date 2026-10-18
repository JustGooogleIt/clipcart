#!/usr/bin/env bash
# Builds the landing page's video previews and posters from the committed fit-check clips.
# Usage (from the repo root): bash apps/web/scripts/landing-media.sh
# Needs ffmpeg/ffprobe with libx264. Output: apps/web/src/assets/landing/
#
# Quality rules:
# - Never upscale. Each output keeps the source's native size, capped at HERO_MAX (hero) or CARD_MAX
#   (gallery and the clips beside the hero). The committed clips are all 360x640, so today every
#   output is 360x640; a sharper source dropped into downloads/fit-checks/ is used up to the cap.
# - The hero is re-encoded only when it has to be scaled down; otherwise its video stream is copied
#   untouched (no generation loss), with audio dropped.
# - Posters are taken from the source frame, not from the re-encoded loop.
set -euo pipefail
SRC=downloads/fit-checks
OUT=apps/web/src/assets/landing
HERO_MAX=1080
CARD_MAX=720
HERO_CRF=19
CARD_CRF=23
mkdir -p "$OUT"

width() { ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$1"; }
x264() { echo -c:v libx264 -preset slow -tune film -crf "$1" -profile:v high -pix_fmt yuv420p -movflags +faststart; }
poster() { # src time out [max width]
  ffmpeg -v error -y -ss "$2" -i "$1" -frames:v 1 -vf "scale='min(${4:-$CARD_MAX},iw)':-2:flags=lanczos" -q:v 2 "$3" </dev/null
}

# Hero: fc08 in full (11.1s).
src=$(ls "$SRC"/fc08_*.mp4)
if [ "$(width "$src")" -le "$HERO_MAX" ]; then
  ffmpeg -v error -y -i "$src" -an -c:v copy -movflags +faststart "$OUT/fc08-loop.mp4" </dev/null
else
  ffmpeg -v error -y -i "$src" -an -vf "scale=$HERO_MAX:-2:flags=lanczos" $(x264 $HERO_CRF) "$OUT/fc08-loop.mp4" </dev/null
fi
poster "$src" 0 "$OUT/fc08-poster.jpg" "$HERO_MAX"

# id  start(s)  length(s)  -- muted loops cut from the part of each clip where the outfit is clearest
LOOPS="
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
  ffmpeg -v error -y -ss "$start" -t "$len" -i "$src" -an -vf "scale='min($CARD_MAX,iw)':-2:flags=lanczos" \
    $(x264 $CARD_CRF) "$OUT/$id-loop.mp4" </dev/null
  poster "$src" "$start" "$OUT/$id-poster.jpg"
done

# The walkthrough plays the original fc01 clip unchanged (it is also the file "Try this video" uploads),
# so its timestamps match the source. Its poster is the walkthrough frame at 22s.
cp "$SRC"/fc01_*.mp4 "$OUT/fc01-sample.mp4"
poster "$OUT/fc01-sample.mp4" 22 "$OUT/fc01-poster.jpg"

for f in "$OUT"/*; do
  printf '%-18s %8s bytes  %s\n' "$(basename "$f")" "$(wc -c <"$f" | tr -d ' ')" \
    "$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 "$f")"
done
