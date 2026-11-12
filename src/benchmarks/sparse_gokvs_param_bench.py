#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Sparse GOKVS parameter sensitivity benchmark.

Tests rho in {2,3,4} and m/n ratios from 1.15 to 1.40.
Records encoding success rate, encoding time, decoding time.
Fixed success flag recording bug.
"""

import csv
import os
import time
import math

from charm.toolbox.pairinggroup import PairingGroup, G2

from config import CURVE
from utils import print_summary
from sparse_gokvs import SparseGOKVS


def main():
    group = PairingGroup(CURVE)

    n_values = [200, 300, 400]
    rho_values = [2, 3, 4]
    m_ratios = [1.15, 1.20, 1.25, 1.30, 1.35, 1.40]
    rounds = 20

    results = []

    for n in n_values:
        attrs = [f"A_{i}" for i in range(n)]
        values = [group.random(G2) for _ in range(n)]
        pairs = list(zip(attrs, values))

        for rho in rho_values:
            for ratio in m_ratios:
                m = int(math.ceil(ratio * n))
                success_count = 0
                encode_times = []
                decode_times = []
                round_success = []         

                print(f"\n--- n={n}, rho={rho}, m/n={ratio:.2f} ---")
                for r in range(rounds):
                    gokvs = SparseGOKVS(group, n, rho=rho, m=m, max_attempts=10)
                    t0 = time.perf_counter()
                    success_flag = True
                    try:
                        D = gokvs.encode(pairs)
                        encode_ms = (time.perf_counter() - t0) * 1000
                        encode_times.append(encode_ms)

                        # decode per attribute (average over 10)
                        t0 = time.perf_counter()
                        for attr in attrs[:10]:
                            gokvs.decode(D, attr)
                        decode_ms = (time.perf_counter() - t0) * 1000 / 10
                        decode_times.append(decode_ms)
                    except RuntimeError:
                        success_flag = False
                        encode_times.append(float('nan'))
                        decode_times.append(float('nan'))

                    round_success.append(success_flag)
                    if success_flag:
                        success_count += 1

                success_rate = success_count / rounds
                # Compute mean of successful encodes only
                valid_encode = [x for x in encode_times if not math.isnan(x)]
                valid_decode = [x for x in decode_times if not math.isnan(x)]
                enc_mean = sum(valid_encode) / len(valid_encode) if valid_encode else float('nan')
                dec_mean = sum(valid_decode) / len(valid_decode) if valid_decode else float('nan')

                print(f"success={success_count}/{rounds}  enc_mean={enc_mean:.3f} ms  dec_mean={dec_mean:.5f} ms")

                for r in range(rounds):
                    results.append({
                        'n': n,
                        'rho': rho,
                        'm_ratio': ratio,
                        'm': m,
                        'round': r,
                        'success': 1 if round_success[r] else 0,  
                        'encode_ms': encode_times[r] if r < len(encode_times) else float('nan'),
                        'decode_ms': decode_times[r] if r < len(decode_times) else float('nan')
                    })

    out_dir = 'results'
    os.makedirs(out_dir, exist_ok=True)
    fields = ['n', 'rho', 'm_ratio', 'm', 'round', 'success', 'encode_ms', 'decode_ms']
    with open(os.path.join(out_dir, 'sparse_gokvs_param.csv'), 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in results:
            writer.writerow(row)
    print("\nCSV written to results/sparse_gokvs_param.csv")


if __name__ == '__main__':
    main()