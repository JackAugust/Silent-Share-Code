#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Benchmark for Sparse GOKVS.

Uses rho=3, m = ceil(1.25 * n) to ensure peeling success with high
probability. Adjust parameters below if needed.
"""

import os
import sys
import time
import math

from charm.toolbox.pairinggroup import PairingGroup, G2

from utils import print_summary
from config import CURVE,POLICY_SIZES
from sparse_gokvs import SparseGOKVS


def main():
    group = PairingGroup(CURVE)

    policy_sizes = POLICY_SIZES
    rounds = 2

    encode_times = {}
    decode_times = {}

    for n in policy_sizes:
        attrs = ["A_%d" % i for i in range(n)]
        values = [group.random(G2) for _ in range(n)]
        pairs = list(zip(attrs, values))

        encode_list = []
        decode_list = []

        m = int(math.ceil(1.25 * n))

        for r in range(rounds):
            gokvs = SparseGOKVS(group, n, rho=3, m=m, max_attempts=20)

            t0 = time.perf_counter()
            D = gokvs.encode(pairs)
            t1 = time.perf_counter()
            encode_ms = (t1 - t0) * 1000
            encode_list.append(encode_ms)

            correct = True
            for attr, expected in zip(attrs[:10], values[:10]):
                decoded = gokvs.decode(D, attr)
                if decoded != expected:
                    correct = False
                    print("Correctness FAILED at n=%d, round=%d, attr=%s" % (n, r, attr))
                    break

            t0 = time.perf_counter()
            for attr in attrs[:10]:
                gokvs.decode(D, attr)
            t1 = time.perf_counter()
            decode_ms_per_attr = (t1 - t0) * 1000 / 10
            decode_list.append(decode_ms_per_attr)

        encode_times[n] = encode_list
        decode_times[n] = decode_list

        print("\n--- n = %d ---" % n)
        print("Encode:")
        print_summary("  wall", encode_list)
        print("Decode (per attribute):")
        print_summary("  wall", decode_list)

    import csv
    out_dir = 'results'
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'sparse_gokvs.csv'), 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['n', 'round', 'encode_ms', 'decode_ms'])
        for n in policy_sizes:
            for r in range(rounds):
                writer.writerow([n, r, encode_times[n][r], decode_times[n][r]])
    print("\nCSV written to results/sparse_gokvs.csv")


if __name__ == '__main__':
    main()