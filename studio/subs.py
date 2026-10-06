"""Speaker-labelled transcript from a Meet recording's embedded subtitle stream.

usage: subs.py SUBS.srt OUT.txt [--strip PREFIX ...]
Meet captions put the speaker as a "(Name)" line; consecutive lines of one speaker are merged.
Output lines: "[h:mm:ss] Speaker: text" in recording time. --strip removes e.g. a company prefix from names.
"""
import re, sys

args = sys.argv[1:]
if len(args) < 2:
    sys.exit(__doc__)
src, dst = args[0], args[1]
strip = [args[i + 1] for i, a in enumerate(args) if a == '--strip' and i + 1 < len(args)]

blocks = open(src, encoding='utf-8').read().strip().split('\n\n')
out = []; cur = None
spk = None
last_t = 0
for b in blocks:
    lines = b.split('\n')
    m = re.match(r'(\d+):(\d+):(\d+)', lines[1]) if len(lines) > 1 else None
    if not m:
        # continuation block without index/time (the "-" separated)
        t = None; body = lines
    else:
        t = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]); body = lines[2:]
        last_t = t
    for ln in body:
        s = re.match(r'^\((.+)\)$', ln.strip())
        if s:
            spk = s[1]
            for p in strip:
                spk = spk.replace(p, '')
            continue
        if ln.strip() in ('', '-'):
            continue
        if cur and cur[1] == spk:
            cur[2] += ln.strip()
        else:
            cur = [last_t, spk, ln.strip()]; out.append(cur)
with open(dst, 'w', encoding='utf-8') as f:
    for t, s, x in out:
        f.write(f"[{t//3600}:{t%3600//60:02d}:{t%60:02d}] {s}: {x}\n")
speakers = {}
for _, s, x in out:
    speakers[s] = speakers.get(s, 0) + len(x)
print(f'{len(out)} turns -> {dst}')
for s, n in sorted(speakers.items(), key=lambda kv: -kv[1]):
    print(f'  {s}: {n} chars')
