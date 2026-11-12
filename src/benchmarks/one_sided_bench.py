#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""One-sided Silent-Share benchmark with CPU/memory/throughput and ciphertext size."""

import csv
import os
import time

from charm.toolbox.pairinggroup import PairingGroup

from config import CURVE, POLICY_SIZES, ATTR_SIZES, DEFAULT_D, ROUNDS
from utils import write_csv, print_summary, measure_operation, get_memory_usage_kb
from silent_share import SilentShare


def generate_scenario(n_policy, n_request, overlap):
    policy = [f"P_{i}" for i in range(n_policy)]
    matching = policy[:overlap]
    requester_extra = [f"R_{i}" for i in range(n_request - overlap)]
    requester = matching + requester_extra
    universe = list(set(policy + requester))
    return universe, policy, requester


def compute_ct_size_bytes(group, ct):
    size = len(ct['E0']) + len(ct['C'])
    for d in ct['D1']:
        size += len(group.serialize(d))
    for d in ct['D2']:
        size += len(group.serialize(d))
    return size


def main():
    group = PairingGroup(CURVE)
    d = DEFAULT_D
    results = []

    for A in ATTR_SIZES:
        if A < d:
            continue
        for n in POLICY_SIZES:
            print(f"\n--- A={A}, n={n}, d={d} ---")
            setup_wall, setup_cpu, setup_mem = [], [], []
            keygen_wall, keygen_cpu, keygen_mem = [], [], []
            enc_wall, enc_cpu, enc_mem = [], [], []
            enc_throughput = []                     # pairs/s
            enc_ops_throughput = []                 
            decode_wall, decode_cpu, decode_mem = [], [], []
            dec_ops_throughput = []                 
            pairing_wall, recon_wall = [], []
            total_dec_wall = []
            ct_sizes = []                           
            trials_list, success_count = [], 0

            for r in range(ROUNDS):
                universe, policy, attrs = generate_scenario(n, A, d)
                ss = SilentShare(group, threshold=d)

                # Setup
                res, wall, cpu, mem = measure_operation(ss.setup, universe)
                pp, msk, _ = res
                setup_wall.append(wall)
                setup_cpu.append(cpu)
                setup_mem.append(mem)

                # KeyGen
                res, wall, cpu, mem = measure_operation(ss.keygen, pp, msk, "requester", attrs)
                sk, _ = res
                keygen_wall.append(wall)
                keygen_cpu.append(cpu)
                keygen_mem.append(mem)

                # Encap
                res, wall, cpu, mem = measure_operation(ss.encap, pp, msk, policy)
                ct, kappa, enc_details = res
                enc_wall.append(wall)
                enc_cpu.append(cpu)
                enc_mem.append(mem)
                enc_throughput.append(n / (wall / 1000))          # pairs per sec
                enc_ops_throughput.append(1000 / wall)            # ops per sec

                ct_size_bytes = compute_ct_size_bytes(group, ct)
                ct_sizes.append(ct_size_bytes)

                # Decap
                res, wall, cpu, mem = measure_operation(ss.decap, pp, sk, ct, optimize='precompute')
                rec_kappa, dec_details = res
                decode_wall.append(wall)
                decode_cpu.append(cpu)
                decode_mem.append(mem)
                dec_ops_throughput.append(1000 / wall)            # ops per sec
                pairing_wall.append(dec_details['pairing_ms'])
                recon_wall.append(dec_details['recon_ms'])
                total_dec_wall.append(dec_details['total_ms'])
                trials_list.append(dec_details['trials'])
                if rec_kappa == kappa:
                    success_count += 1

                gokvs_d1 = enc_details.get('gokvs_d1_ms', 0.0)
                gokvs_d2 = enc_details.get('gokvs_d2_ms', 0.0)
                gokvs_total = enc_details.get('gokvs_total_ms', gokvs_d1 + gokvs_d2)

                results.append({
                    'n': n, 'A': A, 'd': d, 'round': r,
                    'setup_wall_ms': setup_wall[-1],
                    'setup_cpu_ms': setup_cpu[-1],
                    'setup_mem_kb': setup_mem[-1],
                    'keygen_wall_ms': keygen_wall[-1],
                    'keygen_cpu_ms': keygen_cpu[-1],
                    'keygen_mem_kb': keygen_mem[-1],
                    'encap_wall_ms': enc_wall[-1],
                    'encap_cpu_ms': enc_cpu[-1],
                    'encap_mem_kb': enc_mem[-1],
                    'encap_throughput_pairs_per_sec': enc_throughput[-1],
                    'encap_throughput_ops_per_sec': enc_ops_throughput[-1],      
                    'gokvs_d1_ms': gokvs_d1,
                    'gokvs_d2_ms': gokvs_d2,
                    'gokvs_total_ms': gokvs_total,
                    'ct_size_bytes': ct_size_bytes,                              
                    'decode_wall_ms': decode_wall[-1],
                    'decode_cpu_ms': decode_cpu[-1],
                    'decode_mem_kb': decode_mem[-1],
                    'decap_throughput_ops_per_sec': dec_ops_throughput[-1],      
                    'pairing_ms': dec_details['pairing_ms'],
                    'recon_ms': dec_details['recon_ms'],
                    'total_decap_wall_ms': dec_details['total_ms'],
                    'trials': dec_details['trials'],
                    'success': rec_kappa == kappa
                })

            # Print summaries (as before)
            print_summary("Setup wall", setup_wall)
            print_summary("Setup cpu", setup_cpu)
            print_summary("Setup mem", setup_mem, unit='KB')
            print_summary("KeyGen wall", keygen_wall)
            print_summary("KeyGen cpu", keygen_cpu)
            print_summary("KeyGen mem", keygen_mem, unit='KB')
            print_summary("Encap wall", enc_wall)
            print_summary("Encap cpu", enc_cpu)
            print_summary("Encap mem", enc_mem, unit='KB')
            print_summary("Encap throughput pairs/s", enc_throughput)
            print_summary("Encap throughput ops/s", enc_ops_throughput)
            print_summary("CT size bytes", ct_sizes, unit='B')
            print_summary("Decode wall", decode_wall)
            print_summary("Decode cpu", decode_cpu)
            print_summary("Decode mem", decode_mem, unit='KB')
            print_summary("Decap throughput ops/s", dec_ops_throughput)
            print_summary("Pairing", pairing_wall)
            print_summary("Recon", recon_wall)
            print_summary("Total decap wall", total_dec_wall)
            print(f"Success rate: {success_count}/{ROUNDS}")
            print(f"Avg trials: {sum(trials_list)/len(trials_list):.1f}")

    out_dir = 'results'
    os.makedirs(out_dir, exist_ok=True)
    fields = ['n','A','d','round',
              'setup_wall_ms','setup_cpu_ms','setup_mem_kb',
              'keygen_wall_ms','keygen_cpu_ms','keygen_mem_kb',
              'encap_wall_ms','encap_cpu_ms','encap_mem_kb',
              'encap_throughput_pairs_per_sec','encap_throughput_ops_per_sec',
              'gokvs_d1_ms','gokvs_d2_ms','gokvs_total_ms',
              'ct_size_bytes',
              'decode_wall_ms','decode_cpu_ms','decode_mem_kb',
              'decap_throughput_ops_per_sec',
              'pairing_ms','recon_ms','total_decap_wall_ms','trials','success']
    write_csv(os.path.join(out_dir, 'one_sided.csv'), fields, results)
    print("\nCSV written to results/one_sided.csv")


if __name__ == '__main__':
    main()