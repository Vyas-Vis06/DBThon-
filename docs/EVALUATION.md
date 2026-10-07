# Evaluation

**Authoritative for:** how ZeroEntry is measured against stated baselines, what the measurements mean and what they do not
prove. The generated tables and run metadata are in [EVALUATION_RESULTS.md](EVALUATION_RESULTS.md); the supplementary
temporal experiment is in [evaluation/RESULTS.md](evaluation/RESULTS.md). How this answers the DBThon brief is in
[SUBMISSION.md](SUBMISSION.md). Results apply to the exact code, data and machine identified in each run; do not carry old
latencies or metrics forward after a code or fixture change.

## Reproduce

```bash
python scripts/evaluate.py                                   # full run; rewrites docs/EVALUATION_RESULTS.md
python scripts/evaluate.py --sizes 1000 --per-class 5 --out - # small run; printed only
```

The script starts its own throwaway embedded PostgreSQL in a temporary directory, migrates it through the normal Alembic path
and deletes it at the end. It never touches `.pgdata` or any other database. All data is synthetic. Rows are built by
`tests/factories.py` and `eval_add_history()` through the gate; narrowly scoped, owner-only receipt backfills import
historical examples after those checks. The live runtime cannot supply these receipts. The E2 baseline deliberately
disables selected rule triggers in rolled-back experiments to measure the stated comparison.
`tests/db/test_evaluation.py` runs the same code at a tiny scale on every CI run and asserts the counts, never the timings.

## What is compared

| | Question | ZeroEntry | Conventional baseline | Metric |
|---|---|---|---|---|
| E1 | Do the configured detection rules identify labelled missing-clearance evidence states? | `scan_shadow_entries()` (SE1 + SE2, grace window, exemptions as data, persisted alerts) | the job-anchored anti-join in the team's original proposal ([proposal §6.3c](proposal/ZeroEntry_DBThon2026_Proposal.md#63-the-four-signature-queries)) | precision, recall and F1 against synthetic evidence-gap labels; handling of late evidence |
| E2 | Do selected database invariants refuse invalid writes that bypass the UI? | the full schema and database guards | the same schema with the rule triggers disabled ([`rules_in_app_code.sql`](../database/evaluation/rules_in_app_code.sql)) | refusal outcome for each invalid write probe |
| E3 | How do these operations scale on the generated history, and what work do indexes/materialized parameters avoid? | `authorise_entry()` and `scan_shadow_entries()` at increasing synthetic history sizes | the same query logic without selected indexes; the semantically equivalent detection view without the M6 materialized parameter CTE; the stated naive query | median/p95 latency and shared buffers (`EXPLAIN (ANALYZE, BUFFERS)`) |
| E4 | Do the tested concurrent writes preserve permit invariants? | current entry gate and permit-locking implementation | the pre-lock race cases recorded in the tests and development log | whether the tested races can commit an inconsistent authorization/evidence state |

### E1 method

The generator creates labelled complaint/evidence cases for timely evidence, retries, exempt resolutions, the grace window,
missing evidence, absent jobs, failed-only deployments and entrants without logs. It also adds late evidence between scans.
The generated tables list the actual class counts and confusion matrices. A label is the expected result under the configured
evidence rules; it is not ground truth about whether a worker physically entered a sewer. The baseline is the team's earlier
query, not a survey or benchmark of a deployed product.

### E2 method

Each probe builds a valid starting fixture, breaks one database-enforced invariant, attempts the corresponding invalid write,
and rolls back. The generated report names the probes and outcomes. These are tests of stored authorization and record
integrity; a refused authorization write does not prove physical access was blocked. It also does not justify refusing a real
exit, evacuation or rescue record: the safety lifecycle separately preserves truthful exits and records overruns. Probes run
as the table owner, which bypasses row-level security but still exercises database triggers; role-specific access is tested
separately in `tests/db/test_rls.py` and `tests/db/test_privileges.py`.

### E3 method

`eval_add_history(n)` ([`evaluation.sql`](../database/evaluation/evaluation.sql)) creates synthetic history through the real
constraints and triggers, including permits, crew, gear, readings and entries. The fixture's receipt and event times are
generated under the current temporal rules; the result file records row counts. After each growth step, the script analyzes
the data, warms the operation and takes repeated measurements, rolling back timed writes so each repetition starts from the
same state. Index and pre-optimization comparisons use the same workload; the pre-M6 view must preserve the final temporal
view's semantics and differ only by the materialization change.

## Results

Use the per-class, per-rule, size and plan tables in [EVALUATION_RESULTS.md](EVALUATION_RESULTS.md) together with their run
metadata. The M6 historical run predates the safety, temporal-evidence and policy-provenance migrations; use measurements only
when the recorded commit and schema match the release being described. Results are workload-specific: the more complete
temporal and applicability checks may cost more than a simpler anti-join. The M6 optimization materializes the one-row
parameter CTE in the final SE1/SE2 views; the comparison should hold temporal view semantics fixed and quantify only that
query-plan change.

The supplementary [temporal benchmark](evaluation/RESULTS.md) has a separate workload and baseline: its baseline deliberately
lacks the time and applicability semantics evaluated by SE1. Treat it as an evidence-gap/temporal experiment, not an equal-task
speed comparison or a substitute for E1-E4. Its run metadata identifies the measured commit, machine and data.

## What the evaluation does not prove

* **Synthetic data.** E1 measures fidelity to configured evidence-gap labels, not physical-entry truth or accuracy on real ULB
  records. Real-world performance depends on source-system coverage and the correctness of records; a read-only pilot is next.
* **The baselines are bounded.** The naive anti-join is the team's earlier proposal, not an industry-wide query benchmark. The
  E2 baseline models rules enforced only in one application while other database clients can write directly; it is not a
  comparison against every production system.
* **One machine, default settings.** Timings come from one development laptop running the embedded PostgreSQL 16 with default
  settings and a warm local cache. Buffer counts and wall times depend on dataset, schema and hardware and are not production
  capacity guarantees.
* **The scan is a full pass.** It re-evaluates eligible resolved complaints; it is not an incremental event-driven cache.
* **Outcomes.** Nothing here measures actual entries, worker behavior, deaths prevented or compensation paid; those require a
  deployment and independent field evaluation.
