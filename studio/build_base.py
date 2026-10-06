"""Cut + concat the EDL into base.mov (30fps, browser chrome blurred during screen share, tail freeze).

usage: build_base.py --edl EDL.py --src VIDEO [--source-offset S] [--work DIR] [--limit N]

EDL TIMING = 'anchored' (default) writes the per-clip output starts, blur windows and total measured from the real
segment starts (each cut lasts max(video, audio), a few ms more than nominal), so subtitles / telops / SE cues stay
on the speech. TIMING = 'nominal' keeps the plain EDL arithmetic (legacy timing mode: an EDL cut against nominal
clip lengths sets it so a re-render stays frame-identical).
"""
import subprocess, os, json, re, sys, time, wave
from config import ARGS, EDL, venc, clip_is_share

CLIPS, SHARE_BLUR, TAIL = EDL.CLIPS, EDL.SHARE_BLUR, EDL.TAIL
if not hasattr(EDL, 'SHARE_RANGES') and not hasattr(EDL, 'SHARE_FROM'):
    sys.exit('build_base.py: the EDL needs SHARE_FROM (a huge value if never) or SHARE_RANGES')
TIMING = getattr(EDL, 'TIMING', 'anchored')
D = ARGS.work
SRC = ARGS.src
PAD_IN, PAD_OUT = 0.06, 0.10
FPS = 30
W, H = 1920, 1080


def timeline():
    """Merge contiguous clips for cutting; return cut list, per-clip nominal output offsets, total, and the index
    of the cut each clip sits in."""
    cuts, out, owner = [], [], []
    t = 0.0
    for a, b, *_ in CLIPS:
        a2, b2 = a - PAD_IN, b + PAD_OUT
        if cuts and abs(cuts[-1][1] - a2) < 0.25 and a2 >= cuts[-1][0]:
            # contiguous with previous cut: extend it
            prev_a, prev_b = cuts[-1]
            t -= (prev_b - prev_a)
            cuts[-1] = (prev_a, b2)
            out.append((a, b, t + (a - prev_a)))
            t += (b2 - prev_a)
        else:
            cuts.append((a2, b2))
            out.append((a, b, t + PAD_IN))
            t += (b2 - a2)
        owner.append(len(cuts) - 1)
    return cuts, out, t, owner


def nominal_bounds(cuts):
    bounds, t = [], 0.0
    for a2, b2 in cuts:
        bounds.append((t, t + (b2 - a2)))
        t += b2 - a2
    return bounds


def share_windows(bounds, out):
    """Blur windows in output time (bounds = (start, end) of each cut, out = per-clip starts, both in the same
    timing), decided per clip: a merged cut that straddles SHARE_FROM is blurred only from the first screen-share
    clip on. Inside a cut a clip owns the span up to the midpoint of the pause before the next clip; adjacent
    windows are merged."""
    spans, j = [], 0
    for c0, c1 in bounds:
        mine = []
        while j < len(out) and out[j][2] < c1 - 1e-9:
            mine.append(out[j])
            j += 1
        for k, (a, b, s) in enumerate(mine):
            lo = c0 if k == 0 else (mine[k - 1][2] + mine[k - 1][1] - mine[k - 1][0] + s) / 2
            hi = c1 if k == len(mine) - 1 else (s + b - a + mine[k + 1][2]) / 2
            if clip_is_share(EDL, a):
                spans.append([lo, hi])
    wins = []
    for lo, hi in spans:
        if wins and lo <= wins[-1][1] + 1e-6:
            wins[-1][1] = hi
        else:
            wins.append([lo, hi])
    return wins


def probe(args, path):
    r = subprocess.run(['ffprobe', '-v', 'error'] + args + ['-of', 'csv=p=0', path], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        sys.exit(f'build_base.py: ffprobe failed on {path}: {r.stderr.strip()[:300]}')
    return r.stdout.strip()


def ffmpeg(cmd, what, **kw):
    r = subprocess.run(cmd, **kw)
    if r.returncode != 0:
        sys.exit(f'build_base.py: ffmpeg failed ({what}), exit {r.returncode}')
    return r


def main():
    if not SRC or not (os.path.exists(SRC) or '://' in SRC):  # http(s) URLs are read with range requests
        sys.exit(f'build_base.py: source video not found: {SRC!r} (use --src)')
    if TIMING not in ('anchored', 'nominal'):
        sys.exit(f"build_base.py: EDL TIMING must be 'anchored' or 'nominal', not {TIMING!r}")
    cuts, out, total, owner = timeline()
    render = cuts
    if ARGS.limit:
        # keep only the cuts needed for the first N output seconds (output is also cut with -t)
        render, t = [], 0.0
        for a, b in cuts:
            if t >= ARGS.limit:
                break
            render.append((a, min(b, a + ARGS.limit - t + 1.0)))
            t += b - a
    off = ARGS.source_offset
    sw, sh = (int(x) for x in probe(['-select_streams', 'v:0', '-show_entries', 'stream=width,height'],
                                    SRC).split(',')[:2])
    fit = ''
    if (sw, sh) != (W, H):
        # telop coordinates assume 1920x1080: scale to fit, keep aspect, pad with black
        fit = (f',scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,'
               f'setsar=1')
        print(f'build_base: source is {sw}x{sh}; scaling to fit {W}x{H} (aspect kept, black bars)',
              file=sys.stderr, flush=True)
    src_end = float(probe(['-show_entries', 'format=duration'], SRC)) - off  # source end in EDL time
    cut_ends = [b for _, b in cuts]  # untruncated (--limit) cut ends: the last clip ends PAD_OUT before
    print(f'build_base: {len(render)} cuts, src={SRC} offset={off}', file=sys.stderr, flush=True)
    t0 = time.time()

    # 1) Video: one input-seeked pass per cut into a lossless intermediate (frames on a 1 us grid). One graph
    # splitting an input into dozens of trims made ffmpeg 6.1 queue decoded frames on idle branches (~14 GB, OOM
    # in the cloud); a per-cut pass stays ~1 GB. -sn: Meet's mov_text caption stream alone makes even a plain 5 s
    # transcode balloon past 5 GB on 6.1.
    cut_files, nframes = [], []
    for i, (a, b) in enumerate(render):
        cf = os.path.join(D, f'cut{i:03d}.mov')
        # -copyts: the trim uses absolute source time, exactly as the original single-graph cut did
        ffmpeg(['ffmpeg', '-v', 'error', '-y', '-copyts', '-sn',
                '-ss', f'{off + a:.3f}', '-t', f'{b - a + 0.5:.3f}', '-i', SRC,
                '-vf', f'trim=start={a + off:.3f}:end={b + off:.3f},setpts=PTS-STARTPTS,fps={FPS}{fit}',
                '-an', '-pix_fmt', 'yuv420p', '-c:v', 'libx264', '-preset', 'ultrafast', '-qp', '0',
                '-video_track_timescale', '1000000', cf], f'cut {i}')
        n = int(probe(['-select_streams', 'v:0', '-count_packets', '-show_entries', 'stream=nb_read_packets'], cf))
        # the PAD_IN/PAD_OUT margins may hang over the source's start/end (a clip at EOF is fine), the clip
        # itself may not; otherwise the cut must hold every frame of its range (else the render is silently short)
        ea, eb = max(a, -off), min(b, src_end)
        if min(b, cut_ends[i] - PAD_OUT) > src_end + 1 / FPS or abs(n - (eb - ea) * FPS) > 2:
            sys.exit(f'build_base.py: cut {i} ({a:.3f}-{b:.3f} +offset {off:g}) produced {n} frames, expected '
                     f'{(eb - ea) * FPS:.1f} (+-2; source ends at {src_end + off:.3f}): the range runs past the end '
                     f'of the source or the offset is wrong')
        cut_files.append(cf)
        nframes.append(n)
        if i % 10 == 9 or i == len(render) - 1:
            print(f'build_base: cut {i + 1}/{len(render)} ({time.time() - t0:.0f}s)', file=sys.stderr, flush=True)

    # 2) Audio: one input decoded from the offset (the AAC decoder's noise state depends on where decoding
    # starts, so this keeps the samples identical to the original graph), joined by the concat FILTER with a
    # 16x16 stand-in video of each cut's exact frame count. The concat filter ends every segment at
    # max(video, audio) and pads audio with silence, which is what the earlier single-graph build did; the stand-in's
    # first-frame time per segment gives those segment starts so the real video can be placed identically.
    audio = os.path.join(D, 'base_audio.wav')
    ain = (['-ss', f'{off:.3f}'] if off else []) + ['-t', f'{max(b for _, b in render) + 0.5:.3f}', '-i', SRC]
    fc, parts = [], []
    for i, (a, b) in enumerate(render):
        d = b - a
        a, b = a + off, b + off  # -copyts: trims use absolute source time
        fc.append(f'nullsrc=s=16x16:r={FPS},trim=end_frame={nframes[i]}[d{i}]')
        fc.append(f'[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,'
                  f'afade=t=in:d=0.03,afade=t=out:st={max(d-0.04,0):.3f}:d=0.04[a{i}]')
        parts.append(f'[d{i}][a{i}]')
    fc.append(''.join(parts) + f'concat=n={len(render)}:v=1:a=1[dv][ac]')
    fc.append('[dv]settb=AVTB,showinfo,nullsink')
    fc.append(f'[ac]apad=pad_dur={TAIL}[aout]')
    r = ffmpeg(['ffmpeg', '-hide_banner', '-nostats', '-loglevel', 'info', '-y', '-copyts', '-vn', '-sn'] + ain + [
                '-filter_complex', ';'.join(fc), '-map', '[aout]', '-c:a', 'pcm_s16le', '-ar', '48000', audio],
               'audio + segment timing', capture_output=True, text=True)
    pts = [int(m.group(1)) for m in re.finditer(r'Parsed_showinfo.*?\bn:\s*\d+\s+pts:\s*(-?\d+)', r.stderr)]
    if len(pts) != sum(nframes):
        sys.exit(f'build_base.py: segment timing probe saw {len(pts)} frames, expected {sum(nframes)}')
    starts, k = [], 0
    for n in nframes:
        starts.append(pts[k])  # microseconds
        k += n
    starts.append(starts[-1] + round(nframes[-1] * 1e6 / FPS))
    seg = [(starts[i + 1] - starts[i]) / 1e6 for i in range(len(render))]
    # the last segment also ends at max(video, audio): its audio end is the wav length minus the TAIL padding
    with wave.open(audio) as wf:
        audio_end = wf.getnframes() / wf.getframerate() - TAIL
    rel = [(s - starts[0]) / 1e6 for s in starts]  # segment starts (+ video end of the last one), output seconds
    seg_end = max(rel[-1], audio_end)
    drift = round(seg_end - sum(n / FPS for n in nframes), 3) + 0.0
    print(f'build_base: segments {seg_end:.3f}s (video frames {sum(nframes)}, audio-led padding {drift:+.3f}s)',
          file=sys.stderr, flush=True)

    # per-cut shift = real segment start - nominal cut start (cuts past --limit keep the last rendered shift)
    nb = nominal_bounds(cuts)
    nr = len(render)
    shift = [rel[i] - nb[i][0] if i < nr else rel[nr - 1] - nb[nr - 1][0] for i in range(len(cuts))]
    full = nr == len(cuts) and render[-1] == cuts[-1]
    end_shift = (seg_end - nb[-1][1]) if full else shift[-1]
    clip_drift = [shift[c] for c in owner]
    worst = max(range(len(out)), key=lambda k: abs(clip_drift[k]))
    print(f'build_base: timing {TIMING}: real vs nominal clip start drift max {clip_drift[worst]:+.3f}s '
          f'(clip {worst}), end {end_shift:+.3f}s', file=sys.stderr, flush=True)
    if TIMING == 'anchored':
        out = [(a, b, s + shift[c]) for (a, b, s), c in zip(out, owner)]
        bounds = [(nb[i][0] + shift[i], (nb[i + 1][0] + shift[i + 1]) if i + 1 < len(cuts) else nb[i][1] + end_shift)
                  for i in range(len(cuts))]
        total += end_shift
        # every rendered clip must start inside its real segment (a --limit-truncated last cut is not checked)
        for k, ((a, b, s), c) in enumerate(zip(out, owner)):
            if (c < nr - 1 or (c == nr - 1 and full)) and not (rel[c] - 1e-6 <= s <= (rel[c + 1] if c + 1 < nr else seg_end) + 1e-6):
                sys.exit(f'build_base.py: clip {k} anchored start {s:.3f}s is outside its segment {c}')
    else:
        bounds = nb
        if abs(clip_drift[worst]) > 2 / FPS:
            print(f'build_base: WARNING timing nominal: telops drift up to {clip_drift[worst]:+.3f}s from the '
                  f'speech (use TIMING = \'anchored\' for a new EDL)', file=sys.stderr, flush=True)

    # 3) Final pass: cuts read back in order by the concat demuxer, each placed at its segment start via the
    # duration directive (so a cut whose audio is longer than its frames leaves the same timestamp gap the concat
    # filter left), blur, tail freeze, audio from step 2.
    lst = os.path.join(D, 'cuts.txt')
    with open(lst, 'w') as f:
        for cf, sd in zip(cut_files, seg):
            f.write(f"file '{os.path.abspath(cf)}'\nduration {sd:.6f}\n")
    x, y, w, h = SHARE_BLUR
    wins = share_windows(bounds, out)
    en = '+'.join(f'between(t,{s:.3f},{e:.3f})' for s, e in wins) or '0'
    fc = ['[0:v]setpts=PTS-STARTPTS[vc]',
          f'[vc]split[vb][vk];[vk]crop={w}:{h}:{x}:{y},boxblur=luma_radius=14:luma_power=2:chroma_radius=8:'
          f"chroma_power=2[bl];[vb][bl]overlay={x}:{y}:enable='{en}'[vo]",
          f'[vo]tpad=stop_mode=clone:stop_duration={TAIL}[vout]']
    cmd = ['ffmpeg', '-v', 'error', '-stats_period', '10', '-stats', '-y', '-copyts',
           '-f', 'concat', '-safe', '0', '-i', lst, '-i', audio,
           '-filter_complex', ';'.join(fc),
           '-map', '[vout]', '-map', '1:a', '-pix_fmt', 'yuv420p'] + venc('8000k') + [
           '-c:a', 'pcm_s16le', '-ar', '48000']
    if ARGS.limit:
        cmd += ['-t', f'{ARGS.limit:.3f}']
    cmd.append(os.path.join(D, 'base.mov'))
    ffmpeg(cmd, 'final base.mov')
    for p in cut_files + [lst, audio]:
        os.remove(p)
    # total = nominal EDL length (drives the telop schedule); base_duration = what base.mov really lasts (segments
    # end at max(video, audio), so it is a few frames longer) -- telops.py checks the final mp4 against it
    base_dur = seg_end + TAIL
    if ARGS.limit:
        base_dur = min(base_dur, ARGS.limit)
    # share = the spans base.mov shows the screen-share layout: the blur windows, the last one running on through
    # the tail freeze (a clone of the last, blurred frame). telops.py centres on x=720 exactly inside them.
    share = [list(w_) for w_ in wins]
    if share and clip_is_share(EDL, CLIPS[-1][0]):
        share[-1][1] = max(share[-1][1], total + TAIL)
    json.dump({'out': out, 'total': total + TAIL, 'cuts': cuts, 'base_duration': round(base_dur, 6),
               'timing': TIMING, 'seg_starts': [round(x, 6) for x in rel[:-1]], 'nframes': nframes,
               'blur': [[round(s, 6), round(e, 6)] for s, e in wins],
               'share': [[round(s, 6), round(e, 6)] for s, e in share]},
              open(os.path.join(D, 'timeline.json'), 'w'))
    print(f'clips={len(CLIPS)} cuts={len(cuts)} duration={total + TAIL:.1f}s'
          + (f' (rendered first {ARGS.limit:.1f}s)' if ARGS.limit else '') + f' wall={time.time() - t0:.0f}s')


if __name__ == '__main__':
    main()
