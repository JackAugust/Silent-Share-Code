#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Bilateral Silent-Share protocol benchmark with communication overhead."""

import csv
import os
import time

from charm.toolbox.pairinggroup import PairingGroup

from config import CURVE, DEFAULT_D, ROUNDS, BILATERAL_POLICY_SIZES
from utils import write_csv, print_summary, measure_operation, get_memory_usage_kb
from silent_share import SilentShare


def compute_ct_size_bytes(group, ct):
    """Compute the serialized byte size of the ciphertext (excluding metadata)."""
    size = len(ct['E0']) + len(ct['C'])
    for d in ct['D1']:
        size += len(group.serialize(d))
    for d in ct['D2']:
        size += len(group.serialize(d))
    return size


def main():
    group = PairingGroup(CURVE)
    d = DEFAULT_D
    owner_policy_sizes = BILATERAL_POLICY_SIZES
    requester_policy_sizes = BILATERAL_POLICY_SIZES
    owner_attr_size = 10
    requester_attr_size = 10
    rows = []

    # AES-GCM related constants (used for estimating communication overhead)
    AESGCM_TAG_BYTES = 16
    NONCE_BYTES = 12
    KEY_BYTES = 32
    TAU_SIZE_BYTES = KEY_BYTES + AESGCM_TAG_BYTES  # 32 + 16 = 48

    for nO in owner_policy_sizes:
        for nR in requester_policy_sizes:
            print(f"\n--- nO={nO}, nR={nR} ---")
            total_wall, total_cpu, total_mem = [], [], []
            encap_R_wall, encap_O_wall = [], []
            decap_R_wall, decap_O_wall = [], []
            ct_R_sizes = []      # new
            ct_O_sizes = []      # new
            total_comm = []      # new

            for r in range(ROUNDS):
                universe = set()
                owner_policy = [f"PO_{i}" for i in range(nO)]
                requester_policy = [f"PR_{i}" for i in range(nR)]
                owner_attrs = [f"PR_{i}" for i in range(d)] + \
                              [f"AO_{i}" for i in range(owner_attr_size - d)]
                requester_attrs = [f"PO_{i}" for i in range(d)] + \
                                  [f"AR_{i}" for i in range(requester_attr_size - d)]
                universe.update(owner_policy)
                universe.update(requester_policy)
                universe.update(owner_attrs)
                universe.update(requester_attrs)

                ss = SilentShare(group, threshold=d)
                mem_before = get_memory_usage_kb()
                wall_start = time.perf_counter()
                cpu_start = time.process_time()

                pp, msk, _ = ss.setup(list(universe))
                skR, _ = ss.keygen(pp, msk, "requester", requester_attrs)
                skO, _ = ss.keygen(pp, msk, "owner", owner_attrs)

                # Record individual stages
                t0 = time.perf_counter()
                ctR, kR, eR = ss.encap(pp, msk, requester_policy)
                encap_R_wall.append((time.perf_counter() - t0) * 1000)
                t0 = time.perf_counter()
                ctO, kO, eO = ss.encap(pp, msk, owner_policy)
                encap_O_wall.append((time.perf_counter() - t0) * 1000)

                # Compute ciphertext sizes
                size_R = compute_ct_size_bytes(group, ctR)
                size_O = compute_ct_size_bytes(group, ctO)
                ct_R_sizes.append(size_R)
                ct_O_sizes.append(size_O)
                # Total communication: requester sends CT_R, owner replies CT_O + τ + nonce
                comm_bytes = size_R + size_O + TAU_SIZE_BYTES + NONCE_BYTES
                total_comm.append(comm_bytes)

                t0 = time.perf_counter()
                kR2, dR = ss.decap(pp, skO, ctR, optimize='precompute')
                decap_O_wall.append((time.perf_counter() - t0) * 1000)  # Owner decrypts requester capsule
                t0 = time.perf_counter()
                kO2, dO = ss.decap(pp, skR, ctO, optimize='precompute')
                decap_R_wall.append((time.perf_counter() - t0) * 1000)  # Requester decrypts owner capsule

                wall_ms = (time.perf_counter() - wall_start) * 1000
                cpu_ms = (time.process_time() - cpu_start) * 1000
                mem_kb = max(0, get_memory_usage_kb() - mem_before)

                total_wall.append(wall_ms)
                total_cpu.append(cpu_ms)
                total_mem.append(mem_kb)

                rows.append({
                    'nO': nO, 'nR': nR, 'round': r,
                    'total_wall_ms': wall_ms,
                    'total_cpu_ms': cpu_ms,
                    'total_mem_kb': mem_kb,
                    'encap_R_wall_ms': encap_R_wall[-1],
                    'encap_O_wall_ms': encap_O_wall[-1],
                    'decap_R_wall_ms': decap_R_wall[-1],
                    'decap_O_wall_ms': decap_O_wall[-1],
                    'encap_R_gokvs_ms': eR.get('gokvs_total_ms', 0.0),
                    'encap_O_gokvs_ms': eO.get('gokvs_total_ms', 0.0),
                    'decap_R_decode_ms': dO.get('decode_ms', 0.0),    # renamed for clarity
                    'decap_O_decode_ms': dR.get('decode_ms', 0.0),    # renamed for clarity
                    'ct_R_size_bytes': size_R,        # new
                    'ct_O_size_bytes': size_O,        # new
                    'total_comm_bytes': comm_bytes    # new
                })

            print_summary("Total wall", total_wall)
            print_summary("Total cpu", total_cpu)
            print_summary("Total mem", total_mem, unit='KB')
            print_summary("Encap R", encap_R_wall)
            print_summary("Encap O", encap_O_wall)
            print_summary("Decap R", decap_R_wall)
            print_summary("Decap O", decap_O_wall)
            print_summary("CT_R size", ct_R_sizes, unit='B')
            print_summary("CT_O size", ct_O_sizes, unit='B')
            print_summary("Total communication", total_comm, unit='B')

    out_dir = 'results'
    os.makedirs(out_dir, exist_ok=True)
    fields = ['nO','nR','round','total_wall_ms','total_cpu_ms','total_mem_kb',
              'encap_R_wall_ms','encap_O_wall_ms','decap_R_wall_ms','decap_O_wall_ms',
              'encap_R_gokvs_ms','encap_O_gokvs_ms','decap_R_decode_ms','decap_O_decode_ms',
              'ct_R_size_bytes','ct_O_size_bytes','total_comm_bytes']
    write_csv(os.path.join(out_dir, 'bilateral.csv'), fields, rows)
    print("\nCSV written to results/bilateral.csv")


if __name__ == '__main__':
    main()