"""Read one register of one compute kernel on the GPU (OOT_PROBE, runtime/sm86_lower.c): run the game into the level,
dump the frame of the kernel's first dispatch and report the statistics of the images it wrote, which then hold the
register as it was right after the given instruction.

    python tools/probe.py --hash d72101b7 --input 1a62084a --at 0x39f0 --reg 24
    python tools/probe.py --hash d72101b7 --input 1a62084a --bisect probes.txt   # lines "<offset> <register>", in
                                                                                 # program order: the first one NaN

--hash is the start of the kernel's code hash and --input of its input id (tools/kernel.py stats prints both). Each run
replays build/logs/a-spam.txt with the movies skipped (CLAUDE.md, "into the game"), so it takes about two minutes. The
first lines of every report are the pass-0 images: the kernel's own outputs. NaN counts are per component.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_probe(args, offset, reg, tag):
    out = ROOT / 'build' / 'logs' / f'probe-{tag}'
    if (out / 'images.txt').exists():
        (out / 'images.txt').unlink()
    env = [f'OOT_PROBE={args.hash}:{offset:x}:{reg}' + (':i' if args.int else ''), f'OOT_DUMP=cs:{args.input}', f'OOT_DUMP_DIR={out.relative_to(ROOT).as_posix()}']
    cmd = [sys.executable, str(ROOT / 'tools' / 'run.py'), '--kill-existing', '--seconds', str(args.seconds), '--replay',
           args.replay, '--skip-movies', '--expect', 'OOT_PROBE .*program found']
    for e in env + list(args.env):
        cmd += ['--env', e]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    status = [l for l in r.stdout.splitlines() if l.startswith('run:')]
    images = (out / 'images.txt').read_text().splitlines() if (out / 'images.txt').exists() else []
    for png in out.glob('*.png'):   # a frame dump is hundreds of MB of PNGs; only images.txt is read
        png.unlink()
    first = [l for l in images if l.startswith('pass_0000_img')]
    # Only images in a float format can hold NaN (the name ends in the format: ..._r11g11b10f, ..._rgba16f).
    floats = [l for l in first if l.split()[0].endswith('f')]
    nan = sum(int(m.group(1)) for l in floats if (m := re.search(r' nan (\d+)$', l)))
    total = sum(int(w) * int(h) * int(d) * 3 for l in floats
                for w, h, d in re.findall(r' (\d+)x(\d+)x(\d+) min', l))
    print(f'@{offset:#06x} R{reg}: {"; ".join(status[-1:])}')
    for l in first:
        print('   ', l)
    if not first:
        print('    no dump of the kernel (did the run reach it? is --input right?)')
    return nan, total, bool(first)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--hash', required=True)
    ap.add_argument('--input', required=True)
    ap.add_argument('--at', type=lambda s: int(s, 0))
    ap.add_argument('--reg', type=int)
    ap.add_argument('--int', action='store_true', help='capture the register as an unsigned integer (I2F)')
    ap.add_argument('--bisect', type=Path)
    ap.add_argument('--seconds', type=int, default=100)
    ap.add_argument('--replay', default='build/logs/a-spam.txt')
    ap.add_argument('--env', action='append', default=[], metavar='OOT_X=V')
    args = ap.parse_args()
    if args.bisect:
        probes = [(int(a, 0), int(b)) for a, b in (l.split()[:2] for l in args.bisect.read_text().splitlines()
                                                    if l.strip() and not l.startswith('#'))]
        lo, hi = 0, len(probes) - 1   # find the first probe whose value is NaN in every component written
        nan_hi, total_hi, ok = run_probe(args, *probes[hi], 'hi')
        if not ok or nan_hi < total_hi:
            print(f'the last probe is not all NaN ({nan_hi} of {total_hi}): nothing to bisect')
            return 1
        while lo < hi:
            mid = (lo + hi) // 2
            nan, total, ok = run_probe(args, *probes[mid], f'{mid}')
            if not ok:
                print('no dump: stopping')
                return 1
            if nan and nan == total:
                hi = mid
            else:
                lo = mid + 1
        print(f'first all-NaN value: @{probes[lo][0]:#06x} R{probes[lo][1]}')
        return 0
    if args.at is None or args.reg is None:
        ap.error('--at and --reg, or --bisect')
    run_probe(args, args.at, args.reg, f'{args.at:x}-{args.reg}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
