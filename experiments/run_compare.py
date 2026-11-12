#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Collect the points the six-panel comparison figure needs, and nothing else.

The main run (run_all.py) measured the baseline only at n = 5, 10, 30 and
never varied d, which is why the comparison figure was retired.  This script
fills exactly those holes:

  A  fuzzy IB-ME at n in {5,10,30,50,100,200}, d = 5
  B  fuzzy IB-ME at n = 30, d in {2,3,4,5,6,8,10}
  C  Silent-Share at |A| = 30, |P| = 800, same d values, correct-subset hint

Rows use the same schema as run_all.py, so the plotting script can read both
files.  Output goes to results_compare/ by default and never touches the
already-published results/.

    python experiments/run_compare.py
    python experiments/plot_comparison_v4.py
"""

import argparse
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import run_all  # noqa: E402  (reuse env loading and row construction)

SEED = 20261111
D_FIXED = 5
SIZES = [5, 10, 30, 50, 100, 200]
THRESHOLDS = [2, 3, 4, 5, 6, 8, 10]


def fuzzy_rows(env, cache, sizes, thresholds, commit, run_id, skipped):
    """Baseline rows: encryption, decryption, ciphertext and key sizes."""
    import fuzzy_ibme

    rows = []
    for n in sizes:
        try:
            me, mpk, msk = cache.get(n, D_FIXED)[:3]
            result = fuzzy_ibme.benchmark_case(
                me, mpk, msk, n, n, D_FIXED, rounds=3, warmup=1,
                decrypt_mode="hint")
            rows.append(run_all.make_row(
                env, commit, "baseline_enc", "hint", n, D_FIXED, n,
                total_ms=result["enc_ms"], success=True, rep=0,
                run_id=run_id, ct_bytes=result["ct_bytes"],
                sk_bytes=result["dk_bytes"],
                note="fuzzy n=R=%d" % n))
            rows.append(run_all.make_row(
                env, commit, "baseline_dec", "hint", n, D_FIXED, n,
                total_ms=result["dec_ms"], success=True, rep=0,
                run_id=run_id, ct_bytes=result["ct_bytes"],
                sk_bytes=result["dk_bytes"],
                note="fuzzy n=R=%d attempts=%.1f" % (n, result["dec_attempts_mean"])))
            run_all.log("  fuzzy n=%-3d enc=%8.2f dec=%8.2f ct=%6d dk=%7d B"
                        % (n, result["enc_ms"], result["dec_ms"],
                           result["ct_bytes"], result["dk_bytes"]))
        except Exception as exc:
            skipped.append({"mode": "baseline", "n_attr": n,
                            "reason": "%s: %s" % (type(exc).__name__, exc)})
            run_all.log("  skip fuzzy n=%d: %s" % (n, exc))

    for d in thresholds:
        try:
            me, mpk, msk = cache.get(30, d)[:3]
            result = fuzzy_ibme.benchmark_case(
                me, mpk, msk, 30, 30, d, rounds=3, warmup=1,
                decrypt_mode="hint")
            rows.append(run_all.make_row(
                env, commit, "baseline_dec", "hint", 30, d, 30,
                total_ms=result["dec_ms"], success=True, rep=0,
                run_id=run_id, ct_bytes=result["ct_bytes"],
                sk_bytes=result["dk_bytes"],
                note="fuzzy n=30 d=%d" % d))
            run_all.log("  fuzzy d=%-2d dec=%8.2f ms" % (d, result["dec_ms"]))
        except Exception as exc:
            skipped.append({"mode": "baseline", "d": d,
                            "reason": "%s: %s" % (type(exc).__name__, exc)})
            run_all.log("  skip fuzzy d=%d: %s" % (d, exc))
    return rows


def silent_share_threshold_rows(env, thresholds, commit, run_id, skipped,
                                n_attr=30, n_policy=800):
    """Our decapsulation under the correct-subset hint, as a function of d."""
    rows = []
    for d in thresholds:
        try:
            instance, pp, msk, sk, ct, kappa, _, _ = run_all._prepare(
                env, n_policy, n_attr, d, run_id)
            hint = tuple(range(d))
            recovered, details = instance.decap(
                pp, sk, ct, optimize="precompute", hint_subset=hint)
            rows.append(run_all.make_row(
                env, commit, "decap", "hint", n_attr, d, n_policy,
                total_ms=details["total_ms"],
                pairing_ms=details["pairing_ms"],
                gokvs_decode_ms=details["decode_ms"],
                recon_ms=details["recon_ms"], trials=details["trials"],
                success=(recovered == kappa), rep=0, run_id=run_id,
                ct_bytes=run_all.serialized_size(env["group"], [ct["D1"], ct["D2"]]),
                sk_bytes=run_all.serialized_size(env["group"], [sk.D1, sk.D2]),
                note="|A|=30 |P|=800 d=%d" % d))
            run_all.log("  ours  d=%-2d dec=%8.2f ms (%d pairings)"
                        % (d, details["total_ms"], 2 * n_attr))
        except Exception as exc:
            skipped.append({"mode": "decap", "d": d,
                            "reason": "%s: %s" % (type(exc).__name__, exc)})
            run_all.log("  skip ours d=%d: %s" % (d, exc))
    return rows


def main(argv):
    parser = argparse.ArgumentParser(
        description="Fill the comparison-figure gaps.")
    parser.add_argument("--out", default=os.path.join(run_all.REPO,
                                                      "results_compare"))
    parser.add_argument("--sizes", default=",".join(str(s) for s in SIZES))
    parser.add_argument("--thresholds",
                        default=",".join(str(t) for t in THRESHOLDS))
    args = parser.parse_args(argv)

    random.seed(SEED)
    os.makedirs(args.out, exist_ok=True)
    env = run_all.load_crypto()
    commit = env["stats"].git_commit(run_all.REPO)
    run_id = time.strftime("%Y%m%d-%H%M%S")
    sizes = [int(x) for x in args.sizes.split(",")]
    thresholds = [int(x) for x in args.thresholds.split(",")]

    manifest = run_all.machine_info()
    manifest.update({"commit": commit, "sizes": sizes,
                     "thresholds": thresholds,
                     "micro": run_all.micro_benchmark(env)})
    run_all.log("commit %s  curve %s" % (commit, run_all.CURVE))
    run_all.log("pairing %.3f ms" % manifest["micro"]["pairing_ms_min"])

    rows, skipped = [], []

    run_all.log("\n[A] fuzzy IB-ME versus policy size (d=%d)" % D_FIXED)
    import fuzzy_ibme
    cache = fuzzy_ibme.ContextCache(curve=run_all.CURVE, d=D_FIXED)
    rows += fuzzy_rows(env, cache, sizes, thresholds, commit, run_id, skipped)

    run_all.log("\n[B] Silent-Share versus threshold (|A|=30, |P|=800)")
    rows += silent_share_threshold_rows(env, thresholds, commit, run_id,
                                        skipped)

    stats = env["stats"]
    raw = os.path.join(args.out, "raw_all.csv")
    stats.write_csv(raw, rows, stats.RAW_COLUMNS + run_all.EXTRA_COLUMNS)
    stats.write_csv(os.path.join(args.out, "summary.csv"),
                    stats.summarize(rows),
                    stats.SUMMARY_COLUMNS + run_all.EXTRA_COLUMNS[:4])
    stats.write_csv(os.path.join(args.out, "skipped.csv"), skipped,
                    ["mode", "d", "n_attr", "reason"])
    import json
    with open(os.path.join(args.out, "manifest.json"), "w",
              encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)

    run_all.log("\n%d rows, %d skipped -> %s" % (len(rows), len(skipped),
                                                 args.out))
    run_all.log("next: python experiments/plot_comparison_v4.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
