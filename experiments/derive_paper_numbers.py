# -*- coding: utf-8 -*-
"""Derived quantities for the paper, computed from results/raw_all.csv.

raw_all.csv is the authoritative table: one row per repetition, carrying the
stage counters, the ciphertext size and the trial count.  Everything printed
here is a median over repetitions, which is what the paper reports.
"""
import csv
import math
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PATH = os.path.join(ROOT, "results", "raw_all.csv")

rows = list(csv.DictReader(open(PATH, encoding="utf-8")))


def f(row, key):
    v = row.get(key) or ""
    return float(v) if v not in ("", None) else None


def sel(mode, order=None, a=None, d=None, p=None):
    out = []
    for r in rows:
        if r["mode"] != mode:
            continue
        if order is not None and r["order"] != order:
            continue
        if a is not None and int(float(r["n_attr"])) != a:
            continue
        if d is not None and int(float(r["d"])) != d:
            continue
        if p is not None and int(float(r["n_policy"])) != p:
            continue
        out.append(r)
    return out


def med(rs, key):
    vals = [f(r, key) for r in rs if f(r, key) is not None]
    return statistics.median(vals) if vals else None


TPAIR = 15.0263


def _binom(n, k):
    return math.factorial(n) // (math.factorial(k) * math.factorial(n - k))

print("== encapsulation, sparse (rho=3, alpha=1.25) ==")
for p in (50, 100, 200, 400, 800, 1600):
    rs = sel("encap", "sparse", p=p)
    print("  |P|=%4d  %8.1f ms  ct=%7d B  %.2f ms/attr  %.1f B/attr"
          % (p, med(rs, "total_ms"), med(rs, "ct_bytes"),
             med(rs, "total_ms") / p, med(rs, "ct_bytes") / p))

print("== encapsulation, dense (baseline) ==")
for p in (50, 100, 200):
    rs = sel("encap", "dense", p=p)
    print("  |P|=%4d  %8.1f ms  ct=%7d B" % (p, med(rs, "total_ms"),
                                              med(rs, "ct_bytes")))

print("== decapsulation with explicit hint ==")
seen = set()
for r in sel("decap", "hint"):
    key = (int(float(r["n_attr"])), int(float(r["n_policy"])))
    if key in seen:
        continue
    seen.add(key)
    a, p = key
    rs = sel("decap", "hint", a=a, p=p)
    t = med(rs, "total_ms")
    print("  |A|=%2d |P|=%4d  total=%7.1f  pairing=%7.1f  decode=%5.2f  2A*Tpair=%7.1f  ratio=%.3f"
          % (a, p, t, med(rs, "pairing_ms"), med(rs, "gokvs_decode_ms"),
             2 * a * TPAIR, t / (2 * a * TPAIR)))

print("== decapsulation without hint (budget 5000) ==")
seen = set()
for r in sel("decap", "prh"):
    key = (int(float(r["n_attr"])), int(float(r["d"])))
    if key in seen:
        continue
    seen.add(key)
    a, d = key
    rs = sel("decap", "prh", a=a, d=d)
    t = med(rs, "total_ms")
    tr = med(rs, "trials")
    base = 2 * a * TPAIR
    print("  |A|=%2d d=%d  total=%8.1f  trials=%6.1f  per-cand=%5.1f ms  "
          "binom=%d" % (a, d, t, tr, (t - base) / tr, _binom(a, d)))

print("== bilateral ==")
for r in sorted(sel("bilateral"), key=lambda x: int(float(x["n_policy"]))):
    p = int(float(r["n_policy"]))
    rs = sel("bilateral", p=p)
    print("  |P|=%4d  %8.1f ms  comm=%7d B" % (p, med(rs, "total_ms"),
                                               med(rs, "comm_bytes")))

print("== baseline: fuzzy IB-ME ==")
for mode in ("baseline_enc", "baseline_dec"):
    for r in sorted(sel(mode), key=lambda x: int(float(x["n_attr"]))):
        n = int(float(r["n_attr"]))
        rs = sel(mode, a=n)
        print("  %-12s n=%2d  %8.1f ms  ct=%6d B  (%.1f ms/attr, %.0f B/attr)"
              % (mode, n, med(rs, "total_ms"), med(rs, "ct_bytes"),
                 med(rs, "total_ms") / n, med(rs, "ct_bytes") / n))

print("== correctness ==")
for r in sel("correct"):
    rs = sel("correct", r["order"])
    print("  %-16s %s" % (r["order"], r["note"]))

print("== ratios ==")
print("  dense/sparse encap at |P|=50/100/200: %.1fx %.1fx %.1fx"
      % (med(sel("encap", "dense", p=50), "total_ms") / med(sel("encap", "sparse", p=50), "total_ms"),
         med(sel("encap", "dense", p=100), "total_ms") / med(sel("encap", "sparse", p=100), "total_ms"),
         med(sel("encap", "dense", p=200), "total_ms") / med(sel("encap", "sparse", p=200), "total_ms")))
print("  decap |A|=5 vs fuzzy n=5: %.1fx"
      % (med(sel("baseline_dec", a=5), "total_ms") / med(sel("decap", "hint", a=5), "total_ms")))
print("  decap |A|=10 vs fuzzy n=10: %.1fx"
      % (med(sel("baseline_dec", a=10), "total_ms") / med(sel("decap", "hint", a=10), "total_ms")))
print("  decap |A|=30 vs fuzzy n=30: %.2fx"
      % (med(sel("baseline_dec", a=30), "total_ms") / med(sel("decap", "hint", a=30), "total_ms")))

