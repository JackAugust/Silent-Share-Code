#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Peelability of the sparse-GOKVS hypergraph, without Charm.

The sparse encoder retries `salt_b = H_s(salt_0 || b)` until the rho-uniform
hypergraph peels.  Everything that decides whether peeling succeeds is
combinatorial, so this measurement runs anywhere:

    python experiments/peel_rate.py --trials 300

It reports, per n and alpha = m/n:

    p1      fraction of hypergraphs that peel on the very first salt
    E[b]    mean number of salts needed (capped at 20)
    fail20  fraction that never peel -- an encoding failure, not a timing

Reference point: a random 3-uniform hypergraph on m vertices with n edges
has an empty 2-core with high probability iff n/m < 0.8184, i.e. alpha >
1.222.  alpha = 1.25 sits 2% above that threshold, so p1 is expected to be
below 1 and to rise with n.
"""

import argparse
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

import hashdom  # noqa: E402


class _El(object):
    def __init__(self, value, group):
        self.v = int(value) % group.P
        self.g = group

    def __mul__(self, other):
        return _El(self.v * other.v, self.g)

    def __pow__(self, exponent):
        return _El(pow(self.v, int(exponent), self.g.P), self.g)

    def __eq__(self, other):
        return isinstance(other, _El) and self.v == other.v

    def __hash__(self):
        return hash(self.v)


class StubGroup(object):
    P = (1 << 61) - 1

    def order(self):
        return self.P

    def random(self, kind=None):
        import random as _random

        return _El(_random.randrange(2, self.P), self)

    def init(self, kind, value=1):
        return _El(int(value), self)


def first_peelable(salt0, n, m, rho=3, attempts=20):
    """Return 1-based attempt index that peels, or 0 if none does."""
    from sparse_gokvs import SparseGOKVS

    gokvs = SparseGOKVS(StubGroup(), n, rho=rho, m=m, salt=salt0,
                        max_attempts=attempts)
    attrs = ["p%d" % i for i in range(n)]
    for attempt in range(attempts):
        salt = salt0 if attempt == 0 else hashdom.derive_salt(salt0, attempt)
        gokvs._current_salt = salt
        gokvs._row_cache.clear()
        try:
            gokvs._peel(attrs)
        except RuntimeError:
            continue
        return attempt + 1
    return 0


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=200)
    parser.add_argument("--ns", default="16,32,64,100,200,400,800,1600")
    parser.add_argument("--alpha", type=float, default=1.25)
    args = parser.parse_args(argv)

    ns = [int(x) for x in args.ns.split(",")]
    print("alpha = %.3f   rho = 3   trials = %d" %
          (args.alpha, args.trials))
    print("%6s %7s %7s %7s %7s" % ("n", "m", "p1", "E[b]", "fail20"))
    failures = 0
    for n in ns:
        m = int(math.ceil(args.alpha * n))
        if m <= n:
            m = n + 1
        hits = 0
        total = 0
        zero = 0
        first_try = 0
        for trial in range(args.trials):
            got = first_peelable(trial * 7919 + 13, n, m)
            if got == 0:
                zero += 1
            else:
                hits += 1
                total += got
                if got == 1:
                    first_try += 1
        first_try_rate = first_try / float(args.trials)
        mean_b = (total / float(hits)) if hits else float("nan")
        fail = zero / float(args.trials)
        failures += zero
        print("%6d %7d %7.3f %7.2f %7.3f" %
              (n, m, first_try_rate, mean_b, fail))
    print("\nencoding failures at alpha=%.2f: %d of %d" %
          (args.alpha, failures, args.trials * len(ns)))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
