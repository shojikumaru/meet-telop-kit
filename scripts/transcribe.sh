#!/bin/bash
# Transcribe (a segment of) a recording.
#   scripts/transcribe.sh <video> <out-prefix> [--from S] [--to S] [--prompt TEXT | --prompt-file F] [--subs-only]
#                         [--strip PREFIX]
# Writes:
#   <prefix>.speakers.txt  speaker-labelled lines from the embedded subtitle stream (Meet captions), if any,
#                          in RECORDING time ("[h:mm:ss] Name: text")         <- fast, use it to find segments
#   <prefix>.wav           16 kHz mono audio of --from..--to
#   <prefix>.json          whisper segments + tokens, times relative to --from  (input for studio/tok.py)
#   <prefix>.segments.txt  "[start-end] text" per whisper segment
# Use --from as --source-offset later, so EDL times = times in <prefix>.json.
# Whisper is slow on CPU (cloud: run under nohup and poll the log). --subs-only skips audio + whisper.
set -euo pipefail
. "$(dirname "$0")/_lib.sh"

[ $# -ge 2 ] || { sed -n '2,13p' "$0"; exit 2; }
VID="$1"; PFX="$2"; shift 2
FROM=0; TO=""; PROMPT=""; SUBS_ONLY=0; STRIP=""
while [ $# -gt 0 ]; do
  case "$1" in
    --from) FROM="$2"; shift 2 ;;
    --to) TO="$2"; shift 2 ;;
    --prompt) PROMPT="$2"; shift 2 ;;
    --prompt-file) PROMPT="$(cat "$2")"; shift 2 ;;
    --subs-only) SUBS_ONLY=1; shift ;;
    --strip) STRIP="$2"; shift 2 ;;
    *) echo "transcribe.sh: unknown option $1" >&2; exit 2 ;;
  esac
done
[ -f "$VID" ] || { echo "transcribe.sh: no such file: $VID" >&2; exit 2; }
PY="$(pick_python)"
mkdir -p "$(dirname "$PFX")"

if ffprobe -v error -select_streams s -show_entries stream=index -of csv=p=0 "$VID" | grep -q .; then
  ffmpeg -v error -y -i "$VID" -map 0:s:0 "$PFX.subs.srt"
  if [ -n "$STRIP" ]; then
    "$PY" "$REPO/studio/subs.py" "$PFX.subs.srt" "$PFX.speakers.txt" --strip "$STRIP"
  else
    "$PY" "$REPO/studio/subs.py" "$PFX.subs.srt" "$PFX.speakers.txt"
  fi
else
  echo "transcribe.sh: no embedded subtitle stream (no speaker labels); whisper only"
fi
[ "$SUBS_ONLY" = 1 ] && exit 0

if [ ! -f "$MODEL" ]; then echo "transcribe.sh: whisper model missing ($MODEL); run scripts/setup.sh --model" >&2; exit 1; fi
if [ -n "$TO" ]; then
  ffmpeg -v error -y -ss "$FROM" -to "$TO" -i "$VID" -vn -ar 16000 -ac 1 -c:a pcm_s16le "$PFX.wav"
else
  ffmpeg -v error -y -ss "$FROM" -i "$VID" -vn -ar 16000 -ac 1 -c:a pcm_s16le "$PFX.wav"
fi
"$PY" "$REPO/studio/asr.py" "$PFX.wav" "$PFX.json" --model "$MODEL" --prompt "$PROMPT"
"$PY" - "$PFX.json" "$PFX.segments.txt" <<'EOF'
import json, sys
j = json.load(open(sys.argv[1], encoding='utf-8'))
with open(sys.argv[2], 'w', encoding='utf-8') as f:
    for s in j['transcription']:
        f.write(f"[{s['offsets']['from'] / 1000:7.2f}-{s['offsets']['to'] / 1000:7.2f}] {s['text'].strip()}\n")
print(f"{len(j['transcription'])} segments -> {sys.argv[2]}")
EOF
