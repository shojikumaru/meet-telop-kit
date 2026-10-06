#!/bin/bash
# Download a public ("anyone with the link") Google Drive file, large-file safe and resumable.
#   scripts/fetch_drive.sh <share-url-or-id> <out-file> [--probe BYTES]
# - accepts .../file/d/<ID>/view, ...?id=<ID>, or a bare <ID>
# - uses drive.usercontent.google.com with confirm=t; if Drive still answers with its HTML
#   "can't scan for viruses" page, the hidden form fields are parsed and the real URL is used
# - resumes a partial <out-file> (curl -C -), verifies the final size against Content-Range
# - re-running with a complete file is a no-op
# --probe N downloads only the first N bytes (sharing / network / size check, no full download; more than N bytes
#   is refused and nothing is kept; a complete <out-file> is left as is)
# A problem is reported as one English line + one Japanese line (exit 1): NETWORK (the cloud session cannot reach
# a Drive host), NOT SHARED (Drive sends the request to the Google sign-in page or refuses it), NOT FOUND (404),
# HTML PAGE (an HTML page instead of the file: sharing or the daily download quota).
set -euo pipefail
. "$(dirname "$0")/_lib.sh"

[ $# -ge 2 ] || { sed -n '2,13p' "$0"; exit 2; }
SRC="$1"; OUT="$2"; PROBE=""
if [ "${3:-}" = "--probe" ]; then PROBE="${4:-1048576}"; fi

case "$SRC" in
  *"/d/"*) ID=$(printf '%s' "$SRC" | sed -E 's#.*/d/([A-Za-z0-9_-]+).*#\1#') ;;
  *"id="*) ID=$(printf '%s' "$SRC" | sed -E 's#.*[?&]id=([A-Za-z0-9_-]+).*#\1#') ;;
  *) ID="$SRC" ;;
esac
if ! printf '%s' "$ID" | grep -Eq '^[A-Za-z0-9_-]{20,}$'; then
  echo "fetch_drive: cannot find a Drive file id in: $SRC" >&2
  echo "fetch_drive: 日本語: 共有リンクの形が読み取れません。Google Drive の「リンクをコピー」で取ったリンクをそのまま貼ってください。" >&2
  exit 2
fi
URL="https://drive.usercontent.google.com/download?id=$ID&export=download&confirm=t"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/fetch_drive.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

host_of() { printf '%s' "$1" | sed -E 's#^[A-Za-z]+://([^/:?]+).*#\1#'; }
# $1 = kind, $2 = detail (for network: the host, $3 = what curl saw); prints the two lines and exits 1
report() {
  local en ja
  case "$1" in
    network)
      en="NETWORK - cannot reach $2 (${3:-}): this session is not in the 'video' cloud environment, or an allowed domain is missing"
      ja="ネットワークにつながりません（$2）。クラウドの環境が「video」になっていないか、許可するドメインが足りません。docs/はじめに.md の「環境を作る」を確認して、環境 video を選んだ新しい会話でもう一度送ってください。" ;;
    signin)
      en="NOT SHARED - Drive sent the request to the Google sign-in page ($2): the file is not shared as 'Anyone with the link'"
      ja="録画が「リンクを知っている全員」に共有されていません。Google Drive で共有を「リンクを知っている全員」にしてから、もう一度送ってください。" ;;
    denied)
      en="NOT SHARED - Drive refused the file ($2): not shared as 'Anyone with the link', or its daily download limit was hit"
      ja="Google Drive が録画を渡してくれませんでした。共有が「リンクを知っている全員」になっているか確認してください。なっている場合は、ダウンロード回数の上限かもしれないので、時間をおいてもう一度送ってください。" ;;
    notfound)
      en="NOT FOUND - Drive answered 404 ($2): the link or file id is wrong, or the file was deleted"
      ja="録画が見つかりません。共有リンクが正しいか（途中で切れていないか）、ファイルが削除されていないかを確認してください。" ;;
    html)
      en="HTML PAGE - Drive returned an HTML page instead of the file ($2): not shared as 'Anyone with the link', or the daily download quota was hit"
      ja="Google Drive から録画ではなく案内ページが返ってきました。共有が「リンクを知っている全員」になっているか確認してください。なっている場合は、ダウンロード回数の上限かもしれないので、時間をおいてもう一度送ってください。" ;;
    *)
      en="Drive answered $2"
      ja="Google Drive から想定外の応答がありました（$2）。少し時間をおいて、もう一度送ってください。" ;;
  esac
  echo "fetch_drive: $en" >&2
  echo "fetch_drive: 日本語: ${ja}" >&2
  exit 1
}

# One-byte request to $1, following redirects by hand (at most 6) so that every hop is classified:
# sets LAST (the URL that answered 2xx); leaves its headers in $TMP/h and its body in $TMP/b. Never returns on a
# problem (report exits). A blocked host shows up as a curl error / HTTP 000 (the proxy refuses the connection) or
# as a 403 / 407 without Google's own server headers; accounts.google.com is never followed (it means "sign in").
probe() {
  local u="$1" n=0 out rc code next host
  while :; do
    n=$((n + 1))
    [ "$n" -le 6 ] || report other "too many redirects (last: $(host_of "$u"))"
    host=$(host_of "$u")
    rc=0
    out=$(curl -sS --retry 2 --retry-delay 2 --connect-timeout 15 --max-time 60 -r 0-0 -D "$TMP/h" -o "$TMP/b" \
          -w '%{http_code} %{redirect_url}' "$u" 2>"$TMP/err") || rc=$?
    code="${out%% *}"; next="${out#* }"
    if [ "$rc" != 0 ] || [ -z "$code" ] || [ "$code" = 000 ]; then
      report network "$host" "curl exit $rc: $(head -1 "$TMP/err" 2>/dev/null | sed 's/^curl: //')"
    fi
    case "$code" in
      2??) LAST="$u"; return 0 ;;
      30[12378])
        [ -n "$next" ] && [ "$next" != "$out" ] || report other "HTTP $code without a Location from $host"
        case "$(host_of "$next")" in
          accounts.google.com|accounts.youtube.com) report signin "HTTP $code from $host" ;;
        esac
        u="$next" ;;
      404) report notfound "$host" ;;
      407) report network "$host" "HTTP 407 from a proxy" ;;
      403)
        if grep -Eqi '^(server: *(UploadServer|ESF|GSE|gws|sffe|Google)|x-goog|x-guploader)' "$TMP/h"; then
          report denied "HTTP 403 from $host"
        fi
        report network "$host" "HTTP 403 that is not Google's own reply" ;;
      *) report other "HTTP $code from $host" ;;
    esac
  done
}
ctype() { grep -i '^content-type:' "$TMP/h" | tail -1 | tr -d '\r' | sed 's/^[^:]*: *//'; }

probe "$URL"
if ctype | grep -qi 'text/html'; then
  # confirm page: rebuild the URL from the form's hidden inputs
  rc=0
  curl -sS --connect-timeout 15 --max-time 60 -o "$TMP/page.html" "$LAST" 2>"$TMP/err" || rc=$?
  [ "$rc" = 0 ] || report network "$(host_of "$LAST")" "curl exit $rc: $(head -1 "$TMP/err" 2>/dev/null | sed 's/^curl: //')"
  ACTION=$(grep -o '<form[^>]*id="download-form"[^>]*>' "$TMP/page.html" | sed -E 's/.*action="([^"]+)".*/\1/' | head -1 || true)
  Q=$(grep -o '<input type="hidden" name="[^"]*" value="[^"]*"' "$TMP/page.html" \
      | sed -E 's/.*name="([^"]*)" value="([^"]*)"/\1=\2/' | tr '\n' '&' | sed 's/&$//' || true)
  if [ -n "$ACTION" ] && [ -n "$Q" ]; then
    URL="$ACTION?$Q"
    probe "$URL"
  fi
  if ctype | grep -qi 'text/html'; then
    TITLE=$(grep -o '<title>[^<]*' "$TMP/page.html" 2>/dev/null | head -1 | sed 's/<title>//' || true)
    report html "${TITLE:-no title}"
  fi
fi
TOTAL=$(grep -i '^content-range:' "$TMP/h" | tail -1 | tr -d '\r' | sed -E 's#.*/([0-9]+)$#\1#' || true)
NAME=$(grep -i '^content-disposition:' "$TMP/h" | tail -1 | tr -d '\r' | sed -E 's/.*filename="?([^";]*)"?.*/\1/' || true)
case "$TOTAL" in ''|*[!0-9]*) echo "fetch_drive: no Content-Range from Drive; headers:" >&2; cat "$TMP/h" >&2; exit 1 ;; esac
echo "fetch_drive: id=$ID name=\"$NAME\" size=$TOTAL bytes"

mkdir -p "$(dirname "$OUT")"
if [ -n "$PROBE" ]; then
  # the first PROBE bytes, classified like probe(): a hop to the Google sign-in page is NOT SHARED, then only the
  # last answer's headers (after -L) are judged, and the bytes reach OUT only when that answer is a 2xx that is not
  # an HTML page. Capped at 60 s and PROBE bytes: when Drive ignores the range and sends more, the probe is refused
  # and nothing is kept (curl --max-filesize stops early when the size is announced; the size check below catches
  # the rest). A complete OUT is never replaced (the probe bytes stay in the temp dir).
  rc=0
  out=$(curl -sS -L --retry 3 --connect-timeout 15 --max-time 60 --max-filesize "$PROBE" -r "0-$((PROBE - 1))" \
        -D "$TMP/hall" -o "$TMP/part" -w '%{http_code} %{url_effective}' "$URL" 2>"$TMP/err") || rc=$?
  code="${out%% *}"; host=$(host_of "${out#* }"); [ -n "$host" ] || host=$(host_of "$URL")
  case "$host" in accounts.google.com|accounts.youtube.com) report signin "a redirect from $(host_of "$URL")" ;; esac
  if grep -Eqi '^location: *https?://accounts\.(google|youtube)\.com([/:?]|$)' "$TMP/hall" 2>/dev/null; then
    report signin "a redirect from $(host_of "$URL")"
  fi
  [ "$rc" != 63 ] || report other "more than the $PROBE bytes asked for (the byte range was ignored); nothing was kept"
  if [ "$rc" != 0 ] || [ -z "$code" ] || [ "$code" = 000 ]; then
    report network "$host" "curl exit $rc: $(head -1 "$TMP/err" 2>/dev/null | sed 's/^curl: //')"
  fi
  awk '/^HTTP\//{n=0} {b[++n]=$0} END{for (i = 1; i <= n; i++) print b[i]}' "$TMP/hall" > "$TMP/h"
  case "$code" in
    2??) ;;
    404) report notfound "$host" ;;
    407) report network "$host" "HTTP 407 from a proxy" ;;
    403)
      if grep -Eqi '^(server: *(UploadServer|ESF|GSE|gws|sffe|Google)|x-goog|x-guploader)' "$TMP/h"; then
        report denied "HTTP 403 from $host"
      fi
      report network "$host" "HTTP 403 that is not Google's own reply" ;;
    *) report other "HTTP $code from $host" ;;
  esac
  if ctype | grep -qi 'text/html'; then
    TITLE=$(grep -o '<title>[^<]*' "$TMP/part" 2>/dev/null | head -1 | sed 's/<title>//' || true)
    report html "${TITLE:-no title}"
  fi
  got=$(fsize "$TMP/part")
  [ "$got" -le "$PROBE" ] || report other "$got bytes for the $PROBE bytes asked for (HTTP $code; the byte range was ignored); nothing was kept"
  if [ -f "$OUT" ] && [ "$(fsize "$OUT")" = "$TOTAL" ]; then
    echo "fetch_drive: probe ok ($got bytes); $OUT is already complete and was left as is"
    exit 0
  fi
  mv "$TMP/part" "$OUT"
  echo "fetch_drive: probe ok, wrote $(fsize "$OUT") bytes to $OUT"
  exit 0
fi
if [ -f "$OUT" ] && [ "$(fsize "$OUT")" = "$TOTAL" ]; then
  echo "fetch_drive: already complete: $OUT"; exit 0
fi
if [ -f "$OUT" ] && [ "$(fsize "$OUT")" -gt "$TOTAL" ]; then
  echo "fetch_drive: $OUT is larger than the Drive file; delete it and retry" >&2; exit 1
fi
t0=$(date +%s)
n=0
until [ -f "$OUT" ] && [ "$(fsize "$OUT")" = "$TOTAL" ]; do
  n=$((n + 1))
  [ $n -le 5 ] || { echo "fetch_drive: giving up after 5 attempts ($(fsize "$OUT")/$TOTAL bytes)" >&2; exit 1; }
  curl -fL --retry 5 --retry-delay 3 -C - -o "$OUT" "$URL" || echo "fetch_drive: curl exited $?, resuming" >&2
done
echo "fetch_drive: done $OUT ($TOTAL bytes, $(( $(date +%s) - t0 ))s)"
