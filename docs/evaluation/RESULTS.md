# Synthetic evidence evaluation

Measured 2026-10-07T12:45:35.147859+00:00 on macOS-27.0-arm64-arm-64bit; Python 3.12.11, PostgreSQL 16.2, commit 6c55b377919759fe1ddc02f3c1ac4774df9379c1 plus working-tree changes described in the PR.

All data is synthetic. Six evenly interleaved categories: timely, missing, exempt, late, unfinished-finalized-late and pending. Metrics classify evidence gaps, not physical human entries. The baseline lacks temporal/applicability semantics; timing differences do not prove equal-task speedup. Warm-cache local single-client measurements; no network or field workload.

| Complaints | Baseline precision / recall | SE1 precision / recall | Baseline p50 / p95 ms | SE1 p50 / p95 ms | First / repeat scan ms |
|---:|---:|---:|---:|---:|---:|
| 1,000 | 33.4% / 33.3% | 100.0% / 100.0% | 0.94 / 1.03 | 4.34 / 4.42 | 40.24 / 25.53 |
| 10,000 | 33.3% / 33.3% | 100.0% / 100.0% | 5.88 / 16.37 | 16.11 / 16.66 | 264.34 / 143.52 |
| 100,000 | 33.3% / 33.3% | 100.0% / 100.0% | 60.44 / 61.48 | 140.88 / 142.18 | 2460.04 / 1526.75 |

Raw confusion matrices, per-category results, each sample, row counts and EXPLAIN plans are in results.json. Reproduce from a Python 3.11/3.12 source checkout:

```sh
python scripts/evaluate_temporal.py --sizes 1000 10000 100000 --repeats 7
```

SE2 division, concurrency and authorization correctness are covered separately by the real-PG regression suite. This experiment evaluates SE1 only; it does not benchmark an incremental cache or authenticated instruments.
