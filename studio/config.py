"""Shared CLI/env settings for the studio scripts (EDL module, work dir, source, offset, limit, encoder).

Every flag can also be given as an environment variable so `preview.py` / ad-hoc `python3 -c` imports see
the same settings:  --edl STUDIO_EDL, --work STUDIO_WORK, --src STUDIO_SRC,
--source-offset STUDIO_SOURCE_OFFSET, --limit STUDIO_LIMIT, --out STUDIO_OUT, encoder STUDIO_VENC.
"""
import argparse, importlib.util, os, shlex, subprocess, sys


def _env_float(name):
    v = os.environ.get(name)
    return float(v) if v not in (None, '') else None


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--edl', default=os.environ.get('STUDIO_EDL'), help='path to the EDL python module')
    p.add_argument('--work', default=os.environ.get('STUDIO_WORK', 'work'), help='work dir (base.mov, timeline.json, ...)')
    p.add_argument('--src', default=os.environ.get('STUDIO_SRC'), help='source video (build_base only)')
    p.add_argument('--source-offset', type=float, default=_env_float('STUDIO_SOURCE_OFFSET') or 0.0,
                   help='seconds added to every EDL time when reading --src (EDL relative to a clip of a longer file)')
    p.add_argument('--limit', type=float, default=_env_float('STUDIO_LIMIT'),
                   help='render only the first N (> 0) output seconds (quick tests); omit for the full render')
    p.add_argument('--out', default=os.environ.get('STUDIO_OUT'), help='final mp4 path (telops only)')
    args = p.parse_args(sys.argv[1:] if argv is None else argv)  # unknown flags (typos) are an error
    if not args.edl:
        p.error('--edl (or STUDIO_EDL) is required')
    if args.limit is not None and not args.limit > 0:  # 0 / negative / nan would silently mean "full render"
        p.error(f'--limit (or STUDIO_LIMIT) must be > 0 seconds, got {args.limit:g}')
    args.edl = os.path.abspath(args.edl)
    args.work = os.path.abspath(args.work)
    os.makedirs(args.work, exist_ok=True)
    return args


def load_edl(path):
    spec = importlib.util.spec_from_file_location('edl', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules['edl'] = mod
    return mod


def clip_is_share(edl, a):
    """True when a clip starting at source time a shows the screen-share layout. SHARE_RANGES (optional list of
    (from, to) source times) is for recordings that switch between face and share; else a >= SHARE_FROM - 1."""
    ranges = getattr(edl, 'SHARE_RANGES', None)
    if ranges is not None:
        return any(lo <= a < hi for lo, hi in ranges)
    return a >= edl.SHARE_FROM - 1


def venc(bitrate):
    """Video encoder args: STUDIO_VENC override, else h264_videotoolbox (macOS), else libx264."""
    if os.environ.get('STUDIO_VENC'):
        return shlex.split(os.environ['STUDIO_VENC'])
    enc = subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], capture_output=True, text=True).stdout
    if ' h264_videotoolbox ' in enc:
        return ['-c:v', 'h264_videotoolbox', '-b:v', bitrate]
    return ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18']


ARGS = parse_args()
EDL = load_edl(ARGS.edl)
