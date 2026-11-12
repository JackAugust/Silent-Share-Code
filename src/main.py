#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Main entry point to run all benchmarks."""

import argparse

def main():
    parser = argparse.ArgumentParser(description="Silent-Share benchmarks")
    parser.add_argument('--bench',
                        choices=['gokvs', 'sparse_gokvs', 'sparse_param',
                                 'one_sided', 'reconstruction', 'bilateral',
                                 'all'],
                        default='all',
                        help='Which benchmark to run')
    args = parser.parse_args()

    if args.bench in ['gokvs', 'all']:
        print("\n########## GOKVS Benchmark (dense + scalar) ##########")
        from benchmarks.gokvs_bench import main as gokvs_main
        gokvs_main()

    if args.bench in ['sparse_gokvs', 'all']:
        print("\n########## Sparse GOKVS Benchmark ##########")
        from benchmarks.sparse_gokvs_bench import main as sparse_gokvs_main
        sparse_gokvs_main()

    if args.bench in ['sparse_param', 'all']:
        print("\n########## Sparse GOKVS Parameter Sensitivity ##########")
        from benchmarks.sparse_gokvs_param_bench import main as sparse_param_main
        sparse_param_main()

    if args.bench in ['one_sided', 'all']:
        print("\n########## One-sided Benchmark ##########")
        from benchmarks.one_sided_bench import main as one_sided_main
        one_sided_main()

    if args.bench in ['reconstruction', 'all']:
        print("\n########## Reconstruction Benchmark ##########")
        from benchmarks.reconstruction_bench import main as recon_main
        recon_main()

    if args.bench in ['bilateral', 'all']:
        print("\n########## Bilateral Benchmark ##########")
        from benchmarks.bilateral_bench import main as bilateral_main
        bilateral_main()

if __name__ == '__main__':
    main()