"""Whisper transcription -> whisper-cli "-ojf" style JSON (segments + tokens with ms offsets), for tok.py.

usage: asr.py WAV OUT.json [--model PATH] [--lang ja] [--prompt TEXT] [--threads N] [--backend cli|py]
Backend: whisper-cli when it is on PATH (macOS / Metal), else pywhispercpp (Linux CPU).
Both use the same ggml model (default ~/.cache/meet-telop/ggml-large-v3-turbo-q5_0.bin).
Progress: one line per decoded segment on stderr.
"""
import argparse, json, os, shutil, subprocess, sys, time, wave

ap = argparse.ArgumentParser()
ap.add_argument('wav')
ap.add_argument('out')
ap.add_argument('--model', default=os.environ.get('WHISPER_MODEL', os.path.join(
    os.environ.get('MEET_TELOP_CACHE', os.path.expanduser('~/.cache/meet-telop')), 'ggml-large-v3-turbo-q5_0.bin')))
ap.add_argument('--lang', default='ja')
ap.add_argument('--prompt', default='')
ap.add_argument('--threads', type=int, default=os.cpu_count() or 4)
ap.add_argument('--backend', choices=['cli', 'py'], default='cli' if shutil.which('whisper-cli') else 'py')
a = ap.parse_args()
if not os.path.exists(a.model):
    sys.exit(f'asr.py: model not found: {a.model} (run scripts/setup.sh --model)')
with wave.open(a.wav) as w:
    audio_s = w.getnframes() / w.getframerate()
t0 = time.time()

if a.backend == 'cli':
    prefix = a.out[:-5] if a.out.endswith('.json') else a.out
    cmd = ['whisper-cli', '-m', a.model, '-f', a.wav, '-l', a.lang, '-ojf', '-of', prefix, '-t', str(a.threads)]
    if a.prompt:
        cmd += ['--prompt', a.prompt]
    subprocess.run(cmd, check=True, stdout=sys.stderr)
    if prefix + '.json' != a.out:
        os.replace(prefix + '.json', a.out)
else:
    from pywhispercpp.model import Model
    import _pywhispercpp as pw
    m = Model(a.model, n_threads=a.threads, print_progress=False, print_realtime=False,
              redirect_whispercpp_logs_to=None)
    params = dict(language=a.lang, token_timestamps=True)
    if a.prompt:
        params['initial_prompt'] = a.prompt
    m.transcribe(a.wav, new_segment_callback=lambda s: print(
        f'[{s.t0 / 100:8.2f} --> {s.t1 / 100:8.2f}] {s.text}', file=sys.stderr, flush=True), **params)
    ctx = m._ctx
    eot = pw.whisper_token_eot(ctx)
    segs = []
    for i in range(pw.whisper_full_n_segments(ctx)):
        toks, pend, pend_t0 = [], b'', None
        for j in range(pw.whisper_full_n_tokens(ctx, i)):
            d = pw.whisper_full_get_token_data(ctx, i, j)
            if d.id >= eot:
                continue  # special / timestamp tokens
            # raw bytes: whisper_full_get_token_text decodes in C++ and raises on half a Japanese character
            raw = pw.whisper_token_to_bytes(ctx, d.id)
            pend += raw
            pend_t0 = d.t0 if pend_t0 is None else pend_t0
            try:
                txt = pend.decode('utf-8')
            except UnicodeDecodeError:
                continue  # a Japanese char split across tokens: merge with the next token
            toks.append({'text': txt, 'offsets': {'from': pend_t0 * 10, 'to': d.t1 * 10}, 'id': d.id, 'p': d.p})
            pend, pend_t0 = b'', None
        if pend:  # the segment ended inside a character: keep what is there (U+FFFD for the broken bytes), loudly
            txt = pend.decode('utf-8', errors='replace')
            print(f'asr.py: WARNING segment {i} ends with {len(pend)} incomplete UTF-8 byte(s); kept as {txt!r}',
                  file=sys.stderr, flush=True)
            toks.append({'text': txt, 'offsets': {'from': pend_t0 * 10, 'to': d.t1 * 10}, 'id': d.id, 'p': d.p})
        segs.append({'offsets': {'from': pw.whisper_full_get_segment_t0(ctx, i) * 10,
                                 'to': pw.whisper_full_get_segment_t1(ctx, i) * 10},
                     'text': ''.join(t['text'] for t in toks), 'tokens': toks})
    json.dump({'model': os.path.basename(a.model), 'result': {'language': a.lang}, 'transcription': segs},
              open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

dt = time.time() - t0
n = len(json.load(open(a.out, encoding='utf-8'))['transcription'])
print(f'asr: {a.backend} {n} segments, audio {audio_s:.1f}s in {dt:.1f}s ({audio_s / max(dt, 1e-6):.2f}x realtime) -> {a.out}')
