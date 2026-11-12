# Silent-Share

Reference implementation and measurement artifact for **Silent-Share: Decoupling
Pairing-Based Authorization from Hidden-Policy Size in Bilateral Threshold
Matching**.

Silent-Share is a two-message bilateral hidden-policy threshold matching
protocol. It composes two independent one-sided PB-KEM instances, encodes policy
attributes in a sparse group-valued OKVS, and binds the encoded values to
per-user polynomials, so that

* the pairing cost of a receiver is `2|A|`, independent of the policy size `|P|`
  and of the threshold `d`;
* the policy is never stored or transmitted in the clear;
* attributes of different users cannot be combined: a match needs `d` matching
  attributes **of one user**.

All measurements use the BN254 asymmetric pairing curve.

**Code:** https://anonymous.4open.science/r/SilentShare/

---

## 1. What is in this repository

| Path | Contents |
|---|---|
| `src/silent_share.py` | One-sided PB-KEM, bilateral composition, HKDF/AES-GCM binding |
| `src/sparse_gokvs.py` | Sparse group-valued OKVS (peeling encoder, constant-time decode) |
| `src/okvs.py` | Dense Vandermonde GOKVS and scalar OKVS baselines |
| `src/fuzzy_ibme.py` | Fuzzy IB-ME baseline on BN254 (comparison scheme) |
| `src/search.py` | Candidate enumeration orders (lexicographic vs. permutation-hash) |
| `src/hashdom.py` | Hash-to-exponent domain separation |
| `src/stats.py`, `src/utils.py` | Timing, percentile, CSV helpers |
| `src/config.py` | Curve and benchmark defaults |
| `src/main.py` | Dispatcher for the standard benchmarks below |
| `src/benchmarks/` | GOKVS, sparse-parameter, one-sided, reconstruction and bilateral benchmarks |
| `src/sim/external_game.py` | Simulation of the bilateral policy-hiding game (used by the tests) |
| `src/g2_exp_bench.py` | Single G2 exponentiation microbenchmark |
| `experiments/run_all.py` | Main measurement matrix (paper profile, smoke profile, self-test) |
| `experiments/run_compare.py` | Baseline points at matched policy sizes and thresholds |
| `experiments/run_crossover.py` | Measurements above the `2\|A\| = 13d` crossover |
| `experiments/peel_rate.py` | Peelability of the sparse hypergraph (no Charm required) |
| `experiments/plot_comparison.py` | Figure 1 (five panels) |
| `experiments/derive_paper_numbers.py` | Derived quantities quoted in the text |
| `results/` | Per-repetition CSV data (see §4) |
| `results_compare/`, `results_crossover/` | Supplementary measurement batches |
| `tests/` | Unit tests (OKVS, search, statistics, external game) |

The repository holds only the code and the measured data behind the current
paper; earlier experiment drivers and aggregated outputs are not included.
The `commit` column in the CSVs records the development commit at measurement
time, so it is a run label in this snapshot rather than a link into a public
history.

## 2. Environment

Experiments were run on:

* Ubuntu 20.04.1 LTS
* Python 3.6.13 (the code avoids 3.7+ constructs such as `math.comb`)
* Charm-Crypto 0.50 with the BN254 curve
* PBC 0.5.14, OpenSSL 1.1.1n, GMP 6.2.1
* `psutil`, `pandas`, `matplotlib`

`CURVE = "BN254"` is set in `src/config.py`. Charm and PBC are only needed for
timing runs; the peeling study, the search-order study and all plotting run on a
plain Python installation.

```bash
python experiments/run_all.py --self-test   # no Charm: 200 subsets, order study
python experiments/run_all.py --list        # print the matrix, run nothing
python experiments/run_all.py --profile smoke   # ~1 minute sanity run
python experiments/run_all.py               # full paper profile
```

## 3. Reproducing the paper

| Paper item | Command | Output |
|---|---|---|
| Fig. 1(a)–(e) | `python experiments/plot_comparison.py` | `../Silent-Share/Figs/fig_comparison.pdf` |
| Fig. 1 medians (appendix table) | `python experiments/derive_paper_numbers.py` | stdout, read from `results/raw_all.csv` |
| Table 4 (peeling, `p1`/`E[b]`/fail) | `python experiments/peel_rate.py --trials 300` | stdout (one row per `n`, per `alpha`) |
| §7.3 scaling exponents | — | `results/scaling_fit.csv` |
| §7.4–§7.5 encapsulation, decapsulation, ciphertext size | `python experiments/run_all.py` | `results/raw_all.csv`, `results/summary.csv` |
| §7.5 hidden-policy search (no hint) | `python experiments/run_all.py` (profile `paper`) | `results/raw_all.csv`, `mode=decap_nohint` |
| §7.6 bilateral protocol | `python experiments/run_all.py` | `results/bilateral.csv` |
| §7.7 crossover above `2\|A\| = 13d` | `python experiments/run_crossover.py` | `results_crossover/raw_all.csv` |
| Baseline at matched `\|P\|` and `d` | `python experiments/run_compare.py` | `results_compare/raw_all.csv` |
| Correctness (accept/reject) | `python experiments/run_all.py` | `results/raw_all.csv`, `correctness` block |
| Unit tests | `python -m pytest tests -q` | pass/fail |

## 4. Data files

One row per repetition; every row carries the git `commit` and the pairing
`curve`. Unless noted, medians over five repetitions are what the paper quotes.

| File | Rows | Content |
|---|---|---|
| `results/raw_all.csv` | 181 | Authoritative table: `mode` (`encap`, `decap`, `decap_nohint`, `bilateral`, `baseline_dec`), `order` (`hint`/`lex`/`prh`), `n_attr`, `d`, `n_policy`, `overlap`, `pairing_ms`, `gokvs_decode_ms`, `recon_ms`, `total_ms`, `trials`, `budget_exhausted`, `success`, `false_accept`, `ct_bytes`, `sk_bytes`, `comm_bytes` |
| `results/summary.csv` | 32 | One row per configuration: `p50_ms`, `p95_ms`, `p99_ms`, success/false-accept/search-fail rates, sizes |
| `results/scaling_fit.csv` | 4 | Empirical log–log exponent and `R^2` per series (no assumed shape) |
| `results/order_leak.csv` | 400 | Candidate rank vs. attribute-index sum, lexicographic vs. permutation hash |
| `results/bilateral.csv` | 320 | `nO`, `nR`, per-stage wall/CPU times, GOKVS and decode components, ciphertext and communication bytes |
| `results/one_sided.csv` | 200 | Per-stage counters (setup, keygen, encapsulation, decode, pairing, reconstruction) for the one-sided primitive |
| `results/reconstruction.csv` | 176 | Threshold reconstruction: scenario, `d`, `\|A\|`, wall time, number of combinations |
| `results/sparse_gokvs.csv` | 10 | Sparse encoder/decoder microbenchmark |
| `results/sparse_gokvs_param.csv` | 1080 | Parameter sweep over `rho` and `m/n`: peel success, encode and decode time |
| `results/gokvs_group.csv` | 20 | Group-valued (dense) OKVS encode/decode throughput |
| `results/gokvs_scalar.csv` | 10 | Scalar OKVS encode/decode throughput |
| `results/skipped.csv` | 1 | Cases refused by the time budget, with the reason (never silently truncated) |
| `results/only_20261112-123854/` | 45 | The no-hint `d`-sweep batch that was merged into `raw_all.csv`, kept for provenance |
| `results_compare/raw_all.csv` | 26 | Matched points behind Fig. 1(a)–(d): baseline encapsulation and decapsulation at `n ∈ {5,10,30,50,100,200}` (`d = 5`), baseline at `d ∈ {2,3,4,5,6,8,10}` (`n = 30`), and Silent-Share at `\|A\| = 30` over the same `d` values |
| `results_crossover/raw_all.csv` | 15 | `\|A\| ∈ {40,50,60,80,100}` above the crossover |

## 5. Measurement conventions

These rules are enforced by the harness and matter when reading the CSVs:

1. **A hint is passed explicitly.** `order=hint` rows measure reconstruction with
   the correct `d`-subset supplied. They are *not* full decapsulation latency and
   are never described as such.
2. **No-hint rows are searches.** They carry `trials` and `budget_exhausted`; an
   exhausted budget counts as a failed run, never as a success. The paper's
   budget is 5000 candidates.
3. **`pairing_ms` is the authorization cost.** `total_ms` adds GOKVS decoding and
   hidden-threshold reconstruction. The two are reported separately and never
   merged into one claim.
4. **Only cryptographic operations of interest are timed**, with identical
   conventions for Silent-Share and for the fuzzy IB-ME baseline, so the ratios
   are comparable at equal parameters.
5. **Panel (e) of Fig. 1 is a model, not a measurement**: measured per-candidate
   medians multiplied by the worst-case candidate count `C(|A|, d)`.

## 6. Baseline

`src/fuzzy_ibme.py` is a port of the JPBC Type-A fuzzy IB-ME construction to
Charm/BN254, re-parameterized to the same policy sizes, thresholds and repetition
counts. It pays `13d` pairings per candidate, which is why its cost is flat in
`|A|` but repeated for every candidate.

## 7. License

Apache License 2.0; see `LICENSE`.
