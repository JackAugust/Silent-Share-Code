# -*- coding: utf-8 -*-
"""Five-panel Silent-Share versus fuzzy IB-ME comparison at matched parameters.

    python experiments/plot_comparison.py

Reads results/raw_all.csv and results_compare/raw_all.csv (both optional) and
writes ../<paper>/Figs/fig_comparison.pdf.

Panels
  (a) encapsulation versus policy size, same policy sizes for both schemes
  (b) ciphertext size versus policy size
  (c) decapsulation versus |A| at d = 5, best case (one candidate, i.e. the
      correct subset is known); fuzzy IB-ME is flat because it pays 13d
      pairings, Silent-Share grows as 2|A|; the shaded part is 2|A| < 13d
  (d) cost of one further candidate versus d: 13d pairings for fuzzy IB-ME
      against d target-group exponentiations for Silent-Share
  (e) total cost of a hidden-policy search at d = 5: the per-candidate
      medians of (d) multiplied by the worst-case candidate count
      C(|A|, d); this is a model over measured per-candidate costs, not a
      measured search

(c) is the baseline's best case and the only panel where the two schemes are
close; (d) and (e) are the regime a hidden-policy match actually runs in.
"""
import argparse
import csv
import os
import statistics
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DEFAULT_OUT = os.path.join(os.path.dirname(REPO), "Silent-Share", "Figs",
                           "fig_comparison.pdf")

OURS = dict(color="#1f77b4", marker="o", ls="-", ms=3.4, lw=1.1)
DENSE = dict(color="#d62728", marker="s", ls="--", ms=3.0, lw=1.0)
FUZZY = dict(color="#2ca02c", marker="^", ls=":", ms=3.6, lw=1.2)


def load(path):
    if not os.path.exists(path):
        print("missing (skipped): %s" % path)
        return []
    with open(path, encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def nums(row, key):
    try:
        return float(row.get(key) or "")
    except ValueError:
        return None


def points(rows, mode, order=None, x="n_policy", fixed=None, value="total_ms"):
    buckets = {}
    for r in rows:
        if r["mode"] != mode:
            continue
        if order is not None and r["order"] != order:
            continue
        if fixed:
            try:
                if any(int(float(r[k])) != v for k, v in fixed.items()):
                    continue
            except (TypeError, ValueError):
                continue
        try:
            key = int(float(r[x]))
        except (TypeError, ValueError):
            continue
        v = nums(r, value)
        if v:
            buckets.setdefault(key, []).append(v)
    return [(k, statistics.median(buckets[k])) for k in sorted(buckets)]


def comb(n, k):
    """Binomial coefficient without math.comb (Python 3.6 compatible)."""
    if k < 0 or k > n:
        return 0
    k = min(k, n - k)
    out = 1
    for i in range(k):
        out = out * (n - i) // (i + 1)
    return out


def marginal_per_candidate(rows):
    """(d, ms) cost of one further candidate after the one-time pairing layer.

    The pairing layer and the GOKVS decode are paid once per decapsulation,
    so the marginal cost of the remaining candidates is the total minus those
    two columns, divided by the number of candidates tested.
    """
    buckets = {}
    for r in rows:
        if r["mode"] != "decap" or r["order"] == "hint":
            continue
        total, trials = nums(r, "total_ms"), nums(r, "trials")
        pairing, decode = nums(r, "pairing_ms"), nums(r, "gokvs_decode_ms")
        if not (total and trials and pairing):
            continue
        marginal = (total - pairing - (decode or 0.0)) / (trials - 1 or 1)
        if marginal > 0:
            buckets.setdefault(int(float(r["d"])), []).append(marginal)
    return [(k, statistics.median(v)) for k, v in sorted(buckets.items())]


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--results", default=os.path.join(REPO, "results",
                                                     "raw_all.csv"))
    p.add_argument("--compare", default=os.path.join(REPO, "results_compare",
                                                     "raw_all.csv"))
    p.add_argument("--extra", default=os.path.join(REPO, "results_crossover",
                                                   "raw_all.csv"),
                   help="optional rows past the crossover (|A| > 6.5d)")
    p.add_argument("--out", default=DEFAULT_OUT)
    args = p.parse_args(argv)

    ours, theirs = load(args.results), load(args.compare)
    ours = ours + load(args.extra)
    if not ours and not theirs:
        print("no rows to plot")
        return 2

    plt.rcParams.update({
        "font.size": 7, "axes.labelsize": 7, "axes.titlesize": 7,
        "xtick.labelsize": 6.5, "ytick.labelsize": 6.5, "legend.fontsize": 7,
        "figure.dpi": 300, "pdf.fonttype": 42, "axes.linewidth": 0.6,
    })
    fig, axes = plt.subplots(1, 5, figsize=(7.16, 2.02))
    d_line = 5.0

    # (a) encapsulation
    ax = axes[0]
    for rows, mode, order, st in ((ours, "encap", "sparse", OURS),
                                  (ours, "encap", "dense", DENSE),
                                  (theirs, "baseline_enc", None, FUZZY)):
        pts = points(rows, mode, order)
        if pts:
            ax.plot([q[0] for q in pts], [q[1] for q in pts], **st)
    ax.set_title("(a) encapsulation")
    ax.set_xlabel("policy size $|\\mathcal{P}|$")
    ax.set_ylabel("time (ms)")
    ax.set_xscale("log")
    ax.set_yscale("log")

    # (b) ciphertext size (the dense variant is omitted: it is compact but
    # quadratic to build, so it is not a protocol path)
    ax = axes[1]
    for rows, mode, order, st in ((ours, "encap", "sparse", OURS),
                                  (theirs, "baseline_enc", None, FUZZY)):
        pts = [(k, v / 1024.0) for k, v in
               points(rows, mode, order, value="ct_bytes")]
        if pts:
            ax.plot([q[0] for q in pts], [q[1] for q in pts], **st)
    ax.set_title("(b) ciphertext")
    ax.set_xlabel("policy size $|\\mathcal{P}|$")
    ax.set_ylabel("size (KiB)")
    ax.set_xscale("log")
    ax.set_yscale("log")

    # (c) best case: exactly one candidate, i.e. the correct d-subset is
    # known.  Fuzzy IB-ME pays 13d pairings and is therefore flat in |A|;
    # Silent-Share pays 2|A| pairings and grows with |A|.  This is the only
    # panel in which the baseline is competitive.
    ax = axes[2]
    cut = 6.5 * d_line
    ax.axvspan(4, cut, color="#1f77b4", alpha=0.08, lw=0)
    ax.axvline(cut, color="0.45", ls="--", lw=0.7)
    for rows, mode, order, st in ((ours, "decap", "hint", OURS),
                                  (theirs, "baseline_dec", None, FUZZY)):
        pts = points(rows, mode, order, x="n_attr", fixed={"d": int(d_line)})
        if pts:
            ax.plot([q[0] for q in pts], [q[1] for q in pts], **st)
    ax.set_title("(c) one candidate, $d=5$")
    ax.set_xlabel("receiver attributes $|\\mathcal{A}|$")
    ax.set_ylabel("time (ms)")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(3, 300)
    ax.set_ylim(1.3e2, 5.5e3)
    ax.annotate("$|\\mathcal{A}|=6.5d$", xy=(cut, 190), xytext=(0, 0),
                textcoords="offset points", fontsize=5.8,
                color="0.35", ha="center", va="bottom")
    ax.annotate("$13d$", xy=(5.6, 1250), xytext=(0, 0),
                textcoords="offset points", fontsize=6,
                color=FUZZY["color"], ha="left", va="bottom")

    # (d) cost of one further candidate; the search multiplies this by
    # C(|A|, d) candidates, which is what panel (e) plots.
    ax = axes[3]
    pts = marginal_per_candidate(ours)
    if pts:
        ax.plot([q[0] for q in pts], [q[1] for q in pts], **OURS)
    pts_f = points(theirs, "baseline_dec", x="d")
    if pts_f:
        ax.plot([q[0] for q in pts_f], [q[1] for q in pts_f], **FUZZY)
    ax.set_title("(d) per candidate")
    ax.set_xlabel("threshold $d$")
    ax.set_ylabel("time (ms)")
    ax.set_yscale("log")
    ax.set_xlim(1.5, 11)
    ax.set_xticks([2, 4, 6, 8, 10])

    # (e) total cost of one hidden-policy decapsulation: neither side knows
    # the intersection, so both enumerate C(|A|, d) subsets.  Per-candidate
    # costs are the measured medians of (d); the curve is a model over the
    # combinatorial count, not a measured search.
    ax = axes[4]
    marg = dict(marginal_per_candidate(ours))
    base = dict(pts_f)
    if marg.get(int(d_line)) and base.get(int(d_line)):
        aa = list(range(8, 25))
        comb_ = [comb(a, int(d_line)) for a in aa]
        t_pair = 15.03
        ours_tot = [(2 * a * t_pair + c * marg[int(d_line)]) / 1e3
                    for a, c in zip(aa, comb_)]
        fuzzy_tot = [c * base[int(d_line)] / 1e3 for c in comb_]
        ax.plot(aa, ours_tot, **OURS)
        ax.plot(aa, fuzzy_tot, **FUZZY)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ratio = fuzzy_tot[-1] / ours_tot[-1]
        ax.annotate("$%.0f\\times$" % ratio, xy=(aa[-1], fuzzy_tot[-1]),
                    xytext=(-2, 4), textcoords="offset points", fontsize=6,
                    color="0.25", ha="right")
    ax.set_title("(e) full search, $d=5$")
    ax.set_xlabel("receiver attributes $|\\mathcal{A}|$")
    ax.set_ylabel("total time (s)")
    ax.set_xlim(7, 26)
    ax.set_xticks([8, 16, 24])
    ax.xaxis.set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())

    for ax in axes:
        ax.grid(True, which="major", ls=":", lw=0.35, color="0.7")
        ax.tick_params(pad=1.5, length=2.2, width=0.5)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)

    handles = [Line2D([], [], **dict(OURS, label="Silent-Share")),
               Line2D([], [], **dict(FUZZY, label="Fuzzy IB-ME")),
               Line2D([], [], **dict(DENSE, label="Dense (Vandermonde)"))]
    fig.legend(handles=handles, loc="upper center", ncol=3, frameon=False,
               bbox_to_anchor=(0.5, 1.04), handlelength=2.0, columnspacing=1.8)
    fig.tight_layout(pad=0.2, rect=(0, 0, 1, 0.90))

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    fig.savefig(args.out, bbox_inches="tight", pad_inches=0.01)
    print("wrote", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
