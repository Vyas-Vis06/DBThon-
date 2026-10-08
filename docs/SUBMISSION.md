# DBThon 2026 submission guide

**Authoritative for:** how ZeroEntry answers the DBThon 2026 brief: the eight things each team must demonstrate, the five-step
novelty statement, the 30-mark rubric, SDG alignment and the technology readiness level. Each row points at the evidence;
measured values and run metadata come from the generated [EVALUATION_RESULTS.md](EVALUATION_RESULTS.md). The brief itself is
[proposal/DBTHON2026_Challenge.pdf](proposal/DBTHON2026_Challenge.pdf); the original proposal is
[proposal/ZeroEntry_DBThon2026_Proposal.md](proposal/ZeroEntry_DBThon2026_Proposal.md).

## 1. In one paragraph

Indian rules, court directions and government guidance set requirements for hazardous sewer cleaning, but they do not by
themselves describe this prototype's complete data model or executable checks. ZeroEntry turns selected sourced requirements,
guidance thresholds and explicit product assumptions into a PostgreSQL permit workflow. A permit can become `AUTHORISED` only
when the configured checks pass, including for direct SQL writes through the application role; a separate review process flags
defined gaps in clearance records. A fatality workflow atomically records the configured case, contractor status, permit and
invoice changes.
The prototype enforces recorded database state; it cannot observe whether a person physically entered or certify field data.

## 2. What each team must demonstrate (the brief's eight components)

| # | Component | What we show | Evidence |
|---|---|---|---|
| 1 | Problem definition | Sewer and septic-tank worker safety in India; the motivating problem and target users are described with source limitations. The users are municipal engineers, site supervisors, sanitation workers, contractors, auditors and administrators. | [PROJECT_SPEC §2-3](../PROJECT_SPEC.md#2-the-real-world-problem), [proposal §3](proposal/ZeroEntry_DBThon2026_Proposal.md#3-the-problem-real-current-and-local) |
| 2 | Domain | Urban sanitation and occupational safety in municipal sewer maintenance, with Tamil Nadu ULB demo data. Multiple parties create linked complaint, job, permit and evidence records; applicability of some source clauses and the illustrative gear catalogue remains subject to domain review. | [PROJECT_SPEC §1](../PROJECT_SPEC.md#1-problem-statement-and-how-it-was-interpreted), [ADR-001](decisions/README.md#adr-001--interpret-the-problem-as-sanitation-worker-safety) |
| 3 | Existing system | Public product documents show established industrial electronic permit controls and municipal sanitation/workforce records. The reviewed sources do not establish whether a product can be configured for the exact combination in this prototype; lack of documentation is not proof of absence. | [POLICY_AND_PRIOR_ART](POLICY_AND_PRIOR_ART.md), [proposal §5.1](proposal/ZeroEntry_DBThon2026_Proposal.md#51-what-exists-today-and-what-it-does-not-do) |
| 4 | Database design | 50 application tables, 3NF with deliberate historical-snapshot/projection exceptions justified, ER diagrams and a generated schema reference. | [ER_DIAGRAM](ER_DIAGRAM.md), [DATABASE_DESIGN](DATABASE_DESIGN.md), [SCHEMA_REFERENCE](SCHEMA_REFERENCE.md) |
| 5 | Innovation | (A) database-controlled authorization against configured requirements; (B) human-reviewed evidence-gap detection; (C) atomic recording of selected incident consequences. | [DATABASE_DESIGN §5, §6, §8](DATABASE_DESIGN.md#5-the-entry-gate-zero-entry) |
| 6 | Novelty | The five-step statement for each innovation, with measured benefit. | [§3 below](#3-novelty-in-the-briefs-five-steps) |
| 7 | Prototype | PostgreSQL 16 + FastAPI + a browser UI; setup and test scope are documented. | [README quick start](../README.md#quick-start), [DEMO_SCRIPT](development/DEMO_SCRIPT.md), [TESTING](TESTING.md) |
| 8 | Evaluation | Synthetic evidence-gap labels, database-write probes, query timings and concurrency regressions are reported with their baselines and limits. | [EVALUATION](EVALUATION.md), [generated results](EVALUATION_RESULTS.md), [supplementary temporal benchmark](evaluation/RESULTS.md) |

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

### A. The configured entry gate (database integrity for selected requirements)

| Step | |
|---|---|
| Existing approach | Paper permits and application-side checks are familiar approaches; public industrial permit-to-work documentation already describes gas, competence and authorization controls. |
| Limitation | A check implemented only in one client does not constrain a separate database client. Our evaluation models this limitation by comparing the configured database guard with the same schema's rule triggers disabled; it does not claim all deployed systems lack database enforcement. |
| Proposed approach | `permit_clause_check()` checks selected law, guidance and product rules, represented in the schema with source classifications and applicability notes. The database rechecks configured clauses on `authorise_entry()` and raw authorization updates, and serializes evidence changes with the permit decision. |
| Novel component | The prototype makes a passing authorization state conditional on the same database-owned checks across clients, and stores source-linked parameter history and an immutable explanation snapshot. This is a specific implementation composition, not a legal compiler or a claim that the individual techniques are new. |
| Measurable benefit | E2 reports per-rule invalid database-write outcomes; E4 reports the tested concurrency races; E3 reports timing and buffer measurements by dataset size. See the run-specific [generated result tables](EVALUATION_RESULTS.md); these are not claims that physical entry is prevented. |

### B. Shadow-entry detection by absence

| Step | |
|---|---|
| Existing approach | The team's proposal first used a job-anchored anti-join; this is the stated SQL baseline, not a survey of deployed products. |
| Limitation | That query does not encode the prototype's expected population, exemptions, timely evidence rules, or every entrant's entry record. It can miss or over-flag the labelled evidence cases described in the evaluation. |
| Proposed approach | SE1 starts from eligible resolved complaints and checks source-specific, time-aware evidence; SE2 checks entry logs for each closed permit's entrants. Persisted alerts retain evidence for a human decision, including when late records arrive. |
| Novel component | This prototype combines complaint-anchored and permit-entrant evidence-gap rules with an idempotent alert lifecycle and source-linked invoice holds. The evaluation labels represent expected evidence states, not verified physical human entries. Related permit and municipal systems are documented; the exact composition is not asserted to be globally unique. |
| Measurable benefit | E1 reports per-class evidence-gap metrics and late-record handling against the proposal's naive query; E3 compares only the query variants and workloads stated in the run metadata. See the [generated tables](EVALUATION_RESULTS.md) and the separate [temporal benchmark](evaluation/RESULTS.md). Neither establishes field detection accuracy or deaths prevented. |

### C. Consequences in one transaction

| Step | |
|---|---|
| Existing approach | When related consequence records are written in separate transactions, partial database state is possible. |
| Limitation | A database transaction can provide atomicity for stored changes; it cannot make a real-world payment, deadline or sanction happen. |
| Proposed approach | `record_incident()` records the incident and configured fatality response in one transaction: the ₹30-lakh case, product-defined due date, contractor status change, permit aborts and invoice holds. |
| Novel component | The database demonstrates an all-or-nothing transition across these records. The 2023 Supreme Court direction provides a ₹30 lakh amount for sewer-death compensation; its [2026 clarification](https://api.sci.gov.in/supremecourt/2020/4072/4072_2020_16_39_67600_Order_20-Jan-2026.pdf) addresses historical claims. The prototype records a configured value and does not assess case-specific entitlement. The 30-day deadline and automatic blacklist are product policy, not direct commands from that judgment. |
| Measurable benefit | A forced database failure rolls the procedure's writes back (`tests/db/test_consequences.py`); tests cover invoice-hold enforcement and payment recording. See the tested behaviors; they do not show that compensation was paid or harm prevented. |

What we do **not** claim as new: gas detection, electronic permit-to-work controls, worker registries, relational division,
anti-joins, triggers, transactions or stored hashes. Public product documentation already shows overlapping permit and
municipal capabilities. Our bounded claim concerns this prototype's particular database composition; see
[POLICY_AND_PRIOR_ART.md](POLICY_AND_PRIOR_ART.md). This source review does not establish first use, patentability or global novelty.

Source distinctions affect the configured rules: the 2013 Rules provide the cited oxygen minimum/depth requirement and the
30-minute interval after a 90-minute stretch; CPHEEO guidance supplies the explicit oxygen band used for the upper threshold;
the 15-minute gas-reading age is a product assumption; and the gear catalogue is illustrative. The source table and its
applicability notes are in [POLICY_AND_PRIOR_ART.md](POLICY_AND_PRIOR_ART.md).

## 4. The rubric (30 marks) and where each part is answered

| # | Evaluation component | Marks | COs | Answered by |
|---|---|---|---|---|
| 1 | Problem identification and domain relevance | 4 | CO2 | §2 rows 1-3; [PROJECT_SPEC](../PROJECT_SPEC.md) (problem, roles, business rules `BR-nn`, assumptions `A-nn`) |
| 2 | Database design and modelling | 5 | CO1, CO2 | [ER_DIAGRAM](ER_DIAGRAM.md), [DATABASE_DESIGN](DATABASE_DESIGN.md) (3NF and functional dependencies, keys, gate, detection), generated [SCHEMA_REFERENCE](SCHEMA_REFERENCE.md) |
| 3 | DBMS implementation and technical depth | 5 | CO1 | 16 forward-only SQL/PL/pgSQL migrations; relational division and anti-joins; `EXCLUDE` constraint; state-machine/guard/revision triggers; procedure; cursor showcase; `security_invoker` views; row-level security; row/advisory locks; policy history, positive/negative receipts, transactional replay and idempotency; see [TESTING](TESTING.md) for actual verified scope |
| 4 | Innovation | 4 | CO1, CO2 | §3 A-C |
| 5 | Novelty and differentiation | 5 | CO2 | §3 five-step tables; [proposal §5](proposal/ZeroEntry_DBThon2026_Proposal.md#5-novelty-and-prior-art) (prior art) |
| 6 | SDG alignment and societal impact | 2 | CO2 | §5 |
| 7 | Validation and measurable improvement | 3 | CO1, CO2 | [EVALUATION](EVALUATION.md), run-specific [generated tables](EVALUATION_RESULTS.md), and the separately scoped [temporal benchmark](evaluation/RESULTS.md) |
| 8 | TRL and demonstration | 2 | CO1, CO2 | §6; [DEMO_SCRIPT](development/DEMO_SCRIPT.md) |

## 5. SDG alignment and societal impact

| SDG target (UN wording, abridged) | How ZeroEntry serves it |
|---|---|
| **8.8** Protect labour rights and promote safe and secure working environments for all workers, including those in precarious employment | The database rejects authorization when selected configured checks fail; a worker can stop work on their permit; the recorded-workflow limits include daylight, work-stretch and overlap checks. This does not physically control access to a sewer. |
| **3.9** Substantially reduce deaths and illnesses from hazardous chemicals and air pollution | The prototype requires configured gas readings at three depths. Source classifications distinguish the Rules' oxygen minimum/depth requirement, CPHEEO oxygen-band guidance, ERSU gas thresholds and the CO product assumption. |
| **6.2** Adequate and equitable sanitation for all, with attention to those in vulnerable situations | Mechanised-first: a permit cannot be drafted without a written waiver, and the zero-entry rate per ULB is a report (`v_ulb_year_kpi`). |
| **16.6** Effective, accountable and transparent institutions | Explainable refusals, an append-only audit trail, a read-only auditor role, shadow-entry alerts with history, compensation deadlines that become overdue in a view. |

Wording checked against [sdgs.un.org](https://sdgs.un.org/goals) (goals 3, 6, 8, 16) on 2026-10-07.

**Who may benefit.** Workers may gain a database authorization check and stop-work path; families may gain a timely case record;
ULBs can measure configured mechanisation outcomes; auditors can review evidence gaps and the records behind them. **Limits:**
an alert is a suspicion, not proof of entry; the database enforces recorded state, not physics (a typed gas value can be false);
it does not guarantee a payment, field response or reduction in deaths. Legal applicability and statistics must be checked
before presentation
([README](../README.md#before-presenting)).

## 6. Technology readiness level and demonstration

**Self-assessed TRL 4: technology validated in a laboratory environment.** The prototype runs end to end (database, API, UI)
and has automated unit, database and API tests; evaluation uses synthetic records. It is not TRL 5: no real ULB data, users,
sensors or operating environment have validated it.

Path to TRL 5-6: run detection read-only on one zone's complaint history; trial with supervisors and real detector integration;
review legal applicability and gear schedules; independently review the implemented ULB scoping and registry governance; validate against a managed PostgreSQL service
([ROADMAP backlog](../ROADMAP.md#backlog-not-started-not-required-for-the-demo)).

**Demonstration:** the four-to-five-minute script ([DEMO_SCRIPT](development/DEMO_SCRIPT.md)) shows a configured denial, correction,
authorization, an overrun record, evidence-gap alerts and the consequence transaction. Use the current reproduction commands
and measured run metadata in [EVALUATION.md](EVALUATION.md); the separate temporal benchmark is documented in
[evaluation/RESULTS.md](evaluation/RESULTS.md).

## 7. Proposal versus what was built

| The proposal (2 Oct) said | Built | Why |
|---|---|---|
| 20 tables | 50 tables | sessions, source-classified policy history, decision receipts, readiness, serial resources, completion claims, standalone victim assessments, durable commands/events, governed scope allocations, safety events and source-specific holds; table count is not itself novelty |
| Job-anchored anti-join view | complaint-anchored SE1 with a grace window and exemptions, plus SE2 | the team's query baseline can flag or miss labelled evidence states and cannot represent the human review of late evidence ([ADR-006](decisions/README.md#adr-006--detection-is-anchored-on-the-complaint-and-on-recorded-time), E1) |
| JWT access tokens | opaque server-side sessions | real logout and revocation ([ADR-005](decisions/README.md#adr-005--opaque-server-side-sessions-not-jwt)) |
| PostgreSQL in Docker | embedded PostgreSQL 16 from pip; a real server still works | one-command setup on any laptop ([ADR-004](decisions/README.md#adr-004--embedded-postgresql-for-development-and-tests)) |
| React or Jinja + HTMX | a no-build browser UI | nothing to install or build ([ADR-009](decisions/README.md#adr-009--a-no-build-browser-ui)) |
| `EXCLUDE USING gist (worker_id WITH =, ...)` | `int8range(worker_id, worker_id, '[]')` in the exclusion | the embedded server has no `btree_gist` |
| EXPLAIN ANALYZE screenshots | `scripts/evaluate.py`, reproducible and checked in CI | [ADR-013](decisions/README.md#adr-013--measure-against-a-stated-baseline-read-rule-parameters-once-per-statement-migration-0011) |
| A simulated gas-sensor feed | Authenticated local simulator, explicitly labelled SIMULATED and restricted to educational policy scopes | Software observation demo, not authenticated hardware telemetry |
