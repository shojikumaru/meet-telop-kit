#!/bin/bash
# Idempotent setup: system packages, the Python venv and (on request) the whisper model.
#   scripts/setup.sh           system packages + Python venv (Linux: apt; macOS: checks + brew hints only)
#   scripts/setup.sh --model   also download the whisper model (~574 MB) into ~/.cache/meet-telop/
#   scripts/setup.sh --model-only
# Linux venv: ~/.cache/meet-telop/venv (pillow + pywhispercpp). Override the cache dir with MEET_TELOP_CACHE.
set -euo pipefail

. "$(dirname "$0")/_lib.sh"   # CACHE, MODEL_NAME, MODEL_URL
MODEL_SIZE=574041195
PYWHISPERCPP=1.5.1   # verified 2026-10-04: the internals studio/asr.py uses exist in this version
WANT_MODEL=0
WANT_SYSTEM=1
for a in "$@"; do
  case "$a" in
    --model) WANT_MODEL=1 ;;
    --model-only) WANT_MODEL=1; WANT_SYSTEM=0 ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
    *) echo "setup.sh: unknown option $a" >&2; exit 2 ;;
  esac
done
mkdir -p "$CACHE"
t0=$(date +%s)
log() { echo "[setup $(( $(date +%s) - t0 ))s] $*"; }

fetch_model() {
  local dst="$CACHE/$MODEL_NAME" have
  have=$(wc -c < "$dst" 2>/dev/null | tr -d ' ' || true)
  if [ "${have:-0}" = "$MODEL_SIZE" ]; then log "model ok: $dst"; return 0; fi
  log "downloading $MODEL_NAME (resumable) ..."
  curl -fL --retry 5 --retry-delay 3 -C - -o "$dst" "$MODEL_URL"
  have=$(wc -c < "$dst" | tr -d ' ')
  if [ "$have" != "$MODEL_SIZE" ]; then echo "setup.sh: model size $have != $MODEL_SIZE" >&2; exit 1; fi
  log "model ok: $dst"
}

if [ "$WANT_SYSTEM" = 1 ]; then
  case "$(uname -s)" in
    Linux)
      SUDO=""
      if [ "$(id -u)" != 0 ]; then
        if command -v sudo >/dev/null 2>&1; then SUDO="sudo"; else echo "setup.sh: need root or sudo for apt" >&2; exit 1; fi
      fi
      PKGS="ffmpeg fonts-noto-cjk fonts-noto-cjk-extra python3-venv python3-pip curl ca-certificates"
      missing=""
      for p in $PKGS; do dpkg -s "$p" >/dev/null 2>&1 || missing="$missing $p"; done
      if [ -n "$missing" ]; then
        log "apt install:$missing"
        export DEBIAN_FRONTEND=noninteractive
        $SUDO apt-get update -qq
        # shellcheck disable=SC2086
        $SUDO apt-get install -y -qq --no-install-recommends $missing >/dev/null
      else
        log "apt packages already installed"
      fi
      VENV="$CACHE/venv"
      if [ ! -x "$VENV/bin/python" ]; then
        log "creating venv $VENV"
        python3 -m venv "$VENV"
      fi
      if ! "$VENV/bin/python" -c "import PIL, importlib.metadata as m, sys; sys.exit(m.version('pywhispercpp') != '$PYWHISPERCPP')" >/dev/null 2>&1; then
        log "pip install pillow pywhispercpp==$PYWHISPERCPP"
        "$VENV/bin/pip" install -q --disable-pip-version-check --only-binary :all: pillow "pywhispercpp==$PYWHISPERCPP"
      else
        log "python deps already installed (pywhispercpp $PYWHISPERCPP)"
      fi
      # studio/asr.py and phrases.py drive pywhispercpp internals; fail now rather than mid-transcription
      "$VENV/bin/python" - <<'PYEOF' || { echo "setup.sh: pywhispercpp is missing internals asr.py needs (see above)" >&2; exit 1; }
import inspect, sys
import _pywhispercpp as pw
from pywhispercpp.model import Model
need = ['whisper_token_eot', 'whisper_full_n_segments', 'whisper_full_n_tokens', 'whisper_full_get_token_data',
        'whisper_token_to_bytes', 'whisper_full_get_segment_t0', 'whisper_full_get_segment_t1']
miss = [n for n in need if not hasattr(pw, n)]
if '_ctx' not in inspect.getsource(Model):
    miss.append('Model._ctx')
if 'new_segment_callback' not in inspect.signature(Model.transcribe).parameters:
    miss.append('Model.transcribe(new_segment_callback=)')
if miss:
    sys.exit('missing: ' + ', '.join(miss))
PYEOF
      ;;
    Darwin)
      ok=1
      for c in ffmpeg ffprobe whisper-cli gh; do
        if ! command -v "$c" >/dev/null 2>&1; then
          ok=0
          case "$c" in
            whisper-cli) echo "missing whisper-cli -> brew install whisper-cpp" ;;
            ffprobe) ;;
            *) echo "missing $c -> brew install $c" ;;
          esac
        fi
      done
      found=""
      for p in "${PYTHON:-}" python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
        [ -n "$p" ] || continue
        if "$p" -c "import PIL" >/dev/null 2>&1; then found="$p"; break; fi
      done
      if [ -z "$found" ]; then ok=0; echo "missing Pillow -> /opt/homebrew/bin/python3 -m pip install pillow"; fi
      if [ "$ok" = 1 ]; then log "macOS tools ok (python: $found)"; else
        echo "setup.sh: macOS: required tools are missing; install the items above (no sudo used) and rerun" >&2; exit 1
      fi
      ;;
    *) echo "setup.sh: unsupported OS $(uname -s)" >&2; exit 1 ;;
  esac
fi

if [ "$WANT_MODEL" = 1 ]; then fetch_model; fi
log "done"
