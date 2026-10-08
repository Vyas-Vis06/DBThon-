# Synthetic evidence evaluation

Measured 2026-10-08T01:30:39.517436+00:00 on Windows-10-10.0.19045-SP0; Python 3.12.14, PostgreSQL 16.2, commit f68bbfa22b8fcb4267827ef598d10683d0dae51c (dirty=True, schema=0016). Source fingerprint: `0240705c066dddbea5cc5d0f2c452b2e5a6eaeda022071a9ec6c9af608504a06`.

All data is synthetic. Six evenly interleaved categories: timely, missing, exempt, late, unfinished-finalized-late and pending. Metrics classify evidence gaps, not physical human entries. The baseline lacks temporal/applicability semantics; timing differences do not prove equal-task speedup. Warm-cache local single-client measurements; no network or field workload.

| Complaints | Baseline precision / recall | SE1 precision / recall | Baseline p50 / p95 ms | SE1 p50 / p95 ms | First / repeat scan ms |
|---:|---:|---:|---:|---:|---:|
| 1,000 | 33.4% / 33.3% | 100.0% / 100.0% | 16.76 / 17.14 | 112.09 / 129.44 | 176.08 / 127.42 |
| 10,000 | 33.3% / 33.3% | 100.0% / 100.0% | 485.56 / 556.65 | 183.65 / 442.67 | 1226.96 / 994.24 |

Raw confusion matrices, per-category results, each sample, row counts and EXPLAIN plans are in results.json. Reproduce from a Python 3.11/3.12 source checkout:

```sh
python scripts/evaluate_temporal.py --sizes 1000 10000 --repeats 5
```

SE2 division, concurrency and authorization correctness are covered separately by the real-PG regression suite. This experiment evaluates SE1 only; it does not benchmark an incremental cache or authenticated instruments.
