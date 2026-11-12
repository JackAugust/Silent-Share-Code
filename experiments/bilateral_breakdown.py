#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Per-stage breakdown of the bilateral protocol, from results/bilateral.csv.

    python experiments/bilateral_breakdown.py

The bilateral harness records one row per repetition with separate timers for
the two encapsulations and the two decapsulations.  This script reports the
median of each stage so that the end-to-end number in the paper can be
decomposed instead of quoted as a single figure.

Columns written to results/bilateral_breakdown.csv:

    nO, nR          policy sizes of owner and requester
    reps            repetitions behind the medians
    encap_R_ms      requester encapsulation
    encap_O_ms      owner encapsulation
    decap_O_ms      owner decapsulates the requester ciphertext
    decap_R_ms      requester decapsulates the owner ciphertext
    sum_stages_ms   encap_R + encap_O + decap_O + decap_R (no setup)
    total_ms        measured wall clock of the whole session
    overhead_ms     total_ms - sum_stages_ms (setup, HKDF, AES-GCM, I/O)
    comm_bytes      ciphertexts + tag + nonce
"""
import csv
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "results", "bilateral.csv")
OUT = os.path.join(ROOT, "results", "bilateral_breakdown.csv")

STAGES = [
    ("encap_R_ms", "encap_R_wall_ms"),
    ("encap_O_ms", "encap_O_wall_ms"),
    ("decap_O_ms", "decap_O_wall_ms"),
    ("decap_R_ms", "decap_R_wall_ms"),
    ("total_ms", "total_wall_ms"),
    ("comm_bytes", "total_comm_bytes"),
]


def median(values):
    return statistics.median(values) if values else float("nan")


def main():
    with open(SRC, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    groups = {}
    for row in rows:
        key = (int(row["nO"]), int(row["nR"]))
        groups.setdefault(key, []).append(row)

    out_rows = []
    for key in sorted(groups):
        group = groups[key]
        record = {"nO": key[0], "nR": key[1], "reps": len(group)}
        for name, column in STAGES:
            vals = [float(r[column]) for r in group if r[column] not in ("", None)]
            record[name] = round(median(vals), 1)
        record["sum_stages_ms"] = round(
            record["encap_R_ms"] + record["encap_O_ms"]
            + record["decap_O_ms"] + record["decap_R_ms"], 1)
        record["overhead_ms"] = round(
            record["total_ms"] - record["sum_stages_ms"], 1)
        out_rows.append(record)

    columns = ["nO", "nR", "reps", "encap_R_ms", "encap_O_ms", "decap_O_ms",
               "decap_R_ms", "sum_stages_ms", "total_ms", "overhead_ms",
               "comm_bytes"]
    with open(OUT, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(out_rows)

    print("wrote %s (%d configurations)" % (OUT, len(out_rows)))
    for record in out_rows:
        if record["nO"] == record["nR"] and record["nO"] in (10, 400, 1600):
            print("n=%4d  encap %7.1f  decap %7.1f + %7.1f  sum %7.1f  "
                  "total %7.1f  overhead %6.1f  comm %7d"
                  % (record["nO"], record["encap_R_ms"] + record["encap_O_ms"],
                     record["decap_O_ms"], record["decap_R_ms"],
                     record["sum_stages_ms"], record["total_ms"],
                     record["overhead_ms"], record["comm_bytes"]))


if __name__ == "__main__":
    main()
