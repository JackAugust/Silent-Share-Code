#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""GOKVS vs Scalar OKVS microbenchmark with CPU/memory/throughput."""

import csv
import os
import secrets
import time

from charm.toolbox.pairinggroup import PairingGroup, G2

from config import CURVE, POLICY_SIZES, ROUNDS, PARALLEL_WORKERS
from utils import write_csv, print_summary, measure_operation, get_memory_usage_kb
from okvs import LinearOKVS, GOKVS
ROUNDS = 2

def run_scalar(n, rounds=ROUNDS):
    group = PairingGroup(CURVE)
    order = int(group.order())
    m = n + 1
    keys = [f"A_{i}" for i in range(n)]

    encode_wall, encode_cpu, encode_mem = [], [], []
    decode_wall, decode_cpu, decode_mem = [], [], []

    for _ in range(rounds):
        values = [secrets.randbelow(order) for _ in range(n)]
        okvs = LinearOKVS(m, order)

        # Encode measurement
        result, wall_ms, cpu_ms, mem_kb = measure_operation(
            okvs.encode, list(zip(keys, values))
        )
        encode_wall.append(wall_ms)
        encode_cpu.append(cpu_ms)
        encode_mem.append(mem_kb)

        # Decode measurement (average 10 decodes)
        D = result
        start_wall = time.perf_counter()
        start_cpu = time.process_time()
        for key in keys[:10]:
            okvs.decode(D, key)
        wall_ms = (time.perf_counter() - start_wall) * 1000 / 10
        cpu_ms = (time.process_time() - start_cpu) * 1000 / 10
        decode_wall.append(wall_ms)
        decode_cpu.append(cpu_ms)
        decode_mem.append(0)

    encode_throughput = [n / (t / 1000) for t in encode_wall]
    decode_throughput = [1 / (t / 1000) for t in decode_wall]

    return {
        'n': n,
        'encode_wall': encode_wall,
        'encode_cpu': encode_cpu,
        'encode_mem': encode_mem,
        'encode_throughput': encode_throughput,
        'decode_wall': decode_wall,
        'decode_cpu': decode_cpu,
        'decode_mem': decode_mem,
        'decode_throughput': decode_throughput
    }


def run_gokvs(n, workers=1, rounds=ROUNDS):
    group = PairingGroup(CURVE)
    keys = [f"A_{i}" for i in range(n)]
    gokvs = GOKVS.from_attributes(group, keys)  

    encode_wall, encode_cpu, encode_mem = [], [], []
    decode_wall, decode_cpu, decode_mem = [], [], []

    for _ in range(rounds):
        values = [group.random(G2) for _ in range(n)]
        pairs = list(zip(keys, values))

        if workers == 1:
            result, wall_ms, cpu_ms, mem_kb = measure_operation(
                gokvs.encode, pairs
            )
            D = result  
        else:
            mem_before = get_memory_usage_kb()
            start_wall = time.perf_counter()
            start_cpu = time.process_time()
            try:
                D = gokvs.encode_parallel(pairs, workers=workers)
            except Exception:
                start_wall = time.perf_counter()
                start_cpu = time.process_time()
                D = gokvs.encode(pairs)
            wall_ms = (time.perf_counter() - start_wall) * 1000
            cpu_ms = (time.process_time() - start_cpu) * 1000
            mem_kb = max(0, get_memory_usage_kb() - mem_before)

        encode_wall.append(wall_ms)
        encode_cpu.append(cpu_ms)
        encode_mem.append(mem_kb)

        start_wall = time.perf_counter()
        start_cpu = time.process_time()
        for key in keys[:10]:
            gokvs.decode(D, key)
        wall_ms = (time.perf_counter() - start_wall) * 1000 / 10
        cpu_ms = (time.process_time() - start_cpu) * 1000 / 10
        decode_wall.append(wall_ms)
        decode_cpu.append(cpu_ms)
        decode_mem.append(0)

    encode_throughput = [n / (t / 1000) for t in encode_wall]
    decode_throughput = [1 / (t / 1000) for t in decode_wall]

    return {
        'n': n,
        'workers': workers,
        'encode_wall': encode_wall,
        'encode_cpu': encode_cpu,
        'encode_mem': encode_mem,
        'encode_throughput': encode_throughput,
        'decode_wall': decode_wall,
        'decode_cpu': decode_cpu,
        'decode_mem': decode_mem,
        'decode_throughput': decode_throughput
    }


def main():
    scalar_rows = []
    gokvs_rows = []

    for n in POLICY_SIZES:
        print(f"\n--- n = {n} ---")
        # Scalar
        s = run_scalar(n)
        for r in range(ROUNDS):
            scalar_rows.append({
                'n': n,
                'round': r,
                'encode_wall_ms': s['encode_wall'][r],
                'encode_cpu_ms': s['encode_cpu'][r],
                'encode_mem_kb': s['encode_mem'][r],
                'encode_throughput_pairs_per_sec': s['encode_throughput'][r],
                'decode_wall_ms': s['decode_wall'][r],
                'decode_cpu_ms': s['decode_cpu'][r],
                'decode_mem_kb': s['decode_mem'][r],
                'decode_throughput_per_sec': s['decode_throughput'][r],
            })
        print("Scalar OKVS:")
        print_summary("  encode wall", s['encode_wall'])
        print_summary("  encode cpu", s['encode_cpu'])
        print_summary("  encode mem", s['encode_mem'], unit='KB')
        print_summary("  encode throughput", s['encode_throughput'], unit='pairs/s')
        print_summary("  decode wall", s['decode_wall'])
        print_summary("  decode cpu", s['decode_cpu'])
        print_summary("  decode throughput", s['decode_throughput'], unit='ops/s')

        # GOKVS with different worker counts:
        for workers in [1, PARALLEL_WORKERS]:
            g = run_gokvs(n, workers=workers)
            for r in range(ROUNDS):
                gokvs_rows.append({
                    'n': n,
                    'round': r,
                    'workers': workers,
                    'encode_wall_ms': g['encode_wall'][r],
                    'encode_cpu_ms': g['encode_cpu'][r],
                    'encode_mem_kb': g['encode_mem'][r],
                    'encode_throughput_pairs_per_sec': g['encode_throughput'][r],
                    'decode_wall_ms': g['decode_wall'][r],
                    'decode_cpu_ms': g['decode_cpu'][r],
                    'decode_mem_kb': g['decode_mem'][r],
                    'decode_throughput_per_sec': g['decode_throughput'][r],
                })
            print(f"GOKVS (workers={workers}):")
            print_summary("  encode wall", g['encode_wall'])
            print_summary("  encode cpu", g['encode_cpu'])
            print_summary("  encode mem", g['encode_mem'], unit='KB')
            print_summary("  encode throughput", g['encode_throughput'], unit='pairs/s')
            print_summary("  decode wall", g['decode_wall'])
            print_summary("  decode cpu", g['decode_cpu'])
            print_summary("  decode throughput", g['decode_throughput'], unit='ops/s')

    out_dir = 'results'
    os.makedirs(out_dir, exist_ok=True)
    scalar_fields = ['n','round','encode_wall_ms','encode_cpu_ms','encode_mem_kb',
                     'encode_throughput_pairs_per_sec','decode_wall_ms','decode_cpu_ms',
                     'decode_mem_kb','decode_throughput_per_sec']
    gokvs_fields = ['n','round','workers','encode_wall_ms','encode_cpu_ms','encode_mem_kb',
                    'encode_throughput_pairs_per_sec','decode_wall_ms','decode_cpu_ms',
                    'decode_mem_kb','decode_throughput_per_sec']
    write_csv(os.path.join(out_dir, 'gokvs_scalar.csv'), scalar_fields, scalar_rows)
    write_csv(os.path.join(out_dir, 'gokvs_group.csv'), gokvs_fields, gokvs_rows)
    print("\nCSV files written to results/")


if __name__ == '__main__':
    main()