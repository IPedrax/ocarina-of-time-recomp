# Written for ocarina-of-time-recomp (MIT, Copyright (c) 2026 Jeff Aigner).
"""Report of a profile written by runtime/prof_linux.c (OOT_PROFILE=<path>): the samples per function of the exe
(through `nm`) and per library, overall and for the busiest threads.

    python3 tools/prof_report_linux.py <profile> [--exe build/v131072/oot] [--top 30] [--threads 4]

Lines of the profile: `base <exe load address>`, `rip <address> <thread> <count>`, `map <one line of /proc/self/maps>`.
"""
import argparse
import bisect
import subprocess
from collections import Counter
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('profile')
    ap.add_argument('--exe', default='build/v131072/oot')
    ap.add_argument('--top', type=int, default=30)
    ap.add_argument('--threads', type=int, default=4)
    a = ap.parse_args()

    base, rips, maps, period, roles = 0, [], [], 1000, {}
    for line in Path(a.profile).read_text().splitlines():
        w = line.split()
        if w[0] == 'base':
            base = int(w[1], 16)
        elif w[0] == 'role':
            roles[int(w[2])] = w[1]
        elif w[0] == 'period_us':
            period = int(w[1])
        elif w[0] == 'rip':
            rips.append((int(w[1], 16), int(w[2]), int(w[3])))
        elif w[0] == 'map':
            lo, hi = (int(x, 16) for x in w[1].split('-'))
            maps.append((lo, hi, w[-1] if w[-1].startswith('/') else '[anon]'))
    maps.sort()
    los = [m[0] for m in maps]

    syms = []
    out = subprocess.run(['nm', '-n', '-S', '--defined-only', a.exe], capture_output=True, text=True).stdout
    for line in out.splitlines():
        w = line.split()
        if len(w) == 4 and w[2] in 'tTwW':
            syms.append((int(w[0], 16), w[3]))
    addrs = [s[0] for s in syms]

    def where(pc):
        i = bisect.bisect_right(los, pc) - 1
        if i < 0 or pc >= maps[i][1]:
            return '[unmapped]'
        path = maps[i][2]
        if path.endswith('/' + Path(a.exe).name):
            j = bisect.bisect_right(addrs, pc - base) - 1
            return syms[j][1] if j >= 0 else 'exe+%#x' % (pc - base)
        return Path(path).name

    total = sum(c for _, _, c in rips)
    by_thread = Counter()
    for _, t, c in rips:
        by_thread[t] += c
    print(f'{total} samples of {period} us ({total * period / 1e6:.1f} s of CPU time), {len(by_thread)} threads')
    print('threads:', ', '.join(f'{t}{"(" + roles[t] + ")" if t in roles else ""}: {c}' for t, c in by_thread.most_common(8)))

    def show(title, pick):
        cnt = Counter()
        for pc, t, c in rips:
            if pick(t):
                cnt[where(pc)] += c
        tot = sum(cnt.values())
        print(f'\n{title}: {tot} samples')
        for name, c in cnt.most_common(a.top):
            print(f'  {c:7d} {100 * c / tot:5.1f}%  {name}')

    show('all threads', lambda t: True)
    for t, _ in by_thread.most_common(a.threads):
        show(f'thread {t} {roles.get(t, "")}', lambda x, t=t: x == t)


main()
