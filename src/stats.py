#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Unified measurement schema and statistics for Silent-Share benchmarks.

Two tables are produced:

  raw      -- one row per repetition, no percentiles;
  summary  -- one row per configuration, with P50/P95/P99 and rates.

Both share the columns in RAW_COLUMNS; the summary adds the derived ones.
Every row carries the git commit and the curve so that a number in the paper
can be traced back to a recorded run.

Percentiles use linear interpolation between order statistics, matching
numpy's default, so that a reviewer can reproduce them with
`numpy.percentile(values, q)`.
"""

import csv
import os

RAW_COLUMNS = [
    "commit", "curve", "mode", "order", "n_attr", "d", "n_policy", "overlap",
    "pairing_ms", "gokvs_decode_ms", "recon_ms", "total_ms",
    "trials", "budget_exhausted", "success", "false_accept",
    "rss_kb", "run_id", "rep",
]

SUMMARY_COLUMNS = RAW_COLUMNS + [
    "reps", "p50_ms", "p95_ms", "p99_ms",
    "success_rate", "false_accept_rate", "search_fail_rate", "trials_mean",
]

GROUP_KEYS = ["commit", "curve", "mode", "order", "n_attr", "d", "n_policy", "overlap"]


def percentile(values, q):
    """Linear-interpolation percentile; q in [0, 100]."""
    data = sorted(float(v) for v in values)
    if not data:
        raise ValueError("percentile of empty sample")
    if len(data) == 1:
        return data[0]
    if q <= 0:
        return data[0]
    if q >= 100:
        return data[-1]
    position = (len(data) - 1) * (q / 100.0)
    lower = int(position)
    upper = min(lower + 1, len(data) - 1)
    weight = position - lower
    return data[lower] * (1.0 - weight) + data[upper] * weight


def _rate(rows, key):
    if not rows:
        return 0.0
    return sum(1 for r in rows if r.get(key)) / float(len(rows))


def summarize(rows, group_keys=None):
    """Aggregate raw rows into summary rows."""
    keys = list(group_keys or GROUP_KEYS)
    buckets = {}
    for row in rows:
        key = tuple(row.get(k) for k in keys)
        buckets.setdefault(key, []).append(row)

    summary = []
    for key, group in buckets.items():
        totals = [r["total_ms"] for r in group if r.get("total_ms") is not None]
        trials = [r["trials"] for r in group if r.get("trials") is not None]
        entry = {k: v for k, v in zip(keys, key)}
        entry.update({
            "reps": len(group),
            "p50_ms": percentile(totals, 50) if totals else None,
            "p95_ms": percentile(totals, 95) if totals else None,
            "p99_ms": percentile(totals, 99) if totals else None,
            "success_rate": _rate(group, "success"),
            "false_accept_rate": _rate(group, "false_accept"),
            # A search failure is a run that neither succeeded nor was
            # budget-limited (i.e. the tag never verified in full search).
            "search_fail_rate": sum(
                1 for r in group
                if not r.get("success") and not r.get("budget_exhausted")
            ) / float(len(group)),
            "trials_mean": (sum(trials) / float(len(trials))) if trials else None,
        })
        summary.append(entry)
    summary.sort(key=lambda e: tuple(str(e.get(k)) for k in keys))
    return summary


def write_csv(path, rows, columns):
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in columns})
    return path


def git_commit(repo_dir=None):
    """Best-effort commit hash for stamping rows; empty when unavailable."""
    import subprocess

    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except Exception:
        return ""
