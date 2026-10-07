# Evaluation

**Authoritative for:** how ZeroEntry is measured against conventional approaches: what is compared, the baselines, the
metrics, the headline results and what they do not prove. The full generated tables are in
[EVALUATION_RESULTS.md](EVALUATION_RESULTS.md); how this answers the DBThon brief is in [SUBMISSION.md](SUBMISSION.md).

## Reproduce

```bash
python scripts/evaluate.py                                   # full run, about 10 minutes; rewrites docs/EVALUATION_RESULTS.md
python scripts/evaluate.py --sizes 1000 --per-class 5 --out -   # quick look (under a minute), printed only
```

The script starts its own throwaway embedded PostgreSQL in a temporary directory, migrates it through the normal Alembic path
and deletes it at the end. It never touches `.pgdata` or any other database. All data is synthetic and goes through every
constraint and trigger (rows are built by `tests/factories.py` and by `eval_add_history()`, nothing is bypassed).
`tests/db/test_evaluation.py` runs the same code at a tiny scale on every CI run and asserts the counts, never the timings.

## What is compared

| | Question | ZeroEntry | Conventional baseline | Metric |
|---|---|---|---|---|
| E1 | Does detection by absence find the unrecorded entries, and only those? | `scan_shadow_entries()` (SE1 + SE2, grace window, exemptions as data, persisted alerts) | the anti-join the team's own proposal first wrote ([proposal §6.3c](proposal/ZeroEntry_DBThon2026_Proposal.md#63-the-four-signature-queries)): job-anchored, no exemptions, no grace window, any closed permit counts | precision, recall, F1 on labelled complaints; suspicions silently dropped when late paperwork appears |
| E2 | Does the law hold for every client, not just the UI? | the full schema | the same tables and constraints with every rule trigger disabled ([`rules_in_app_code.sql`](../database/evaluation/rules_in_app_code.sql)): the usual design in which rules live in application code | invalid writes refused, out of one per database-enforced rule |
| E3 | Does it stay fast as history grows, and do the indexes earn their place? | `authorise_entry()` and `scan_shadow_entries()` at 1k, 10k and 100k complaints | the same queries without their indexes; the detection views as they were before migration `0011`; the naive query | median and p95 latency; shared buffers touched (`EXPLAIN (ANALYZE, BUFFERS)`), the "unnecessary data processing" measure |
| E4 | Is the gate race-free? | migration `0010` (`lock_permit()`) | the guards before `0010` | concurrent races that commit a broken proof (`tests/db/test_concurrency.py`) |

### E1 method

Ten classes of resolved complaints, 20 of each, with the right answer known by construction (the table in the results file
lists them): machine cleared; retried after a failed machine; evidence synced late but inside the 24 h grace window; a lawful
manual entry; an exempt resolution (`NO_BLOCKAGE_FOUND` and the like); resolved two hours before the scan; and four kinds that
should alert: no evidence, no job at all, only a failed machine, a closed permit with an entrant who never logged an entry.
A first scan runs 25 h after resolution and a second at 48 h. A further 20 complaints get a CLEARED machine log 30 h after
resolution, between the two scans: that tests whether late paperwork can make a suspicion disappear without a human decision.

### E2 method

Each probe builds a fresh permit that passes every clause, breaks exactly one rule, sends the invalid write a client could send
(a raw `UPDATE`, an `INSERT`, a `DELETE`), and rolls everything back. The 18 probes are one per rule that the database enforces
on writes (BR-01 to BR-12, BR-22, BR-23, BR-31, BR-34, BR-36, BR-41). The other rules are not refusals and are evidenced
elsewhere: detection rules BR-30, BR-32, BR-33, BR-35 by E1 and `tests/db/test_detection.py`; the atomic consequences BR-20 and
BR-21 by the forced-failure test in `tests/db/test_consequences.py`; audited rule parameters BR-40 by
`test_daylight_hours_are_law_as_data_and_the_change_is_audited` (`tests/db/test_entry_rules.py`); row-level security BR-42 by
`tests/db/test_rls.py`. Probes run as the table owner, which bypasses row-level security but not triggers,
so they measure the rules, not the roles.

### E3 method

`eval_add_history(n)` ([`evaluation.sql`](../database/evaluation/evaluation.sql)) appends resolved complaints: 5 % cleared by a
lawful manual entry through the real gate (waiver, permit, crew of four, statutory gear, three gas readings,
`authorise_entry()`, two logged entries, closed), 3 % exempt, the rest cleared by a machine except about 2 % left without
evidence. So permits, crew, gear, readings and entries grow with the history, not only complaints. After each step: `ANALYZE`,
one warm-up, then 30 repetitions of the entry decision and 5 of the scan, each rolled back so every repetition does the same
work. "Before 0011" and "without indexes" re-create the old views or drop the indexes inside a transaction that is rolled back
(PostgreSQL DDL is transactional), on the same data.

## Results

Run of 2026-10-07 on one Windows laptop (22 logical CPUs), embedded PostgreSQL 16.2 with default settings. Counts below are
exact; times are rounded from [EVALUATION_RESULTS.md](EVALUATION_RESULTS.md) (which has the exact figures and the per-class and
per-rule tables), because they move a little from run to run and machine to machine.

| | ZeroEntry | Conventional baseline | Improvement |
|---|---|---|---|
| **E1** detection, 200 labelled complaints | precision 100 %, recall 100 %, F1 1.00 | naive anti-join: precision 40 %, recall 50 %, F1 0.44 | 60 false alarms and 40 missed shadow entries removed |
| **E1** late paperwork, 20 invoiced cases | 20 kept for human review, all 20 invoices still held | 20 silently dropped from the list | no suspicion disappears without a decision |
| **E2** invalid writes refused | 18 of 18 | 1 of 18 (only the `UNIQUE` constraint both designs share) | 17 rule violations that any non-UI client could commit are refused |
| **E3a** entry decision, 1k to 100k complaints | about 2 ms median and about 50 buffers at every size | without its indexes: several times slower at 100k, and growing | the cost of a decision does not grow with history |
| **E3b** detection candidate query, 100k complaints | about 0.3 s, about 57,000 buffers | without its indexes: tens of seconds, about 7.8 million buffers | about 100x faster, over 100x less data processed |
| **E3b** detection before and after migration `0011`, 100k complaints | candidate query about 0.3 s; full scan under a second | the same views before `0011`: about 4x longer and 2.7x more buffers; full scan several seconds | found by this evaluation; scan 4x to 12x faster across sizes |
| **E4** concurrent races that commit a broken proof | 0 of 4 | before migration `0010`: 4 of 4 | the gate is race-free |

Reading the numbers:

* **Where the naive query goes wrong (E1).** It flags complaints whose first machine failed and a second one cleared, exempt
  resolutions, and complaints still inside the grace window. It misses complaints resolved with no job at all and closed
  permits whose entrant never logged an entry. At 100,000 complaints it is cheaper but flags 4,751 complaints where
  1,900 are real candidates: the extra 2,851 are exactly the exempt resolutions in the history.
* **What the baseline still refuses (E2).** Only the duplicate alert, because `UNIQUE` is part of the shared schema. Every other
  rule is a trigger or a function in ZeroEntry; without them the same tables accept an authorised permit with no standby, a
  95-minute entry, a re-opened closed permit, a deleted audit row, and the rest of the list.
* **Scalability (E3).** The decision touches about 50 buffers whatever the size of the history, because every clause is an
  index lookup on one permit. The scan grows linearly with history (about ten times the time for ten times the complaints)
  because it re-evaluates every resolved complaint; without its indexes it grows much faster than linearly.
* **The evaluation found a real defect (0011).** The first run showed the detection views calling `rule_num()` once per joined
  row: PostgreSQL 12+ inlines a CTE that is referenced once. Materialising it makes the candidate query about 4x faster with
  about 2.7x fewer buffers (the same ratio in every run so far), with identical results (`rule_num()` is `STABLE`). The full
  scan gained 4x to 12x across sizes in the published run; the exact factor depends on the plan PL/pgSQL settles on. A test now checks the plan
  keeps the CTE ([ADR-013](decisions/README.md#adr-013--measure-against-a-stated-baseline-read-rule-parameters-once-per-statement-migration-0011)).
* **E4** is not re-run by the script: `tests/db/test_concurrency.py` reproduces the four races, and the 2026-10-07 build
  session recorded each of them committing before `0010` and being refused after ([DEV_LOG](development/DEV_LOG.md)).

## What the evaluation does not prove

* **Synthetic data.** E1 measures fidelity to the stated rules on labelled cases built to exercise them, not accuracy on real
  municipal records. Real-world precision depends on how faithfully a ULB records resolutions; a pilot on one zone's complaint
  history is the next step (see TRL in [SUBMISSION.md](SUBMISSION.md#6-technology-readiness-level-and-demonstration)).
* **The baselines are ours.** The naive anti-join is the team's earlier design, written down in the proposal before the build,
  not a product someone else ships. The enforcement baseline models "rules in application code"; a real application would also
  check, but every other client would not, which is what E2 measures.
* **One machine, default settings.** Timings come from one development laptop running the embedded PostgreSQL 16 with default
  settings, warm cache, one session. Buffers and counts transfer to other machines better than milliseconds do.
* **The scan is a full pass.** It re-evaluates every resolved complaint each time (idempotent, simple, under a second at 100,000
  complaints). If volumes ever make that too slow, the upgrade path is an incremental scan fed by a change queue.
* **Outcomes.** Nothing here measures deaths prevented; that needs a deployment.
