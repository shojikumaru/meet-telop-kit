#!/bin/bash
# Deliver a finished render to GitHub so it survives the cloud VM.
#   scripts/deliver.sh <file> [tag]        (tag default: render-YYYYMMDD-HHMMSS, UTC)
# Tries, in order, and stops at the first that works (each failure is printed):
#   1. gh       - Release asset via `gh` (installed + logged in, or GH_TOKEN set); in the cloud a Release may fail
#                 through the GitHub proxy - then the branch route below is the one that works
#   2. rest     - Release asset via the REST API with a real $GH_TOKEN / $GITHUB_TOKEN (Contents: read/write)
#   3. branch   - token-free: one orphan commit (the file + a README) pushed as branch deliver/<tag> with plain
#                 `git push` (the route that works through the cloud GitHub proxy). Files >= 95 MB are refused:
#                 scripts/shrink.sh.
# Repo: $GH_REPO or parsed from `git remote origin`. Env: DELIVER_VIA=gh,rest,branch (subset/order),
# DELIVER_REMOTE=origin (remote name or URL for the branch push; the printed link names the repo of THAT remote,
# or only the ref + remote when it is not a GitHub repo). Exit 0 only when one method verified the upload.
# rest needs a real token: a local-run route. In the cloud VM GH_TOKEN / GITHUB_TOKEN only hold the placeholder
# "proxy-injected" (the GitHub proxy keeps the real credential and allows a pinned set of API calls), so it is skipped.
set -euo pipefail
. "$(dirname "$0")/_lib.sh"

[ $# -ge 1 ] || { sed -n '2,15p' "$0"; exit 2; }
FILE="$1"
TAG="${2:-render-$(date -u +%Y%m%d-%H%M%S)}"
[ -f "$FILE" ] || { echo "deliver: no such file: $FILE" >&2; exit 2; }
printf '%s' "$TAG" | grep -Eq '^[A-Za-z0-9._-]+$' || { echo "deliver: tag must be [A-Za-z0-9._-]+: $TAG" >&2; exit 2; }
SIZE=$(fsize "$FILE")
NAME="$(basename "$FILE")"
VIA="${DELIVER_VIA:-gh,rest,branch}"
REMOTE="${DELIVER_REMOTE:-origin}"
BRANCH_MAX=99614720  # 95 MiB: GitHub rejects pushed files > 100 MB

if [ -z "${GH_REPO:-}" ]; then
  RURL=$(git -C "$REPO" remote get-url origin 2>/dev/null || true)
  GH_REPO=$(printf '%s' "$RURL" | sed -E 's#\.git$##; s#^.*[:/]([^/:]+/[^/]+)$#\1#')
fi
printf '%s' "${GH_REPO:-}" | grep -Eq '^[^/]+/[^/]+$' || { echo "deliver: cannot tell the repo; set GH_REPO=owner/name" >&2; exit 2; }
export GH_REPO
PY="$(command -v python3 || true)"
[ -n "$PY" ] || { echo "deliver: python3 not found (needed to encode names / read API replies); run scripts/setup.sh" >&2; exit 2; }
NOTES="Rendered $(date -u +%Y-%m-%dT%H:%MZ) by scripts/deliver.sh ($NAME, $SIZE bytes)."
TOKEN="${GH_TOKEN:-${GITHUB_TOKEN:-}}"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/deliver.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
echo "deliver: $NAME ($SIZE bytes) -> $GH_REPO tag/branch $TAG (methods: $VIA)"
loud() { echo "deliver: ======== $* ========" >&2; }

# ---------------------------------------------------------------- 1. gh
via_gh() {
  if ! command -v gh >/dev/null 2>&1; then loud "gh: not installed"; return 1; fi
  if [ -z "$TOKEN" ] && ! gh auth status >/dev/null 2>&1; then loud "gh: not logged in and no GH_TOKEN"; return 1; fi
  if gh release view "$TAG" >/dev/null 2>&1; then
    gh release upload "$TAG" "$FILE" --clobber || { loud "gh: release upload FAILED (gh error above)"; return 1; }
  else
    gh release create "$TAG" "$FILE" --prerelease --title "$TAG" --notes "$NOTES" \
      || { loud "gh: release create FAILED (gh error above)"; return 1; }
  fi
  local got
  got=$(DELIVER_NAME="$NAME" gh release view "$TAG" --json assets \
      -q '.assets[] | select(.name == env.DELIVER_NAME) | "\(.size) \(.url)"' 2>&1) \
    || { loud "gh: could not read the release back: $got"; return 1; }
  if [ "${got%% *}" != "$SIZE" ] || [ -z "${got#* }" ] || [ "${got#* }" = "$got" ]; then
    loud "gh: asset check FAILED (want $SIZE bytes, release shows: ${got:-nothing})"; return 1
  fi
  echo "deliver: OK (release) ${got#* }"
  echo "deliver: release page https://github.com/$GH_REPO/releases/tag/$TAG"
}

# ---------------------------------------------------------------- 2. REST
api() {  # method url [curl args...] -> body in $TMP/r, prints http code ("000" + message on transport errors)
  local m="$1" u="$2" code; shift 2
  if ! code=$(curl -sS -o "$TMP/r" -w '%{http_code}' -X "$m" -H "Authorization: Bearer $TOKEN" \
      -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" "$@" "$u" 2>"$TMP/curl.err"); then
    echo "deliver: curl transport error on $m $u: $(head -c 300 "$TMP/curl.err")" >&2
    : > "$TMP/r"; echo 000; return 0
  fi
  echo "$code"
}
jget() { "$PY" -c "import json,sys; d=json.load(open(sys.argv[1])); n=sys.argv[2]; print($1)" "$TMP/r" "$NAME" 2>/dev/null || true; }
via_rest() {
  if [ -z "$TOKEN" ] || [ "$TOKEN" = proxy-injected ]; then loud "rest: no usable GH_TOKEN/GITHUB_TOKEN"; return 1; fi
  local API="https://api.github.com/repos/$GH_REPO" code RID OLD ENC URL GOT
  code=$(api GET "$API/releases/tags/$TAG")
  if [ "$code" = 404 ]; then
    BODY=$("$PY" -c "import json,sys; print(json.dumps({'tag_name':sys.argv[1],'name':sys.argv[1],'body':sys.argv[2],'prerelease':True}))" "$TAG" "$NOTES")
    code=$(api POST "$API/releases" -d "$BODY")
  fi
  case "$code" in 200|201) ;; *) loud "rest: release lookup/create HTTP $code: $(head -c 400 "$TMP/r")"; return 1 ;; esac
  RID=$(jget "d['id']")
  [ -n "$RID" ] || { loud "rest: release response has no id"; return 1; }
  OLD=$(jget "next((a['id'] for a in d.get('assets', []) if a['name'] == n), '')")
  if [ -n "$OLD" ]; then
    code=$(api DELETE "$API/releases/assets/$OLD")
    [ "$code" = 204 ] || { loud "rest: could not replace the existing asset (HTTP $code)"; return 1; }
  fi
  ENC=$("$PY" -c "import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1]))" "$NAME")
  code=$(api POST "https://uploads.github.com/repos/$GH_REPO/releases/$RID/assets?name=$ENC" \
    -H "Content-Type: application/octet-stream" -T "$FILE")
  case "$code" in 201) ;; *) loud "rest: asset upload HTTP $code: $(head -c 400 "$TMP/r")"; return 1 ;; esac
  URL=$(jget "d.get('browser_download_url') or ''")
  GOT=$(jget "d.get('size', '')")
  if [ -z "$URL" ] || [ "$GOT" != "$SIZE" ]; then
    loud "rest: asset check FAILED (want $SIZE bytes, got '${GOT}', url '${URL}')"; return 1
  fi
  echo "deliver: OK (release) $URL"
  echo "deliver: release page https://github.com/$GH_REPO/releases/tag/$TAG"
}

# ---------------------------------------------------------------- 3. orphan branch
# owner/name of a GitHub remote URL, else nothing: https://[user@]github.com/o/n[.git], ssh://git@github.com/o/n,
# git@github.com:o/n, or the cloud sandbox's loopback git proxy http://<user>@127.0.0.1:<port>/git/o/n.
# A path, file:// URL or any other host gives nothing.
github_repo_of() {
  local u="${1%/}" n='([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)'
  u="${u%.git}"
  local re1="^(https?|ssh)://([^@/]+@)?github\\.com(:[0-9]+)?/$n\$" re2="^[^@/:]+@github\\.com:$n\$"
  local re3="^http://([^@/]+@)?(127\\.0\\.0\\.1|localhost)(:[0-9]+)?/git/$n\$"
  if [[ $u =~ $re1 ]]; then printf '%s' "${BASH_REMATCH[4]}"
  elif [[ $u =~ $re2 ]]; then printf '%s' "${BASH_REMATCH[1]}"
  elif [[ $u =~ $re3 ]]; then printf '%s' "${BASH_REMATCH[4]}"
  fi
}
via_branch() {
  local BR="deliver/$TAG" DUR SRCC BLOB RBLOB TREE COMMIT REMOTE_SHA ENC
  if [ "$SIZE" -ge "$BRANCH_MAX" ]; then
    loud "branch: $NAME is $SIZE bytes; a pushed file must be < 95 MB. Shrink it first, then rerun:"
    echo "  scripts/shrink.sh '$FILE'   (-> ${FILE%.*}.small.mp4, <= 90 MB, 1080p, audio kept)" >&2
    return 1
  fi
  git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1 || { loud "branch: $REPO is not a git checkout"; return 1; }
  DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$FILE" 2>/dev/null || echo "?")
  SRCC=$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo "?")
  printf '# %s\n\n- file: `%s`\n- size: %s bytes\n- duration: %s s\n- rendered from commit: %s\n- delivered: %s by scripts/deliver.sh\n\nDownload: open the file above -> "Download raw file" (iPhone: open it, then ... -> Download).\n' \
    "$TAG" "$NAME" "$SIZE" "$DUR" "$SRCC" "$(date -u +%Y-%m-%dT%H:%MZ)" > "$TMP/README.md"
  # plumbing only: new objects + a throwaway index file; the checkout, its index, HEAD and branches are untouched
  # (set -e is off inside a function called from `if`, so every step is checked by hand)
  local IDX="$TMP/index"
  BLOB=$(git -C "$REPO" hash-object -w -- "$FILE") \
    && RBLOB=$(git -C "$REPO" hash-object -w -- "$TMP/README.md") \
    && GIT_INDEX_FILE="$IDX" git -C "$REPO" update-index --add --cacheinfo 100644 "$BLOB" "$NAME" \
    && GIT_INDEX_FILE="$IDX" git -C "$REPO" update-index --add --cacheinfo 100644 "$RBLOB" README.md \
    && TREE=$(GIT_INDEX_FILE="$IDX" git -C "$REPO" write-tree) \
    || { loud "branch: building the commit FAILED (git error above)"; return 1; }
  [ -n "$(git -C "$REPO" config user.name || true)" ] || export GIT_AUTHOR_NAME="meet-telop deliver" GIT_COMMITTER_NAME="meet-telop deliver"
  [ -n "$(git -C "$REPO" config user.email || true)" ] || export GIT_AUTHOR_EMAIL="deliver@users.noreply.github.com" GIT_COMMITTER_EMAIL="deliver@users.noreply.github.com"
  COMMIT=$(printf 'deliver %s (%s, %s bytes)\n\nRendered from %s.\n' "$TAG" "$NAME" "$SIZE" "$SRCC" | git -C "$REPO" commit-tree "$TREE") \
    && [ -n "$COMMIT" ] || { loud "branch: git commit-tree FAILED"; return 1; }
  echo "deliver: branch: pushing commit $COMMIT as $BR to $REMOTE ..."
  # explicit refspec: exactly one ref, refs/heads/deliver/<tag>, is pushed; no force (an existing branch is kept)
  if ! git -C "$REPO" push "$REMOTE" "$COMMIT:refs/heads/$BR"; then
    loud "branch: git push FAILED (if $BR already exists, rerun with another tag)"; return 1
  fi
  REMOTE_SHA=$(git -C "$REPO" ls-remote "$REMOTE" "refs/heads/$BR" | cut -f1)
  if [ "$REMOTE_SHA" != "$COMMIT" ]; then
    loud "branch: verify FAILED (remote $BR is '${REMOTE_SHA:-missing}', pushed $COMMIT)"; return 1
  fi
  # the link names the repo that was actually pushed to (not $GH_REPO); no link when that is not provably GitHub
  local PURL PREPO
  PURL=$(git -C "$REPO" remote get-url "$REMOTE" 2>/dev/null || printf '%s' "$REMOTE")
  PREPO=$(github_repo_of "$PURL")
  if [ -z "$PREPO" ]; then
    echo "deliver: OK (branch) ref refs/heads/$BR (commit $COMMIT) on remote $PURL"
    echo "deliver: that remote is not a recognisable GitHub repo, so no web link is printed"
    return 0
  fi
  ENC=$("$PY" -c "import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1]))" "$NAME")
  echo "deliver: OK (branch) https://github.com/$PREPO/blob/$BR/$ENC"
  echo "deliver: download: open that page -> \"Download raw file\" (iPhone: ... -> Download), or"
  echo "  https://github.com/$PREPO/raw/$BR/$ENC   (needs a GitHub login with access to the repo)"
}

if [ "$SIZE" -ge 2147483648 ]; then
  echo "deliver: $FILE is $SIZE bytes; nothing can take >= 2 GiB. Run scripts/shrink.sh '$FILE' and deliver the result." >&2
  exit 1
fi
for m in $(printf '%s' "$VIA" | tr ',' ' '); do
  case "$m" in
    gh) if via_gh; then exit 0; fi ;;
    rest) if via_rest; then exit 0; fi ;;
    branch) if via_branch; then exit 0; fi ;;
    *) echo "deliver: unknown method in DELIVER_VIA: $m" >&2; exit 2 ;;
  esac
done
echo "deliver: FAILED - every method failed ($VIA); nothing was delivered. Report the messages above." >&2
if [ "${CLAUDE_CODE_REMOTE:-}" = true ]; then
  # cloud VM: there is no real token inside it (GH_TOKEN reads "proxy-injected") and the GitHub proxy allows pushing
  # branches (not tags), so setting a token cannot help; the branch is the way
  echo "  Cloud: read the 'branch:' message above (git push / ls-remote error, or the 95 MB refusal ->" >&2
  echo "  scripts/shrink.sh '$FILE'); fix that, then rerun: scripts/deliver.sh <file> <new tag>" >&2
else
  echo "  Options: GH_TOKEN (fine-grained, repo $GH_REPO, Contents read/write) in the environment variables, or" >&2
  echo "  scripts/shrink.sh '$FILE' if the branch method refused the size; then rerun: scripts/deliver.sh '$FILE' $TAG" >&2
fi
exit 1
