# Validation, baselines and evidence capture

Status: specifications and expected outcomes, not executed results. B owns automated tests/measurements, A owns SQL invariants and query plans, C owns readable charts, L reviews interpretation. App tests must use PostgreSQL16, not SQLite emulation.

## Baselines and claims

Use disposable databases/profiles, never a runtime switch that disables the deployed safeguards. B0 is an optional record/checklist baseline. B1 is a correctly implemented server-side validator with the same current evidence, policy, scope and ordinary sequential outcomes, but without the coordinated transition/reservation protocol. B2 is the strengthened application validator using equivalent transactions/locks; it is an explanatory comparison where practical, not a required full second product.

The hypothesis is narrower than 'database code is always safer': coordinating all writers and persisting decisions/consequences prevents the tested inconsistent states. B2 may achieve the same correctness. Our contribution is the specific integrated protocol and evidence, not proof that application code is intrinsically incapable.

Compare full reference query, indexed query and projection on the SAME labelled data and answer set. An incrementally maintained result may improve reads while adding write cost and contention. Publish that trade-off. Do not confuse rows returned by EXPLAIN with total rows scanned, or a hash join with a hash index.

## Acceptance matrix

Each case must assert committed rows/statuses as well as HTTP responses. IDs become test names in backend/tests, db/tests or integration-tests. Relate them to the syllabus document's topic-specific checks where named differently.

| ID | Setup/action | Required observed result |
|---|---|---|
| T01 | Chennai prohibited activity, otherwise complete evidence | G0 denial; G1-G8 NOT_EVALUATED, no authorization/reservations |
| T02 | No active policy/empty required gear/depth configuration | CONFIG/POLICY denial, not vacuous pass |
| T03 | No entrants/two crew/same person in multiple roles | G4 failure and no occupied entry |
| T04 | Assigned worker never acknowledged or was withdrawn | ACK_REQUIRED; no entry |
| T05 | One entrant missing harness; site first-aid present | Personal G1 fails for that entrant; site evidence cannot substitute |
| T06 | Shared-site item missing but personal items complete | Site G1 failure; do not issue one tripod per worker |
| T07 | Older safe sample then newer unsafe at same depth | New decision denied; no safe-row filtering |
| T08 | Newer incomplete sample | Incomplete denial even when an older complete safe sample exists |
| T09 | Stale/future/invalid-clock sample | Explicit failure/quality flag; accepted adverse fact retained |
| T10 | Expired detector/gear/fitness/training | Relevant G3/G1/G7 failure |
| T11 | Missing exception or worker tries RSA approval | Denial/403; cannot overcome G0 |
| T12 | Planned95min interval | DURATION_LIMIT; no planned allocation |
| T13 | Actual exit after95min | True exit retained, duration violation; no erased entry |
| T14 | Same worker new permit before30min rest | REST_REQUIRED across permit IDs |
| T15 | Two concurrent permits same standby or serial asset | At most one valid committed allocation; loser conflict/denial |
| T16 | Permit-authorise races with incoming adverse evidence | Serial result: adverse-before denies; adverse-after suspends; no final usable stale receipt |
| T17 | Preview passes, evidence changes before command | Actual command rechecks, does not trust preview |
| T18 | Receipt expires before begin-entry | Conflict/denial immediately, even with watchdog disabled |
| T19 | Worker refusal then supervisor retries authorization | Stop latch persists; review cannot silently erase refusal |
| T20 | Dangerous/incomplete reading while ACTIVE | Reading, suspension, revision, audit and outbox all commit; open entry stays open |
| T21 | Same reading/key replay and changed-body replay | Exact retry idempotent; changed bytes/key409, no duplicate evidence |
| T22 | Late unsafe reading; later safe older record | Unsafe latch; late safe does not clear it |
| T23 | Successful machine completion | Job completes without a fabricated manual permit; no evidence-gap flag |
| T24 | One complaint with valid job and separate cancelled job | No complaint-wide false positive; reason at job level |
| T25 | Imported completed claim lacking internal proof | Claim retained, no fake valid closure; review gap and related invoice hold |
| T26 | Valid past completion whose gas evidence has since aged | Historical completion remains valid; no automatic retroactive stale-gas accusation |
| T27 | Insert/retract/rematch evidence and rebuild projection | shadow_ledger exactly equals reference query for current inputs |
| T28 | Record incident with2victims and no permit |2 victim records and2 pending cases; no fake entry; payment remains0 |
| T29 | Inject exception after first consequence | All incident/case/hold/event effects rolled back; unrelated prior state unchanged |
| T30 | Retry successful incident with same key | Same IDs, no duplicate case/event/hold |
| T31 | Unknown contractor/private site incident | Incident/cases recorded; contractor effect INVESTIGATION_REQUIRED, no invented entity |
| T32 | Restricted direct SQL UPDATE permit/readings/policy | Privilege/guard rejection; no forbidden committed mutation |
| T33 | ContractorAlpha asks forBeta job; auditor mutation; pooled alternating actors |404/403 as applicable; no row/count leakage or retained actor context |
| T34 | Listener disconnected before commit, reconnect with cursor | Durable events recovered; rolled-back event never appears |
| T35 | Watchdog stopped then restarted | No new entry with expired receipt; eventual derived/persisted state reconciles; latency disclosed |
| T36 | Corrupted receipt bytes against known exported digest | Digest mismatch; do not claim protection if attacker rewrites both without external anchor |
| T37 | Clean migrations, single Alembic head, reset, backup/restore | Recreated schema/seed; expected counts and invariants match restored copy |
| T38 | G0 unknown, non-gas cave-in scenario and unverified news facts | Review/out-of-scope/unknown labels; no invented prevention outcome |

Add SQL tests for PK/FK/UNIQUE/NOT NULL/CHECK and malformed time bounds, plus route validation and login failures. Test the static whitelist rather than only mirrored implementation expressions. Use a real connection pool with at least two connections for actor isolation. A golden fixture is corrected through the same routines that the UI uses.

## Controlled experiments E1-E7

| Experiment | Setup and scale | Metrics / interpretation | Budget |
|---|---|---|---:|
| E1 Integrity | Fixed38 cases plus100 seeded generated evidence permutations; B1 andZE use identical policy | Unsafe/inconsistent committed states, false denials, reason correctness; confusion matrix on labelled cases |1h |
| E2 Concurrency | Two deterministic barrier-synchronised connections; then K=2,4,8 with100attempts each | Conflicts committed, retries/aborts, success throughput and lock wait; report serialization cost |45min |
| E3 Reconciliation |10k and100k jobs;1M only if time/memory allow. Same claims/completions; compare scan,index,projection | Correctness equality, query median/p95,buffers, scoped update cost and storage |1h |
| E4 Gate query |10warmups then>=1000 timed calls over representative complete/incomplete permits; seed fixed | Median/p95, timeout count, DB plan; p99 only if sample is large enough and clearly qualified |30min |
| E5 Events |100synthetic events; compare persisted transition and visible UI with5/30/60s polling | Event-received-to-commit separately from commit-to-visible; median/p95, loss/reconnect results |30min |
| E6 Incident motivation |23 supplied leads kept tri-state; derive selected synthetic scenarios separately | Known facts, unknowns, scope match, which database condition is checked. No death-prevention rate |30min |
| E7 Digest |Export known receipt+digest; mutate a copy; compare | Detected mismatch; show privileged rewrite limitation |15min optional |

E3 is the clearest database-specific performance experiment. E1/E2/E5 show behavioural improvement. If time is short, prioritise correctness, projection equality and one defensible performance chart over millions of rows or many metrics.

### Exact measurement records

`results.csv`: run_id,git_sha,contract_version,postgres_version,python_version,os,cpu,ram_gb,scenario,variant,seed,row_count,concurrency,repetition,warmup,elapsed_ms,success,sqlstate,expected_outcome,observed_outcome,rows_returned,shared_hit_blocks,shared_read_blocks,notes.

E3 write CSV adds changed_jobs,related_rows,write_elapsed_ms,projection_mismatches. E5 adds received_at,committed_ack_observed_at,visible_at,notification_mode,clock_basis. A client acknowledgement is an observable bound after commit, not the exact instant of WAL commit. Use one host monotonic clock for end-to-end timing; do not subtract unsynchronised ESP32 and browser wall clocks.

Use deterministic RNG seed20261007; same dataset cloned into variants. Synthetic labels include validmechanised,cancelled,missingcompletion,missingentrant,openentry,unmatchedclaim. Separate a200-job visual dataset from benchmark data. Sample5-10% gaps is an experimental choice, not a real prevalence estimate. Report precision=TP/(TP+FP), recall=TP/(TP+FN) only where labels are known; undefined denominators display N/A. Case creation latency cannot measure compensation payment timeliness.

Index experiment: two disposable equivalent schemas with identical rows; ordinary planner settings, ANALYZE after load, consistent warmup. Keep uniqueness/security controls equal for query comparison; don't drop correctness constraints to obtain speed. Save `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` for SELECT paths; mutating EXPLAIN executes the action, so use an isolated test transaction/data and explicitly roll back or reset.

## Race demonstrations

Operational test: both clients wait on a barrier, request different permits sharing an asset/standby, then commit. Inspect resource_reservation and entry_log. Under the ulb mutex plus exclusion, one request loses or waits and then fails current availability. Do not show only two successful HTTP calls without reading committed state.

SSI teaching test uses a separate `demo_oncall(worker_id,on_duty)` table with two true rows. T1/T2 each reads that another worker remains; each turns off a different worker; both commit at READ COMMITTED, leaving zero. Repeat SERIALIZABLE: one transaction must abort40001 in the interleaving, then a whole retry observes insufficient coverage. Do not describe this toy as the exact production crew algorithm; connect it to the need to coordinate a cross-row standby invariant.

Recovery demonstration: force a transaction error after incident+case creation and inspect zero committed effects; then success and idempotent retry. Separately take `pg_dump -Fc` and restore into `zeroentry_restore_test`, then run integrity counts and the reference reconciliation query. Logical restore is not proof of crash recovery or every WAL algorithm; explain the distinction in the viva.

## Evidence folders and stopping rule

Future app paths: evidence/db/{lab,races,plans,restore}, evidence/api/{tests,raw_bench}, evidence/ui/{screenshots,recording}, evidence/release/manifest.json. Each item carries commit/date/command, expected vsobserved and owner. No secrets or real victim-identifying information in screenshots. Once required tests pass on merged main, run one clean demo rehearsal; repeat only after a relevant change or failure.

Release blocks: live UI uses mock while claiming DB results; fresh evidence permits prohibited activity; old receipt usable after change; adverse reading rolled back to preserve state; resources released while someone remains inside; projection diverges; incident partially commits; role leakage; fabricated metric; a missing LAB procedure or cursor. Cosmetic refinements do not justify deferring these.
