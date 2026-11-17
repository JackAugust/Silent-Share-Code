# Silent-Share

Reference implementation and measurement artifact for

> **Silent-Share: Decoupling Pairing-Based Authorization from Hidden-Policy
> Size in Bilateral Threshold Matching**

Silent-Share is a two-message bilateral hidden-policy threshold matching
protocol. Two independent one-sided PB-KEM instances are composed, each policy
is encoded as a sparse group-valued OKVS whose values live directly in the
pairing source group, and the two directions are bound into one session key by a
KDF plus an HMAC-SHA256 confirmation tag. Consequently

* a receiver that holds `|A|` attributes performs exactly `2|A|` pairings, no
  matter how large the hidden policy `|P|` or the threshold `d` is;
* the policy is never stored or sent in the clear;
* attributes of different users cannot be combined: a match requires `d`
  attributes **of a single identity**.

All measurements use the BN254 asymmetric pairing curve (Charm-Crypto 0.50).

---

## 1. Layout

| Path | Contents |
|---|---|
| `src/silent_share.py` | One-sided PB-KEM, bilateral composition, KDF/HMAC binding, published salt index `J_enc` |
| `src/sparse_gokvs.py` | Sparse group-valued OKVS: peeling encoder, `joint_encode` for the two correlated vectors, `ρ`-bucket decoder |
| `src/okvs.py` | Dense Vandermonde GOKVS and scalar OKVS (dense path and baselines) |
| `src/fuzzy_ibme.py` | Fuzzy IB-ME baseline on BN254, ported to the same parameter grid |
| `src/search.py` | Candidate enumeration orders (lexicographic, permutation hash) |
| `src/hashdom.py` | Domain-separated hashing: row seeds, salt chain `salt_b = H_s(salt_0‖b)`, attribute points |
| `src/stats.py`, `src/utils.py` | Timing, percentiles, CSV helpers |
| `src/config.py` | Curve, GOKVS parameters (`ρ`, `α`, retry budget `B = 384`), benchmark grids |
| `src/main.py` | Dispatcher for the component benchmarks (`--bench gokvs|sparse_gokvs|sparse_param|one_sided|reconstruction|bilateral|all`) |
| `src/benchmarks/` | `gokvs_bench`, `sparse_gokvs_bench`, `sparse_gokvs_param_bench`, `one_sided_bench`, `reconstruction_bench`, `bilateral_bench` |
| `src/sim/external_game.py` | Executable model of the bilateral policy-hiding game, used by the tests |
| `src/g2_exp_bench.py` | G2 exponentiation / pairing microbenchmark (`T_pair`) |
| `experiments/run_all.py` | Main matrix: `raw_all`, `summary`, `scaling_fit`, `order_leak`, `skipped`, `manifest.json` |
| `experiments/decap_hint_sweep.py` | Decapsulation at `|A| = 10`, `|P| = 50…800` (flatness in `|P|`) |
| `experiments/peel_sweep.py` | First-salt peeling rate with Wilson intervals (Table 5) |
| `experiments/peel_rate.py` | Peelability without Charm, one row per `n` and `α` |
| `experiments/run_compare.py` | Matched points against fuzzy IB-ME |
| `experiments/run_crossover.py` | Attribute counts above the `2|A| = 13d` crossover |
| `experiments/bilateral_breakdown.py` | Per-stage breakdown derived from `results/bilateral.csv` |
| `experiments/plot_comparison.py` | Figure 1 (five panels) |
| `experiments/derive_paper_numbers.py` | Derived quantities quoted in the text, printed to stdout |
| `experiments/check_paper_numbers.py` | Asserts every number quoted in the paper against the CSVs |
| `results/` | Canonical per-repetition data (§4) |
| `results_compare/`, `results_crossover/` | Supplementary batches for §7.4 and the crossover study |
| `tests/` | `test_gokvs`, `test_search`, `test_stats`, `test_external_game` |
| `LICENSE` | Apache License 2.0 |

## 2. Requirements

Experiments were run on Ubuntu 20.04.1 LTS with Python 3.6.13,
Charm-Crypto 0.50 (BN254), PBC 0.5.14, OpenSSL 1.1.1n, GMP 6.2.1, plus
`psutil`, `pandas` and `matplotlib`.

Charm and PBC are needed only for timing runs. The peeling study, the
search-order study, the plotting script and the number checker run on a plain
Python installation. The code avoids Python 3.7+ constructs such as `math.comb`.

## 3. Quick start

```bash
python experiments/run_all.py --list            # print the matrix, run nothing
python experiments/run_all.py --self-test       # no Charm: peeling and order study
python experiments/run_all.py --profile smoke   # ~1 minute sanity run
python experiments/run_all.py                   # full paper profile (needs Charm)
python src/main.py --bench bilateral            # single component benchmark
```

## 4. Reproducing the paper

Section, figure and table numbers refer to the current manuscript.

| Paper item | Command | Output |
|---|---|---|
| Fig. 1(a)–(e) | `python experiments/plot_comparison.py` | `../Silent-Share/Figs/fig_comparison.pdf` |
| Table 4 (cost decomposition) | `python experiments/derive_paper_numbers.py` | stdout, read from `results/raw_all.csv` |
| Table 5 (first-salt rate, Wilson CI) | `python experiments/peel_sweep.py` | `results/peel_sweep.csv` |
| §7.1 setup, hardware, `T_pair` | `python src/g2_exp_bench.py` | stdout |
| §7.2 theoretical cost model | — | closed form, no data |
| §7.3 flatness in `|P|` | `python experiments/decap_hint_sweep.py` | `results/decap_hint_sweep.csv` |
| §7.4 comparison with fuzzy IB-ME | `python experiments/run_compare.py` | `results_compare/raw_all.csv` |
| §7.4 crossover above `2|A| = 13d` | `python experiments/run_crossover.py` | `results_crossover/raw_all.csv` |
| §7.5 blind search, rejection path | `python experiments/run_all.py` | `results/raw_all.csv`, `order=prh` |
| Eq. (cost model) scaling exponents | `python experiments/run_all.py` | `results/scaling_fit.csv` |
| App. A dense vs sparse encoding | `python src/main.py --bench sparse_gokvs` | `results/sparse_gokvs.csv`, `results/gokvs_group.csv` |
| App. B error accounting | `python experiments/check_paper_numbers.py` | printed PASS/FAIL |
| Correctness (accept/reject, tampering) | `python experiments/run_all.py` | `results/raw_all.csv`, `mode=correct` |
| Unit tests | `python -m pytest tests -q` | pass/fail |

## 5. Data files

One row per repetition; every row carries `commit`, `curve` and `run_id`.
Medians over the repetitions of a configuration are what the paper quotes.

| File | Rows | Produced by | Content |
|---|---|---|---|
| `results/raw_all.csv` | 151 | `run_all.py` | Authoritative table. `mode` ∈ `encap`, `decap`, `bilateral`, `baseline_enc`, `baseline_dec`, `correct`; `order` ∈ `sparse`, `dense`, `hint`, `prh`; stage times, `trials`, `budget_exhausted`, `success`, `false_accept`, `ct_bytes`, `sk_bytes` |
| `results/summary.csv` | 35 | `run_all.py` | One row per configuration: `p50/p95/p99_ms`, success and false-accept rates, `trials_mean` |
| `results/decap_hint_sweep.csv` | 25 | `decap_hint_sweep.py` | `|A| = 10`, `d = 5`, `|P| = 50…800`: total, pairing, decode and reconstruction times |
| `results/peel_sweep.csv` | 40 | `peel_sweep.py` | Per `n`: `m`, `p1`, Wilson interval, `mean_salts`, failures within 20 salts |
| `results/scaling_fit.csv` | 4 | `run_all.py` | Empirical log–log exponent and `R²` per series, no assumed shape |
| `results/order_leak.csv` | 400 | `run_all.py` | Candidate rank vs. attribute-index sum, lexicographic vs. permutation hash |
| `results/skipped.csv` | 2 | `run_all.py` | Cases the time budget refused, with the reason |
| `results/one_sided.csv` | 200 | `main.py --bench one_sided` | Per-stage counters of the one-sided primitive |
| `results/reconstruction.csv` | 176 | `main.py --bench reconstruction` | `d`, `|A|`, scenario, wall time, number of combinations |
| `results/bilateral.csv` | 320 | `main.py --bench bilateral` | `nO`, `nR`, per-stage times, salt trials, ciphertext and communication bytes |
| `results/bilateral_breakdown.csv` | 64 | `bilateral_breakdown.py` | Per-stage summary derived from `bilateral.csv` |
| `results/sparse_gokvs.csv` | 10 | `main.py --bench sparse_gokvs` | Sparse encoder/decoder microbenchmark |
| `results/sparse_gokvs_param.csv` | 1080 | `main.py --bench sparse_param` | Sweep over `ρ` and `m/n`: peel success, encode and decode time |
| `results/gokvs_group.csv` | 20 | `main.py --bench gokvs` | Dense group-valued OKVS throughput |
| `results/gokvs_scalar.csv` | 10 | `main.py --bench gokvs` | Scalar OKVS throughput |
| `results/manifest.json` | — | `run_all.py` | Host, CPU, curve, microbenchmarks, seed, sizes |
| `results_compare/raw_all.csv` | 26 | `run_compare.py` | Fuzzy IB-ME at `n ∈ {5,10,30,50,100,200}` (`d = 5`) and `d ∈ {2,3,4,5,6,8,10}` (`n = 30`), plus Silent-Share at `|A| = 30` over the same `d` |
| `results_crossover/raw_all.csv` | 15 | `run_crossover.py` | `|A| ∈ {40,50,60,80,100}` above the crossover |

`run_all.py --only <case>` writes a timestamped batch directory; those batches
are scratch output and are not part of this artifact.

## 6. Measurement conventions

1. **A hint is passed explicitly.** `order=hint` rows reconstruct with the
   correct `d`-subset supplied. They are not blind-search latency and are never
   described as such.
2. **No-hint rows are searches.** `order=prh` rows carry `trials` and
   `budget_exhausted`; an exhausted budget counts as a failed run, never as a
   success. The paper's budget is 5000 candidates.
3. **Decapsulation figures in the paper are per salt trial.** A row's
   `total_ms` covers every salt attempt it performed; dividing by
   `summary.csv:trials_mean` gives the single-trial figure the paper quotes,
   and `E[J_try] = 1/p1 = 2.87` converts it to an expected end-to-end cost.
4. **`pairing_ms` is the authorization cost.** `total_ms` adds GOKVS decoding
   and hidden-threshold reconstruction; the three are reported separately.
5. **Only the cryptographic operations of interest are timed**, with identical
   conventions for Silent-Share and fuzzy IB-ME, so ratios at equal parameters
   are comparable.
6. **Panel (e) of Fig. 1 is a model, not a measurement**: measured per-candidate
   medians multiplied by the candidate count `C(|A|, d)`.

## 7. Parameters and security numbers

| Quantity | Value | Where |
|---|---|---|
| Curve | BN254, 254-bit base field | `src/config.py` |
| Sparse encoder | `ρ = 3`, `α = 1.25`, `M = ⌈1.25n⌉`, dense below `n₀ = 10` | `src/config.py` |
| Retry budget | `B = 384`, published index `J_enc ∈ {0…B} ∪ {⊥}`, 9 bits | `config.py`, `silent_share.py` |
| First-salt rate at `n = 100` | `p1 = 0.349`; at `n = 12`, `p1 = 0.235` | `results/peel_sweep.csv` |
| Peel failure bound | `(1-p1)^B = 2^-134` at `B = 384`, `2^-89` at `B = 256` | App. B.8 |
| Candidate count at `|A| = 10`, `d = 5` | `C(10,5) = 252`; largest configuration `142506` | Table 4, §7.5 |
| Expected trials / candidates | `E[J_try] = 2.87`, `E[J_enc] = 1.87`, `E[R] = 36.1` | Table 4 |

An encoder that exhausts `B` salts publishes a uniform dummy vector rather than
aborting, so the ciphertext distribution does not reveal the failure.

## 8. Consistency check

`experiments/check_paper_numbers.py` binds every number quoted in the
manuscript to the file and column it comes from and exits non-zero on drift:

```bash
python experiments/check_paper_numbers.py
```

It covers the decapsulation sweep, the `|A| = 5…30` totals, the whole Table 5
peeling row set, the fuzzy IB-ME comparison points, the encapsulation range,
both ciphertext densities and the bilateral communication sizes. Re-run it after
any experiment batch; if the paper is updated instead, update the expected value
in the same commit.

## 9. Baseline

`src/fuzzy_ibme.py` is a port of the JPBC Type-A fuzzy IB-ME construction to
Charm/BN254, re-parameterized to the same policy sizes, thresholds and
repetition counts. It pays `13d` pairings per candidate, which is why its cost
is set by `d` rather than by `|A|` and why it repeats for every candidate.

## 10. License

Apache License 2.0, see `LICENSE`.
