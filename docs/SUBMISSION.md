# DBThon 2026 submission guide

**Authoritative for:** how ZeroEntry answers the DBThon 2026 brief: the eight things each team must demonstrate, the five-step
novelty statement, the 30-mark rubric, SDG alignment and the technology readiness level. Each row points at the evidence; the
numbers come from [EVALUATION.md](EVALUATION.md) (run of 2026-10-07). The brief itself is
[proposal/DBTHON2026_Challenge.pdf](proposal/DBTHON2026_Challenge.pdf); the original proposal is
[proposal/ZeroEntry_DBThon2026_Proposal.md](proposal/ZeroEntry_DBThon2026_Proposal.md).

## 1. In one paragraph

Indian law defines "hazardous cleaning" of sewers by what is **missing**: the gear, the gas tests, the standby, the written
reason why no machine could do the job. Workers keep dying because nothing checks those safeguards at the moment of entry, and
an entry nobody records leaves no trace. ZeroEntry is a PostgreSQL database in which a permit becomes `AUTHORISED` only when
relational division proves every safeguard is on record, for every client (UI, script or raw SQL); in which unrecorded
entries are found from the absence of the records a lawful clearance leaves; and in which a death opens compensation,
blacklists the contractor and holds its invoices in one transaction.

## 2. What each team must demonstrate (the brief's eight components)

| # | Component | What we show | Evidence |
|---|---|---|---|
| 1 | Problem definition | Sewer and septic-tank deaths in India (1,248 since 1993, Tamil Nadu highest); the law lists the safeguards but nothing enforces them at entry. Users: municipal engineers, site supervisors, sanitation workers, contractors, auditors, administrators (six roles). | [PROJECT_SPEC §2-3](../PROJECT_SPEC.md#2-the-real-world-problem), [proposal §3](proposal/ZeroEntry_DBThon2026_Proposal.md#3-the-problem-real-current-and-local) |
| 2 | Domain | Urban sanitation and occupational safety in municipal sewer maintenance (Tamil Nadu urban local bodies; demo data for three Chennai zones). Chosen because the legal requirements are already precise enough to be data, several parties write to the same records (ULB, contractor, supervisor, worker), and the harm is fatal and measurable. | [PROJECT_SPEC §1](../PROJECT_SPEC.md#1-problem-statement-and-how-it-was-interpreted), [ADR-001](decisions/README.md#adr-001--interpret-the-problem-as-sanitation-worker-safety) |
| 3 | Existing system | Verbal permission and paper checklists; NAMASTE worker profiling, DIGIT/SUJOG registries, industrial permit-to-work tools, cleaning robots, licensing under the TN 2022 Act. None refuses an entry; none looks for entries nobody recorded. | [proposal §5.1](proposal/ZeroEntry_DBThon2026_Proposal.md#51-what-exists-today-and-what-it-does-not-do) |
| 4 | Database design | 30 tables, 53 foreign keys, 3NF with the deliberate exceptions justified; four ER diagrams; the generated relational schema. | [ER_DIAGRAM](ER_DIAGRAM.md), [DATABASE_DESIGN](DATABASE_DESIGN.md), [SCHEMA_REFERENCE](SCHEMA_REFERENCE.md) |
| 5 | Innovation | (A) a default-deny entry gate proved by relational division inside the database; (B) shadow-entry detection by absence; (C) consequences as one atomic transaction. | [DATABASE_DESIGN §5, §6, §8](DATABASE_DESIGN.md#5-the-entry-gate-zero-entry) |
| 6 | Novelty | The five-step statement for each innovation, with measured benefit. | [§3 below](#3-novelty-in-the-briefs-five-steps) |
| 7 | Prototype | PostgreSQL 16 + FastAPI + a browser UI, one command to run; 513 automated tests, green in CI on Linux, Windows and macOS. | [README quick start](../README.md#quick-start), [DEMO_SCRIPT](development/DEMO_SCRIPT.md) |
| 8 | Evaluation | Accuracy, enforcement, latency and scalability against stated baselines, reproducible with one command. | [EVALUATION](EVALUATION.md), [EVALUATION_RESULTS](EVALUATION_RESULTS.md) |

The brief's list of DBMS concepts to demonstrate (requirement e):

| Concept | Where |
|---|---|
| SQL queries (joins, aggregates, search, division, anti-join) | [`database/queries/01-05`](../database/queries/), each run by `tests/db/test_demo_queries.py` |
| Constraints | PK, FK, UNIQUE, CHECK, NOT NULL, the `EXCLUDE` overlap rule ([DATABASE_DESIGN §3](DATABASE_DESIGN.md#3-keys-and-constraints)) |
| Transactions | `record_incident()` procedure, one transaction per API request, row locks ([§8](DATABASE_DESIGN.md#8-transactions-and-concurrency), [`06_transactions.sql`](../database/queries/06_transactions.sql)) |
| Indexing | [DATABASE_DESIGN §9](DATABASE_DESIGN.md#9-indexes); measured with and without in E3 |
| Security | least-privilege role, row-level security, append-only evidence, audit trail, bcrypt sessions, CSRF ([SECURITY.md](../SECURITY.md)) |
| Triggers, functions, procedure, views | [DATABASE_DESIGN §7](DATABASE_DESIGN.md#7-programmable-objects); refusals in [`07_trigger_refusals.sql`](../database/queries/07_trigger_refusals.sql) |

## 3. Novelty in the brief's five steps

### A. The default-deny entry gate (law as database integrity)

| Step | |
|---|---|
| Existing approach | A checklist on paper or in an app; at best the application checks the rules before it saves. |
| Limitation | Any client that skips that check (another app, a script, a SQL console, a buggy endpoint, two sessions racing) can record an unlawful entry; a checklist never refuses; a refusal does not say which legal clause failed. |
| Proposed approach | The statute's safeguards are rows (`gear_item`, `rule_parameter`, `legal_clause`). `permit_clause_check()` proves each clause by relational division (every entrant × every statutory item; every depth level × a fresh, in-limit reading from a calibrated detector). The same function runs inside `authorise_entry()` and inside a `BEFORE UPDATE` trigger, and evidence changes lock the permit row. |
| Novel component | "Authorised" is a state only the database can grant, proved the same way for every client, with the failed clause named in the refusal. The law's numbers are audited data, editable without code. |
| Measurable benefit | E2: **18 of 18** invalid writes refused, against **1 of 18** for the same schema with its rules in application code. E4: 4 of 4 concurrency races closed (each committed before migration `0010`). E3a: a decision takes **1.7 ms** (median) and touches about 50 buffers whether the history holds 1,000 or 100,000 complaints. |

### B. Shadow-entry detection by absence

| Step | |
|---|---|
| Existing approach | A complaint closed as cleared is taken as done; deaths surface afterwards. A straightforward anti-join (our own first design, proposal §6.3c) lists jobs with no machine log and no closed permit. |
| Limitation | An unrecorded entry leaves no row to query. The naive anti-join misses complaints with no job at all and closed permits with an unlogged entrant, flags exempt, retried and still-in-grace complaints, and forgets a suspicion as soon as paperwork appears late. |
| Proposed approach | An explicit expected population anchored on the complaint; evidence counts only if it was recorded within a grace window; exempt resolutions are data; a second rule divides each closed permit's entrants by their entry logs; alerts are persisted, idempotent, decided by an engineer with a written note, and hold the contractor's invoices. |
| Novel component | The absence of expected records as a persisted, reviewable, payment-linked alert computed inside the database. Late evidence never closes an alert on its own. |
| Measurable benefit | E1: precision and recall **100 % / 100 %** (F1 1.00) against **40 % / 50 %** (F1 0.44) for the naive anti-join on 200 labelled complaints. Late paperwork: 20 of 20 suspicions kept for a human decision, against 20 of 20 silently dropped. E3b: a full scan of 100,000 complaints in **735 ms**, 12x faster than before migration `0011`, which this evaluation found. |

### C. Consequences in one transaction

| Step | |
|---|---|
| Existing approach | Compensation, contract cancellation and payment holds are separate, manual follow-ups after a death. |
| Limitation | A death can be half-recorded: the case opened but the contractor still active and still paid; Parliament answers show families waiting years (2019: 87 of 117 compensated). |
| Proposed approach | `record_incident()`: incident, ₹30-lakh case with a deadline from rule data, blacklist, permits aborted, invoices held, as one procedure call. |
| Novel component | A Supreme Court direction (*Balram Singh*, 2023) expressed as an all-or-nothing database transaction. |
| Measurable benefit | A forced failure after the first insert leaves zero rows (`tests/db/test_consequences.py`); a held invoice cannot be approved (E2, BR-23); overdue cases are a view (`v_compensation_overdue`). |

What we do **not** claim as new: gas detection, permit-to-work software or worker registries (proposal §5.3). The novelty is
modelling the Indian statute as integrity, detection from absence, and the consequence transaction.

## 4. The rubric (30 marks) and where each part is answered

| # | Evaluation component | Marks | COs | Answered by |
|---|---|---|---|---|
| 1 | Problem identification and domain relevance | 4 | CO2 | §2 rows 1-3; [PROJECT_SPEC](../PROJECT_SPEC.md) (problem, roles, business rules `BR-nn`, assumptions `A-nn`) |
| 2 | Database design and modelling | 5 | CO1, CO2 | [ER_DIAGRAM](ER_DIAGRAM.md), [DATABASE_DESIGN](DATABASE_DESIGN.md) (3NF and functional dependencies, keys, gate, detection), generated [SCHEMA_REFERENCE](SCHEMA_REFERENCE.md) |
| 3 | DBMS implementation and technical depth | 5 | CO1 | 11 forward-only migrations of SQL and PL/pgSQL; relational division and anti-joins; `EXCLUDE` constraint; state-machine and guard triggers; procedure; `security_invoker` views; row-level security; row locks; 513 tests ([TESTING](TESTING.md)) |
| 4 | Innovation | 4 | CO1, CO2 | §3 A-C |
| 5 | Novelty and differentiation | 5 | CO2 | §3 five-step tables; [proposal §5](proposal/ZeroEntry_DBThon2026_Proposal.md#5-novelty-and-prior-art) (prior art) |
| 6 | SDG alignment and societal impact | 2 | CO2 | §5 |
| 7 | Validation and measurable improvement | 3 | CO1, CO2 | [EVALUATION](EVALUATION.md): E1-E4 against stated baselines, and the 6x scan improvement the evaluation itself found (migration `0011`) |
| 8 | TRL and demonstration | 2 | CO1, CO2 | §6; [DEMO_SCRIPT](development/DEMO_SCRIPT.md) |

## 5. SDG alignment and societal impact

| SDG target (UN wording, abridged) | How ZeroEntry serves it |
|---|---|
| **8.8** Protect labour rights and promote safe and secure working environments for all workers, including those in precarious employment | Contract sanitation workers are precarious employment. The gate refuses an unsafe entry for every client; a worker can stop work on their own permit; 90-minute, daylight and overlap limits are enforced. |
| **3.9** Substantially reduce deaths and illnesses from hazardous chemicals and air pollution | Entry needs fresh in-limit readings of O₂, H₂S, combustibles and CO at three depths from a calibrated detector. |
| **6.2** Adequate and equitable sanitation for all, with attention to those in vulnerable situations | Mechanised-first: a permit cannot be drafted without a written waiver, and the zero-entry rate per ULB is a report (`v_ulb_year_kpi`). |
| **16.6** Effective, accountable and transparent institutions | Explainable refusals, an append-only audit trail, a read-only auditor role, shadow-entry alerts with history, compensation deadlines that become overdue in a view. |

Wording checked against [sdgs.un.org](https://sdgs.un.org/goals) (goals 3, 6, 8, 16) on 2026-10-07.

**Who benefits.** Workers (an entry the law forbids is refused, not merely discouraged); families (the compensation case and
its deadline exist the moment a death is recorded); urban local bodies (mechanisation becomes a measured rate); auditors and
courts (unrecorded clearances surface as alerts, and payment stops until someone decides). **Limits:** the database enforces
recorded state, not physics (a typed gas value can be false; serials, calibration dates, sign-off and the audit trail make a
false one traceable), and the statistics and legal references must be re-verified before presenting
([README](../README.md#before-presenting)).

## 6. Technology readiness level and demonstration

**TRL 4: technology validated in a laboratory environment.** The whole system runs end to end (database, API, UI); 513
automated tests pass on Linux, Windows and macOS; the evaluation exercises it at 100,000 complaints of synthetic history. It is
not TRL 5, because nothing has been validated in a relevant environment: no real ULB data, users or sensors.

Path to TRL 5-6: run the detection read-only on one zone's real complaint history; a field trial with supervisors and a
detector feed instead of typed readings; legal review of the clause list and gear schedule; per-ULB row scoping; CI against a
managed PostgreSQL server ([ROADMAP backlog](../ROADMAP.md#backlog-not-started-not-required-for-the-demo)).

**Demonstration:** the three-minute script ([DEMO_SCRIPT](development/DEMO_SCRIPT.md)) shows the denial, the fix, the
authorisation, the refused 95-minute entry, the shadow-entry alerts and the consequence transaction; its last step shows the
measured results, and `python scripts/evaluate.py --sizes 1000 --per-class 5 --out -` reproduces them live in under a minute.

## 7. Proposal versus what was built

| The proposal (2 Oct) said | Built | Why |
|---|---|---|
| 20 tables | 30 tables | sessions, holds with provenance, alert history, legal clauses, resolution types (data, not code) |
| Job-anchored anti-join view | complaint-anchored SE1 with a grace window and exemptions, plus SE2 | the naive form is wrong on 5 of the 10 labelled classes and drops late-paperwork suspicions ([ADR-006](decisions/README.md#adr-006--detection-is-anchored-on-the-complaint-and-on-recorded-time), E1) |
| JWT access tokens | opaque server-side sessions | real logout and revocation ([ADR-005](decisions/README.md#adr-005--opaque-server-side-sessions-not-jwt)) |
| PostgreSQL in Docker | embedded PostgreSQL 16 from pip; a real server still works | one-command setup on any laptop ([ADR-004](decisions/README.md#adr-004--embedded-postgresql-for-development-and-tests)) |
| React or Jinja + HTMX | a no-build browser UI | nothing to install or build ([ADR-009](decisions/README.md#adr-009--a-no-build-browser-ui)) |
| `EXCLUDE USING gist (worker_id WITH =, ...)` | `int8range(worker_id, worker_id, '[]')` in the exclusion | the embedded server has no `btree_gist` |
| EXPLAIN ANALYZE screenshots | `scripts/evaluate.py`, reproducible and checked in CI | [ADR-013](decisions/README.md#adr-013--measure-against-a-stated-baseline-read-rule-parameters-once-per-statement-migration-0011) |
| A simulated gas-sensor feed | typed readings, bound to a calibrated detector | backlog |
