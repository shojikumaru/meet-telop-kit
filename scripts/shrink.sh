#!/bin/bash
# Re-encode a render small enough for the token-free branch delivery (scripts/deliver.sh, files < 95 MB).
#   scripts/shrink.sh <in.mp4> [out.mp4] [--max-mb N]      (default out: <in>.small.mp4, N = 90)
# Single-pass libx264 CRF 23 with a bitrate cap derived from the duration so the result lands under N MB;
# 1080p and the audio track are kept (audio stream-copied). Retries with a lower cap if still too big.
# Exit 0 only when the output exists and is <= N MB. ~1x realtime on 4 vCPU: run it detached in the cloud.
set -euo pipefail
. "$(dirname "$0")/_lib.sh"

IN=""; OUT=""; MAX_MB=90
while [ $# -gt 0 ]; do
  case "$1" in
    --max-mb) MAX_MB="$2"; shift 2 ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    -*) echo "shrink.sh: unknown option $1" >&2; exit 2 ;;
    *) if [ -z "$IN" ]; then IN="$1"; elif [ -z "$OUT" ]; then OUT="$1"; else echo "shrink.sh: extra argument $1" >&2; exit 2; fi; shift ;;
  esac
done
[ -n "$IN" ] || { sed -n '2,6p' "$0"; exit 2; }
[ -f "$IN" ] || { echo "shrink.sh: no such file: $IN" >&2; exit 2; }
OUT="${OUT:-${IN%.*}.small.mp4}"
[ "$OUT" != "$IN" ] || { echo "shrink.sh: output would overwrite the input" >&2; exit 2; }
PY="$(command -v python3)"
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$IN")
ABR=$(ffprobe -v error -select_streams a:0 -show_entries stream=bit_rate -of csv=p=0 "$IN" | head -1)
case "$ABR" in ''|N/A) ABR=192000 ;; esac
MAX_BYTES=$((MAX_MB * 1024 * 1024))
# video kbps cap = 93% of (budget - audio - 1% container overhead) / duration
CAP=$("$PY" -c "import sys; d,a,m=map(float,sys.argv[1:]); print(max(300, int((m*0.99*8/d - a)*0.93/1000)))" "$DUR" "$ABR" "$MAX_BYTES")
for try in 1 2 3; do
  echo "shrink: try $try: ${DUR}s, video cap ${CAP}k (crf 23, preset veryfast) -> $OUT"
  ffmpeg -v error -stats -y -i "$IN" -map 0:v:0 -map 0:a:0 -c:v libx264 -preset veryfast -crf 23 \
    -maxrate "${CAP}k" -bufsize "$((CAP * 2))k" -pix_fmt yuv420p -c:a copy -movflags +faststart "$OUT"
  S=$(fsize "$OUT")
  if [ "$S" -le "$MAX_BYTES" ]; then
    echo "shrink: OK $OUT ($S bytes, $(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT")s)"
    echo "  next: scripts/deliver.sh '$OUT' <tag>"
    exit 0
  fi
  echo "shrink: $S bytes > $MAX_BYTES, lowering the cap" >&2
  CAP=$((CAP * 80 / 100))
done
echo "shrink: FAILED - could not get $IN under $MAX_MB MB" >&2
exit 1
