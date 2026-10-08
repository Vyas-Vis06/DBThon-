# Synthetic evidence evaluation

Measured 2026-10-08T01:25:31.093473+00:00 on Windows-10-10.0.19045-SP0; Python 3.12.14, PostgreSQL 16.2, commit 1876ffa6acedfa10bab97a53c55a3085cf338416 (dirty=True, schema=0016). Source fingerprint: `97e55be1c0bf21968b569c78c865f1c543dd43d38535404568e4305ef7b46301`.

All data is synthetic. Six evenly interleaved categories: timely, missing, exempt, late, unfinished-finalized-late and pending. Metrics classify evidence gaps, not physical human entries. The baseline lacks temporal/applicability semantics; timing differences do not prove equal-task speedup. Warm-cache local single-client measurements; no network or field workload.

| Complaints | Baseline precision / recall | SE1 precision / recall | Baseline p50 / p95 ms | SE1 p50 / p95 ms | First / repeat scan ms |
|---:|---:|---:|---:|---:|---:|
| 1,000 | 33.4% / 33.3% | 100.0% / 100.0% | 17.69 / 21.07 | 25.81 / 27.33 | 182.93 / 130.96 |
| 10,000 | 33.3% / 33.3% | 100.0% / 100.0% | 197.32 / 227.92 | 179.93 / 313.48 | 1267.95 / 1036.44 |

Raw confusion matrices, per-category results, each sample, row counts and EXPLAIN plans are in results.json. Reproduce from a Python 3.11/3.12 source checkout:

```sh
python scripts/evaluate_temporal.py --sizes 1000 10000 --repeats 5
```

SE2 division, concurrency and authorization correctness are covered separately by the real-PG regression suite. This experiment evaluates SE1 only; it does not benchmark an incremental cache or authenticated instruments.
