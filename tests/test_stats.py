#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for the measurement schema (C4)."""

import csv
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from stats import (RAW_COLUMNS, SUMMARY_COLUMNS, percentile, summarize,
                   write_csv, git_commit)


def test_percentile_matches_numpy():
    values = [3.0, 1.0, 4.0, 1.5, 9.0, 2.5, 6.0]
    for q in (0, 5, 25, 50, 75, 95, 99, 100):
        assert percentile(values, q) == pytest.approx(
            float(np.percentile(values, q)), rel=0, abs=1e-12
        )


def test_summary_rates_and_quantiles():
    rows = []
    for i, total in enumerate([100.0, 110.0, 120.0, 130.0, 400.0]):
        rows.append({
            "commit": "abc1234", "curve": "BN254", "mode": "no-hint",
            "order": "prh", "n_attr": 10, "d": 5, "n_policy": 50, "overlap": 5,
            "total_ms": total, "trials": i + 1, "budget_exhausted": False,
            "success": i < 4, "false_accept": False,
        })
    rows.append({
        "commit": "abc1234", "curve": "BN254", "mode": "no-hint",
        "order": "prh", "n_attr": 10, "d": 5, "n_policy": 50, "overlap": 5,
        "total_ms": None, "trials": 0, "budget_exhausted": True,
        "success": False, "false_accept": False,
    })

    summary = summarize(rows)
    assert len(summary) == 1
    entry = summary[0]
    assert entry["reps"] == 6
    assert entry["success_rate"] == pytest.approx(4 / 6)
    assert entry["false_accept_rate"] == 0.0
    # one run neither succeeded nor hit the budget -> a genuine search failure
    assert entry["search_fail_rate"] == pytest.approx(1 / 6)
    assert entry["p50_ms"] == pytest.approx(120.0)
    assert entry["p99_ms"] >= entry["p95_ms"] >= entry["p50_ms"]


def test_summary_groups_by_configuration():
    base = dict(commit="abc1234", curve="BN254", order="prh", n_attr=10,
                d=5, n_policy=50, overlap=5, budget_exhausted=False,
                success=True, false_accept=False)
    rows = [
        dict(base, mode="hint", total_ms=10.0, trials=1),
        dict(base, mode="no-hint", total_ms=100.0, trials=7),
    ]
    summary = summarize(rows)
    assert len(summary) == 2
    assert {e["mode"] for e in summary} == {"hint", "no-hint"}


def test_csv_roundtrip_and_schema(tmp_path):
    rows = [{
        "commit": "abc1234", "curve": "BLS12_381", "mode": "no-hint",
        "order": "prh", "n_attr": 15, "d": 5, "n_policy": 200, "overlap": 5,
        "pairing_ms": 1.0, "gokvs_decode_ms": 2.0, "recon_ms": 3.0,
        "total_ms": 6.0, "trials": 11, "budget_exhausted": False,
        "success": True, "false_accept": False, "rss_kb": 1024,
        "run_id": "r1", "rep": 1,
    }]
    path = str(tmp_path / "raw.csv")
    write_csv(path, rows, RAW_COLUMNS)
    with open(path, newline="", encoding="utf-8") as handle:
        read_back = list(csv.DictReader(handle))
    assert list(read_back[0].keys()) == RAW_COLUMNS
    assert read_back[0]["curve"] == "BLS12_381"


def test_commit_hash_is_present_in_a_repo():
    # A snapshot without git metadata (for example an anonymous artifact
    # archive) has no commit to report, which is not a failure.
    commit = git_commit()
    if not commit:
        pytest.skip("no git metadata in this snapshot")
    assert len(commit) >= 7


def test_summary_columns_are_a_superset():
    assert set(SUMMARY_COLUMNS) > set(RAW_COLUMNS)
