# -*- coding: utf-8 -*-
"""Check the numbers quoted in SP.V34.tex against the result files.

Every claim is paired with the file and column it comes from, so the check
fails loudly if the CSVs are regenerated and the paper is not updated.
Run:  python experiments/check_paper_numbers.py
"""
import csv
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "results")
CMP = os.path.join(ROOT, "results_compare")

FAILS = []


def load(path):
    with open(path, newline="", encoding="utf-8") as h:
        return list(csv.DictReader(h))


def med(rs, col):
    vals = [float(r[col]) for r in rs if r.get(col) not in (None, "")]
    return statistics.median(vals) if vals else None


def check(name, paper, computed, tol, unit=""):
    if computed is None:
        FAILS.append((name, paper, None))
        return
    ok = abs(paper - computed) <= tol
    if not ok:
        FAILS.append((name, paper, computed))
    print("  %-58s paper %8.3f%s  data %8.3f%s  %s"
          % (name, paper, unit, computed, unit, "ok" if ok else "MISMATCH"))


# ---------------------------------------------------------------- decapsulation
print("== decapsulation with hint, |A|=10, d=5 (results/decap_hint_sweep.csv) ==")
hs = load(os.path.join(RES, "decap_hint_sweep.csv"))
by_p = {}
for r in hs:
    by_p.setdefault(int(float(r["n_policy"])), []).append(r)
tot = {p: med(by_p[p], "total_ms") for p in sorted(by_p)}
rec = {p: med(by_p[p], "recon_ms") for p in sorted(by_p)}
pair = {p: med(by_p[p], "pairing_ms") for p in sorted(by_p)}
check("total, |P|=100 (ms)", 360.1, tot[100], 0.3)
check("total, |P|=400 (ms)", 360.8, tot[400], 0.3)
check("reconstruction (ms)", 17.5, statistics.median(list(rec.values())), 0.3)
spread = 100 * (tot[800] - tot[50]) / tot[50]
check("sweep |P|=50..800 spread (%)", 0.7, spread, 0.15)
share_hi = max(100 * pair[p] / tot[p] for p in tot)
check("pairing share, high (%)", 93.0, share_hi, 0.5)

print("== decapsulation at |A|=5,10,15,20,30 (results/summary.csv, per salt trial) ==")
sm = load(os.path.join(RES, "summary.csv"))


def decap_total(a, p):
    rs = [r for r in sm if r["mode"] == "decap" and int(float(r["n_attr"])) == a
          and int(float(r["n_policy"])) == p]
    if not rs:
        return None
    r = rs[0]
    trials = float(r["trials_mean"]) if r["trials_mean"] else 1.0
    return float(r["p50_ms"]) / trials


for a, p, paper in ((5, 100, 187.4), (10, 100, 362.7), (15, 400, 541.9),
                    (20, 800, 722.0), (30, 800, 1101.4)):
    check("total per salt trial, |A|=%d (ms)" % a, paper, decap_total(a, p), 1.0)

# --------------------------------------------------------------------- peeling
print("== first-salt peeling (results/peel_sweep.csv) ==")
ps = {int(float(r["n"])): r for r in load(os.path.join(RES, "peel_sweep.csv"))}
for n, p1, lo, hi in ((10, 0.321, 0.298, 0.345), (12, 0.235, 0.215, 0.258),
                      (50, 0.334, 0.302, 0.367), (100, 0.349, 0.317, 0.382),
                      (200, 0.438, 0.390, 0.487), (1600, 0.860, 0.816, 0.895),
                      (2000, 0.910, 0.872, 0.937)):
    r = ps[n]
    check("p1, n=%d" % n, p1, float(r["p1"]), 0.0015)
    check("CI low, n=%d" % n, lo, float(r["p1_lo"]), 0.0015)
    check("CI high, n=%d" % n, hi, float(r["p1_hi"]), 0.0015)

# ------------------------------------------------------------------ comparison
print("== fuzzy IB-ME baseline and threshold sweep (results_compare/) ==")
cs = load(os.path.join(CMP, "summary.csv"))


def cmp_row(mode, n, d):
    for r in cs:
        if r["mode"] == mode and int(float(r["n_attr"])) == n and int(float(r["d"])) == d:
            return float(r["p50_ms"])
    return None


check("baseline dec, n=5 (ms)", 1035.2, cmp_row("baseline_dec", 5, 5), 1.0)
check("baseline dec, n=10 (ms)", 1032.4, cmp_row("baseline_dec", 10, 5), 1.0)
check("baseline dec, n=30 (ms)", 1042.5, cmp_row("baseline_dec", 30, 5), 1.0)
check("baseline dec, n=30, d=2 (ms)", 419.0, cmp_row("baseline_dec", 30, 2), 1.0)
check("baseline dec, n=30, d=10 (ms)", 2096.0, cmp_row("baseline_dec", 30, 10), 2.0)
check("Silent-Share dec, |A|=30, d=5 (ms)", 1015.6, cmp_row("decap", 30, 5), 2.0)

print("== encapsulation at equal policy size (results_compare/) ==")
cr = load(os.path.join(CMP, "raw_all.csv"))
base_enc = {int(float(r["n_policy"])): float(r["total_ms"]) for r in cr
            if r["mode"] == "baseline_enc"}
check("baseline enc, |P|=50 (ms)", 338.0, base_enc.get(50), 1.5)
check("baseline enc, |P|=200 (ms)", 1262.0, base_enc.get(200), 2.0)

sp = {}
for r in load(os.path.join(RES, "raw_all.csv")):
    if r["mode"] == "encap" and r["order"] == "sparse":
        sp.setdefault(int(float(r["n_policy"])), []).append(r)
sp_t = {p: med(sp[p], "total_ms") for p in sp}
sp_ct = {p: med(sp[p], "ct_bytes") for p in sp}
dn = {}
for r in load(os.path.join(RES, "raw_all.csv")):
    if r["mode"] == "encap" and r["order"] == "dense":
        dn.setdefault(int(float(r["n_policy"])), []).append(r)
dn_t = {p: med(dn[p], "total_ms") for p in dn}
dn_ct = {p: med(dn[p], "ct_bytes") for p in dn}

check("sparse enc, |P|=50 (ms)", 134.0, sp_t[50], 2.0)
check("sparse enc, |P|=200 (ms)", 522.0, sp_t[200], 2.0)
check("dense enc, |P|=50 (s)", 5.23, dn_t[50] / 1000.0, 0.05)
check("dense enc, |P|=200 (s)", 81.0, dn_t[200] / 1000.0, 0.5)
check("ciphertext, sparse |P|=100 (B/attr)", 225.0, sp_ct[100] / 100, 1.5)
check("ciphertext, dense |P|=100 (B/attr)", 182.0, dn_ct[100] / 100, 1.5)

print("== bilateral ciphertext sizes (results/bilateral.csv) ==")
bl = load(os.path.join(RES, "bilateral.csv"))
bg = {}
for r in bl:
    bg.setdefault((int(float(r["nO"])), int(float(r["nR"]))), []).append(r)
for size, paper_kb in ((10, 4.9), (400, 180.0), (1600, 720.0)):
    c = statistics.median(float(r["total_comm_bytes"]) for r in bg[(size, size)]) / 1000.0
    check("comm at (%d,%d) (KB)" % (size, size), paper_kb, c, 1.0)

print()
if FAILS:
    print("MISMATCHES: %d" % len(FAILS))
    for name, paper, computed in FAILS:
        print("  - %-56s paper %s, data %s" % (name, paper,
              "n/a" if computed is None else round(computed, 3)))
    sys.exit(1)
print("all checked numbers agree with the result files")
