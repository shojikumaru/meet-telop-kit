# meet-telop-kit

Interview recording (Google Drive link) -> ~5 min YouTube-style ad cut with telops -> delivered to this GitHub
repo (Release asset, or a `deliver/<tag>` branch).

- Procedure: `.claude/skills/meet-interview-edit/SKILL.md` (動作テスト mode and fresh mode). Follow it.
- The user is usually not an engineer. Reply in plain, friendly Japanese without jargon (no command names, log
  lines or file paths unless asked). On an error, give the cause in one sentence and the fix in one sentence.
- A message that is just 「動作テスト」 means: run the 動作テスト mode now (no questions first).
- **Always ask the user** for every speaker's name and title / company, the hook title wording and the end card
  text when the request does not give them. Never invent names, never guess them from the recording, never reuse
  names from an earlier job or from `templates/edl_template.py` (its 話者A / 話者B are placeholders).
- In fresh mode, check the Drive link first (`scripts/fetch_drive.sh "<link>" work/src/probe.bin --probe`, step 0
  of the skill), then run `bash scripts/setup.sh` (idempotent) before the work steps. The 動作テスト runs setup
  itself.
- Long steps (setup check, fetch, whisper, renders) must run with `nohup setsid … > out/x.log 2>&1 &` and be polled
  (a foreground command is moved to the background after 2 min, out of your sight).
- Deliver the final mp4 with `scripts/deliver.sh` before reporting: an idle VM pauses and may later be reclaimed,
  and then its files are gone. Do not upload recordings or renders anywhere else.
- Keep the look: do not restyle `studio/telops.py`; new content goes into an EDL file (start from
  `templates/edl_template.py`).
- Tests: `make test` (smoke, ~20 s), `make selftest` (動作テスト). User guide (Japanese): `docs/はじめに.md`.
