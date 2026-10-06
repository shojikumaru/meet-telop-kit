---
name: meet-interview-edit
description: Turn a Google Meet / Zoom interview recording (Drive share link) into a ~5 min YouTube-style ad cut with pop telops, speaker subtitles, Q-section headers, animated panels and sound effects, and deliver the mp4 to GitHub (Release asset, or a deliver/<tag> branch when Releases are unavailable). Two modes - "動作テスト" (setup check: network, install, renders a 10 s synthetic demo and delivers it) and "fresh" (edits a new recording). Use when the user's message is just 「動作テスト」 or asks for the setup check (動作テスト mode), or asks to make a ~5 min ad version from a recording (e.g. 「この録画から約5分の広告版を作ってください。」 with a Drive link), edit or cut an interview video, add telops, or make an ad cut (fresh mode).
---

# Meet interview edit (telop ad cut)

Pipeline (all in this repo): `fetch_drive.sh` -> `transcribe.sh` -> write an EDL -> `studio/build_base.py`
(cut + concat + blur + tail freeze -> `base.mov`) -> `studio/preview.py` (stills) -> `studio/telops.py`
(telop layer + SE + loudnorm -> final mp4, checked) -> `deliver.sh` (GitHub).

## Ground rules

- **Names come from the user.** Speaker names, titles / companies, the hook title and the end card text are taken
  from the user's request. If any of them is missing, ask the user before writing the EDL. Never invent a name,
  never guess one from the recording alone, never reuse names from an earlier job or from the template.
- People in the recording must have agreed to the cut being made; if the user's request suggests otherwise, ask.
- Deliver only through `scripts/deliver.sh` (this repo). Do not upload the recording or the cut anywhere else.

## Cloud constraints (claude.ai/code) - read first

- VM: Ubuntu 24.04 x86_64, 4 vCPU, 16 GB RAM, 30 GB disk, no GPU. A 1.8 GB recording + work files fit; delete
  `work/` of old jobs if disk gets tight (`df -h .`). build_base cuts one clip per ffmpeg pass, so ffmpeg stays
  well under 1 GB; the telop renderer (Python) peaks around 2.5 GB.
- A foreground Bash call waits 2 min by default (up to 10 when asked); then it is moved to the background and may
  run up to 30 more minutes, out of your sight. Run every long step detached yourself and poll its log:
  ```bash
  mkdir -p out && nohup setsid scripts/selftest.sh > out/selftest.log 2>&1 < /dev/null &
  tail -c 800 out/selftest.log | tr '\r' '\n' | tail -5      # poll every ~30-60 s; ffmpeg lines use \r
  ```
  Never `sleep` in a loop for long; check, do something useful (e.g. look at stills), check again.
- After a few minutes without activity the VM pauses (files kept; the next message restores it), but a paused VM
  can later be reclaimed and then its files are gone: **deliver the mp4 (scripts/deliver.sh) as soon as it is
  rendered**, then report the URL it prints (Release asset, or the `deliver/<tag>` branch).
- First thing in a session: `bash scripts/setup.sh` (idempotent; seconds when the environment cache has it).
  Whisper model (574 MB, only for fresh mode): `bash scripts/setup.sh --model`.
- Whisper large-v3-turbo on CPU is slow: transcribe only the interview segment, never the whole meeting.

## 動作テスト mode (setup check) - no recording needed

Run it when the user's message is just 「動作テスト」 (or asks for the setup check), or before the first real job in
a new environment. Start it at once; no questions needed.

```bash
mkdir -p out && nohup setsid scripts/selftest.sh > out/selftest.log 2>&1 < /dev/null &
tail -c 800 out/selftest.log | tr '\r' '\n' | tail -5      # poll until "SELFTEST PASS" or "FAILED"
```

`selftest.sh` first checks the network (the Google Drive hosts, one `*.googleusercontent.com` host and the Hugging
Face model URL answer as measured; a failure
stops it before setup with a Japanese `selftest: FAILED - ネットワークにつながりません（host）…` line), then runs
`scripts/setup.sh`, the smoke test (`tests/smoke.sh`), renders a ~10 s synthetic demo (colour bars + a tone,
speakers 話者A / 話者B, hook title, Q header, pop, name plates, end card; EDL `tests/selftest_edl.py`) to
`out/selftest.mp4`, checks its length and audio, and delivers it with
`scripts/deliver.sh out/selftest.mp4 selftest-<UTC date-time>`. Usually 3-6 min in the cloud (an estimate, first
setup included). It ends with a `selftest: 結果 = 合格 / 不合格` line (and `selftest: 動画のリンク = …` after a delivery).
It cannot check the user's own Drive link (its sharing, the download quota, the `doc-*.googleusercontent.com` host
Drive picks for that file); fresh mode checks that first (step 0).
`SELFTEST_NO_NET=1` skips the network step, `SELFTEST_NO_DELIVER=1` skips the delivery (local runs only).

Look at 1-2 stills from `work/selftest/prev/`, then reply in short, plain Japanese, exactly these three parts:
1. 合否 - 「合格です」 or 「不合格でした」
2. 動画のリンク - the URL `deliver.sh` printed (the `deliver: OK …` line), as is; none on failure
3. 次の一手 - on success: 「はじめに」の「新しい録画で動画を作る」へ進んでください. On failure: the cause in one
   sentence and the fix in one sentence (the `FAILED` line says both; the usual causes are in "When something
   fails" below)

No step timings or log lines unless the user asks for them.

## Fresh mode (new recording)

Run every command from the repo root (no `cd`).

0. **Check the link first, then the request** (before any setup): as soon as there is a Drive link, run
   `mkdir -p out work/src && scripts/fetch_drive.sh "<share link>" work/src/probe.bin --probe` (a few seconds,
   1 MB). If it fails, relay its `日本語:` line to the user (sharing / network / wrong link) and stop there - do
   not ask for names yet. When it passes, check the rest: every speaker's name and title / company as it should
   appear on screen, and (optional) the part to use and the points to show. Ask for whatever is missing (names
   first). Then run the setup block; it defines `PY`, used by every later step (if the shell was restarted, run
   the `PY=` line again):

   ```bash
   bash scripts/setup.sh && bash scripts/setup.sh --model      # the model is needed for whisper (steps 4 and 6)
   PY=$(bash scripts/_lib.sh --python) && echo "$PY"            # venv python on Linux, python3 with Pillow on macOS
   ```
1. **Fetch** (background, 1-2 GB):
   `nohup setsid scripts/fetch_drive.sh "<share link>" work/src/rec.mp4 > out/fetch.log 2>&1 < /dev/null &`
   (resumable; rerun the same line if it stops). Poll `tail -c 400 out/fetch.log`.
2. **Speaker transcript (fast)**: `scripts/transcribe.sh work/src/rec.mp4 work/rec --subs-only`
   -> `work/rec.speakers.txt` from Meet's embedded captions ("[h:mm:ss] Name: text", recording time).
   `--strip "Company "` removes a company prefix from names. No subtitle stream -> go to step 3 for a range.
3. **Pick the segment**: read `work/rec.speakers.txt`, find the interview part (e.g. a mock interview inside a
   long meeting), note FROM/TO in recording seconds (e.g. 1:20:00-1:35:00 = 4800-5700). If unsure, propose
   candidates to the user and ask.
4. **Whisper the segment only** (background):
   `nohup setsid scripts/transcribe.sh work/src/rec.mp4 work/seg --from FROM --to TO --prompt "names, products, jargon" > out/asr.log 2>&1 < /dev/null &`
   -> `work/seg.json` (tokens with times, relative to FROM), `work/seg.wav`, `work/seg.segments.txt`.
   The prompt is a vocabulary list (the people, company and product names the user gave you, plus jargon from
   speakers.txt); a long list can go in a file passed with `--prompt-file`.
5. **Read & choose clips**: `STUDIO_WHISPER_JSON=work/seg.json "$PY" studio/tok.py 0 120` prints text with
   `[sec]` marks. Pick a hook (the most surprising 10-15 s, placed first), then Q&A blocks (question by the
   interviewer, answer by the guest), dropping filler and long tangents. Aim for ~5 min.
6. **Exact boundaries**: `"$PY" studio/phrases.py work/seg.wav work/phrases.json --from A --to B` lists
   speech phrases between silences with per-phrase text; use their start/end (2 decimals) for CLIPS so cuts
   land in silences. Re-check a doubtful end by cutting it and transcribing it alone.
   If phrases.py hangs on a range (whisper looping on one phrase: one python process at ~400% CPU for minutes),
   kill it and snap the whisper token times to silences instead: `ffmpeg -i work/seg.wav -af
   silencedetect=noise=-38dB:d=0.12 -f null -` -> start = last silence_end <= start, end = first
   silence_start >= end.
   Several separate parts of a long meeting: whisper each range (`work/s1`, `work/s2`, ...) with one
   `--source-offset` = the first FROM, and write EDL times as `segment time + (its FROM - first FROM)`.
7. **Write the EDL**: `cp templates/edl_template.py work/edl.py`, then replace everything (every key is
   documented in the template; its times and texts are placeholders). All times are seconds in the segment
   (= whisper JSON times):
   - `CLIPS` (start, end, speaker, subtitle) in OUTPUT order; `\n` = line break, `||` = next subtitle page.
     Subtitles are hand-edited readable Japanese, not raw ASR. Keep each page <= 2 lines of ~20 chars.
   - `SPEAKERS`, `PLATE_TEXT`, `PLATES` (name plates when each person first speaks) - names and titles exactly
     as the user gave them.
   - `SECTIONS` (time, 'Q1', short question title) at each question start.
   - `POPS` (time, text, 'gold'|'red'|'blue', seconds) for numbers/punchlines, ~1 per 20-30 s.
   - `TITLE` + `HOOK_TITLE_END` (banner over the hook), `END_CARD` + `END_CARD_FROM`, `TAIL`.
   - `TIMING`: leave it out (= `'anchored'`): build_base places subtitles, telops, SE cues and the blur on the
     measured segment starts (each cut runs a few ms past its nominal end; a 50-cut EDL drifts ~0.6 s by the end).
   - `SHARE_FROM` / `SHARE_BLUR`: from this time the layout is screen-share (content on the left 1440 px,
     the browser bar at SHARE_BLUR is blurred, telops centre on x=720). Use a huge SHARE_FROM if never.
     A recording that switches between face view and screen share: add `SHARE_RANGES = [(from, to), ...]`
     (source times of the share clips); it overrides SHARE_FROM per clip (SHARE_FROM may then be left out).
     build_base writes the resulting share spans to `timeline.json` (`share`); the blur and the telop centring
     both follow them, so they switch on the same frame (at the midpoint of the pause between two clips).
   - Who is on screen: grab 2 frames per candidate clip before choosing. Meet's floating window and the
     right-hand tile can show other participants' faces during a share, and a guest's shared screen can show
     their user name or codes; leave those clips out (or ask) when the cut should show only one person.
   - Optional panels: delete a whole block in the template to skip a panel. A panel you keep needs ALL its
     companions; a missing `*_END` makes it silently never appear, a missing key or text crashes the render.

     | panel | list | companions |
     | :- | :- | :- |
     | logo chips | `CHIPS` (t, label, colour) | `CHIPS_END` |
     | log bars | `TIERS` (t, label, value text, value, highlight) | `TIERS_START`, `TIERS_END`, `TIERS_BADGE`, `TIERS_TITLE`, `TIERS_NOTE`, `TIERS_BADGE_TEXT` (optional `TIERS_LOG_RANGE`) |
     | linear bars | `REPOS` (same shape as TIERS) | `REPOS_END`, `REPOS_TITLE`, `REPOS_MAX` |
     | 3 cards | `SITES` (t, key): key `server` (panel start), every `SITES_CARDS` key, and `center` | `SITES_END`, `SITES_CARDS`, `SITES_CENTER_TEXT` |
     | money | `MONEY` (t, key): key `api` (panel start), every `MONEY_ROWS` key, and `actual` | `MONEY_END`, `MONEY_ROWS`, `MONEY_ACTUAL_TEXT` |

     Reveal times = when the speaker says the item. `tests/smoke_edl.py` is a minimal EDL that uses every panel.
   - `PREVIEW_AT`: source times worth checking as stills.
8. **Base + stills** (base in background, a few minutes in the cloud):
   `nohup setsid "$PY" studio/build_base.py --edl work/edl.py --work work/job --src work/src/rec.mp4 --source-offset FROM > out/base.log 2>&1 < /dev/null &`
   then, once `out/base.log` shows `clips=... duration=...`: `"$PY" studio/preview.py --edl work/edl.py --work work/job`
   -> `work/job/prev/*.jpg`. **Look at the stills** (Read the jpgs): text overflow, overlaps with faces/slides,
   wrong speaker colour, typos, names spelled exactly as the user wrote them. Fix the EDL, rerun preview (rerun
   build_base only when CLIPS changed). Also listen-check cut points by transcribing `work/job/base.mov` audio if
   unsure. A source that is not 1920x1080 is scaled to fit (aspect kept, black bars); build_base logs it.
   If the user asked to confirm before rendering, show the stills now and wait for their OK.
9. **Render** (background):
   `nohup setsid "$PY" studio/telops.py --edl work/edl.py --work work/job --out out/NAME.mp4 > out/render.log 2>&1 < /dev/null &`
   Poll until `done` (a `telops.py: ... FAILED` line means the mp4 is wrong: do not deliver, fix and rerun);
   then extract 4-6 frames with ffmpeg and look at them once more.
10. **Deliver**: `scripts/deliver.sh out/NAME.mp4 NAME` and report the URL it prints + duration to the user.

Unknown flags are errors (a typo such as `--soruce-offset` stops the script instead of being ignored).

## Settings reference

`studio/*.py` flags (or env): `--edl` STUDIO_EDL, `--work` STUDIO_WORK, `--src` STUDIO_SRC (file or http URL),
`--source-offset` STUDIO_SOURCE_OFFSET, `--limit N` STUDIO_LIMIT (first N output seconds, N > 0; omit for the
full render), `--out` STUDIO_OUT. A `--limit` on telops.py/preview.py must be the same one build_base.py was run
with (the overlay runs to the end of base.mov; a mismatch fails the output check).
`preview.py` also takes `--at t1,t2` (output seconds).
Encoder: h264_videotoolbox on macOS, else libx264 veryfast crf 18; override with STUDIO_VENC="-c:v ...".
Fonts: Hiragino W6/W8/W9 (macOS) or Noto Sans CJK JP Medium/Bold/Black (Linux); override STUDIO_FONT_W6/W8/W9.
Telop rendering (telops.py): shapes are drawn 4x and downsampled (smooth edges), labels are centred on their
visible pixels (any font), and text with thick outlines gets its closed holes (る, 画, の) filled with the
innermost outline colour. Keep it that way when adding sprites (`rrect`, `disc`, `ink_xy`, `text_sprite`).
Tests: `make test` (or `bash tests/smoke.sh`, ~20 s); `make selftest` = the 動作テスト above.

## When something fails

- fetch_drive prints one English line and one `日本語:` line; relay the Japanese one. `NETWORK` = the session is
  not in the `video` cloud environment or an allowed domain is missing (docs/はじめに.md「環境を作る」);
  `NOT SHARED` = not shared as "Anyone with the link" (or Drive refused / daily limit); `NOT FOUND` = wrong link or
  deleted file; `HTML PAGE` = sharing or the daily download quota (the page title is shown) - ask the user.
- selftest / setup cannot reach a host (`selftest: FAILED - ネットワークにつながりません`, `Could not resolve host`,
  a `403` from the proxy): the session is not using the `video` cloud environment (or its allowed domains are
  wrong) - tell the user to check docs/はじめに.md「環境を作る」 and start a new session in `video`.
- deliver: tries a Release via `gh` (in the cloud it may fail through the GitHub proxy), then the REST API (only
  with a real `GH_TOKEN`; in the cloud `GH_TOKEN` / `GITHUB_TOKEN` hold only the placeholder `proxy-injected`,
  so it is skipped there - a local-run route), then pushes branch - in the cloud the branch route is the one that
  works (the GitHub proxy allows pushing branches, not tags):
  `deliver/<tag>` (one orphan commit holding the mp4 + a README; nothing else is pushed, the checkout is not
  touched). The branch route refuses files >= 95 MB: run
  `nohup setsid scripts/shrink.sh out/NAME.mp4 > out/shrink.log 2>&1 < /dev/null &` (-> `out/NAME.small.mp4`,
  <= 90 MB, still 1080p) and deliver that file. Report the printed URL (Release asset, or
  `https://github.com/<repo>/blob/deliver/<tag>/<file>`). On FAILED report the exact messages; do not upload
  anywhere else (no chat attachments).
- A render that dies: check `free -m` / `df -h .`; rerun with `--limit 20` to reproduce quickly.
