"""Resolve the three telop weights (W6 / W8 / W9) to (path, ttc_index).

Order: env override (STUDIO_FONT_W6 / _W8 / _W9, value "path" or "path#index")
       -> Hiragino Sans W6/W8/W9 (macOS)
       -> Noto Sans CJK JP Medium/Bold/Black (Linux: apt fonts-noto-cjk fonts-noto-cjk-extra).
Exits with an error listing every path tried when a weight is missing.
"""
import glob, os, sys

HIRAGINO = {
    'W6': '/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc',
    'W8': '/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc',
    'W9': '/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc',
}
NOTO = {'W6': 'Medium', 'W8': 'Bold', 'W9': 'Black'}
NOTO_DIRS = ['/usr/share/fonts/opentype/noto', '/usr/share/fonts/noto-cjk', '/usr/share/fonts/google-noto-cjk',
             '/usr/share/fonts']


def _split(v):
    if '#' in v:
        p, i = v.rsplit('#', 1)
        return p, int(i)
    return v, 0


def resolve(weight):
    tried = []
    env = os.environ.get(f'STUDIO_FONT_{weight}')
    if env:
        p, i = _split(env)
        if os.path.exists(p):
            return p, i
        tried.append(f'STUDIO_FONT_{weight}={env}')
    tried.append(HIRAGINO[weight])
    if os.path.exists(HIRAGINO[weight]):
        return HIRAGINO[weight], 0
    name = f'NotoSansCJK-{NOTO[weight]}.ttc'  # index 0 = Noto Sans CJK JP
    for d in NOTO_DIRS:
        tried.append(os.path.join(d, name))
        hits = sorted(glob.glob(os.path.join(d, '**', name), recursive=True))
        if hits:
            return hits[0], 0
    sys.exit(f'fonts.py: no font for {weight}. Tried: ' + ', '.join(tried) +
             '\nInstall fonts-noto-cjk fonts-noto-cjk-extra (Linux) or set STUDIO_FONT_' + weight)


FW6, FW8, FW9 = resolve('W6'), resolve('W8'), resolve('W9')

if __name__ == '__main__':
    for k, v in (('W6', FW6), ('W8', FW8), ('W9', FW9)):
        print(k, v[0], f'#{v[1]}')
