#!/bin/bash
# Fast end-to-end smoke test: synthetic 12 s source -> build_base -> telops (--limit 5) -> preview stills.
# Asserts frame count, duration, audio, that telops were drawn, and that preview stills exist. ~20 s.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1   # leave no __pycache__ in the tree under test
REPO="$(cd "$(dirname "$0")/.." && pwd)"
. "$REPO/scripts/_lib.sh"
PY="$(pick_python)"
T="$(mktemp -d "${TMPDIR:-/tmp}/meet-telop-smoke.XXXXXX")"
trap 'rm -rf "$T"' EXIT
fail() { echo "SMOKE FAIL: $*" >&2; exit 1; }

ffmpeg -v error -y -f lavfi -i "testsrc2=size=1920x1080:rate=24:duration=12" \
  -f lavfi -i "sine=frequency=440:sample_rate=48000:duration=12" -c:v libx264 -preset ultrafast -pix_fmt yuv420p \
  -c:a aac -shortest "$T/src.mp4"
export STUDIO_EDL="$REPO/tests/smoke_edl.py" STUDIO_WORK="$T/work"
cd "$REPO/studio"
"$PY" fonts.py
"$PY" build_base.py --src "$T/src.mp4" --limit 5
"$PY" telops.py --limit 5 --out "$T/out.mp4"
"$PY" preview.py --limit 5 --at 1.0,3.4 >/dev/null

frames=$(ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 "$T/out.mp4")
dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$T/out.mp4")
astreams=$(ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "$T/out.mp4" | wc -l | tr -d ' ')
[ "$frames" = 150 ] || fail "expected 150 frames, got $frames"
"$PY" -c "import sys; sys.exit(0 if abs(float(sys.argv[1]) - 5.0) < 0.1 else 1)" "$dur" || fail "duration $dur != 5.0"
[ "$astreams" = 1 ] || fail "expected 1 audio stream, got $astreams"
total=$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['total'])" "$T/work/timeline.json")
"$PY" -c "import sys; sys.exit(0 if abs(float(sys.argv[1]) - 7.32) < 0.05 else 1)" "$total" || fail "timeline total $total != 7.32"
# telops must change the picture (base vs final at 1.6 s: section header, plate, chips, gold pop)
ffmpeg -v error -y -ss 1.6 -i "$T/work/base.mov" -frames:v 1 -vf scale=480:270 -f rawvideo -pix_fmt gray "$T/b.gray"
ffmpeg -v error -y -ss 1.6 -i "$T/out.mp4" -frames:v 1 -vf scale=480:270 -f rawvideo -pix_fmt gray "$T/f.gray"
"$PY" - "$T/b.gray" "$T/f.gray" <<'EOF' || fail "telop layer not visible at 1.6 s"
import sys
a, b = open(sys.argv[1], 'rb').read(), open(sys.argv[2], 'rb').read()
changed = sum(1 for x, y in zip(a, b) if abs(x - y) > 40) / len(a)
print(f'pixels changed by telops at 1.6s: {changed:.1%}')
sys.exit(0 if changed > 0.05 else 1)
EOF
for s in 1.0 3.4; do [ -s "$T/work/prev/$s.jpg" ] || fail "missing preview still $s"; done
# a typo'd flag is an error, not silently ignored
if "$PY" telops.py --limit 5 --soruce-offset 1 --out "$T/typo.mp4" 2>/dev/null; then fail "config accepted --soruce-offset"; fi
# telops must exit non-zero when base.mov is shorter than build_base recorded (no silent short render)
ffmpeg -v error -y -i "$T/work/base.mov" -t 3 -c copy "$T/short.mov"
mv "$T/short.mov" "$T/work/base.mov"
if "$PY" telops.py --limit 5 --out "$T/short.mp4" 2>"$T/short.err"; then fail "telops accepted a truncated base.mov"; fi
grep -q 'telops.py: .*FAILED\|telops.py: .*failed' "$T/short.err" || fail "no telops failure message: $(tail -c 300 "$T/short.err")"
# --limit must be > 0 (0 used to mean "full render" silently)
for bad in 0 -3; do
  if "$PY" build_base.py --src "$T/src.mp4" --work "$T/lim" --limit "$bad" 2>"$T/lim.err"; then fail "build_base accepted --limit $bad"; fi
  grep -q 'must be > 0' "$T/lim.err" || fail "no --limit message for $bad: $(tail -c 300 "$T/lim.err")"
done
# a cut that runs past the end of the source is an error, not a silently short render
printf 'exec(open(%s).read())\nCLIPS = [(9.0, 14.0, "J", "past EOF")]\n' "'$REPO/tests/smoke_edl.py'" > "$T/eof_edl.py"
if STUDIO_EDL="$T/eof_edl.py" "$PY" build_base.py --src "$T/src.mp4" --work "$T/eof" 2>"$T/eof.err"; then
  fail "build_base accepted a cut past the end of the source"
fi
grep -q 'past the end of the source' "$T/eof.err" || fail "no past-EOF message: $(tail -c 300 "$T/eof.err")"
# ...but a final clip that ends exactly at the end of the source is fine (only its PAD_OUT margin is missing)
printf 'exec(open(%s).read())\nCLIPS = [(10.0, 12.0, "J", "ends at EOF")]\n' "'$REPO/tests/smoke_edl.py'" > "$T/ateof_edl.py"
STUDIO_EDL="$T/ateof_edl.py" "$PY" build_base.py --src "$T/src.mp4" --work "$T/ateof" 2>"$T/ateof.err" \
  || fail "build_base rejected a clip ending exactly at EOF: $(tail -c 300 "$T/ateof.err")"
# anchored timing (default): clip starts, blur window and total follow the REAL segment starts in base.mov
STUDIO_EDL="$REPO/tests/smoke_anchored_edl.py" "$PY" build_base.py --src "$T/src.mp4" --work "$T/anch" 2>"$T/anch.err" \
  || fail "anchored build_base failed: $(tail -c 300 "$T/anch.err")"
ffprobe -v error -select_streams v:0 -show_entries packet=pts_time -of csv=p=0 "$T/anch/base.mov" > "$T/anch.pts"
anch=$("$PY" - "$T/anch/timeline.json" "$T/anch.pts" <<'EOF'
import json, sys
tl = json.load(open(sys.argv[1]))
pts = sorted(float(x) for x in open(sys.argv[2]) if x.strip())
pts = [p - pts[0] for p in pts]
F = 1 / 30
assert tl['timing'] == 'anchored', tl['timing']
real, k = [], 0
for n in tl['nframes']:  # first frame of each segment, as ffprobe sees it in base.mov
    real.append(pts[k]); k += n
nominal, t = [], 0.0
for a2, b2 in tl['cuts']:
    nominal.append(t); t += b2 - a2
for i, (r, s) in enumerate(zip(real, tl['seg_starts'])):
    assert abs(r - s) <= F, f'segment {i}: base.mov starts at {r:.3f}, timeline says {s:.3f}'
for i, ((a, b, s), r) in enumerate(zip(tl['out'], real)):  # non-contiguous: clip i opens cut i, PAD_IN in
    assert abs(s - (r + 0.06)) <= F, f'clip {i}: subtitle start {s:.3f}, segment starts {r:.3f}'
drift = real[-1] - nominal[-1]
assert drift > F, f'test EDL should drift > 1 frame, drifted {drift:.3f}s'
(b0, b1), = tl['blur']  # share from the 4th clip: one window from that segment start to the end of the last
assert abs(b0 - real[3]) <= F and b1 >= real[-1] + 0.8, f'blur window {b0:.3f}-{b1:.3f}, segments {real}'
dur = pts[-1] + F
assert abs(tl['total'] - tl['base_duration']) < 1e-3 and abs(dur - tl['base_duration']) <= 2 * F, \
    f"total {tl['total']:.3f} base_duration {tl['base_duration']:.3f} base.mov video {dur:.3f}"
print(f'{drift:.3f}')
EOF
) || fail "anchored timing does not follow the real segment starts"
# SHARE_RANGES (face <-> share, no SHARE_FROM): the telop layout switches on exactly the frames the blur does
printf 'exec(open(%s).read())\ndel SHARE_FROM\nSHARE_RANGES = [(3.0, 6.0), (9.0, 11.0)]\nSPEAKERS = {}\n' \
  "'$REPO/tests/smoke_anchored_edl.py'" > "$T/ranges_edl.py"
STUDIO_EDL="$T/ranges_edl.py" "$PY" build_base.py --src "$T/src.mp4" --work "$T/rng" 2>"$T/rng.err" \
  || fail "SHARE_RANGES build_base failed: $(tail -c 300 "$T/rng.err")"
STUDIO_EDL="$T/ranges_edl.py" STUDIO_WORK="$T/rng" "$PY" - <<'EOF' || fail "telop share layout disagrees with the blur windows"
import telops as T
from config import EDL, clip_is_share
blur, share, total = T.TL['blur'], T.TL['share'], T.TL['total']
assert len(blur) == 2, f'expected 2 blur windows (clips c+d, g), got {blur}'
assert share[0] == blur[0] and share[1][0] == blur[1][0] and share[1][1] >= total - 1e-6, (blur, share)
end = blur[-1][1]  # the tail freeze after it clones the last (share) clip
for f in range(int(total * 30) + 1):
    t = f / 30
    want = any(lo <= t <= hi for lo, hi in blur) or t > end
    assert T.is_share(t) == want, f'frame {f} ({t:.3f}s): telops share={T.is_share(t)}, blur={want}'
for a, b, s in T.OUT:
    assert T.is_share(s + (b - a) / 2) == clip_is_share(EDL, a), f'clip at {a}: wrong layout'
EOF
# a tiers panel without TIERS_BADGE shows no badge, not one over the whole panel: its frames match the smoke EDL
# up to the badge cue (tiers panel from 3.42 s, badge at 4.02 s output) and differ once the real badge pops
telop_md5() {
  STUDIO_EDL="$1" STUDIO_LIMIT="$2" "$PY" - <<'EOF'
import hashlib, telops as T
h = hashlib.md5()
T.render(h.update, [])
print(h.hexdigest())
EOF
}
printf 'exec(open(%s).read())\ndel TIERS_BADGE\n' "'$REPO/tests/smoke_edl.py'" > "$T/nobadge_edl.py"
m_none=$(telop_md5 "$T/nobadge_edl.py" 4.0) || fail "telops crashed on an EDL without TIERS_BADGE"
m_real=$(telop_md5 "$REPO/tests/smoke_edl.py" 4.0)
[ "$m_none" = "$m_real" ] || fail "missing TIERS_BADGE drew a badge before any cue ($m_none != $m_real)"
[ "$(telop_md5 "$T/nobadge_edl.py" 5)" != "$(telop_md5 "$REPO/tests/smoke_edl.py" 5)" ] \
  || fail "badge check is vacuous: the smoke EDL badge does not show in the first 5 s"
# frame reuse keys the whole cue: the same subtitle text from another speaker is a new frame (other name chip)
cat > "$T/samesub_edl.py" <<'EOF'
CLIPS = [(1.0, 2.0, 'J', 'はい。'), (2.0, 3.0, 'I', 'はい。')]
SHARE_FROM, SHARE_BLUR, TAIL = 1e9, (0, 86, 1440, 72), 0.5
SPEAKERS = {'J': ('話者J', '#0A6CFF', '#0047B3'), 'I': ('話者I', '#FF3D7F', '#C2185B')}
EOF
STUDIO_EDL="$T/samesub_edl.py" "$PY" build_base.py --src "$T/src.mp4" --work "$T/same" 2>"$T/same.err" \
  || fail "same-text build_base failed: $(tail -c 300 "$T/same.err")"
STUDIO_EDL="$T/samesub_edl.py" STUDIO_WORK="$T/same" "$PY" - <<'EOF' || fail "same text, other speaker reused the first speaker's frame"
import hashlib, telops as T
fr = []
T.render(lambda b: fr.append(hashlib.md5(b).hexdigest()), [])
(a0, b0, s0), (a1, b1, s1) = T.OUT
mid = lambda s, a, b: fr[int((s + (b - a) / 2) * T.FPS)]
assert mid(s0, a0, b0) != mid(s1, a1, b1), 'speaker J and speaker I subtitle frames are identical'
EOF
echo "SMOKE PASS frames=$frames duration=$dur total=$total (+ typo flag, truncated base, --limit 0/-3, past-EOF cut rejected, clip at EOF accepted; anchored drift ${anch}s tracked; SHARE_RANGES layout = blur; missing TIERS_BADGE; same text other speaker)"
