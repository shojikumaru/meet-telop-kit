"""Character-level time lookup over whisper tokens (whisper-cli -ojf JSON, as written by transcribe.sh).

usage: tok.py [WHISPER.json] T0 T1        -> print the text between T0 and T1 with [sec] marks
       import: STUDIO_WHISPER_JSON=work/x.json python3 -c "from tok import span, show; ..."
"""
import json, os, sys
if __name__ == '__main__' and len(sys.argv) == 4:
    os.environ['STUDIO_WHISPER_JSON'] = sys.argv.pop(1)
_j = json.load(open(os.environ.get('STUDIO_WHISPER_JSON', os.path.join('work', 'whisper.json')), encoding='utf-8'))
TEXT = ''
T0 = []  # start time per char
T1 = []  # end time per char
for s in _j['transcription']:
    for t in s['tokens']:
        tx = t['text']
        if tx.startswith('[_'):
            continue
        a, b = t['offsets']['from'] / 1000, t['offsets']['to'] / 1000
        n = len(tx)
        for i, ch in enumerate(tx):
            TEXT += ch
            T0.append(a + (b - a) * i / max(n, 1))
            T1.append(a + (b - a) * (i + 1) / max(n, 1))


def span(start_text, end_text, after=0.0):
    """Return (t_start, t_end) from first start_text at/after `after` to the end of end_text following it."""
    i = 0
    while True:
        i = TEXT.find(start_text, i)
        if i < 0:
            raise ValueError(f'start not found: {start_text} after {after}')
        if T0[i] >= after - 0.05:
            break
        i += 1
    j = TEXT.find(end_text, i)
    if j < 0:
        raise ValueError(f'end not found: {end_text}')
    return T0[i], T1[j + len(end_text) - 1]


def show(a, b):
    out = ''
    last = -1
    for ch, t in zip(TEXT, T0):
        if a <= t <= b:
            if int(t) != last:
                out += f'[{t:.1f}]'
                last = int(t)
            out += ch
    return out


if __name__ == '__main__':
    print(show(float(sys.argv[1]), float(sys.argv[2])))
