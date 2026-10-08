# ZeroEntry integration and judge handoff

## What was retained

The downloaded repository is a substantial working foundation, not a scaffold. All 168 downloaded files matched
upstream commit `a3db1b4ce104477cb04b2c73b2f55f4c6113d5d4`. Before extensions, the independent Windows/embedded
PostgreSQL run passed 574 tests in 104.47 seconds. Preserve its real migrations, database guards, late-evidence review,
source-specific financial holds, transactional request lifetime and no-build strict-CSP interface.

Implementation was developed in a separate Git checkout to preserve the Desktop download during review. After final
verification, the authorized release is copied into the Desktop folder and published on a separate branch. The integration uses
three GPT-6 Luna lanes. The full process and adapted account instructions are
[the contract](INTEGRATION_CONTRACT.md), [database lane](WORKER_A_EXECUTION.md),
[backend lane](WORKER_B_EXECUTION.md) and [interface lane](WORKER_C_EXECUTION.md).

## Bounded novelty statement

Existing electronic permit systems already have competency, gas and approval controls. Municipal systems already
have work orders and workforce records. The claim here is a demonstrable composition: recorded actual participation,
current evidence and shared resources determine database authorization; denied as well as passing decisions are
retained; outside closure claims remain separate; missing evidence leads to human review and source-specific holds;
unregistered multi-victim incidents can be recorded atomically. Do not claim global first use, certified physical
prevention or deaths prevented. See [the source review](../POLICY_AND_PRIOR_ART.md) and
[expanded research](../plan/REVIEW_AND_EVIDENCE.md).

## Start and verify

Use Python 3.11 or 3.12. The normal start remains `python scripts/dev.py`; it migrates its local embedded PostgreSQL,
seeds synthetic records and serves `http://127.0.0.1:8000`. Passwords printed at local startup are not portable
credentials. Do not expose this development server to the Internet. For existing PostgreSQL use
[SETUP](../SETUP.md), and do not reset a teammate's database.

Install development dependencies with `python -m pip install -e ".[dev]"`. For real-browser tests add
`python -m pip install -e ".[dev,browser]"` and `python -m playwright install chromium`.
The ordinary suite uses `python -m pytest -n auto`; limit xdist workers on a small laptop.
The release proof command `python scripts/verify_release.py --workers 4` binds the entire run to unchanged sources.
For the presentation, follow [DEMO_SCRIPT](DEMO_SCRIPT.md), including the authenticated educational
`scripts/prepare_demo.py` helper rather than attempting to turn the real-scope seeded denial into permission.
Generated schema/API documentation must be refreshed with `python scripts/gen_docs.py` after migrations/routes change.

## Presentation order

1. Explain sanitation safety evidence consistency and the actual-participant gap. Missing records are suspicious,
   not proof of physical entry.
2. Show ER design, relational keys and constraints; show personal versus site equipment rather than requiring all
   catalogue items for each person.
3. Show the real scope's `REVIEW_REQUIRED` denial even with complete PPE. Switch only to the clearly marked
   educational fixture for a successful end-to-end demonstration.
4. Remove one acknowledgment/readiness/channel: inspect the denied receipt. Restore explicit evidence and authorize.
   Show the digest, revision, earliest expiry and original source classifications.
5. Attempt simultaneous reuse of a standby person or serial asset. The database refuses conflicting occupancy.
   Introduce adverse evidence; show stopped permission while truthful exits remain recordable.
6. Import a municipal completion claim that has no matching job or disagrees with evidence. Show reconciliation
   alongside the existing complaint-anchored SE1/SE2 grace/review workflow and source-linked invoice hold.
7. Record an incident with two unregistered victims and no permit. Retry the same command key; verify one report and
   pending cases, no fabricated payment and no asserted legal blacklist.
8. Show the LAB SQL demonstration and actual test/measurement report. Reconnect a browser and replay persisted events.

## Syllabus and honest proof boundaries

All six LAB experiments have highest priority: DDL/DML, constraints, scalar functions, operators/aggregates,
subqueries/views/joins, and language extensions including explicit cursor handling. Runtime PostgreSQL uses PL/pgSQL,
not Oracle PL/SQL. PostgreSQL 16 does not implement `CREATE ASSERTION`; explain the invariant enforced through
constraints/trigger routines instead of presenting unsupported syntax as runnable.

The integrated architecture, normalized relationships, workload indexes/query plans, transactions and concurrency
are practical theory evidence. WAL recovery, Thomas write rule, graph/tree locking protocols, CAP and NoSQL store
families are explanatory comparisons unless a concrete verified demonstration says otherwise. Do not bolt on an
unused NoSQL service or claim a hand-built storage engine. The full topic list and official eight-row 30-mark rubric,
including the challenge PDF's TRL/demonstration row, are in [SYLLABUS_AND_RUBRIC](../plan/SYLLABUS_AND_RUBRIC.md).

## Evaluation discipline

Rerun results after schema/fixtures change. E1's earlier proposal anti-join has different evidence semantics; it is an
evidence-label comparison, not a fair same-task speed comparison. E2 disables triggers in a throwaway database to
isolate their contribution; it is an unguarded-database ablation, not an actual application validator. E3's identical
semantics index/plan variants support bounded performance claims. Record actual dataset sizes, repetition counts,
machine, migration fingerprint and dirty/committed state. Use no made-up percentages or carried-forward timing claims.

Deployment requires reviewed jurisdiction applicability, valid evidence collection, competent operators, TLS,
backup/restore and incident-response arrangements. Hashes detect local snapshot changes within the runtime boundary;
they are not signatures and cannot protect against a privileged owner. No software check establishes sensor truth.
