"""Hinted one-sided decapsulation across policy sizes, same code path as
experiments/run_all.py (decap_hint).  Writes results/decap_hint_sweep.csv."""
import csv
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_all as R  # noqa: E402


def main():
    env = R.load_crypto()
    run_id = "hint-sweep"
    rows = []
    for n_policy in (50, 100, 200, 400, 800):
        inst, pp, msk, sk, ct, kappa, keygen_ms, _ = R._prepare(
            env, n_policy, 10, R.DEFAULT_D, run_id)
        hint = tuple(range(R.DEFAULT_D))
        for rep in range(5):
            rec, det = inst.decap(pp, sk, ct, optimize="precompute",
                                  hint_subset=hint)
            rows.append({
                "n_policy": n_policy,
                "n_attr": 10,
                "d": R.DEFAULT_D,
                "rep": rep,
                "total_ms": det["total_ms"],
                "pairing_ms": det["pairing_ms"],
                "decode_ms": det["decode_ms"],
                "recon_ms": det["recon_ms"],
                "trials": det["trials"],
                "success": rec == kappa,
            })
        med = statistics.median(r["total_ms"] for r in rows[-5:])
        print("|P|=%-4d  median %.2f ms  pairing %.2f  decode %.2f  recon %.2f  ok=%s"
              % (n_policy, med,
                 statistics.median(r["pairing_ms"] for r in rows[-5:]),
                 statistics.median(r["decode_ms"] for r in rows[-5:]),
                 statistics.median(r["recon_ms"] for r in rows[-5:]),
                 all(r["success"] for r in rows[-5:])))
        sys.stdout.flush()
    out = os.path.join(R.REPO, "results", "decap_hint_sweep.csv")
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("wrote", out)


if __name__ == "__main__":
    main()
