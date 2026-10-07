# Synthetic evidence evaluation

Measured 2026-10-07T12:06:46.559695+00:00 on macOS-27.0-arm64-arm-64bit; Python 3.12.11, PostgreSQL 16.2, commit e8632699e85c4167940194649444d45ff5537621 plus working-tree changes described in the PR.

All data is synthetic. Six evenly interleaved categories: timely, missing, exempt, late, unfinished-finalized-late and pending. Metrics classify evidence gaps, not physical human entries. The baseline lacks temporal/applicability semantics; timing differences do not prove equal-task speedup. Warm-cache local single-client measurements; no network or field workload.

| Complaints | Baseline precision / recall | SE1 precision / recall | Baseline p50 / p95 ms | SE1 p50 / p95 ms | First / repeat scan ms |
|---:|---:|---:|---:|---:|---:|
| 1,000 | 33.4% / 33.3% | 100.0% / 100.0% | 0.98 / 1.02 | 6.10 / 6.34 | 45.97 / 30.62 |
| 10,000 | 33.3% / 33.3% | 100.0% / 100.0% | 6.02 / 17.17 | 42.37 / 42.90 | 309.76 / 212.52 |
| 100,000 | 33.3% / 33.3% | 100.0% / 100.0% | 63.03 / 65.95 | 451.00 / 627.16 | 4326.30 / 2377.25 |

Raw confusion matrices, per-category results, each sample, row counts and EXPLAIN plans are in results.json. Reproduce from a Python 3.11/3.12 source checkout:

```sh
python scripts/evaluate.py --sizes 1000 10000 100000 --repeats 7
```

SE2 division, concurrency and authorization correctness are covered separately by the real-PG regression suite. This experiment evaluates SE1 only; it does not benchmark an incremental cache or authenticated instruments.
