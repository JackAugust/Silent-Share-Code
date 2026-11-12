#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Measure the far side of the 2|A| = 13d crossover.

    python experiments/run_crossover.py

Silent-Share's decapsulation pays 2|A| pairings, fuzzy IB-ME pays 13d, so the
two are equal at |A| = 6.5d = 32.5 for d = 5.  The main run stops at |A| = 30,
i.e. just below that point; this script measures above it (|A| in
{40, 50, 60, 80, 100} at |P| = 800), so the crossing can be plotted instead of
argued.  Rows go to results_crossover/ and never touch results/.
"""
import argparse
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_all  # noqa: E402

ATTRS = (40, 50, 60, 80, 100)
N_POLICY = 800
D_FIXED = 5
REPS = 3
SEED = 20260112


def rows_for(env, attrs, commit, run_id, skipped):
    rows = []
    for n_attr in attrs:
        for rep in range(REPS):
            try:
                instance, pp, msk, sk, ct, kappa, _, _ = run_all._prepare(
                    env, N_POLICY, n_attr, D_FIXED, run_id)
                recovered, details = instance.decap(
                    pp, sk, ct, optimize="precompute",
                    hint_subset=tuple(range(D_FIXED)))
                rows.append(run_all.make_row(
                    env, commit, "decap", "hint", n_attr, D_FIXED, N_POLICY,
                    total_ms=details["total_ms"],
                    pairing_ms=details["pairing_ms"],
                    gokvs_decode_ms=details["decode_ms"],
                    recon_ms=details["recon_ms"], trials=details["trials"],
                    success=(recovered == kappa), rep=rep, run_id=run_id,
                    ct_bytes=run_all.serialized_size(
                        env["group"], [ct["D1"], ct["D2"]]),
                    sk_bytes=run_all.serialized_size(
                        env["group"], [sk.D1, sk.D2]),
                    note="|A|=%d |P|=%d d=%d" % (n_attr, N_POLICY, D_FIXED)))
                run_all.log("  |A|=%-3d dec=%8.2f ms" %
                            (n_attr, details["total_ms"]))
            except Exception as exc:  # keep going, record why
                skipped.append({"mode": "decap", "d": D_FIXED,
                                "n_attr": n_attr,
                                "reason": "%s: %s" % (type(exc).__name__, exc)})
                run_all.log("  skip |A|=%d: %s" % (n_attr, exc))
    return rows


def main(argv):
    parser = argparse.ArgumentParser(
        description="Extend decapsulation past |A| = 6.5d.")
    parser.add_argument("--out", default=os.path.join(run_all.REPO,
                                                      "results_crossover"))
    parser.add_argument("--attrs", default=",".join(str(a) for a in ATTRS))
    args = parser.parse_args(argv)

    random.seed(SEED)
    os.makedirs(args.out, exist_ok=True)
    env = run_all.load_crypto()
    commit = env["stats"].git_commit(run_all.REPO)
    run_id = time.strftime("%Y%m%d-%H%M%S")
    attrs = [int(x) for x in args.attrs.split(",")]

    manifest = run_all.machine_info()
    manifest.update({"commit": commit, "attrs": attrs, "n_policy": N_POLICY,
                     "d": D_FIXED, "reps": REPS})
    run_all.log("commit %s  curve %s" % (commit, run_all.CURVE))

    skipped = []
    rows = rows_for(env, attrs, commit, run_id, skipped)

    stats = env["stats"]
    stats.write_csv(os.path.join(args.out, "raw_all.csv"), rows,
                    stats.RAW_COLUMNS + run_all.EXTRA_COLUMNS)
    stats.write_csv(os.path.join(args.out, "skipped.csv"), skipped,
                    ["mode", "d", "n_attr", "reason"])
    with open(os.path.join(args.out, "manifest.json"), "w",
              encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
    run_all.log("\n%d rows, %d skipped -> %s" % (len(rows), len(skipped),
                                                 args.out))
    run_all.log("next: python experiments/plot_comparison.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
