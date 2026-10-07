# Synthetic evidence evaluation

Measured 2026-10-07T12:32:14.833651+00:00 on macOS-27.0-arm64-arm-64bit; Python 3.12.11, PostgreSQL 16.2, commit f819d5f7b03a79565e0dd55749ef9f7fd37e9f0e plus working-tree changes described in the PR.

All data is synthetic. Six evenly interleaved categories: timely, missing, exempt, late, unfinished-finalized-late and pending. Metrics classify evidence gaps, not physical human entries. The baseline lacks temporal/applicability semantics; timing differences do not prove equal-task speedup. Warm-cache local single-client measurements; no network or field workload.

| Complaints | Baseline precision / recall | SE1 precision / recall | Baseline p50 / p95 ms | SE1 p50 / p95 ms | First / repeat scan ms |
|---:|---:|---:|---:|---:|---:|
| 1,000 | 33.4% / 33.3% | 100.0% / 100.0% | 0.86 / 0.96 | 4.09 / 4.53 | 41.08 / 24.61 |
| 10,000 | 33.3% / 33.3% | 100.0% / 100.0% | 6.07 / 16.34 | 16.27 / 17.13 | 251.63 / 144.32 |
| 100,000 | 33.3% / 33.3% | 100.0% / 100.0% | 59.44 / 61.56 | 138.31 / 140.57 | 2435.54 / 1554.84 |

Raw confusion matrices, per-category results, each sample, row counts and EXPLAIN plans are in results.json. Reproduce from a Python 3.11/3.12 source checkout:

```sh
python scripts/evaluate_temporal.py --sizes 1000 10000 100000 --repeats 7
```

SE2 division, concurrency and authorization correctness are covered separately by the real-PG regression suite. This experiment evaluates SE1 only; it does not benchmark an incremental cache or authenticated instruments.
