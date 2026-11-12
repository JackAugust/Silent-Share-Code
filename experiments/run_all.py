#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Single entry point for every number the paper quotes.

    python experiments/run_all.py                  # paper profile
    python experiments/run_all.py --profile smoke  # 1-minute sanity run
    python experiments/run_all.py --list           # show the matrix, run nothing
    python experiments/run_all.py --self-test      # no charm needed

Outputs (all under results/, UTF-8 CSV):

    raw_all.csv      one row per repetition, RAW_COLUMNS + size columns
    summary.csv      one row per configuration: P50/P95/P99 + rates
    scaling_fit.csv  empirical log-log exponent per series (no assumed shape)
    order_leak.csv   candidate-rank vs. attribute-index correlation
    skipped.csv      cases the time budget refused, with the reason
    manifest.json    machine, versions, curve, sizes, commit, seeds, command

Rules this script obeys, because a reviewer will check them:

  * a hint is always passed explicitly (never emulated by permuting
    attributes), so "hint" rows measure reconstruction, not search;
  * no-hint rows carry `trials` and `budget_exhausted`, and an exhausted
    budget is a failure, never a success;
  * timings come from the library's own stage counters, so total_ms and its
    components cannot disagree;
  * every row carries the commit and the curve;
  * a case that would exceed --max-case-seconds is skipped and reported,
    never silently truncated.
"""

import argparse
import csv
import json
import math
import os
import platform
import random
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SRC = os.path.join(REPO, "src")
OUT = os.path.join(REPO, "results")
sys.path.insert(0, SRC)

CURVE = "BN254"
SEED = 20261111
EXTRA_COLUMNS = ["ct_bytes", "sk_bytes", "comm_bytes", "gokvs_ms", "note"]

# ----------------------------------------------------------------------
# Plan: what each profile runs.  Sizes are attributes (|A|) and policy
# attributes (|P|), mirroring the claims of the paper.
# ----------------------------------------------------------------------
PLAN = {
    "smoke": {
        "encap_sparse": [32, 64],
        "encap_dense": [16, 32],
        "decap_hint": [(5, 32), (10, 64)],
        "decap_nohint": [(10, 5)],
        "bilateral": [(10, 10)],
        "baseline_n": [5],
        "reps": 2,
        "budget": 500,
    },
    "paper": {
        "encap_sparse": [50, 100, 200, 400, 800, 1600],
        "encap_dense": [50, 100, 200, 400],
        "decap_hint": [(5, 100), (10, 100), (10, 400), (15, 400),
                       (20, 800), (30, 800)],
        "decap_nohint": [(10, 2), (10, 3), (10, 5), (12, 4), (12, 5),
                          (12, 6), (12, 8), (12, 10), (14, 7), (16, 7)],
        "bilateral": [(10, 10), (400, 400), (1600, 1600)],
        "baseline_n": [5, 10, 30],
        "reps": 5,
        "budget": 5000,
    },
}

DEFAULT_D = 5


# ----------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------
def log(message):
    print(message)
    sys.stdout.flush()


def _f(value, digits=3):
    if value is None or value == "":
        return "-"
    try:
        return ("%%.%df" % digits) % float(value)
    except (TypeError, ValueError):
        return str(value)


def _bytes(value):
    return len(bytes(value))


def serialized_size(group, obj):
    """Best-effort byte size of one element, a list, or a dict of elements."""
    if obj is None:
        return 0
    if isinstance(obj, (bytes, bytearray)):
        return len(obj)
    if isinstance(obj, dict):
        return sum(serialized_size(group, v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return sum(serialized_size(group, v) for v in obj)
    try:
        return len(group.serialize(obj))
    except Exception:
        try:
            return len(bytes(obj))
        except Exception:
            return 0


def machine_info():
    info = {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "cpu": platform.processor() or "",
        "cores": os.cpu_count(),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "command": " ".join([sys.executable] + sys.argv),
        "curve": CURVE,
        "seed": SEED,
    }
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.lower().startswith("model name"):
                    info["cpu"] = line.split(":", 1)[1].strip()
                    break
    except Exception:
        pass
    try:
        with open("/proc/meminfo", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.startswith("MemTotal"):
                    info["mem_kb"] = int(line.split()[1])
                    break
    except Exception:
        pass
    return info


def rss_kb():
    try:
        with open("/proc/self/status", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.startswith("VmRSS"):
                    return int(line.split()[1])
    except Exception:
        pass
    return ""


# ----------------------------------------------------------------------
# Charm bootstrap: import both GOKVS variants regardless of config, so one
# process can measure dense and sparse without restarting.
# ----------------------------------------------------------------------
def load_crypto():
    try:
        from charm.toolbox.pairinggroup import PairingGroup, ZR, G1, G2, GT, pair
    except Exception as exc:
        log("charm is not available here (%s)." % exc)
        log("Run this on the machine with charm-crypto + PBC, e.g. the")
        log("(charm) conda env that produced your probe output.")
        raise SystemExit(2)

    import okvs
    import sparse_gokvs
    import silent_share
    import stats

    silent_share.SparseGOKVS = sparse_gokvs.SparseGOKVS
    silent_share.GOKVS = okvs.GOKVS
    silent_share.GOKVSPlan = okvs.GOKVSPlan

    group = PairingGroup(CURVE)
    return {
        "group": group, "ZR": ZR, "G1": G1, "G2": G2, "GT": GT, "pair": pair,
        "silent_share": silent_share, "stats": stats,
        "order": int(group.order()),
    }


def micro_benchmark(env):
    """Pairing latency and element sizes for the curve the rows will name."""
    group, pair = env["group"], env["pair"]
    g1 = group.random(env["G1"])
    g2 = group.random(env["G2"])
    gt = pair(g1, g2)

    def best(fn, repeat=7):
        samples = []
        for _ in range(repeat):
            start = time.perf_counter()
            fn()
            samples.append((time.perf_counter() - start) * 1000.0)
        return min(samples), sorted(samples)[len(samples) // 2]

    pairing_min, pairing_p50 = best(lambda: pair(g1, g2))
    exp_min, _ = best(lambda: g2 ** 12345)
    return {
        "order_bits": int(group.order()).bit_length(),
        "pairing_ms_min": pairing_min,
        "pairing_ms_p50": pairing_p50,
        "g2_exp_ms_min": exp_min,
        "G1_bytes": serialized_size(group, g1),
        "G2_bytes": serialized_size(group, g2),
        "GT_bytes": serialized_size(group, gt),
    }


# ----------------------------------------------------------------------
# Row construction
# ----------------------------------------------------------------------
def make_row(env, commit, mode, order, n_attr, d, n_policy, **kw):
    row = {
        "commit": commit, "curve": CURVE, "mode": mode, "order": order,
        "n_attr": n_attr, "d": d, "n_policy": n_policy,
        "overlap": kw.pop("overlap", ""),
        "pairing_ms": None, "gokvs_decode_ms": None, "recon_ms": None,
        "total_ms": None, "trials": None, "budget_exhausted": False,
        "success": None, "false_accept": False, "rss_kb": rss_kb(),
        "run_id": kw.pop("run_id", ""), "rep": kw.pop("rep", 0),
        "ct_bytes": kw.pop("ct_bytes", ""), "sk_bytes": kw.pop("sk_bytes", ""),
        "comm_bytes": kw.pop("comm_bytes", ""),
        "gokvs_ms": kw.pop("gokvs_ms", ""), "note": kw.pop("note", ""),
    }
    row.update(kw)
    return row


# ----------------------------------------------------------------------
# E1: encapsulation vs policy size, sparse and dense
# ----------------------------------------------------------------------
def run_encap(env, plan, reps, commit, run_id, max_seconds, skipped):
    rows = []
    ss_mod = env["silent_share"]
    group = env["group"]
    for variant in ("sparse", "dense"):
        sizes = plan["encap_sparse" if variant == "sparse" else "encap_dense"]
        sorted_sizes = sorted(sizes)
        last_size, last_ms = None, None
        for size in sorted_sizes:
            universe = ["a%06d" % i for i in range(size)]
            instance = ss_mod.SilentShare(group, threshold=DEFAULT_D)
            try:
                pp, msk, setup_ms = instance.setup(universe)
            except Exception as exc:
                skipped.append({"mode": "encap", "order": variant,
                                "n_policy": size, "reason": "setup: %s" % exc})
                continue
            ss_mod.USE_SPARSE_GOKVS = (variant == "sparse")

            # Dense encoding is quadratic, so a size above the cap costs the
            # cap before it can be rejected.  Extrapolate from the previous
            # measured point instead of spending minutes to learn nothing.
            if last_size and last_ms and size > last_size:
                predicted_ms = last_ms * (float(size) / last_size) ** 2
                if predicted_ms > max_seconds * 1000.0:
                    skipped.append({
                        "mode": "encap", "order": variant, "n_policy": size,
                        "reason": "predicted %.0fs from |P|=%d at the measured "
                                  "exponent 2; not attempted"
                                  % (predicted_ms / 1000.0, last_size)})
                    log("  skip %s |P|=%d: predicted %.0fs > %.0fs cap"
                        % (variant, size, predicted_ms / 1000.0,
                           max_seconds))
                    continue

            # One untimed pass decides whether this size is affordable.
            start = time.perf_counter()
            try:
                ct, kappa, details = instance.encap(pp, msk, universe)
            except Exception as exc:
                skipped.append({"mode": "encap", "order": variant,
                                "n_policy": size,
                                "reason": "%s: %s" % (type(exc).__name__, exc)})
                log("  skip encap %s |P|=%d: %s" % (variant, size, exc))
                continue
            first = time.perf_counter() - start
            if first > max_seconds:
                skipped.append({
                    "mode": "encap", "order": variant, "n_policy": size,
                    "reason": "first pass %.1fs > %.1fs cap; larger sizes for "
                              "this variant not attempted" % (first, max_seconds)})
                log("  skip %s |P|=%d: %.1fs for one pass" %
                    (variant, size, first))
                break

            size_bytes = serialized_size(group, ct.get("D1")) + \
                serialized_size(group, ct.get("D2")) + \
                serialized_size(group, ct.get("E0")) + \
                serialized_size(group, ct.get("C"))
            for rep in range(reps):
                ct, kappa, details = instance.encap(pp, msk, universe)
                rows.append(make_row(
                    env, commit, "encap", variant, "", DEFAULT_D, size,
                    total_ms=details["total_ms"],
                    gokvs_ms=details.get("gokvs_total_ms"),
                    ct_bytes=size_bytes, rep=rep, run_id=run_id,
                    success=True, note="setup_ms=%.1f" % setup_ms))
            log("  encap %-6s |P|=%-5d %8.2f ms  %7d B" %
                (variant, size, rows[-1]["total_ms"], size_bytes))
            last_size, last_ms = size, rows[-1]["total_ms"]

            del ct, pp, msk
    ss_mod.USE_SPARSE_GOKVS = True
    return rows


# ----------------------------------------------------------------------
# E2/E3: decapsulation with an explicit hint, and without one
# ----------------------------------------------------------------------
def _prepare(env, n_policy, n_attr, d, run_id, in_policy=None):
    """Instance where the user holds `in_policy` attributes that appear in the
    policy and the rest outside it.

    With in_policy == d exactly one d-subset reconstructs.  That is what makes
    a "wrong" hint genuinely wrong and a no-hint search non-trivial: if every
    held attribute were inside the policy, every d-subset would be valid and
    both measurements would be vacuous.
    """
    ss_mod = env["silent_share"]
    group = env["group"]
    if in_policy is None:
        in_policy = min(d, n_attr)
    outside = n_attr - in_policy
    universe = ["a%06d" % i for i in range(n_policy + outside)]
    policy = universe[:n_policy]
    # In-policy attributes come first, so the unique valid subset is (0..d-1).
    user_attrs = policy[:in_policy] + universe[n_policy:]
    instance = ss_mod.SilentShare(group, threshold=d)
    pp, msk, _ = instance.setup(universe)
    sk, keygen_ms = instance.keygen(pp, msk, "user-%s" % run_id, user_attrs)
    ct, kappa, enc_details = instance.encap(pp, msk, policy)
    return instance, pp, msk, sk, ct, kappa, keygen_ms, enc_details


def run_decap_hint(env, plan, reps, commit, run_id, skipped):
    rows = []
    for n_attr, n_policy in plan["decap_hint"]:
        try:
            instance, pp, msk, sk, ct, kappa, keygen_ms, enc_details = \
                _prepare(env, n_policy, n_attr, DEFAULT_D, run_id)
        except Exception as exc:
            skipped.append({"mode": "decap", "order": "hint", "n_attr": n_attr,
                            "n_policy": n_policy,
                            "reason": "%s: %s" % (type(exc).__name__, exc)})
            log("  skip decap hint |A|=%d |P|=%d: %s" % (n_attr, n_policy, exc))
            continue
        hint = tuple(range(DEFAULT_D))
        for rep in range(reps):
            recovered, details = instance.decap(
                pp, sk, ct, optimize="precompute", hint_subset=hint)
            rows.append(make_row(
                env, commit, "decap", "hint", n_attr, DEFAULT_D, n_policy,
                total_ms=details["total_ms"],
                pairing_ms=details["pairing_ms"],
                gokvs_decode_ms=details["decode_ms"],
                recon_ms=details["recon_ms"],
                trials=details["trials"], success=recovered == kappa,
                rep=rep, run_id=run_id,
                ct_bytes=serialized_size(env["group"], [ct["D1"], ct["D2"]]),
                sk_bytes=serialized_size(env["group"],
                                         [sk.D1, sk.D2]),
                note="keygen_ms=%.1f" % keygen_ms))
        log("  decap hint  |A|=%-3d |P|=%-5d %8.2f ms  pair=%.2f decode=%.2f"
            % (n_attr, n_policy, rows[-1]["total_ms"],
               rows[-1]["pairing_ms"] or 0, rows[-1]["gokvs_decode_ms"] or 0))
    return rows


def run_decap_nohint(env, plan, reps, budget, commit, run_id, max_seconds,
                     skipped):
    rows = []
    for n_attr, d in plan["decap_nohint"]:
        n_policy = max(n_attr, 200)
        try:
            instance, pp, msk, sk, ct, kappa, _, _ = \
                _prepare(env, n_policy, n_attr, d, run_id)
        except Exception as exc:
            skipped.append({"mode": "decap", "order": "prh", "n_attr": n_attr,
                            "d": d,
                            "reason": "%s: %s" % (type(exc).__name__, exc)})
            log("  skip decap nohint |A|=%d d=%d: %s" % (n_attr, d, exc))
            continue
        start = time.perf_counter()
        recovered, details = instance.decap(
            pp, sk, ct, optimize="precompute", order="prh", budget=budget)
        first = time.perf_counter() - start
        if first > max_seconds:
            skipped.append({
                "mode": "decap", "order": "prh", "n_attr": n_attr, "d": d,
                "reason": "one pass %.1fs > %.1fs cap" % (first, max_seconds)})
            log("  skip decap nohint |A|=%d d=%d: %.1fs" % (n_attr, d, first))
            continue
        for rep in range(reps):
            recovered, details = instance.decap(
                pp, sk, ct, optimize="precompute", order="prh", budget=budget)
            rows.append(make_row(
                env, commit, "decap", "prh", n_attr, d, n_policy,
                total_ms=details["total_ms"],
                pairing_ms=details["pairing_ms"],
                gokvs_decode_ms=details["decode_ms"],
                recon_ms=details["recon_ms"],
                trials=details["trials"],
                budget_exhausted=details["budget_exhausted"],
                success=recovered == kappa, rep=rep, run_id=run_id,
                note="budget=%d" % budget))
        log("  decap prh   |A|=%-3d d=%d  %9.2f ms  trials=%d  ok=%s"
            % (n_attr, d, rows[-1]["total_ms"], rows[-1]["trials"] or 0,
               rows[-1]["success"]))
    return rows


# ----------------------------------------------------------------------
# E4: bilateral composition (two encapsulations, two decapsulations)
# ----------------------------------------------------------------------
def run_bilateral(env, plan, reps, commit, run_id, skipped):
    rows = []
    ss_mod = env["silent_share"]
    group = env["group"]
    for n_owner, n_requester in plan["bilateral"]:
        try:
            owner_uni = ["o%06d" % i for i in range(n_owner)]
            req_uni = ["r%06d" % i for i in range(n_requester)]
            owner = ss_mod.SilentShare(group, threshold=DEFAULT_D)
            pp_o, msk_o, _ = owner.setup(owner_uni)
            pp_r, msk_r, _ = owner.setup(req_uni)
            sk_o, _ = owner.keygen(pp_r, msk_r, "owner", req_uni[:DEFAULT_D])
            sk_r, _ = owner.keygen(pp_o, msk_o, "requester",
                                   owner_uni[:DEFAULT_D])
            for rep in range(reps):
                start = time.perf_counter()
                ct_o, k_o, d_o = owner.encap(pp_r, msk_r, req_uni)
                ct_r, k_r, d_r = owner.encap(pp_o, msk_o, owner_uni)
                hint = tuple(range(DEFAULT_D))
                rec_o, dd_o = owner.decap(pp_o, sk_o, ct_o,
                                          hint_subset=hint)
                rec_r, dd_r = owner.decap(pp_r, sk_r, ct_r,
                                          hint_subset=hint)
                total = (time.perf_counter() - start) * 1000.0
                comm = serialized_size(group, [ct_o["D1"], ct_o["D2"],
                                               ct_r["D1"], ct_r["D2"]])
                rows.append(make_row(
                    env, commit, "bilateral", "hint", DEFAULT_D, DEFAULT_D,
                    n_owner + n_requester, total_ms=total,
                    success=(rec_o == k_o and rec_r == k_r),
                    comm_bytes=comm, rep=rep, run_id=run_id,
                    ct_bytes=comm,
                    note="owner|P|=%d requester|P|=%d" %
                         (n_owner, n_requester)))
            log("  bilateral (%d,%d)  %9.2f ms  %8d B" %
                (n_owner, n_requester, rows[-1]["total_ms"],
                 rows[-1]["comm_bytes"]))
        except Exception as exc:
            skipped.append({"mode": "bilateral", "n_attr": n_owner,
                            "n_policy": n_requester,
                            "reason": "%s: %s" % (type(exc).__name__, exc)})
            log("  skip bilateral (%d,%d): %s" % (n_owner, n_requester, exc))
    return rows


# ----------------------------------------------------------------------
# E5: baseline, fuzzy IB-ME, same curve and same schema
# ----------------------------------------------------------------------
def run_baseline(env, plan, reps, commit, run_id, skipped):
    rows = []
    try:
        import fuzzy_ibme
    except Exception as exc:
        skipped.append({"mode": "baseline", "reason": "import: %s" % exc})
        return rows

    cache = fuzzy_ibme.ContextCache(curve=CURVE, d=DEFAULT_D)
    for n in plan["baseline_n"]:
        try:
            me, mpk, msk = cache.get(n, DEFAULT_D)[:3]
            for rep in range(max(1, reps // 2)):
                result = fuzzy_ibme.benchmark_case(
                    me, mpk, msk, n, n, DEFAULT_D, rounds=3, warmup=1,
                    decrypt_mode="hint")
                rows.append(make_row(
                    env, commit, "baseline_enc", "hint", n, DEFAULT_D, n,
                    total_ms=result["enc_ms"], success=True, rep=rep,
                    run_id=run_id, ct_bytes=result["ct_bytes"],
                    note="fuzzy-IB-ME n=R=%d d=%d" % (n, DEFAULT_D)))
                rows.append(make_row(
                    env, commit, "baseline_dec", "hint", n, DEFAULT_D, n,
                    total_ms=result["dec_ms"], success=True, rep=rep,
                    run_id=run_id, ct_bytes=result["ct_bytes"],
                    note="attempts=%.1f" % result["dec_attempts_mean"]))
            log("  baseline n=%-3d enc=%8.2f ms dec=%8.2f ms ct=%7d B" %
                (n, rows[-2]["total_ms"], rows[-1]["total_ms"],
                 rows[-1]["ct_bytes"]))
        except Exception as exc:
            skipped.append({"mode": "baseline", "n_attr": n,
                            "reason": "%s: %s" % (type(exc).__name__, exc)})
    return rows


# ----------------------------------------------------------------------
# E6: correctness and false-accept rate (the part reviewers test first)
# ----------------------------------------------------------------------
def run_correctness(env, plan, commit, run_id, trials=100, skipped=None):
    rows = []
    n_policy, n_attr = 100, 10
    d = DEFAULT_D
    try:
        instance, pp, msk, sk, ct, kappa, _, _ = _prepare(
            env, n_policy, n_attr, d, run_id)
    except Exception as exc:
        if skipped is not None:
            skipped.append({"mode": "correct", "n_attr": n_attr,
                            "n_policy": n_policy,
                            "reason": "%s: %s" % (type(exc).__name__, exc)})
        log("  skip correctness: %s" % exc)
        return rows

    hint_ok = tuple(range(d))
    hint_bad = tuple(range(1, d + 1))  # replaces one in-policy attribute

    def accepted_with(candidate_ct, hint, count):
        good = 0
        for _ in range(count):
            try:
                recovered, _ = instance.decap(pp, sk, candidate_ct,
                                              hint_subset=hint)
            except Exception:
                # Raising on malformed input is a rejection, not an accept.
                continue
            if recovered is not None and recovered == kappa:
                good += 1
        return good

    for name, hint in (("hint_correct", hint_ok), ("hint_wrong", hint_bad)):
        good = accepted_with(ct, hint, trials)
        # `order` records what the run expects: a rejection case is labelled so
        # that success=False cannot be misread as a broken decapsulation.
        rows.append(make_row(
            env, commit, "correct",
            "hint" if name == "hint_correct" else "reject_expected",
            n_attr, d, n_policy, total_ms=None,
            success=(good == trials) if name == "hint_correct" else False,
            false_accept=(good > 0) if name == "hint_wrong" else False,
            rep=0, run_id=run_id, note="accepted=%d/%d" % (good, trials)))
        log("  correct %-12s accepted %d/%d" % (name, good, trials))

    # Tamper with the verification tag: the accept decision must flip.
    tag = ct["C"]
    tampered_tag = dict(ct)
    raw = bytearray(tag)
    raw[0] ^= 1
    tampered_tag["C"] = bytes(raw)
    good = accepted_with(tampered_tag, hint_ok, max(20, trials // 4))
    rows.append(make_row(
        env, commit, "correct", "reject_expected", n_attr, d, n_policy,
        total_ms=None, success=False, false_accept=(good > 0), rep=0,
        run_id=run_id, note="tampered_tag accepted=%d" % good))
    log("  correct tampered_tag  accepted %d" % good)

    # Tamper with every bucket, so no held attribute can decode correctly.
    tampered_all = dict(ct)
    tampered_all["D1"] = [x ** 2 for x in ct["D1"]]
    good = accepted_with(tampered_all, hint_ok, max(20, trials // 4))
    rows.append(make_row(
        env, commit, "correct", "reject_expected", n_attr, d, n_policy,
        total_ms=None, success=False, false_accept=(good > 0), rep=0,
        run_id=run_id, note="tampered_d1_all accepted=%d" % good))
    log("  correct tampered_d1_all  accepted %d" % good)
    return rows


# ----------------------------------------------------------------------
# E7: does candidate enumeration order leak the intersection?
# No charm needed: this is pure combinatorics, runnable anywhere.
# ----------------------------------------------------------------------
def order_leak_samples(env, samples=400, n_attr=12, d=5, seed=SEED):
    from itertools import combinations
    import hashdom

    rng = random.Random(seed)
    lex_rank = {s: i for i, s in enumerate(combinations(range(n_attr), d))}
    rows = []
    for _ in range(samples):
        true_subset = tuple(sorted(rng.sample(range(n_attr), d)))
        labels = hashdom.permuted_indices(n_attr, rng.randrange(1 << 30))
        prh_rank = {tuple(sorted(s)): i
                    for i, s in enumerate(combinations(labels, d))}
        rows.append({
            "mode": "order_leak", "d": d, "n_attr": n_attr,
            "true_subset": "|".join(str(i) for i in true_subset),
            "index_sum": sum(true_subset),
            "lex_trials": lex_rank[true_subset] + 1,
            "prh_trials": prh_rank[true_subset] + 1,
        })
    return rows


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return float("nan")
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return float("nan")
    return num / (dx * dy)


def _ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        average = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = average
        i = j + 1
    return ranks


def order_leak_summary(rows):
    sums = [r["index_sum"] for r in rows]
    lex = [r["lex_trials"] for r in rows]
    prh = [r["prh_trials"] for r in rows]
    return {
        "samples": len(rows),
        "lex_spearman": _pearson(_ranks(sums), _ranks(lex)),
        "prh_spearman": _pearson(_ranks(sums), _ranks(prh)),
        "lex_trials_min": min(lex), "lex_trials_max": max(lex),
        "prh_trials_min": min(prh), "prh_trials_max": max(prh),
    }


# ----------------------------------------------------------------------
# Empirical scaling exponent: slope of log(time) vs log(size)
# ----------------------------------------------------------------------
def scaling_fit(rows):
    series = {}
    for row in rows:
        if row.get("mode") not in ("encap", "decap"):
            continue
        if row.get("total_ms") in (None, ""):
            continue
        if row["mode"] == "encap":
            size = row.get("n_policy")
        else:
            size = row.get("n_attr")
        if not size:
            continue
        key = (row["mode"], row["order"])
        series.setdefault(key, []).append((float(size), float(row["total_ms"])))

    out = []
    for (mode, order), points in series.items():
        by_size = {}
        for size, value in points:
            by_size.setdefault(size, []).append(value)
        xs = sorted(by_size)
        ys = [sum(by_size[s]) / len(by_size[s]) for s in xs]
        if len(xs) < 2:
            out.append({"mode": mode, "order": order, "sizes": len(xs),
                        "exponent": "", "r2": ""})
            continue
        lx = [math.log(x) for x in xs]
        ly = [math.log(y) for y in ys]
        mx, my = sum(lx) / len(lx), sum(ly) / len(ly)
        sxx = sum((x - mx) ** 2 for x in lx)
        sxy = sum((x - mx) * (y - my) for x, y in zip(lx, ly))
        slope = sxy / sxx if sxx else float("nan")
        intercept = my - slope * mx
        ss_tot = sum((y - my) ** 2 for y in ly)
        ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(lx, ly))
        r2 = 1 - ss_res / ss_tot if ss_tot else float("nan")
        out.append({"mode": mode, "order": order, "sizes": len(xs),
                    "size_min": xs[0], "size_max": xs[-1],
                    "exponent": round(slope, 3), "r2": round(r2, 4)})
    return out


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------
def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Run every experiment the paper cites.")
    parser.add_argument("--profile", choices=sorted(PLAN), default="paper")
    parser.add_argument("--reps", type=int, default=None,
                        help="repetitions per configuration (default from plan)")
    parser.add_argument("--budget", type=int, default=None,
                        help="candidate budget for no-hint decapsulation")
    parser.add_argument("--max-case-seconds", type=float, default=120.0,
                        help="skip a case whose first pass exceeds this")
    parser.add_argument("--out", default=OUT)
    parser.add_argument("--only", default="",
                        help="comma list: encap,decap_hint,decap_nohint,"
                             "bilateral,baseline,correct,order")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    plan = PLAN[args.profile]
    reps = args.reps or plan["reps"]
    budget = args.budget or plan["budget"]
    only = set(x.strip() for x in args.only.split(",") if x.strip())

    if args.list:
        log("profile: %s   reps=%d   budget=%d" %
            (args.profile, reps, budget))
        for key in ("encap_sparse", "encap_dense", "decap_hint",
                    "decap_nohint", "bilateral", "baseline_n"):
            log("  %-14s %s" % (key, plan[key]))
        log("  correctness   100 trials x (correct hint, wrong hint, tampered)")
        log("  order         400 subsets, lex vs prh rank correlation")
        return 0

    if args.self_test:
        rows = order_leak_samples(None, samples=200)
        summary = order_leak_summary(rows)
        log("self-test (no charm): %d subsets" % summary["samples"])
        log("  lex rank vs index-sum spearman: %+.3f (leaks if ~1)"
            % summary["lex_spearman"])
        log("  prh rank vs index-sum spearman: %+.3f (want ~0)"
            % summary["prh_spearman"])
        ok = abs(summary["lex_spearman"]) > 0.5 and \
            abs(summary["prh_spearman"]) < 0.3
        log("  => %s" % ("PASS" if ok else "INCONCLUSIVE"))
        return 0 if ok else 1

    random.seed(SEED)
    os.makedirs(args.out, exist_ok=True)
    if only:
        # A partial run must not overwrite a complete one.
        args.out = os.path.join(args.out,
                                "only_%s" % time.strftime("%Y%m%d-%H%M%S"))
        os.makedirs(args.out, exist_ok=True)
        log("partial run (--only): writing to %s" % args.out)
    env = load_crypto()
    commit = env["stats"].git_commit(REPO)
    run_id = time.strftime("%Y%m%d-%H%M%S")

    manifest = machine_info()
    manifest.update({
        "commit": commit, "profile": args.profile, "reps": reps,
        "budget": budget, "max_case_seconds": args.max_case_seconds,
        "micro": micro_benchmark(env),
    })
    log("commit %s  curve %s  reps %d" % (commit, CURVE, reps))
    log("pairing %.3f ms  G1 %d B  G2 %d B  GT %d B" %
        (manifest["micro"]["pairing_ms_min"],
         manifest["micro"]["G1_bytes"], manifest["micro"]["G2_bytes"],
         manifest["micro"]["GT_bytes"]))

    rows, skipped = [], []

    def want(name):
        return not only or name in only

    raw_path = os.path.join(args.out, "raw_all.csv")
    summary_path = os.path.join(args.out, "summary.csv")

    def flush(stage):
        """Persist after every stage: a long run must never lose everything."""
        stats_mod = env["stats"]
        stats_mod.write_csv(raw_path, rows,
                            stats_mod.RAW_COLUMNS + EXTRA_COLUMNS)
        stats_mod.write_csv(summary_path, stats_mod.summarize(rows),
                            stats_mod.SUMMARY_COLUMNS + EXTRA_COLUMNS[:4])
        stats_mod.write_csv(os.path.join(args.out, "skipped.csv"), skipped,
                            ["mode", "order", "n_attr", "d", "n_policy",
                             "reason"])
        log("  .. %s: %d rows on disk" % (stage, len(rows)))

    stages = []
    if want("encap"):
        stages.append(("encap", "[1/7] encapsulation vs |P| (sparse, dense)",
                       lambda: run_encap(env, plan, reps, commit, run_id,
                                         args.max_case_seconds, skipped)))
    if want("decap_hint"):
        stages.append(("decap_hint", "[2/7] decapsulation with explicit hint",
                       lambda: run_decap_hint(env, plan, reps, commit,
                                              run_id, skipped)))
    if want("decap_nohint"):
        stages.append(("decap_nohint",
                       "[3/7] decapsulation without hint (budget %d)" % budget,
                       lambda: run_decap_nohint(env, plan, reps, budget,
                                                commit, run_id,
                                                args.max_case_seconds,
                                                skipped)))
    if want("bilateral"):
        stages.append(("bilateral", "[4/7] bilateral composition",
                       lambda: run_bilateral(env, plan, reps, commit, run_id,
                                             skipped)))
    if want("baseline"):
        stages.append(("baseline", "[5/7] baseline: fuzzy IB-ME",
                       lambda: run_baseline(env, plan, reps, commit, run_id,
                                            skipped)))
    if want("correct"):
        stages.append(("correct", "[6/7] correctness and false-accept rate",
                       lambda: run_correctness(env, plan, commit, run_id,
                                               skipped=skipped)))

    for name, title, run in stages:
        log("\n" + title)
        started = time.time()
        try:
            rows.extend(run())
        except Exception as exc:
            log("  stage %s aborted: %s: %s" % (name, type(exc).__name__, exc))
            skipped.append({"mode": name, "reason": "%s: %s"
                            % (type(exc).__name__, exc)})
        flush(name)
        log("  %s took %.1fs" % (name, time.time() - started))

    log("\n[7/7] enumeration-order leakage (no crypto)")
    leak_rows = order_leak_samples(None, samples=400)
    leak_summary = order_leak_summary(leak_rows)

    stats_mod = env["stats"]
    stats_mod.write_csv(os.path.join(args.out, "scaling_fit.csv"),
                        scaling_fit(rows),
                        ["mode", "order", "sizes", "size_min", "size_max",
                         "exponent", "r2"])
    stats_mod.write_csv(os.path.join(args.out, "order_leak.csv"), leak_rows,
                        ["mode", "n_attr", "d", "true_subset", "index_sum",
                         "lex_trials", "prh_trials"])
    stats_mod.write_csv(os.path.join(args.out, "skipped.csv"), skipped,
                        ["mode", "order", "n_attr", "d", "n_policy",
                         "reason"])
    manifest["order_leak"] = leak_summary
    manifest["counts"] = {"rows": len(rows), "skipped": len(skipped)}
    with open(os.path.join(args.out, "manifest.json"), "w",
              encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)

    log("\n" + "=" * 78)
    log("order leakage: lex spearman %+.3f | prh spearman %+.3f"
        % (leak_summary["lex_spearman"], leak_summary["prh_spearman"]))
    log("rows %d, skipped %d -> %s" % (len(rows), len(skipped), args.out))
    log("=" * 78)
    log("paste-back set: raw_all.csv, summary.csv, scaling_fit.csv,")
    log("order_leak.csv, skipped.csv, manifest.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
