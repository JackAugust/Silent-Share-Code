#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""G2 exponentiation microbenchmark.

Usage:
    python src/g2_exp_bench.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from charm.toolbox.pairinggroup import PairingGroup, G2, ZR
from utils import print_summary
from config import CURVE

def benchmark_g2_exp(num_ops=1000, rounds=5):
    """Benchmark single G2 exponentiation by performing num_ops exponentiations."""
    group = PairingGroup(CURVE)

    base = group.random(G2)
    exponents = [group.random(ZR) for _ in range(num_ops)]

    total_times = []
    per_exp_times = []
    for _ in range(rounds):
        acc = group.init(G2, 1)
        t0 = time.perf_counter()
        for e in exponents:
            acc = acc * (base ** e)
        t1 = time.perf_counter()
        elapsed_ms = (t1 - t0) * 1000
        total_times.append(elapsed_ms)
        per_exp_times.append(elapsed_ms / num_ops)

    print(f"\nG2 exponentiation benchmark: {num_ops} ops, {rounds} rounds")
    print_summary("Total time", total_times)
    print_summary("Per exponentiation", per_exp_times)

if __name__ == "__main__":
    for n_ops in [100, 1000, 5000]:
        benchmark_g2_exp(num_ops=n_ops, rounds=5)