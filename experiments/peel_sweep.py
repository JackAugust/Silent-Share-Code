#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Dense sweep of the first-salt peeling rate p1 over n, plus the salt budget.

`peel_rate.py` samples a coarse grid (10, 50, 100, ...).  Because
m = ceil(1.25 n), the load m/n oscillates and p1 is non-monotone for small n,
so the minimum can fall between those grid points.  This script sweeps every
n in [10, 30] and a geometric tail, reports p1 with a Wilson 95% interval,
and derives the number of salts B needed for eps_peel <= 2^-128 / 2^-64 from
the *lower* confidence bound (conservative).

    python experiments/peel_sweep.py            # ~5 min
    python experiments/peel_sweep.py --quick
"""

import argparse
import csv
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))
sys.path.insert(0, HERE)

from peel_rate import first_peelable  # noqa: E402


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / float(n)
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (c - h) / d), min(1.0, (c + h) / d))


def trials_for(n, quick):
    base = 1500 if n <= 30 else (800 if n <= 100 else (400 if n <= 400 else 300))
    return max(60, base // 5) if quick else base


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--alpha", type=float, default=1.25)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--out", default="results/peel_sweep.csv")
    args = ap.parse_args(argv)

    grid = (list(range(10, 31)) + [32, 35, 40, 45, 50, 60, 70, 80, 100]
            + [150, 200, 250, 300, 400] + [600, 800, 1200, 1600, 2000])

    rows = []
    print("%6s %6s %7s %8s %8s %9s %8s" %
          ("n", "m", "trials", "p1", "lo", "E[salts]", "fail"))
    for n in grid:
        m = max(int(math.ceil(args.alpha * n)), n + 1)
        trials = trials_for(n, args.quick)
        first = none = 0
        total = 0
        for t in range(trials):
            got = first_peelable(t * 7919 + 13, n, m)
            if got == 0:
                none += 1
            else:
                total += got
                if got == 1:
                    first += 1
        p1 = first / float(trials)
        lo, hi = wilson(first, trials)
        mean_s = (total / float(trials - none)) if (trials - none) else float("nan")
        rows.append([n, m, trials, round(p1, 4), round(lo, 4), round(hi, 4),
                     round(mean_s, 3), none])
        print("%6d %6d %7d %8.4f %8.4f %9.3f %8d" %
              (n, m, trials, p1, lo, mean_s, none))
        sys.stdout.flush()

    path = os.path.join(os.path.dirname(HERE), args.out)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["n", "m", "trials", "p1", "p1_lo", "p1_hi",
                    "mean_salts", "fail20"])
        w.writerows(rows)
    print("\nwrote %s" % path)

    worst = min(rows, key=lambda r: r[3])
    print("min p1: n=%d p1=%.4f (lo %.4f)  E[salts]=%.2f"
          % (worst[0], worst[3], worst[4], worst[6]))
    for target in (128, 64):
        need = math.log(2) * target / (-math.log(1 - worst[4]))
        print("  need B >= %.0f for 2^-%d at the Wilson lower bound" %
              (math.ceil(need), target))
    for B in (256, 384, 512):
        e = (1 - worst[4]) ** B
        print("  B=%d -> eps_peel = 2^%.1f (lower-bound p1)" %
              (B, math.log2(e) if e > 0 else float("-inf")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
