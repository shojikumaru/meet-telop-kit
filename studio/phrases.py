"""Phrase table for exact clip boundaries (the boundary refinement step).

usage: phrases.py WAV OUT.json [--noise -38dB] [--min-silence 0.12] [--from T0 --to T1] [--prompt TEXT]
1. ffmpeg silencedetect -> speech phrases between silences (phrases < 0.25 s are merged into the previous one)
2. every phrase (optionally only those overlapping T0..T1) is cut and transcribed on its own
3. OUT.json = [[start, end, text], ...] in WAV seconds; also printed as "start-end text" lines.
Use the printed start/end (2 decimals) as CLIPS boundaries: they sit in the silences, so cuts never clip words.
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile, wave

ap = argparse.ArgumentParser()
ap.add_argument('wav')
ap.add_argument('out')
ap.add_argument('--noise', default='-38dB')
ap.add_argument('--min-silence', type=float, default=0.12)
ap.add_argument('--from', dest='t0', type=float, default=0.0)
ap.add_argument('--to', dest='t1', type=float, default=None)
ap.add_argument('--prompt', default='', help='vocabulary hint (names, products, jargon; comma-separated)')
ap.add_argument('--model', default=os.environ.get('WHISPER_MODEL', os.path.join(
    os.environ.get('MEET_TELOP_CACHE', os.path.expanduser('~/.cache/meet-telop')), 'ggml-large-v3-turbo-q5_0.bin')))
ap.add_argument('--threads', type=int, default=os.cpu_count() or 4)
a = ap.parse_args()
with wave.open(a.wav) as w:
    total = w.getnframes() / w.getframerate()
t1 = a.t1 if a.t1 is not None else total

log = subprocess.run(['ffmpeg', '-hide_banner', '-i', a.wav, '-af', f'silencedetect=noise={a.noise}:d={a.min_silence}',
                      '-f', 'null', '-'], capture_output=True, text=True).stderr
S, st = [], None
for l in log.splitlines():
    m = re.search(r'silence_start: ([\d.]+)', l)
    if m:
        st = float(m[1]); continue
    m = re.search(r'silence_end: ([\d.]+)', l)
    if m and st is not None:
        S.append((st, float(m[1]))); st = None
# phrase = speech between silences
bounds = [0.0]
for s0, s1 in S:
    bounds += [s0, s1]
bounds.append(total)
ph = []
for i in range(0, len(bounds) - 1, 2):
    p0, p1 = bounds[i], bounds[i + 1]
    if p1 - p0 < 0.25:
        if ph:
            ph[-1] = (ph[-1][0], p1)
        continue
    ph.append((p0, p1))
ph = [(p0, p1) for p0, p1 in ph if p1 >= a.t0 and p0 <= t1]
print(f'{len(S)} silences, {len(ph)} phrases in {a.t0:.1f}-{t1:.1f}s', file=sys.stderr, flush=True)

tmp = tempfile.mkdtemp(prefix='phrases.')
wavs = []
for i, (p0, p1) in enumerate(ph):
    f = os.path.join(tmp, '%04d.wav' % i)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{max(p0 - 0.05, 0):.3f}', '-to', f'{p1 + 0.05:.3f}',
                    '-i', a.wav, '-af', 'apad=pad_dur=0.4', f], check=True)
    wavs.append(f)
texts = []
if shutil.which('whisper-cli'):
    cmd = ['whisper-cli', '-m', a.model, '-l', 'ja', '-nt', '-otxt', '-t', str(a.threads), '-np']
    if a.prompt:
        cmd += ['--prompt', a.prompt]
    subprocess.run(cmd + wavs, check=True, stdout=subprocess.DEVNULL)
    for f in wavs:
        p = f + '.txt'
        texts.append(open(p, encoding='utf-8').read().strip().replace('\n', ' ') if os.path.exists(p) else '?')
else:
    from pywhispercpp.model import Model
    m = Model(a.model, n_threads=a.threads, print_progress=False, print_realtime=False, redirect_whispercpp_logs_to=None)
    for i, f in enumerate(wavs):
        # pywhispercpp rejects initial_prompt=None: pass it only when set
        segs = m.transcribe(f, language='ja', **({'initial_prompt': a.prompt} if a.prompt else {}))
        texts.append(' '.join(s.text.strip() for s in segs) or '?')
        if i % 20 == 0:
            print(f'phrase {i}/{len(wavs)}', file=sys.stderr, flush=True)
shutil.rmtree(tmp, ignore_errors=True)
rows = [(round(p0, 2), round(p1, 2), tx) for (p0, p1), tx in zip(ph, texts)]
json.dump(rows, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
for p0, p1, tx in rows:
    print(f'{p0:7.2f}-{p1:7.2f} {tx}')
