#!/bin/bash
# 動作テスト (setup check) that needs no real recording:
#   scripts/selftest.sh
# 1. network check: the Drive hosts, one *.googleusercontent.com host and the Hugging Face model URL answer (fails fast)
# 2. scripts/setup.sh  3. tests/smoke.sh  4. renders a ~10 s synthetic demo (colour bars + tone, 2 neutral speakers,
# hook title, Q header, pop, name plates, end card; EDL tests/selftest_edl.py) to out/selftest.mp4 and checks it
# 5. scripts/deliver.sh out/selftest.mp4 selftest-<UTC date-time>  (prints the URL to report)
# SELFTEST_NO_NET=1 skips step 1 (offline local runs, tests). SELFTEST_NO_DELIVER=1 skips step 5 (local runs).
# Cloud: run detached and poll the log:
#   mkdir -p out && nohup setsid scripts/selftest.sh > out/selftest.log 2>&1 < /dev/null &
set -euo pipefail
. "$(dirname "$0")/_lib.sh"

[ $# -eq 0 ] || { sed -n '2,10p' "$0"; exit 2; }
t0=$(date +%s)
STEP="開始前"
step() { echo "[selftest $(( $(date +%s) - t0 ))s] $*"; }
fail() { echo "selftest: FAILED - $*" >&2; exit 1; }
# a short Japanese result block on every exit (the FAILED line and the deliver lines above stay as printed)
# PASSED is set only on the last line, so an exit from anywhere else (fail, set -e, set -u) is reported as 不合格 and
# leaves non-zero even where bash 3.2 hands the trap a 0 status
PASSED=0
result() {
  local rc=$?
  [ -z "${T_ERR:-}" ] || rm -f "$T_ERR"
  [ -z "${T_BODY:-}" ] || rm -f "$T_BODY"
  if [ "$rc" = 0 ] && [ "$PASSED" = 1 ]; then
    echo "selftest: 結果 = 合格（${NET_CHECKED:+ネットワーク・}準備・テスト・動画の書き出し${DELIVERED:+・お届け}まで成功）"
    [ -z "${LINK:-}" ] || echo "selftest: 動画のリンク = ${LINK}"
  else
    echo "selftest: 結果 = 不合格（「${STEP}」で止まりました。理由は上の FAILED / エラーの行です）" >&2
    [ "$rc" != 0 ] || exit 1
  fi
}
trap result EXIT

# ---------------------------------------------------------------- 1. network check
# What a real job downloads from, through the cloud environment's allowed domains:
# - drive.google.com, drive.usercontent.google.com: /robots.txt is a small text file Google serves itself with
#   HTTP 200 and no redirect (measured 2026-10-05 and 2026-10-06 with curl on both hosts); the whole body is fetched
#   and must contain "User-agent", so a login or placeholder page that also answers 200 does not pass
# - *.googleusercontent.com (the allowlist's wildcard line; Drive sends a shared file's bytes from a host there):
#   https://lh3.googleusercontent.com/robots.txt answers HTTP 400 from Google's own server ("server: fife"; measured
#   2026-10-06 with curl, 3 of 3; doc-00-00-docs.googleusercontent.com answers 404, also 3 of 3). This probe only
#   proves the host is reachable, so 400 / 404 / 200 pass (Google may change which one it sends); 403 / 407 fail
# - huggingface.co: the first byte of the model URL setup.sh downloads, following its redirect to the *.hf.co CDN;
#   the origin answers 206 (measured 2026-10-05; 200 accepted if a server ignores the range)
# Fail-closed: a curl error, HTTP 000, a 403 / 407 (what a blocking proxy answers; Google and Hugging Face do not
# send it for these URLs) or any other unexpected code is a FAIL. Each request is capped at 20 s, no retries.
# Proven: the session reaches those Drive hosts, the *.googleusercontent.com wildcard and Hugging Face.
# Not checked (honest limit): the user's own recording and share link (its sharing setting, the download quota and
# the doc-*.googleusercontent.com host Drive picks for it); a real job finds that out when it fetches the recording
# (scripts/fetch_drive.sh --probe).
NET_HELP="クラウドの環境が「video」になっていないか、許可するドメインが足りません。docs/はじめに.md の「環境を作る」を確認して、環境 video を選び直してからもう一度「動作テスト」と送ってください。"
net_probe() {  # $1 = url, $2 = accepted codes ("200" or "200 206"), $3 = -L to follow redirects or "",
               # $4 = text the body must contain ("" = only the first byte is fetched, the body is not read)
  local url="$1" want="$2" follow="${3:-}" needle="${4:-}" out rc=0 code host err
  if [ -n "$needle" ]; then
    out=$(curl -sS $follow -o "$T_BODY" --connect-timeout 10 --max-time 20 \
          -w '%{http_code}|%{url_effective}' "$url" 2>"$T_ERR") || rc=$?
  else
    out=$(curl -sS $follow -r 0-0 -o /dev/null --connect-timeout 10 --max-time 20 \
          -w '%{http_code}|%{url_effective}' "$url" 2>"$T_ERR") || rc=$?
  fi
  code="${out%%|*}"
  host=$(printf '%s' "${out#*|}" | sed -E 's#^[A-Za-z]+://([^/:?]+).*#\1#')
  [ -n "$host" ] || host=$(printf '%s' "$url" | sed -E 's#^[A-Za-z]+://([^/:?]+).*#\1#')
  err=$(head -1 "$T_ERR" 2>/dev/null || true)
  case " $want " in
    *" $code "*)
      if [ "$rc" = 0 ]; then
        if [ -n "$needle" ] && ! grep -qF "$needle" "$T_BODY" 2>/dev/null; then
          echo "selftest: network: $host answered HTTP $code without \"$needle\" (a login or placeholder page, not Google's file)" >&2
          fail "ネットワークにつながりません（${host}）。${NET_HELP}"
        fi
        echo "  network ok: $host (HTTP $code)"; return 0
      fi ;;
  esac
  case "$rc:$code" in
    0:403|0:407|*:000|[1-9]*)
      echo "selftest: network: cannot reach $host (curl exit $rc, HTTP ${code:-000}${err:+, $err})" >&2
      fail "ネットワークにつながりません（${host}）。${NET_HELP}" ;;
    *)
      echo "selftest: network: $host answered HTTP $code (expected $want)" >&2
      fail "${host} から想定外の応答がありました（HTTP ${code}）。少し時間をおいて、もう一度「動作テスト」と送ってください。続くときは docs/はじめに.md の「うまくいかないとき」を見てください。" ;;
  esac
}

STEP="1/5 ネットワークの確認"
if [ "${SELFTEST_NO_NET:-}" = 1 ]; then
  step "1/5 network check skipped (SELFTEST_NO_NET=1)"
else
  step "1/5 network check"
  T_ERR="$(mktemp "${TMPDIR:-/tmp}/selftest-net.XXXXXX")"
  T_BODY="$(mktemp "${TMPDIR:-/tmp}/selftest-body.XXXXXX")"
  net_probe "https://drive.google.com/robots.txt" "200" "" "User-agent"
  net_probe "https://drive.usercontent.google.com/robots.txt" "200" "" "User-agent"
  net_probe "https://lh3.googleusercontent.com/robots.txt" "400 404 200"
  net_probe "$MODEL_URL" "200 206" -L
  NET_CHECKED=1
fi

STEP="2/5 準備（setup）"
step "2/5 setup"
bash "$REPO/scripts/setup.sh"
STEP="3/5 テスト（smoke）"
step "3/5 smoke test"
bash "$REPO/tests/smoke.sh"

STEP="4/5 テスト動画の書き出し"
step "4/5 demo render"
PY="$(pick_python)"
WORK="$REPO/work/selftest"
OUT="$REPO/out/selftest.mp4"
rm -rf "$WORK"
mkdir -p "$WORK" "$(dirname "$OUT")"
ffmpeg -v error -y -f lavfi -i "testsrc2=size=1920x1080:rate=24:duration=14" \
  -f lavfi -i "sine=frequency=330:sample_rate=48000:duration=14" -c:v libx264 -preset ultrafast -pix_fmt yuv420p \
  -c:a aac -shortest "$WORK/src.mp4"
export STUDIO_EDL="$REPO/tests/selftest_edl.py" STUDIO_WORK="$WORK"
(
  cd "$REPO/studio"
  "$PY" build_base.py --src "$WORK/src.mp4"
  "$PY" telops.py --out "$OUT"
  "$PY" preview.py --at 1.5,5.0,7.5,9.5 >/dev/null
)
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT")
TOTAL=$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['total'])" "$WORK/timeline.json")
"$PY" -c "import sys; sys.exit(0 if abs(float(sys.argv[1]) - float(sys.argv[2])) <= 0.1 else 1)" "$DUR" "$TOTAL" \
  || fail "out/selftest.mp4 lasts ${DUR}s, the timeline says ${TOTAL}s"
NA=$(ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "$OUT" | wc -l | tr -d ' ')
[ "$NA" = 1 ] || fail "out/selftest.mp4 has $NA audio streams, expected 1"
step "rendered $OUT (${DUR}s, $(fsize "$OUT") bytes); stills in $WORK/prev/"

STEP="5/5 お届け（deliver）"
if [ "${SELFTEST_NO_DELIVER:-}" = 1 ]; then
  step "5/5 deliver skipped (SELFTEST_NO_DELIVER=1)"
else
  step "5/5 deliver"
  bash "$REPO/scripts/deliver.sh" "$OUT" "selftest-$(date -u +%Y%m%d-%H%M%S)" | tee "$WORK/deliver.log"
  DELIVERED=1
  LINK=$(sed -nE 's/^deliver: OK \([a-z]+\) (https:[^ ]+)$/\1/p' "$WORK/deliver.log" | head -1)
fi
step "done - SELFTEST PASS"
PASSED=1
