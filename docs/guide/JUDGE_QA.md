# Judge Q&A: the questions a panel will ask, and our answers

Written from both sides of the table: the reviewer's question, then the answer we give, with the evidence. Answers are
short enough to say aloud. Figures are rounded; the exact values are in [EVALUATION_RESULTS.md](../EVALUATION_RESULTS.md).
Where the honest answer is "no" or "not yet", we say so.

**Contents:** [A. Problem and idea](#a-problem-and-idea) · [B. Database design](#b-database-design) ·
[C. ACID and transactions](#c-acid-and-transactions) · [D. Concurrency](#d-concurrency) · [E. Security](#e-security) ·
[F. Detection by absence](#f-detection-by-absence) · [G. Performance](#g-performance) ·
[H. Testing and evaluation](#h-testing-and-evaluation) · [I. Hard questions](#i-hard-questions) ·
[J. Live demo challenges](#j-live-demo-challenges)

---

## A. Problem and idea

**Q1. What problem are you solving, in one sentence?**
Sewer entry by a person is legally an exception that needs proven safeguards, yet those safeguards are often checked on paper
or not at all. Unrecorded entries are invisible when a complaint is simply closed as "cleared".

**Q2. What is new here?**
Two things, combined with consequences. **Default deny:** the database itself refuses to authorise an entry until every
configured check is proven, whichever client asks. **Detection by absence:** we compute the complaints whose expected evidence
is *missing*, and route each one to a human with an invoice hold. The contribution is the **integration**: permits, evidence
time and money linked in one enforceable model. It is not a new algorithm; we use established techniques (relational
division, anti-join, row locks, RLS).

**Q3. Who uses it?**
Six roles: municipal engineer, field supervisor, contractor office, worker, auditor and admin. Contractors and workers see only
their own rows, enforced by row-level security in PostgreSQL as well as by role checks in the API.

**Q4. Why a database project and not just an app with validations?**
A rule in application code protects only that application. A script, a second app, a SQL console or a buggy endpoint
bypasses it. We measured this: with the same schema but the rule triggers disabled, **1 of 18** invalid writes is refused; with
the rules in the database, **18 of 18** are (E2).

**Q5. Which SDGs and what TRL?**
The intended contribution is safer occupational work (**SDG 8**) and accountable sanitation services (**SDG 6**). We claim
no observed reduction in injuries or deaths. The exact targets and our technology readiness level, with the path to a pilot,
are stated in [SUBMISSION.md](../SUBMISSION.md). Quote them from there: a lab prototype on synthetic data, not field-validated.

## B. Database design

**Q6. How many tables, and what is the central one?**
35 tables. The heart is `permit_crew (permit_id, worker_id, crew_role)`, the many-to-many link between a permit and its
workers. Gear issues, entry logs and incidents reference **that composite key**, so the database itself refuses gear issued to,
or an entry logged for, someone who is not on the crew.

**Q7. Is the schema normalised? Prove it.**
Yes, to 3NF. The functional dependencies of the central tables are listed in
[DATABASE_DESIGN §4](../DATABASE_DESIGN.md#4-normalisation-3nf-and-the-deliberate-exceptions). For example, the ULB is reached
through `manhole`, not copied into `complaint`. The only composite primary key, `permit_crew`, has one attribute, `crew_role`,
which depends on the whole key, so 2NF holds.

**Q8. Then why is `contractor_id` stored on `incident`? Isn't that redundant?**
It is a deliberate **snapshot**: the employer *at the time of the incident*. Workers change contractor, but the sanction and
compensation must stay with the employer of that day. That is a historical fact, not a derivable value. Status columns that
summarise other columns are tied to them with a `CHECK`, so they cannot disagree.

**Q9. Where is relational division used?**
In the gear check: "every entrant holds every required item" is written as *there is no (entrant, required item) pair
without a matching gear issue*, a double `NOT EXISTS`. It deliberately **fails** rather than passing vacuously when no required
item is configured. The gas check is a per-group "latest row" condition: for each of the three depths, the newest reading must
be fresh, in limits and taken by a calibrated detector.

**Q10. Name constraints beyond primary and foreign keys.**
`CHECK` constraints tying statuses to columns. **Composite FKs** through `permit_crew`, and from incident to
`entry_permit (permit_id, job_id)`. The **exclusion constraint** `ex_entry_no_overlap` stops one worker having two overlapping
entries. **Partial unique indexes** allow one hold per invoice per alert and one per incident. `UNIQUE (complaint_id, rule_code)`
allows one alert per complaint per rule.

**Q11. Why an `int8range` in the exclusion constraint instead of `btree_gist`?**
The embedded PostgreSQL build has no `btree_gist`. Turning the worker id into a single-point range `[id, id]` lets a plain GiST
index express "same worker AND overlapping period". This works on any PostgreSQL build.

**Q12. Why triggers? Aren't they hard to maintain?**
They cover the rules a constraint cannot state: the gate, the state machine, frozen crew, calibration, daylight, rest time.
Each lives in a numbered migration and has a pass test and a fail test. Business failures raise a custom SQLSTATE class
(`ZE001`-`ZE006`) that the API maps to clean HTTP errors carrying the database's own sentence.

**Q13. How do schema changes work?**
Numbered raw-SQL migrations (`0001`-`0014`) run by Alembic, forward-only. An applied migration is never edited; a fix is a new
migration. `0011`, for example, fixed a performance bug our benchmark found.

## C. ACID and transactions

**Q14. Walk me through atomicity in your system.**
Every API request is **one transaction**. If any trigger refuses, everything in that request is rolled back. The strongest
example is the `record_incident` **procedure**: one call records the incident, opens a compensation case with a deadline,
blacklists or suspends the contractor, stops their permits and holds their invoices. A test forces a failure *after* the
incident row is written and checks that nothing remains (`test_forced_failure_inside_the_procedure_leaves_nothing_behind`).
`python run.py sql database/queries/06_transactions.sql` shows the commit and rollback live.

**Q15. Consistency?**
Invalid states are unrepresentable. Keys, `CHECK`, composite FKs and the exclusion constraint cover the declarative part;
triggers cover the rest. Even a raw `UPDATE entry_permit SET status='AUTHORISED'` typed as the database owner is refused with the
list of unmet clauses, because the same check function guards the update.

**Q16. Isolation: which level do you use, and why not SERIALIZABLE?**
**READ COMMITTED with explicit row locks**, by design. In PostgreSQL's READ COMMITTED, a statement that waited for a lock
re-reads the latest committed row, and later statements see a fresh snapshot. So our "lock, then re-check" protocol always
decides on current data. Under REPEATABLE READ or SERIALIZABLE, the snapshot is frozen at the first statement, and waiting for
a lock does not refresh it. The transaction could decide on stale credentials or miss a hold that was just committed. The
financial paths and runtime authorisation therefore **refuse other isolation levels with SQLSTATE `40001`**, a retryable
error, instead of silently using stale data. The API always uses READ COMMITTED, and every race the lock protocol closes has
a two-connection test (section D).

**Q17. Durability?**
The transaction commits **before** the HTTP response is sent, so a 2xx always means committed. That was a real bug we found
and fixed: FastAPI's default dependency teardown ran *after* the response, so a failed commit could still return 200. Beyond
that, PostgreSQL's write-ahead log persists committed data. The safety sweep commits separately from the detection scan, so a
failed scan cannot undo a safety stop.

**Q18. Show me a rollback.**
`python run.py sql database/queries/06_transactions.sql` prints the counts before, then runs the consequence procedure inside
`BEGIN ... ROLLBACK`, including a failure inside the procedure. The counts afterwards are unchanged.

## D. Concurrency

**Q19. Two supervisors act at the same time. What can go wrong, and what stops it?**
The dangerous case is evidence changing *while* a permit is being decided, for example a standby removed mid-authorisation.
`authorise_entry` takes `FOR UPDATE` on the permit, and every guard on crew, gear, readings and entries first takes `FOR SHARE`
on the same permit (`lock_permit()`, migration `0010`). Whoever comes second waits, re-reads the committed state and is refused
if the proof no longer holds. Four tests in `tests/db/test_concurrency.py` reproduce these races with two real connections.
**Each of them committed a wrong result before `0010`.**

**Q20. What about money: a payment racing a new hold?**
There is a fixed lock order: **the complaint first, then the invoice row**, which is shared by approval, payment and hold
placement. If the payment commits first, the invoice stays paid and gets no hold (it is history). If the hold commits first,
payment is blocked. Both orders are tested, for both hold sources (an alert or an incident), including an invoice being
created during the race (`tests/db/test_temporal_evidence_and_invoice_races.py`).

**Q21. Two workers' entries overlap in time. Who catches that?**
The exclusion constraint, a declarative rule. Two concurrent inserts cannot both succeed, without any application locking.

**Q22. Two clerks pay the same compensation at once?**
`record_compensation_payment` locks the case `FOR UPDATE`. The second waits, sees the new balance and cannot overpay.

**Q23. Deadlocks?**
The lock protocols use one fixed order each: the permit row for evidence and decisions, and the complaint before the invoice
for money. A consistent order is the standard way to avoid lock cycles. If PostgreSQL ever did detect a deadlock, it would abort
one transaction (`40P01`) and the other would proceed, so data stays correct either way. Automatic maintenance uses `pg_try_advisory_xact_lock` and **skips** the tick if another process holds it, rather than queueing.

**Q24. Is the absence scan safe to run twice, or concurrently?**
Yes. `UNIQUE (complaint_id, rule_code)` with `INSERT ... ON CONFLICT` makes it idempotent: no duplicates, no re-opening a
dismissed alert, and no automatic closing.

## E. Security

**Q25. How are passwords and sessions handled?**
bcrypt (cost 12), with a minimum of 12 characters including mixed case and a digit. Lockout after 5 failures, plus a per-IP
throttle. An unknown e-mail and a wrong password get the same response at the same cost, so accounts cannot be enumerated.
Sessions use opaque 256-bit tokens, and only their SHA-256 is stored. The cookie is `HttpOnly; SameSite=Strict`, and cookie
writes also need a CSRF token plus a same-origin `Origin`.

**Q26. How is authorisation enforced?**
Twice. The API: every endpoint declares its roles with `require(...)`, and a test calls **every endpoint as every role**. The
database: row-level security scopes contractors and workers to their own rows. The user context is set per transaction with
`set_config(..., true)`, so it cannot leak to the next request on a pooled connection. Identity comes only from the session row;
a role or user id sent by the client is ignored.

**Q27. SQL injection?**
Parameterised queries and the ORM only, with filters type-checked first. A test sends SQL fragments as search text. The app's
database role `ze_app` owns nothing and has no DDL, so even a bug could not drop a table.

**Q28. What can the app's database user NOT do?**
It cannot run DDL, delete or rewrite evidence (readings, entries, waivers, incidents, alert history, holds), write `audit_log`,
add roles or rules, or rewrite a rule's legal reference. `tests/db/test_privileges.py` checks 31 refused statements.

**Q29. Can the audit log be tampered with?**
Not by the application or its users. It is written by an owner-rights trigger and is append-only; `DELETE` is refused with
`ZE003`. **A database superuser could disable triggers.** We state that boundary openly. The authorisation snapshot's SHA-256 is
a local integrity check, not an external signature.

## F. Detection by absence

**Q30. How do you detect something that was never recorded?**
As a set difference over an **explicit expected population**: complaints resolved as "cleared", **minus** those with a timely
machine log **or** a timely closed permit with a logged entry. What remains is suspicious. That is an anti-join (`NOT EXISTS`),
in the views `v_shadow_se1` (per complaint) and `v_shadow_se2` (per entrant of a closed permit).

**Q31. Won't that flood people with false alarms?**
Three things stop it. Resolutions that legitimately need no evidence ("duplicate", "no blockage found") are excluded. A
**grace window** (24 h) allows for late sync. Evidence counts by the **server's receipt time**, so it cannot be back-dated.
On the labelled synthetic set this gives **100 % precision and recall**, against **40 % and 50 %** for the naive anti-join
from our original proposal (E1).

**Q32. Is a missing record proof that someone entered illegally?**
No. It is grounds for a human review, nothing more. Late evidence moves an alert to `EVIDENCE_RECEIVED`, but **nothing is ever
closed automatically**: an engineer confirms or dismisses it, with a written note.

**Q33. What does an alert actually do?**
It holds the contractor's unpaid invoices on that complaint, with provenance (which alert placed each hold). Dismissing the
alert releases **exactly its own holds**, never an incident's. A held invoice cannot be approved or paid.

## G. Performance

**Q34. Does it scale?**
On one laptop, the entry decision takes **about 2 ms** at about 50 buffers, **flat from 1,000 to 100,000 complaints** (E3a).
The persisted absence scan has a **median of about 0.25 s** at 100,000 complaints (E3b), against about 18 s without its
indexes. The supplementary SE1 experiment ([evaluation/RESULTS.md](../evaluation/RESULTS.md)) uses a different, heavier
temporal workload. It records about 2.5 s for the first scan at 100,000, with the query plans and raw samples. Both are
single-laptop timings.

**Q35. Which indexes matter and why?**
Every foreign key used in a join (PostgreSQL does not index FKs automatically). A partial index on resolved complaints,
which is the expected population of the scan. `(permit_id, depth_level, taken_at DESC)` for "latest reading per depth".
Prefix indexes for search. E3 measures the gate and the scan with and without their indexes. At 100,000 complaints, the
decision without the gate indexes is several times slower.

**Q36. Did you find any performance problem yourselves?**
Yes. PostgreSQL inlined a one-row parameter CTE and evaluated the grace-window function **once per joined row**. Migration
`0011` (`WITH g AS MATERIALIZED`) makes the candidate query and the scan about 3x faster at 100,000 complaints in the
current results, with identical output. A test now guards it. We also found a benchmark pitfall: PL/pgSQL re-plans for its first five calls in a session, so
we warm up six times before measuring.

**Q37. The scan re-checks every resolved complaint each time. Isn't that wasteful?**
It is a deliberate, simple, idempotent full pass, and it is measured. The upgrade path, if volumes demand it, is an incremental
scan driven by a change queue. We haven't built it, because nothing yet needs it.

## H. Testing and evaluation

**Q38. How do you test a database?**
Against **real PostgreSQL**. One embedded cluster per test session, one migrated template, and a **fresh clone per test**,
run in parallel. Every rule has a pass test and a fail test. Every endpoint is called as every role. Raw-SQL attacks skip the
API, and synchronised two-connection races run against real locks. Result on this code: **574 passed** in about 2.5 minutes on
Windows. CI runs the suite on Linux, Windows and macOS, and against a real PostgreSQL 16 service.

**Q39. How did you measure "better"? Better than what?**
Against stated baselines, on labelled synthetic data. **E1, detection:** a naive anti-join. **E2, enforcement:** the same
schema with rules in application code. **E3, latency:** with and without indexes, and before and after `0011`. Method and
limits are in [EVALUATION.md](../EVALUATION.md). Counts are machine-independent; timings come from one laptop.

**Q40. Can I see it run now?**
`python run.py evaluate --sizes 1000 --per-class 5 --out -` takes about a minute on its own throwaway server.
`python run.py test` runs the full suite.

## I. Hard questions

**Q41. The database can't know if the gas reading is real. So what is the point?**
Correct, it enforces **state, not physics**. What it guarantees is that no entry is authorised **without** a reading at every
depth, from a detector calibrated that day, taken by a signed-in person, and stored permanently. That turns "we checked" from
a claim into a record someone is accountable for. Authenticated instruments are future work.

**Q42. Is your rule set the law?**
No. It is a selected set of configured checks. Each check is labelled as law, guidance or product policy, with its source
([POLICY_AND_PRIOR_ART.md](../POLICY_AND_PRIOR_ART.md)). Gear applicability, waiver authority and compensation defaults need
domain review before any real use.

**Q43. Commercial permit-to-work systems exist. Why is this different?**
They do offer gas and competence gates and audit trails, and we cite them. Our difference is integration: default-deny permits
linked to time-aware **evidence gaps** in municipal complaint closure, human review and **source-specific financial holds**,
all enforced in the database and tested under concurrency. We do not claim competitors *cannot* do this, only that their public
documentation does not show it.

**Q44. Did any of this run in the field?**
No. All data is synthetic, and accuracy is measured on synthetic labels, not field accuracy. We claim no reduction in
injuries or deaths. A pilot is the next step.

**Q45. What if the app server is down?**
Admission always re-checks current conditions, so nothing is authorised on stale data. Time-based stops (expiry, overstays,
stale readings) run on a periodic sweep, every 30 s by default. While the app is down, those sweeps are delayed. The system has
no independent physical access-control channel, and we say so.

**Q46. A superuser can bypass everything. Doesn't that defeat the design?**
It bounds it. The guarantees hold for every application path and every non-owner role. That covers the realistic threats:
buggy clients, scripts, tenants and stolen app credentials. Protection against the database owner needs external anchoring
of the hashes, which is listed as future work.

**Q47. What would you do with two more months?**
In order: authenticated instrument and registry integration, ULB-scoped visibility for engineers and supervisors, automated
headless-browser tests, external notifications and hash anchoring, multilingual mobile operator testing, and a validated
pilot.

**Q48. What was the hardest bug?**
The concurrency races closed by `0010`: four interleavings that each committed a wrong result. Three changed the evidence
while a permit was being authorised, and one started an entry while the permit was being closed. Second place goes to the commit-after-response bug (Q17). Third: row-level security on lookup
tables silently dropping rows from inner joins, which we fixed with outer joins for display names.

## J. Live demo challenges

The judge asks, and you show:

| "Show me..." | Do this |
|---|---|
| ...that the UI can't bypass the rules | In `python run.py psql` (the owner console), on a **DRAFT** permit (`SELECT permit_id FROM entry_permit WHERE status='DRAFT';`): `UPDATE entry_permit SET status='AUTHORISED' WHERE permit_id=<that id>;` is refused with `ZE001` and the same reasons as the UI |
| ...a rollback | `python run.py sql database/queries/06_transactions.sql` |
| ...all the refusals at once | `python run.py sql database/queries/07_trigger_refusals.sql` (nine rules, nine refused writes) |
| ...relational division and the anti-join in SQL | `python run.py sql database/queries/04_division_and_anti_join.sql` |
| ...that the scan is idempotent | as `engineer@`, press *Run the absence scan now* twice: zero new alerts |
| ...that dismissal releases only its own hold | dismiss the CHN-ADY-006 alert, then open **Invoices & holds** |
| ...an unsafe reading stopping work | on an authorised permit with an open entry, log a BOTTOM reading with O₂ 12 %: the permit is ABORTED, safety events are appended, and *Record exit* still works |
| ...the concurrency tests | `python run.py test tests/db/test_concurrency.py tests/db/test_temporal_evidence_and_invoice_races.py` |
| ...the numbers | [EVALUATION_RESULTS.md](../EVALUATION_RESULTS.md), or run the one-minute evaluation live |
