# Synthetic evidence evaluation

Measured 2026-10-07T18:22:45.726354+00:00 on Windows-10-10.0.19045-SP0; Python 3.12.14, PostgreSQL 16.2, commit a3db1b4ce104477cb04b2c73b2f55f4c6113d5d4 (dirty=True, schema=0016). Source fingerprint: `5b387aef35f696e3f77e972333054eb289d464962e9f1cd33466529b0d15b5d5`.

All data is synthetic. Six evenly interleaved categories: timely, missing, exempt, late, unfinished-finalized-late and pending. Metrics classify evidence gaps, not physical human entries. The baseline lacks temporal/applicability semantics; timing differences do not prove equal-task speedup. Warm-cache local single-client measurements; no network or field workload.

| Complaints | Baseline precision / recall | SE1 precision / recall | Baseline p50 / p95 ms | SE1 p50 / p95 ms | First / repeat scan ms |
|---:|---:|---:|---:|---:|---:|
| 1,000 | 33.4% / 33.3% | 100.0% / 100.0% | 16.87 / 18.57 | 25.55 / 26.15 | 171.14 / 127.40 |
| 10,000 | 33.3% / 33.3% | 100.0% / 100.0% | 174.87 / 193.07 | 192.09 / 253.05 | 1129.18 / 950.75 |

Raw confusion matrices, per-category results, each sample, row counts and EXPLAIN plans are in results.json. Reproduce from a Python 3.11/3.12 source checkout:

```sh
python scripts/evaluate_temporal.py --sizes 1000 10000 --repeats 5
```

SE2 division, concurrency and authorization correctness are covered separately by the real-PG regression suite. This experiment evaluates SE1 only; it does not benchmark an incremental cache or authenticated instruments.
