# shellcheck shell=bash
# Sourced by the scripts: repo root, cache dir, and a Python that has Pillow.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE="${MEET_TELOP_CACHE:-$HOME/.cache/meet-telop}"
# the whisper model `scripts/setup.sh --model` downloads (scripts/selftest.sh probes the same URL)
MODEL_NAME="ggml-large-v3-turbo-q5_0.bin"
MODEL_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$MODEL_NAME"
MODEL="${WHISPER_MODEL:-$CACHE/$MODEL_NAME}"

pick_python() {
  local p
  for p in "${PYTHON:-}" "$CACHE/venv/bin/python" python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    [ -n "$p" ] || continue
    if "$p" -c "import PIL" >/dev/null 2>&1; then echo "$p"; return 0; fi
  done
  echo "no python3 with Pillow found; run scripts/setup.sh" >&2
  return 1
}

fsize() { wc -c < "$1" | tr -d ' '; }

# `bash scripts/_lib.sh --python` prints the Python to use (for copy-paste steps: PY=$(bash scripts/_lib.sh --python))
if [ "${BASH_SOURCE[0]}" = "$0" ] && [ "${1:-}" = --python ]; then
  pick_python
fi
