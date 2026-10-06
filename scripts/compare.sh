#!/bin/bash
# Regression check of a render against a reference video.
#   scripts/compare.sh <out.mp4> <reference.mp4> [--fps N] [--json FILE] [--min-ssim X] [--max-dt S]
# Duration delta (ffprobe) + SSIM on 480p frames sampled at N fps (default 5) over the common length.
# Prints one verdict line (PASS/FAIL) and writes JSON (default <out>.compare.json). Exit 0 on PASS, 1 on FAIL.
set -euo pipefail
. "$(dirname "$0")/_lib.sh"

[ $# -ge 2 ] || { sed -n '2,6p' "$0"; exit 2; }
OUT="$1"; REF="$2"; shift 2
FPS=5; JSON="$OUT.compare.json"; MIN_SSIM=0.97; MAX_DT=0.1
while [ $# -gt 0 ]; do
  case "$1" in
    --fps) FPS="$2"; shift 2 ;;
    --json) JSON="$2"; shift 2 ;;
    --min-ssim) MIN_SSIM="$2"; shift 2 ;;
    --max-dt) MAX_DT="$2"; shift 2 ;;
    *) echo "compare.sh: unknown option $1" >&2; exit 2 ;;
  esac
done
for f in "$OUT" "$REF"; do [ -f "$f" ] || { echo "compare.sh: missing $f" >&2; exit 2; }; done
PY="$(pick_python)"
dur() { ffprobe -v error -show_entries format=duration -of csv=p=0 "$1"; }
D_OUT=$(dur "$OUT"); D_REF=$(dur "$REF")
STATS="$(mktemp "${TMPDIR:-/tmp}/ssim.XXXXXX")"
trap 'rm -f "$STATS"' EXIT
ffmpeg -hide_banner -nostats -v error -i "$OUT" -i "$REF" -lavfi \
  "[0:v]fps=$FPS,scale=854:480,setsar=1[a];[1:v]fps=$FPS,scale=854:480,setsar=1[b];[a][b]ssim=stats_file=$STATS:shortest=1" \
  -f null -
"$PY" - "$STATS" "$OUT" "$REF" "$D_OUT" "$D_REF" "$FPS" "$MIN_SSIM" "$MAX_DT" "$JSON" <<'EOF'
import json, re, sys
stats, out, ref, d_out, d_ref, fps, min_ssim, max_dt, js = sys.argv[1:]
v = [float(re.search(r'All:([\d.]+)', l).group(1)) for l in open(stats) if 'All:' in l]
if not v:
    sys.exit('compare.sh: no SSIM frames (empty or undecodable video?)')
mean = sum(v) / len(v)
worst = min(range(len(v)), key=v.__getitem__)
dt = float(d_out) - float(d_ref)
ok = abs(dt) <= float(max_dt) and mean >= float(min_ssim)
r = dict(out=out, reference=ref, duration_out=float(d_out), duration_ref=float(d_ref), duration_delta=round(dt, 3),
         ssim_mean=round(mean, 6), ssim_min=round(v[worst], 6), ssim_min_at_s=round(worst / float(fps), 2),
         frames_compared=len(v), sample_fps=float(fps), min_ssim=float(min_ssim), max_dt=float(max_dt),
         verdict='PASS' if ok else 'FAIL')
json.dump(r, open(js, 'w'), indent=1)
print(f"{r['verdict']} dt={dt:+.3f}s ssim_mean={mean:.4f} ssim_min={v[worst]:.4f}@{r['ssim_min_at_s']}s "
      f"frames={len(v)} json={js}")
sys.exit(0 if ok else 1)
EOF
