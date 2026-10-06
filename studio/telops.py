"""YouTube-style pop telop layer: renders RGBA frames and pipes them into ffmpeg over base.mov."""
import json, math, os, struct, subprocess, sys, wave
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from config import ARGS, EDL as edl, venc, clip_is_share
from fonts import FW6, FW8, FW9  # (path, ttc index)

D = ARGS.work
W, H, FPS = 1920, 1080, 30

TL = json.load(open(os.path.join(D, 'timeline.json')))
OUT = TL['out']          # [(src_a, src_b, out_start)]
TOTAL = TL['total']
SPK = edl.SPEAKERS       # {key: (name, color, dark color)}
NEVER = -1e9             # cue time for panels the EDL does not use
# screen-share spans in output time, written by build_base (the blur windows, the last one running through the tail
# freeze when the last clip is a share clip): the telop layout follows exactly what base.mov shows
SHARE = TL['share'] if 'share' in TL else TL.get('blur', [])


def o(src):
    """Map a source time to output time (snaps to the nearest clip)."""
    best = None
    for a, b, s in OUT:
        if a <= src <= b:
            return s + (src - a)
    for a, b, s in OUT:
        if a - 0.3 <= src <= b + 0.3:
            return s + (min(max(src, a), b) - a)
        d = min(abs(src - a), abs(src - b))
        if best is None or d < best[0]:
            best = (d, s + (min(max(src, a), b) - a))
    return best[1]


def is_share(t):
    """True when the output time t shows the screen-share layout (content on the left 1440px), i.e. when base.mov
    is blurred there: same windows, same inclusive bounds as build_base's between(t, start, end)."""
    if TL.get('timing') == 'nominal':
        return _is_share_nominal(t)
    return any(lo <= t <= hi for lo, hi in SHARE)


def _is_share_nominal(t):
    """Legacy centring of the nominal timing mode (TIMING = 'nominal' keeps it frame for frame): per clip from
    0.2 s before its start to 0.3 s after its end, share elsewhere. It disagrees with the blur for a few frames at a switch."""
    for a, b, s in OUT:
        if s - 0.2 <= t <= s + (b - a) + 0.3:
            return clip_is_share(edl, a)
    return True


def cx_for(t):
    return 720 if is_share(t) else W / 2


def font(path, size):
    return _font(path, size)


@lru_cache(maxsize=None)
def _font(path, size):
    return ImageFont.truetype(path[0], size, index=path[1])


def hexc(h, a=255):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


def vgrad(w, h, c1, c2):
    g = Image.new('RGBA', (w, h))
    px = g.load()
    a, b = hexc(c1), hexc(c2)
    for y in range(h):
        t = y / max(h - 1, 1)
        c = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(4))
        for x in range(w):
            px[x, y] = c
    return g


def hgrad(w, h, c1, c2):
    col = Image.new('RGBA', (w, 1))
    a, b = hexc(c1), hexc(c2)
    for x in range(w):
        t = x / max(w - 1, 1)
        col.putpixel((x, 0), tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(4)))
    return col.resize((w, h))


def shadow(img, off=(6, 8), blur=10, alpha=0.55):
    a = img.getchannel('A').point(lambda v: int(v * alpha))
    sh = Image.new('RGBA', img.size, (10, 8, 30, 0))
    sh.putalpha(a)
    pad = blur * 3
    big = Image.new('RGBA', (img.width + pad * 2 + abs(off[0]), img.height + pad * 2 + abs(off[1])), (0, 0, 0, 0))
    big.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)) if False else sh, (pad + off[0], pad + off[1]))
    big = big.filter(ImageFilter.GaussianBlur(blur))
    big.alpha_composite(img, (pad, pad))
    return big


def text_sprite(lines, fpath, size, fill='#FFFFFF', strokes=(), grad=None, spacing=0.18, align='center'):
    f = font(fpath, size)
    maxs = max([w for w, _ in strokes], default=0)
    boxes = [f.getbbox(l) for l in lines]
    lw = [b[2] - b[0] for b in boxes]
    lh = int(size * (1 + spacing))
    width = max(lw) + maxs * 2 + 8
    height = lh * len(lines) + maxs * 2 + int(size * 0.25)
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pos = []
    for i, l in enumerate(lines):
        x = maxs + 4 + ((max(lw) - lw[i]) // 2 if align == 'center' else 0) - boxes[i][0]
        y = maxs + i * lh
        pos.append((x, y))
    for w, c in sorted(strokes, key=lambda s: -s[0]):
        for (x, y), l in zip(pos, lines):
            d.text((x, y), l, font=f, fill=c, stroke_width=w, stroke_fill=c)
    if maxs >= 10:
        # thick outer strokes leave dark specks inside closed letter shapes (る, 画, の, e): paint those holes
        # with the innermost (coloured) stroke so they read as part of the letter
        holes = glyph_holes(img.size, pos, lines, f)
        img.paste(Image.new('RGBA', img.size, hexc(min(strokes)[1])), (0, 0), holes)
    if grad:
        mask = Image.new('L', img.size, 0)
        md = ImageDraw.Draw(mask)
        for (x, y), l in zip(pos, lines):
            md.text((x, y), l, font=f, fill=255)
        g = vgrad(1, img.height, *grad).resize(img.size)
        img.paste(g, (0, 0), mask)
    else:
        for (x, y), l in zip(pos, lines):
            d.text((x, y), l, font=f, fill=fill)
    return img


SS = 4  # shapes are drawn SS times larger and downsampled: PIL draws them without anti-aliasing


def glyph_holes(size, pos, lines, f):
    """L mask of the background areas enclosed by the glyphs (not reachable from the sprite border)."""
    m = Image.new('L', size, 0)
    md = ImageDraw.Draw(m)
    for (x, y), l in zip(pos, lines):
        md.text((x, y), l, font=f, fill=255)
    m = m.point(lambda v: 255 if v >= 96 else 0)
    outside = Image.new('L', (size[0] + 2, size[1] + 2), 0)  # 1 px frame so the flood starts outside
    outside.paste(m, (1, 1))
    ImageDraw.floodfill(outside, (0, 0), 128)
    return outside.crop((1, 1, size[0] + 1, size[1] + 1)).point(lambda v: 255 if v == 0 else 0)


def rrect(w, h, r, fill=None, grad=None, hg=None, outline=None, ow=0):
    """Anti-aliased rounded rectangle (a fresh copy: callers draw on it)."""
    return _rrect(w, h, r, fill, grad, hg, outline, ow).copy()


@lru_cache(maxsize=1024)  # panels ask for the same shells / bar widths every frame
def _rrect(w, h, r, fill, grad, hg, outline, ow):
    W, H, R, O = w * SS, h * SS, r * SS, ow * SS
    img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    mask = Image.new('L', (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, H - 1), R, fill=255)
    if grad:
        src = vgrad(1, H, *grad).resize((W, H))
    elif hg:
        src = hgrad(W, H, *hg)
    else:
        src = Image.new('RGBA', (W, H), hexc(fill) if isinstance(fill, str) else fill)
    img.paste(src, (0, 0), mask)
    if outline:
        ImageDraw.Draw(img).rounded_rectangle((O // 2, O // 2, W - 1 - O // 2, H - 1 - O // 2), R, outline=outline, width=O)
    return img.resize((w, h), Image.LANCZOS)


def disc(d, fill, outline, ow):
    """Anti-aliased filled circle of diameter d with an outline ow px wide (a fresh copy)."""
    return _disc(d, fill, outline, ow).copy()


@lru_cache(maxsize=64)
def _disc(d, fill, outline, ow):
    big =Image.new('RGBA', (d * SS, d * SS), (0, 0, 0, 0))
    ImageDraw.Draw(big).ellipse((0, 0, d * SS - 1, d * SS - 1), fill=fill, outline=outline, width=ow * SS)
    return big.resize((d, d), Image.LANCZOS)


def ink_xy(spr, box_w=None, box_h=None, x=None, y=None):
    """Offset that centres the sprite's visible pixels (not its padded box) in a box_w x box_h area."""
    l, t, r, b = spr.getbbox()
    return (x if box_w is None else (box_w - l - r) // 2, y if box_h is None else (box_h - t - b) // 2)


# ---------------------------------------------------------------- sprites
@lru_cache(maxsize=None)
def subtitle_sprite(spk, text):
    name, col, dark = SPK[spk]
    lines = text.split('\n')
    size = 62 if max(len(l) for l in lines) <= 20 else 54
    body = text_sprite(lines, FW8, size, fill='#FFFFFF', strokes=((15, '#0B1026'), (10, col)))
    chip_t = text_sprite([name], FW8, 30, fill='#FFFFFF')
    chip = rrect(chip_t.width + 28, 48, 24, grad=(col, dark), outline=(255, 255, 255, 255), ow=4)
    chip.alpha_composite(chip_t, ink_xy(chip_t, box_w=chip.width, box_h=48))
    img = Image.new('RGBA', (max(body.width, chip.width + 40), body.height + 34), (0, 0, 0, 0))
    img.alpha_composite(body, ((img.width - body.width) // 2, 34))
    img.alpha_composite(chip, ((img.width - body.width) // 2 + 18, 0))
    return shadow(img, (4, 6), 6, 0.5)


POP_STYLES = {
    'gold': dict(grad=('#FFF7A8', '#FFB300'), strokes=((34, '#1A1030'), (26, '#FFFFFF'), (13, '#E6002E'))),
    'red': dict(grad=('#FFFFFF', '#FFE3EA'), strokes=((34, '#1A1030'), (26, '#FFFFFF'), (13, '#FF1F5A'))),
    'blue': dict(grad=('#FFFFFF', '#DDF3FF'), strokes=((34, '#1A1030'), (26, '#FFFFFF'), (13, '#0A6CFF'))),
}


@lru_cache(maxsize=None)
def pop_sprite(text, style):
    size = 118 if len(text) <= 10 else (100 if len(text) <= 14 else 86)
    s = POP_STYLES[style]
    img = text_sprite([text], FW9, size, grad=s['grad'], strokes=s['strokes'])
    img = shadow(img, (8, 12), 12, 0.6)
    return img.rotate(-3, resample=Image.BICUBIC, expand=True)


@lru_cache(maxsize=None)
def header_sprite(label, title):
    t = text_sprite([title], FW8, 44, fill='#FFFFFF', strokes=((4, '#3A0CA3'),))
    badge = disc(84, hexc('#FFE94D'), hexc('#FFFFFF'), 5)
    bt = text_sprite([label], FW9, 36, fill='#3A0CA3')
    badge.alpha_composite(bt, ink_xy(bt, box_w=84, box_h=84))
    bar = rrect(t.width + 110, 70, 35, hg=('#7B2FF7', '#F107A3'), outline=(255, 255, 255, 255), ow=4)
    bar.alpha_composite(t, ink_xy(t, box_h=70, x=74))
    img = Image.new('RGBA', (bar.width + 20, 90), (0, 0, 0, 0))
    img.alpha_composite(bar, (20, 10))
    img.alpha_composite(badge, (0, 3))
    return shadow(img, (4, 6), 6, 0.45)


@lru_cache(maxsize=None)
def plate_sprite(spk):
    lines = edl.PLATE_TEXT[spk]
    _, col, dark = SPK[spk]
    top = text_sprite([lines[0]], FW6, 28, fill='#FFFFFF')
    name = text_sprite([lines[1]], FW9, 54, fill='#1A1030')
    w = max(top.width, name.width) + 60
    img = Image.new('RGBA', (w, 130), (0, 0, 0, 0))
    img.alpha_composite(rrect(w, 46, 10, grad=(col, dark)), (0, 0))
    img.alpha_composite(top, ink_xy(top, box_h=46, x=22))
    img.alpha_composite(rrect(w, 78, 12, fill='#FFFFFF', outline=hexc(col), ow=5), (0, 48))
    nx, ny = ink_xy(name, box_h=78, x=24)
    img.alpha_composite(name, (nx, 48 + ny))
    return shadow(img, (5, 7), 8, 0.45)


@lru_cache(maxsize=None)
def chip_sprite(label, color):
    t = text_sprite([label], FW8, 44, fill='#FFFFFF')
    c = rrect(t.width + 56, 84, 42, fill=color, outline=(255, 255, 255, 255), ow=5)
    c.alpha_composite(t, ink_xy(t, box_w=c.width, box_h=84))
    return shadow(c, (4, 6), 6, 0.45)


@lru_cache(maxsize=None)
def title_sprite():
    l1 = text_sprite([edl.TITLE[0]], FW9, 66,
                     grad=('#FFF7A8', '#FFB300'), strokes=((26, '#1A1030'), (20, '#FFFFFF'), (10, '#E6002E')))
    rib_t = text_sprite([edl.TITLE[1]], FW8, 46, fill='#FFFFFF')
    rib = rrect(rib_t.width + 70, 80, 16, hg=('#FF1F5A', '#FF7A00'), outline=(255, 255, 255, 255), ow=5)
    rib.alpha_composite(rib_t, ink_xy(rib_t, box_w=rib.width, box_h=80))
    img = Image.new('RGBA', (max(l1.width, rib.width), l1.height + 70), (0, 0, 0, 0))
    img.alpha_composite(l1, ((img.width - l1.width) // 2, 0))
    img.alpha_composite(rib, ((img.width - rib.width) // 2, l1.height - 22))
    return shadow(img, (6, 10), 10, 0.5)


# ---------------------------------------------------------------- animation helpers
def pop_scale(t):
    if t < 0:
        return 0
    if t < 0.10:
        return 0.35 + 0.85 * (t / 0.10)
    if t < 0.20:
        return 1.20 - 0.20 * ((t - 0.10) / 0.10)
    return 1.0


def ease_out(x):
    x = min(max(x, 0), 1)
    return 1 - (1 - x) ** 3


def place(canvas, spr, cx, cy, scale=1.0, alpha=1.0):
    if scale <= 0.01 or alpha <= 0.01:
        return
    if abs(scale - 1) > 0.01:
        spr = spr.resize((max(1, int(spr.width * scale)), max(1, int(spr.height * scale))), Image.BILINEAR)
    if alpha < 0.99:
        spr = spr.copy()
        spr.putalpha(spr.getchannel('A').point(lambda v: int(v * alpha)))
    canvas.alpha_composite(spr, (int(cx - spr.width / 2), int(cy - spr.height / 2)))


# ---------------------------------------------------------------- panels
def panel_bars(canvas, t, t0, t1, title, rows, scale_fn, note=None, badge=None):
    """rows: [(appear_out, label, value_text, value, highlight)]"""
    fade = min(ease_out((t - t0) / 0.25), ease_out((t1 - t) / 0.25))
    if fade <= 0:
        return
    pw, ph = 1220, 140 + 86 * len(rows) + (40 if note else 0)
    px, py = 110, 130
    panel = rrect(pw, ph, 28, fill=(255, 255, 255, 236), outline=hexc('#7B2FF7'), ow=6)
    d = ImageDraw.Draw(panel)
    tt = text_sprite([title], FW8, 42, fill='#1A1030')
    panel.alpha_composite(tt, (40, 26))
    barx, barw = 540, 500
    for i, (ta, label, vtxt, val, hi) in enumerate(rows):
        if t < ta:
            continue
        k = ease_out((t - ta) / 0.45)
        y = 112 + i * 86
        if hi:
            panel.alpha_composite(rrect(pw - 40, 88, 18, fill=(255, 233, 77, 110)), (20, y - 6))
        lab = text_sprite([label], FW8 if hi else FW6, 32 if not hi else 34, fill='#E6002E' if hi else '#23233A', align='left')
        panel.alpha_composite(lab, (40, y + 14))
        bw = max(12, int(barw * scale_fn(val) * k))
        bar = rrect(bw, 50, 25, hg=('#FF7A00', '#FF1F5A') if hi else ('#5B8CFF', '#7B2FF7'))
        panel.alpha_composite(bar, (barx, y + 12))
        vt = text_sprite([vtxt], FW9 if hi else FW8, 34 if not hi else 40,
                         fill='#FFFFFF', strokes=((7, '#E6002E' if hi else '#23233A'),))
        panel.alpha_composite(vt, (min(barx + bw + 12, pw - vt.width - 14), y + 6))
    if note:
        n = text_sprite([note], FW6, 24, fill='#6B6B80', align='left')
        panel.alpha_composite(n, (40, ph - 52))
    panel = shadow(panel, (8, 12), 14, 0.5)
    place(canvas, panel, px + pw / 2, py + ph / 2, 0.92 + 0.08 * fade, fade)
    if badge and t >= badge[0]:
        spr = pop_sprite(badge[1], 'red')
        place(canvas, spr, px + pw - 250, py + 40, pop_scale(t - badge[0]) * 0.75, 1.0)


def icon(kind, w=150, h=110):
    img = Image.new('RGBA', (w * SS, h * SS), (0, 0, 0, 0))
    d = _ScaledDraw(ImageDraw.Draw(img))
    navy = hexc('#23233A')
    if kind == 'server':
        for i in range(3):
            d.rounded_rectangle((25, 6 + i * 34, 125, 36 + i * 34), 6, fill=navy)
            d.ellipse((104, 16 + i * 34, 114, 26 + i * 34), fill=hexc('#2BE38A'))
    elif kind == 'desktop':
        d.rounded_rectangle((10, 4, 140, 82), 8, fill=navy)
        d.rectangle((20, 14, 130, 72), fill=hexc('#5B8CFF'))
        d.rectangle((65, 82, 85, 96), fill=navy)
        d.rounded_rectangle((40, 96, 110, 106), 4, fill=navy)
    else:
        d.rounded_rectangle((25, 10, 125, 78), 8, fill=navy)
        d.rectangle((33, 18, 117, 70), fill=hexc('#7B2FF7'))
        d.rounded_rectangle((8, 80, 142, 96), 6, fill=navy)
    return img.resize((w, h), Image.LANCZOS)


class _ScaledDraw:
    """ImageDraw proxy that multiplies coordinates and radii by SS (for supersampled icons)."""
    def __init__(self, d):
        self.d = d

    def __getattr__(self, name):
        def call(box, *a, **k):
            box = tuple(v * SS for v in box)
            if name == 'rounded_rectangle' and a:
                a = (a[0] * SS,) + a[1:]
            return getattr(self.d, name)(box, *a, **k)
        return call


def panel_sites(canvas, t, marks, t1):
    t0 = marks['server']
    fade = min(ease_out((t - t0) / 0.25), ease_out((t1 - t) / 0.25))
    if fade <= 0:
        return
    cards = edl.SITES_CARDS
    for i, (k, l1, l2) in enumerate(cards):
        ta = marks[k]
        if t < ta:
            continue
        c = rrect(330, 290, 26, fill=(255, 255, 255, 240), outline=hexc('#7B2FF7'), ow=6)
        c.alpha_composite(icon(k), (90, 26))
        a = text_sprite([l1], FW8, 36, fill='#7B2FF7')
        b = text_sprite([l2], FW8, 38, fill='#1A1030')
        c.alpha_composite(a, ((330 - a.width) // 2, 150))
        c.alpha_composite(b, ((330 - b.width) // 2, 205))
        c = shadow(c, (6, 9), 10, 0.45)
        place(canvas, c, 290 + i * 430, 380, pop_scale(t - ta), fade)
    if t >= marks['center']:
        spr = pop_sprite(edl.SITES_CENTER_TEXT, 'gold')
        place(canvas, spr, 720, 640, pop_scale(t - marks['center']) * 0.82, fade)


def panel_money(canvas, t, marks, t1):
    t0 = marks['api']
    fade = min(ease_out((t - t0) / 0.25), ease_out((t1 - t) / 0.3))
    if fade <= 0:
        return
    pw, ph = 1100, 560
    panel = rrect(pw, ph, 28, fill=(255, 255, 255, 238), outline=hexc('#FF1F5A'), ow=6)
    rows = edl.MONEY_ROWS
    y = 40
    for key, txt, kind in rows:
        if t < marks[key]:
            y += 120
            continue
        k = ease_out((t - marks[key]) / 0.3)
        if kind == 'strike':
            s = text_sprite([txt], FW9, 64, fill='#E6002E', strokes=((6, '#FFFFFF'),))
            layer = Image.new('RGBA', (pw, 100), (0, 0, 0, 0))
            layer.alpha_composite(s, (40, 6))
            if t >= marks['actual']:
                kk = ease_out((t - marks['actual']) / 0.35)
                ImageDraw.Draw(layer).line((34, 52, 34 + int((s.width + 10) * kk), 46), fill=hexc('#1A1030'), width=9)
        else:
            s = text_sprite([txt], FW8, 40, fill='#23233A', align='left')
            layer = Image.new('RGBA', (pw, 100), (0, 0, 0, 0))
            layer.alpha_composite(s, (40, 20))
        layer.putalpha(layer.getchannel('A').point(lambda v: int(v * k)))
        panel.alpha_composite(layer, (0, y))
        y += 120
    panel = shadow(panel, (8, 12), 14, 0.5)
    place(canvas, panel, 720, 470, 0.92 + 0.08 * fade, fade)
    if t >= marks['actual']:
        spr = pop_sprite(edl.MONEY_ACTUAL_TEXT, 'gold')
        place(canvas, spr, 720, 700, pop_scale(t - marks['actual']) * 0.8, fade)


def end_card(canvas, t, t0):
    k = ease_out((t - t0) / 0.5)
    if k <= 0:
        return
    ov = Image.new('RGBA', (W, H), (12, 8, 40, int(200 * k)))
    canvas.alpha_composite(ov)
    if t >= t0 + 0.3:
        spr = pop_sprite(edl.END_CARD[0], 'gold')
        place(canvas, spr, W / 2, 420, pop_scale(t - t0 - 0.3) * 1.15)
    if t >= t0 + 0.9:
        kk = ease_out((t - t0 - 0.9) / 0.4)
        a = text_sprite([edl.END_CARD[1]], FW8, 46, fill='#FFFFFF', strokes=((8, '#0A6CFF'),))
        b = text_sprite([edl.END_CARD[2]], FW8, 40, fill='#FFFFFF', strokes=((8, '#FF3D7F'),))
        place(canvas, a, W / 2, 640, 1, kk)
        place(canvas, b, W / 2, 730, 1, kk)


# ---------------------------------------------------------------- schedule
def build_schedule():
    subs = []
    for (a, b, spk, text), (_, _, s) in zip(edl.CLIPS, OUT):
        parts = text.split('||')
        total = sum(len(p) for p in parts)
        t0 = s
        for p in parts:
            d = (b - a) * len(p) / total
            subs.append((t0, t0 + d + 0.05, spk, p))
            t0 += d
    secs = [(o(t), lab, ti) for t, lab, ti in getattr(edl, 'SECTIONS', [])]
    pops = [(o(t), tx, st, du) for t, tx, st, du in getattr(edl, 'POPS', [])]
    chips = [(o(t), l, c) for t, l, c in getattr(edl, 'CHIPS', [])]
    return subs, secs, pops, chips


def render(write, se_events):
    subs, secs, pops, chips = build_schedule()
    # every panel is optional: an EDL without e.g. TIERS simply never shows that panel
    oo = lambda name, add=0.0: o(getattr(edl, name)) + add if hasattr(edl, name) else NEVER
    chips_end = oo('CHIPS_END')
    tiers = [(o(t), l, v, val, hi) for t, l, v, val, hi in getattr(edl, 'TIERS', [])]
    t_start, t_end, t_badge = oo('TIERS_START'), oo('TIERS_END'), oo('TIERS_BADGE')
    sites = {k: o(t) for t, k in getattr(edl, 'SITES', [])}
    sites_end = oo('SITES_END')
    repos = [(o(t), l, v, val, hi) for t, l, v, val, hi in getattr(edl, 'REPOS', [])]
    repos_end = oo('REPOS_END', 0.4)
    money = {k: o(t) for t, k in getattr(edl, 'MONEY', [])}
    money_end = oo('MONEY_END', 0.3)
    plates = [(o(t), spk, du) for t, spk, du in getattr(edl, 'PLATES', [])]
    hook_end = oo('HOOK_TITLE_END')
    end_from = oo('END_CARD_FROM')
    if end_from == NEVER:
        end_from = -NEVER

    # SE cue list
    for t, *_ in pops: se_events.append((t, 'pop'))
    for t, *_ in chips: se_events.append((t, 'tick'))
    for t, *_ in tiers: se_events.append((t, 'tick'))
    for t, *_ in repos: se_events.append((t, 'tick'))
    for k, t in sites.items(): se_events.append((t, 'pop' if k == 'center' else 'tick'))
    for k, t in money.items(): se_events.append((t, 'kira' if k == 'actual' else 'tick'))
    for t, *_ in secs: se_events.append((t, 'swoosh'))
    if hook_end != NEVER:
        se_events.append((0.25, 'kira'))
    if end_from != -NEVER:
        se_events.append((end_from + 0.3, 'kira'))

    n = int(min(TOTAL, ARGS.limit or TOTAL) * FPS)
    last_key, last_bytes = None, None
    lo, hi_ = getattr(edl, 'TIERS_LOG_RANGE', (4, 10.7))
    lin = lambda v: (math.log10(v) - lo) / (hi_ - lo)
    for fi in range(n):
        t = fi / FPS
        key = []
        # quantize animation state; static states reuse bytes
        def anim(x, dur=0.6):
            return round(x, 3) if 0 <= x <= dur else ('done' if x > dur else 'no')
        cur_sub = next((s for s in subs if s[0] <= t < s[1]), None)
        key.append(('sub', cur_sub[2:] if cur_sub else None))  # (speaker, text): same words, other speaker = other sprite
        cur_sec = None
        for s in secs:
            if s[0] <= t and t < end_from:
                cur_sec = s
        key.append(('sec', cur_sec, anim(t - cur_sec[0]) if cur_sec else None))
        act_pops = [p for p in pops if p[0] <= t < p[0] + p[3]]
        key += [('pop', p, anim(t - p[0]), anim(p[0] + p[3] - t, 0.2)) for p in act_pops]
        if t < hook_end:
            key.append(('title', anim(t - 0.25), anim(hook_end - t, 0.3)))
        act_chips = [c for c in chips if c[0] <= t < chips_end + 0.3]
        key += [('chip', c, anim(t - c[0]), anim(chips_end + 0.3 - t, 0.3)) for c in act_chips]
        # panels: key on their animation clocks (fade in / out, each row, pops) so a settled panel reuses bytes
        if t_start - 0.1 <= t <= t_end + 0.3:
            key.append(('tier', anim(t - t_start, 0.25), anim(t_end + 0.3 - t, 0.25),
                        tuple(anim(t - r[0], 0.45) for r in tiers),
                        anim(t - t_badge, 0.2) if t_badge != NEVER else None))
        if sites and sites['server'] <= t <= sites_end + 0.3:
            key.append(('sites', anim(t - sites['server'], 0.25), anim(sites_end + 0.3 - t, 0.25),
                        tuple(anim(t - v, 0.2) for v in sites.values())))
        if repos and repos[0][0] <= t <= repos_end + 0.3:
            key.append(('repos', anim(t - repos[0][0], 0.25), anim(repos_end + 0.3 - t, 0.25),
                        tuple(anim(t - r[0], 0.45) for r in repos)))
        if money and money['api'] <= t <= money_end + 0.3:
            key.append(('money', anim(t - money['api'], 0.25), anim(money_end + 0.3 - t, 0.3),
                        tuple(anim(t - v, 0.35) for v in money.values())))
        key.append(('share', is_share(t)))  # subtitles / chips move when the layout switches
        act_pl = [p for p in plates if p[0] <= t < p[0] + p[2]]
        key += [('plate', p, anim(t - p[0], 0.4), anim(p[0] + p[2] - t, 0.3)) for p in act_pl]
        if t >= end_from:
            key.append(('end', round(t, 3) if t < end_from + 1.6 else 'done'))
        key = tuple(key)
        if key == last_key:
            write(last_bytes)
            continue

        cv = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        if t < hook_end:
            k = min(ease_out((t - 0.25) / 0.35), ease_out((hook_end - t) / 0.3))
            place(cv, title_sprite(), W / 2, 150, 0.85 + 0.15 * k, k)
        if cur_sec:
            k = ease_out((t - cur_sec[0]) / 0.35)
            spr = header_sprite(cur_sec[1], cur_sec[2])
            place(cv, spr, 30 + spr.width / 2 - (1 - k) * (spr.width + 60), 70, 1, k)
        for tt, l, c in act_chips:
            i = [x[1] for x in chips].index(l)
            row, col = divmod(i, 4)
            fade = ease_out((chips_end + 0.3 - t) / 0.3)
            place(cv, chip_sprite(l, c), cx_for(t) - 495 + col * 330, 250 + row * 110, pop_scale(t - tt), fade)
        if tiers:
            panel_bars(cv, t, t_start, t_end + 0.3, edl.TIERS_TITLE, tiers, lin,
                       note=edl.TIERS_NOTE, badge=(t_badge, edl.TIERS_BADGE_TEXT) if t_badge != NEVER else None)
        if sites:
            panel_sites(cv, t, sites, sites_end + 0.3)
        if repos:
            panel_bars(cv, t, repos[0][0], repos_end + 0.3, edl.REPOS_TITLE, repos,
                       lambda v: v / edl.REPOS_MAX)
        if money:
            panel_money(cv, t, money, money_end + 0.3)
        for tt, spk, du in act_pl:
            k = min(ease_out((t - tt) / 0.4), ease_out((tt + du - t) / 0.3))
            spr = plate_sprite(spk)
            place(cv, spr, 40 + spr.width / 2 - (1 - k) * 80, 470, 1, k)
        for tt, tx, st, du in act_pops:
            k = ease_out((tt + du - t) / 0.2)
            place(cv, pop_sprite(tx, st), cx_for(tt), 560 if tt < hook_end else 500, pop_scale(t - tt), k)
        if t >= end_from:
            end_card(cv, t, end_from)
        if cur_sub and t < end_from + 0.2:
            spr = subtitle_sprite(cur_sub[2], cur_sub[3])
            place(cv, spr, cx_for(t), H - 20 - spr.height / 2 + 10)
        last_key, last_bytes = key, cv.tobytes()
        write(last_bytes)
        if fi % 300 == 0:
            print(f'{t:6.1f}s / {TOTAL:.1f}s', file=sys.stderr, flush=True)


# ---------------------------------------------------------------- SE synth
def synth_se(events, path, sr=48000):
    n = int((TOTAL + 1) * sr)
    buf = [0.0] * n

    def add(t0, fn, dur):
        s = int(t0 * sr)
        for i in range(int(dur * sr)):
            if 0 <= s + i < n:
                buf[s + i] += fn(i / sr)

    for t, kind in events:
        if kind == 'pop':
            add(t, lambda x: 0.30 * math.sin(2 * math.pi * (900 - 2500 * x) * x) * math.exp(-x * 28), 0.16)
        elif kind == 'tick':
            add(t, lambda x: 0.16 * math.sin(2 * math.pi * 1500 * x) * math.exp(-x * 60), 0.08)
        elif kind == 'kira':
            for j, f in enumerate((1318.5, 1760, 2349.3)):
                add(t + j * 0.07, (lambda f: lambda x: 0.12 * math.sin(2 * math.pi * f * x) * math.exp(-x * 9))(f), 0.5)
        elif kind == 'swoosh':
            import random
            rnd = random.Random(int(t * 1000))
            add(t, lambda x: 0.10 * (rnd.random() * 2 - 1) * math.sin(math.pi * min(x / 0.25, 1)), 0.25)
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(b''.join(struct.pack('<h', max(-32767, min(32767, int(v * 32767)))) for v in buf))


def main():
    out_path = os.path.abspath(ARGS.out or os.path.join(D, 'final.mp4'))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    preview = os.environ.get('PREVIEW')  # "t1,t2,..." -> write PNG stills only
    events = []
    if preview:
        want = [float(x) for x in preview.split(',')]
        frames = {int(x * FPS): x for x in want}
        idx = [0]

        def w(bts):
            if idx[0] in frames:
                bg = Image.open(os.path.join(D, 'prev_bg', f'{frames[idx[0]]:.1f}.png')).convert('RGBA')
                bg.alpha_composite(Image.frombytes('RGBA', (W, H), bts))
                bg.convert('RGB').resize((960, 540)).save(os.path.join(D, 'prev', f'{frames[idx[0]]:.1f}.jpg'))
            idx[0] += 1
            if idx[0] > max(frames):
                raise SystemExit
        render(w, events)
        return
    render_events = []
    # first pass for SE cues only (cheap: schedule is deterministic)
    se_path = os.path.join(D, 'se.wav')
    cmd = ['ffmpeg', '-v', 'error', '-y', '-i', os.path.join(D, 'base.mov'),
           '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
           '-filter_complex', '[0:v][1:v]overlay=0:0:format=auto,format=yuv420p[v]',
           '-map', '[v]', '-map', '0:a'] + venc('9000k') + ['-c:a', 'pcm_s16le',
           os.path.join(D, 'video_noaudio_mix.mov')]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        render(p.stdin.write, render_events)
        p.stdin.close()
    except BrokenPipeError:
        print('telops.py: the overlay ffmpeg stopped reading the telop frames early', file=sys.stderr)
    if p.wait() != 0:
        sys.exit(f'telops.py: overlay ffmpeg failed (exit {p.returncode}); nothing was muxed')
    synth_se(render_events, se_path)
    mix = ['ffmpeg', '-v', 'error', '-y', '-i', os.path.join(D, 'video_noaudio_mix.mov'), '-i', se_path,
           '-filter_complex', '[0:a]highpass=f=80,acompressor=threshold=-20dB:ratio=3:attack=5:release=120,'
           'loudnorm=I=-15:TP=-1.5:LRA=9[vo];[1:a]volume=0.9[se];[vo][se]amix=inputs=2:duration=first:normalize=0[a]',
           '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', out_path]
    if subprocess.run(mix).returncode != 0:
        sys.exit('telops.py: final mux ffmpeg failed')
    check_output(out_path)
    print('done', out_path)


def check_output(path):
    """Fail (non-zero) unless the final mp4 has the expected duration, every base frame and an audio stream."""
    def probe(f, *args):
        r = subprocess.run(['ffprobe', '-v', 'error', *args, '-of', 'csv=p=0', f], capture_output=True, text=True)
        return r.stdout.strip()
    want = TL.get('base_duration', TOTAL)  # rendered length of base.mov per build_base
    if ARGS.limit:
        want = min(want, ARGS.limit)
    errs = []
    try:
        dur = float(probe(path, '-show_entries', 'format=duration'))
    except ValueError:
        dur = -1.0
    if abs(dur - want) > 0.1:
        errs.append(f'duration {dur:.3f}s, expected {want:.3f}s (+-0.1)')
    count = ['-select_streams', 'v:0', '-count_packets', '-show_entries', 'stream=nb_read_packets']
    nv, nb = probe(path, *count), probe(os.path.join(D, 'base.mov'), *count)
    if not nv.isdigit() or nv != nb:
        errs.append(f'video frames {nv or "none"}, base.mov has {nb or "none"}')
    if not probe(path, '-select_streams', 'a', '-show_entries', 'stream=index'):
        errs.append('no audio stream')
    if errs:
        sys.exit(f'telops.py: output check FAILED for {path}: ' + '; '.join(errs))
    print(f'telops: output ok ({dur:.3f}s, {nv} frames, audio)', file=sys.stderr)


if __name__ == '__main__':
    main()
