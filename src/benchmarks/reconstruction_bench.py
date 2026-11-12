#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Parallel threshold reconstruction benchmark.

Usage:
    python src/benchmarks/reconstruction_bench.py

Runs naive and precompute modes for d in {2,4,6,8} and A in
{5,10,15,20,25,30}, with one round per configuration.
Uses ProcessPoolExecutor for parallelism.
"""

import csv
import os
import random
import time
from itertools import combinations
from concurrent.futures import ProcessPoolExecutor, as_completed

from charm.toolbox.pairinggroup import PairingGroup, GT

from config import CURVE, ROUNDS
from utils import write_csv, print_summary, get_memory_usage_kb, hash_to_nonzero_zr
from silent_share import SilentShare

# ------------------------------------------------------------
# Parameter settings (override defaults in config)
# ------------------------------------------------------------
D_VALUES = [2, 4, 6, 8]
A_VALUES = [5, 10, 15, 20, 25, 30]
MODES = ['naive', 'precompute']
ROUNDS_PER_CONFIG = 1   # Run one round per configuration

# ------------------------------------------------------------
# Combination calculation (compatible with Python 3.6)
# ------------------------------------------------------------
def comb(n, k):
    if k < 0 or k > n:
        return 0
    k = min(k, n - k)
    result = 1
    for i in range(1, k + 1):
        result = result * (n - k + i) // i
    return result


# ------------------------------------------------------------
# Single task (executed in each subprocess)
# ------------------------------------------------------------
def worker_task(task):
    d, A, mode = task
    # Each subprocess initializes independently
    group = PairingGroup(CURVE)
    max_d = max(D_VALUES)
    ss = SilentShare(group, threshold=max_d)

    # Generate attribute list and x values
    attrs = [f"A_{i}" for i in range(A)]
    xs = [int(hash_to_nonzero_zr(group, attr)) for attr in attrs]

    # Construct Z values: first d attributes are points on the correct polynomial, rest are random points
    base = group.random(GT)
    coeffs = [group.random() for _ in range(d)]
    Z = []
    for i in range(A):
        x = xs[i]
        exponent = int(coeffs[-1])
        for j in range(d - 2, -1, -1):
            exponent = (exponent * x + int(coeffs[j])) % int(group.order())
        if i < d:  # First d attributes as correct points
            Z.append(base ** exponent)
        else:
            Z.append(group.random(GT))

    # Precompute ratio_cache (if required by mode)
    ratio_cache = None
    cache_ms = 0.0
    if mode == 'precompute':
        t0 = time.perf_counter()
        ratio_cache = ss.prepare_lagrange_cache(xs)
        cache_ms = (time.perf_counter() - t0) * 1000

    total_comb = comb(A, d)

    results = []
    # Scenarios: best, median, worst, failure
    scenarios = [
        ('best', 0),
        ('median', total_comb // 2),
        ('worst', total_comb - 1),
        ('failure', None)
    ]

    for scenario_name, target_idx in scenarios:
        # For failure scenario, modify Z so that no combination is correct
        Z_use = list(Z)
        if scenario_name == 'failure':
            for i in range(d):
                Z_use[i] = group.random(GT)

        mem_before = get_memory_usage_kb()
        wall_start = time.perf_counter()
        cpu_start = time.process_time()

        trials = 0
        if scenario_name == 'failure':
            # Enumerate all combinations
            for subset in combinations(range(A), d):
                trials += 1
                _ = ss.reconstruct_candidate(
                    subset, Z_use, xs, mode, ratio_cache)
        else:
            # Enumerate up to target_idx
            for idx, subset in enumerate(combinations(range(A), d)):
                trials += 1
                if idx == target_idx:
                    _ = ss.reconstruct_candidate(
                        subset, Z_use, xs, mode, ratio_cache)
                    break

        wall_ms = (time.perf_counter() - wall_start) * 1000
        cpu_ms = (time.process_time() - cpu_start) * 1000
        mem_kb = max(0, get_memory_usage_kb() - mem_before)

        results.append({
            'd': d,
            'A': A,
            'mode': mode,
            'scenario': scenario_name,
            'round': 1,  # Fixed as 1
            'wall_ms': wall_ms,
            'cpu_ms': cpu_ms,
            'mem_kb': mem_kb,
            'trials': trials,
            'cache_ms': cache_ms,
            'total_combinations': total_comb
        })

        # Optional: print progress in subprocess
        print(f"[{mode}] d={d}, A={A}, scenario={scenario_name}, "
              f"trials={trials}, wall={wall_ms:.1f} ms")

    return results


def main():
    tasks = []
    for d in D_VALUES:
        for A in A_VALUES:
            if A < d:
                continue
            for mode in MODES:
                tasks.append((d, A, mode))

    print(f"Total tasks: {len(tasks)}")
    print("Starting parallel execution...")

    all_rows = []
    # Use 12 workers, adjust according to machine core count
    max_workers = 12
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {executor.submit(worker_task, task): task for task in tasks}
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            try:
                result = future.result()
                all_rows.extend(result)
            except Exception as exc:
                print(f"Task {task} generated an exception: {exc}")

    # Write CSV
    out_dir = 'results'
    os.makedirs(out_dir, exist_ok=True)
    fields = ['d', 'A', 'mode', 'scenario', 'round', 'wall_ms', 'cpu_ms',
              'mem_kb', 'trials', 'cache_ms', 'total_combinations']
    write_csv(os.path.join(out_dir, 'reconstruction.csv'), fields, all_rows)
    print(f"\nCSV written to results/reconstruction.csv with {len(all_rows)} rows.")


if __name__ == '__main__':
    main()