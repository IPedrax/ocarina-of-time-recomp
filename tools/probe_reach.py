#!/usr/bin/env python3
# Written for ocarina-of-time-recomp (MIT, Copyright (c) 2026 Jeff Aigner).
"""Find where the threads of a compute kernel leave it: OOT_PROBE_REACH over 32 points a run, narrowed run by run.

    python3 tools/probe_reach.py --input e6d5432f --hash a2731d1f --slot 4 --dump 0x29bb96000:0x1040 [--frame 4500]

Each run (tools/run.py, the level route with OOT_MEMORY=import) lowers the kernel with bit k of R254 set right after
the instruction at point k and every thread storing R254 at its EXIT into storage slot --slot (sm86_lower.c,
OOT_PROBE_REACH); OOT_WATCH_DUMP writes that buffer at --frame. The share of the sampled threads (one u32 each) that
reached each point is printed; the next run puts 32 points between the two neighbouring points with the largest drop,
until they are adjacent instructions. Points are the kernel's non-branch instructions (tools/kernel.py dis). The
slot must be one the game's CPU does not read back (docs/level.md). About 3 minutes a run.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SKIP = re.compile(r'^(BRA|BRX|EXIT|BSSY|BSYNC|BREAK|WARPSYNC|NOP|RET|CALL)$')


def points(prefix):
    dis = subprocess.run([sys.executable, str(ROOT / 'tools' / 'kernel.py'), 'dis', prefix], capture_output=True,
                         text=True, cwd=ROOT).stdout.splitlines()
    out = []
    for line in dis:
        f = line.split()
        if len(f) < 3 or not re.fullmatch(r'[0-9a-f]{6}', f[0]):
            continue
        name = f[2] if f[1].startswith('@') else f[1]
        if not SKIP.match(name):
            out.append(int(f[0], 16))
    return out


def run(args, pts, tag):
    addr = args.dump.split(':')[0]
    dump = ROOT / 'build' / 'logs' / f'watchdump-{int(addr, 16):x}.bin'
    dump.unlink(missing_ok=True)
    spec = f'{args.hash}:b{args.slot}:' + ','.join(f'{p:x}' for p in pts)
    cmd = [sys.executable, str(ROOT / 'tools' / 'run.py'), '--kill-existing', '--seconds', str(args.seconds), '--replay',
           args.replay, '--skip-movies', '--env', 'OOT_MEMORY=import', '--env', f'OOT_PROBE_REACH={spec}',
           '--env', f'OOT_WATCH_DUMP={args.dump}@{args.frame}', '--expect', 'OOT_PROBE .*program found']
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    status = [l for l in r.stdout.splitlines() if l.startswith('run:')]
    if not dump.exists():
        sys.exit(f'{tag}: no dump ({"; ".join(status[-1:])})')
    a = np.fromfile(dump, dtype='<u4')
    a = a[a != 0]                                     # threads that stored nothing (no EXIT reached, or not this run)
    share = [float(((a >> k) & 1).mean()) if len(a) else 0.0 for k in range(len(pts))]
    print(f'{tag}: {len(a)} threads sampled ({"; ".join(status[-1:])})')
    for p, s in zip(pts, share):
        print(f'    {p:#06x} {s:6.1%}')
    return share


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--input', required=True, help='input id prefix (tools/kernel.py)')
    ap.add_argument('--hash', required=True, help='code hash prefix (tools/kernel.py stats)')
    ap.add_argument('--slot', type=int, required=True)
    ap.add_argument('--dump', required=True, help='<addr>:<len> of the slot\'s buffer')
    ap.add_argument('--frame', type=int, default=4500)
    ap.add_argument('--seconds', type=int, default=170)
    ap.add_argument('--replay', default='build/logs/a-spam.txt')
    ap.add_argument('--rounds', type=int, default=4)
    args = ap.parse_args()
    all_pts = points(args.input)
    if not all_pts:
        sys.exit('no instructions: is the input id right?')
    lo, hi = 0, len(all_pts) - 1
    for rnd in range(args.rounds):
        span = all_pts[lo:hi + 1]
        step = max(1, len(span) // 31)
        pts = span[::step][:31] + [span[-1]]
        pts = sorted(set(pts))
        share = run(args, pts, f'round {rnd + 1}, {span[0]:#x}-{span[-1]:#x}')
        drops = [(share[i] - share[i + 1], i) for i in range(len(pts) - 1)]
        if not drops:
            break
        d, i = max(drops)
        print(f'  largest drop {d:.1%} between {pts[i]:#x} and {pts[i + 1]:#x}')
        nlo, nhi = all_pts.index(pts[i]), all_pts.index(pts[i + 1])
        if nhi - nlo <= 1 or d <= 0:
            print(f'  narrowed to {pts[i]:#x} -> {pts[i + 1]:#x}')
            break
        lo, hi = nlo, nhi


if __name__ == '__main__':
    main()
