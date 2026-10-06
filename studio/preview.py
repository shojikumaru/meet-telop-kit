"""Render preview stills (telops over base frames) at key moments -> <work>/prev/<t>.jpg (960x540).

usage: preview.py --edl EDL.py [--work DIR] [--at t1,t2,...]   (--at = OUTPUT seconds)
Default moments: 1.5 s, every EDL.PREVIEW_AT source time (or every section/pop cue), the last second.
"""
import os, subprocess, sys

# --at is ours; strip it before telops/config parse the remaining (shared) flags strictly
AT = None
if '--at' in sys.argv:
    i = sys.argv.index('--at')
    if i + 1 >= len(sys.argv):
        sys.exit('preview.py: --at needs a comma-separated list of output seconds')
    AT = sys.argv[i + 1]
    del sys.argv[i:i + 2]
import telops as T

D = T.D
o = T.o
if AT is not None:
    ts = [float(x) for x in AT.split(',')]
else:
    src = getattr(T.edl, 'PREVIEW_AT', None)
    if src is None:
        src = [t for t, *_ in getattr(T.edl, 'SECTIONS', [])] + [t + 0.4 for t, *_ in getattr(T.edl, 'POPS', [])]
    ts = [1.5] + [o(t) for t in src] + [T.TOTAL - 1.0]
ts = [round(t, 1) for t in ts]
os.makedirs(os.path.join(D, 'prev_bg'), exist_ok=True)
os.makedirs(os.path.join(D, 'prev'), exist_ok=True)
for t in ts:
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{t:.1f}', '-i', os.path.join(D, 'base.mov'),
                    '-frames:v', '1', os.path.join(D, 'prev_bg', f'{t:.1f}.png')], check=True)
os.environ['PREVIEW'] = ','.join(f'{t:.1f}' for t in ts)
try:
    T.main()
except SystemExit:
    pass
print(ts)
print('stills:', os.path.join(D, 'prev'))
