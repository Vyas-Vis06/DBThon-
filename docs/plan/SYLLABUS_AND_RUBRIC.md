# ZeroEntry: syllabus and rubric coverage plan

**Planning artifact only.** Every implementation path and test ID below is proposed work; no application, SQL demo, benchmark, or test has been run. “Integrated planned” means implement and demonstrate in the DB-backed prototype; “Controlled demo planned” means a bounded, synthetic exercise that is not claimed as a production capability; “Conceptual” means explain accurately without claiming implementation. Course syllabi are BCSE302P Database Systems Lab and BCSE302L Database Systems, both syllabus version 1.0. Challenge requirements are from DBTHON2026 Challenge.pdf.

## Laboratory experiments

| Official indicative experiment | Planned coverage and proof artifact | Status/classification |
|---|---|---|
| 1. Data Definition and Data Manipulation Language | `db/demos/01_ddl_dml.sql`: create/migrate the relational schema, seed a synthetic ULB/job/crew, and show insert, select, update through permitted transitions, and archive behavior. IDs `LAB1-DDL`, `LAB1-DML`. | Integrated planned |
| 2. Constraints | `db/demos/02_constraints.sql`: PK/FK, NOT NULL, CHECK, uniqueness, exclusion/overlap or transaction-backed resource reservation, and negative inserts for invalid evidence/state. `LAB2-PASS`, `LAB2-REJECT`. | Integrated planned |
| 3. Single row functions | `db/demos/03_functions.sql`: date/time validity and expiry, normalization/display, and safe derived status using PostgreSQL scalar functions; show boundary inputs. `LAB3-BOUNDARY`. | Integrated planned |
| 4. Operators and group functions | `db/demos/04_operators_aggregates.sql`: boolean/null operators, filters, grouping and aggregates for job/evidence summaries; explain `COUNT`, conditional aggregates, and why null is not proof of safety. `LAB4-AGG`. | Integrated planned |
| 5. Sub query, views and joins | `db/demos/05_queries_views.sql`: joins across job, actual entrants, evidence and reservations; `EXISTS`/`NOT EXISTS` for missing evidence and completion reconciliation; read views for dashboard/audit. `LAB5-JOIN`, `LAB5-ANTI`, `LAB5-VIEW`. | Integrated planned |
| 6. High Level Language Extensions — Procedures, Functions, Cursors and Triggers | `db/demos/06_routines.sql`: eligibility/decision function, atomic incident procedure, audit/revision trigger, and explicit cursor open-fetch-close over a bounded report with cleanup on error. `LAB6-FN`, `LAB6-PROC`, `LAB6-TRG`, `LAB6-CURSOR`. | Integrated planned |

These are the six experiments exactly as listed in the lab PDF. The challenge prototype should make the lab SQL visible and runnable independently of the UI. Planned paths are future artifacts, not files asserted to exist.

## Theory syllabus traceability

Key: **I** = Integrated planned; **D** = Controlled demo planned; **C** = Conceptual. Test/demo IDs identify planned evidence. Brief rationale keeps classification honest: core relational decisions are implemented; physical internals and broader paradigms are taught or simulated rather than falsely claimed.

| Module and syllabus topics | Coverage, planned artifact / evidence | Class |
|---|---|---|
| 1. Database Systems Concepts and Architecture: need for database systems; characteristics and advantages of DBMS; actors including DBA; DBMS classification; data models; schemas and instances; three-schema architecture; DBMS environment; centralized and client/server architectures; overall DBMS architecture | `docs/architecture.md` plus ER/schema, API and trust-boundary diagram. Show why a shared DBMS is needed for linked evidence, constraints and auditing; distinguish physical PostgreSQL, relational schema, and role-specific views/API. Present DBA/admin and other actors. Discuss centralized Docker database and client/server app architecture, and classify relational system. | I for schema/architecture; C for comparison and internal overall architecture |
| 2. Relational Model and E-R Modeling: candidate/primary/foreign keys; integrity constraints; nulls; attribute types, relationships, structural constraints; relational constraints; ER-to-relational mapping; extended ER, generalization/specialization, aggregation | `docs/er-diagram.*`, `docs/schema-contract.md`, `db/migrations/versions/`; `LAB1-DDL`, `LAB2-PASS/REJECT`. Model worker as identity/entity plus role/qualification relations; job/activity, evidence, policy and resource relations. Explain optional evidence and SQL three-valued logic. Map associative relations and cardinalities. Use role/category or typed subtype design where it clarifies specialization; ER aggregation is shown conceptually around a job’s participation/evidence bundle. | I for keys, mappings, constraints, null treatment; D for ER aggregation/EER explanation |
| 3. Relational Database Design: design/refinement/guidelines; functional dependencies and axioms; 1NF, 2NF, 3NF, BCNF, multivalued dependencies/4NF, join dependencies/5NF | `docs/normalization.md`: identify keys and dependencies for worker-job participation, evidence, rule versions, and reservation relations; show decomposition to 3NF/BCNF where appropriate and lossless joins. Explain why repeating entrant/evidence arrays and storing derived decision state create anomalies. Discuss MVD and join dependency/4NF/5NF examples as design analysis; do not claim every relation requires 5NF. `NORM-REVIEW`. | I for normalized relational design; C for formal axioms/advanced decomposition proof beyond selected examples |
| 4. Physical Database Design and Query Processing: file organization; single/multi-level/dynamic indexing; B+ trees; static/dynamic hashing; relational algebra; SQL-to-algebra; query processing; algebraic/heuristic optimization; join optimization by index/hash; tuple relational calculus | Index likely filters/joins with `db/indexes/` and `benchmarks/`; capture `EXPLAIN (ANALYZE, BUFFERS)` for identical useful results. Map one query to relational algebra and describe selection/projection pushdown and join order. Compare index use with a controlled unindexed copy where useful. Explain PostgreSQL’s physical choices without asserting its internals are a hand-built B+ tree/hash implementation. Tuple relational calculus and file organizations are whiteboard concepts. `PHY-PLAN`. | I for workload-specific indexes and query plan evidence; D for index comparison; C for algorithm internals/calculus |
| 5. Transaction Processing and Recovery: transaction concepts, ACID, states; serial/serializable schedules; recoverability; conflict serializability; log recovery, deferred/immediate update, shadow paging | Reservation and incident flows use transactions; run two-session overlap and forced failure/rollback; describe state changes and atomicity. `db/tests/transactions.sql`, `evidence/db/`; `TX-ATOMIC`, `TX-RACE`, `TX-ROLLBACK`. Explain PostgreSQL WAL/log recovery and backup/restore plan; demonstrate backup restore if time permits. Shadow paging is a conceptual comparison only. | I for transactions/ACID outcomes; D for concurrency/rollback; C for recovery algorithm details and shadow paging |
| 6. Concurrency Control: concurrent transactions, lost update; timestamp protocols/Thomas write rule; lock protocols, compatibility matrix, 2PL, lock conversions, graph/tree protocols; deadlock detection/prevention; multigranularity locking | Deliberate concurrent reservation and stale receipt tests; document chosen PostgreSQL isolation/row or advisory lock strategy, invariant and retry behavior. `TX-RACE`, `TX-LOST-UPDATE`. Explain lock compatibility, 2PL and deadlock handling with schedule diagrams, including why selected DB behavior is not a full implementation of timestamp, Thomas, graph/tree, or multigranularity protocols. | I for selected lock/transaction invariants; D for races; C for other named protocols |
| 7. NoSQL Database Management: need, CAP theorem, key-value, column families, document and graph databases | `docs/architecture.md` records why relational integrity and transactional joins fit this prototype; compare hypothetical evidence/event or graph needs. Explain CAP trade-offs and four store families. No NoSQL service is required or represented as deployed. | Conceptual |
| 8. Contemporary Issues | Short presentation discussion of database security, privacy/minimisation, auditability, synthetic data and limits; no unspecified contemporary trend is claimed as implemented. | Conceptual |

The theory topics above are enumerated from all eight modules in the supplied theory PDF. “Integrated” does not mean every theory algorithm is implemented; the class column states the boundary.

## Provisional schema inventory and policy sequence

The frozen schema contract specifies **37 base relations**: `role`, `app_user`, `ulb`, `manhole`, `complaint`, `contractor`, `worker`, `job`, `machine`, `machine_deployment`, `mechanisation_waiver`, `entry_permit`, `permit_crew`, `gear_item`, `gear_issue`, `gas_detector`, `gas_reading`, `entry_log`, `incident`, `compensation_case`, `invoice`, `rule_parameter`, `audit_log`, `legal_clause`, `rule`, `compliance_certificate`, `shadow_ledger`, `worker_refusal`, `gear_asset`, `incident_victim`, `completion_claim`, `job_completion`, `resource_reservation`, `outbox_event`, `request_dedup`, `readiness_evidence`, and `certificate_evidence`. This list matches `SCHEMA_CONTRACT.md`; it replaces the earlier provisional inventory. `certificate_evidence` carries normalized foreign-key links to the receipt’s gas, gear issue, crew, readiness, waiver or reservation evidence. `compliance_certificate` also stores a JSON snapshot, while normalized links provide referential integrity. `permit_crew` uses UUID `id` as primary key and `UNIQUE (permit_id, worker_id)`.

The default-deny policy gate order is G0 jurisdiction/activity eligibility; G1 gear; G2 gas; G3 calibration; G4 crew; G5 exception approval; G6 time/window; G7 qualification; G8 ongoing validity. G0 cannot be bypassed by complete PPE or educational fixture controls: a demo-only eligible policy must be visibly marked non-deployable. Decision receipts bind policy version, evidence IDs/revisions and expiry; entry-start rechecks. No legal rule is asserted by this plan.

## Eight-row official 30-mark rubric evidence matrix

The challenge PDF gives a 30-mark heading and page 4 includes **TRL 2 & Demonstration, 2 marks**. The prior seven-row/28-mark rendering omitted that row. Preserve the seven published values and add the page 4 TRL row; no marks are redistributed.

| # / component | Marks, CO | Planned concrete artifact and proof ID | Owner; demo moment | Status |
|---|---:|---|---|---|
| 1 Problem Identification & Domain Relevance | 4, CO2 | `docs/novelty-evidence.md`: municipal sanitation safety-evidence consistency, users, verified Garima actual-participant gap, baseline limits. `R1-PROBLEM`. | Coordinator/domain; opening problem and existing-system comparison | Planned |
| 2 Database Design & Modeling | 5, CO1/CO2 | ER diagram, 37-relation schema from the canonical contract, keys/cardinalities, normalization explanation. `R2-ER`, `R2-NORM`. | A DB; show ER then relation/keys | Planned |
| 3 DBMS Implementation & Technical Depth | 5, CO1 | PostgreSQL migrations, constraints, routines, views, indexes, permissions and runnable six lab demos. `R3-LAB1`–`R3-LAB6`, `R3-DENY`. | A DB with B integration; direct SQL and UI path | Planned |
| 4 Innovation | 4, CO1/CO2 | Versioned evidence-linked receipt, recheck, exclusive reservations and reconciliation/atomic incident mechanism. `R4-RECEIPT`, `R4-RACE`, `R4-RECON`. | A/B; invalidate stale receipt and show reconciliation | Planned |
| 5 Novelty & Differentiation | 5, CO2 | Named baseline comparison and qualified claim: municipal workflow integrates actual participant evidence with DB-enforced decisions and downstream reconciliation; no universal-first claim. `R5-BASELINE`. | Coordinator; explain documented gap and boundaries | Planned |
| 6 SDG Alignment & Societal Impact | 2, CO2 | `docs/sdg-evidence.md`: direct proposed links to worker safety, sanitation and accountability; impact is intended, not achieved/measured. `R6-SDG`. | Coordinator/domain; one concise slide | Planned |
| 7 Validation & Measurable Improvement | 3, CO1/CO2 | Controlled labelled scenarios, correctness/false-denial counts, latency/query-plan CSV and method in `benchmarks/`; no fabricated results. `R7-METRICS`. | B bench; report actual results and limitations | Planned |
| 8 TRL 2 & Demonstration | 2, CO1/CO2 | `docs/demo-script.md`, deterministic synthetic fixture and working DB-backed prototype evidence. TRL 2 is a concept/technology-formulated stage; label readiness honestly and do not imply deployment validation. `R8-TRL2`. | C UI/demo with all; golden path plus backup | Planned |
| **Total** | **30** |  |  |  |

Official challenge also expects problem, domain, existing system, design, innovation, novelty, prototype and evaluation to be shown. These are covered above. Innovation names the mechanism; novelty compares its evidenced difference with a named baseline.

## 23-item proposal checklist (planning checklist, not official rules)

These items reproduce Astra prompt section 9. They originate in the proposal/planning prompt and **are not represented as an official mandatory DBThon checklist**. Each item maps to planned artifact and acceptance evidence.

| # | Proposal checklist item | Future artifact / proof |
|---:|---|---|
| 1 | ER diagram | `docs/er-diagram.*`; `R2-ER` |
| 2 | Relational schema | `docs/schema-contract.md`; `LAB1-DDL` |
| 3 | At least eight related tables | schema inventory; FK graph evidence `SCHEMA-REL` |
| 4 | At least four primary entities | ER with `ulb`, `worker`, `job`, `manhole`; `R2-ER` |
| 5 | At least three meaningful relationships | cardinalities and associative entities; `SCHEMA-REL` |
| 6 | Primary and foreign keys | migration DDL and rejected orphan test; `LAB2-PASS/REJECT` |
| 7 | Constraints | CHECK/FK/unique/exclusion or transactional invariant tests; `LAB2-REJECT` |
| 8 | Justified 3NF or better | `docs/normalization.md`; `NORM-REVIEW` |
| 9 | CRUD with defensible delete/archive policy | demo SQL/API; immutable audit and archive rules; `CRUD-ARCHIVE` |
| 10 | Multi-table joins | `db/demos/05_queries_views.sql`; `LAB5-JOIN` |
| 11 | Aggregates | `db/demos/04_operators_aggregates.sql`; `LAB4-AGG` |
| 12 | Views | read/report views; `LAB5-VIEW` |
| 13 | Transactions | reservation/incident atomicity; `TX-ATOMIC` |
| 14 | Triggers | revision/audit trigger with direct test; `LAB6-TRG` |
| 15 | Stored procedures/functions plus lab cursor | SQL routine demos and explicit cursor lifecycle; `LAB6-FN/PROC/CURSOR` |
| 16 | Indexes | migration plus plan/buffer comparison; `PHY-PLAN` |
| 17 | ORM with migrations | backend ORM migration history; clean-database migration check `MIG-CLEAN` |
| 18 | Authentication | FastAPI auth path with test identities; `AUTH-LOGIN` |
| 19 | At least two working roles; plan proposed six | Admin, Engineer/RSA, Supervisor, Worker, Contractor, Auditor permission matrix; `AUTH-ROLE` |
| 20 | RBAC, representative RLS and direct access tests | DB policies/grants and cross-tenant/unauthorized direct SQL checks; `AUTH-RLS` |
| 21 | Search/filtering | jobs/evidence filters with bound parameters and pagination; `API-FILTER` |
| 22 | Validation and meaningful exceptions | structured validation/denial codes and negative tests; `API-ERROR` |
| 23 | Secrets hygiene and parameterised queries | `.env.example`, ignored local secrets, static/code review and injection-shaped input check; `SEC-SECRETS` |

## Delivery ownership and unimplemented status

The coordinator owns domain framing, rubric/release evidence and integration decisions. Worker A owns PostgreSQL schema, procedures/functions, lab SQL and database evidence. Worker B owns FastAPI/authentication/tests/benchmarks and integration against frozen contracts. Worker C owns React UI, demo flow and presentation assets. They coordinate through a single versioned schema/API contract; B and C may use stable mock fixtures while A builds the DB lane. Course integration is recommended and pedagogically valuable, **not a compulsory official challenge rule**.

Planned app paths include `db/demos/01_ddl_dml.sql` through `06_routines.sql`, `benchmarks/`, and `docs/normalization.md`; these are future deliverables and remain unimplemented at this planning stage. No application tests or benchmarks are claimed as run. References used for this coverage document: the three exact supplied PDFs and section 9 of `outputs/ZeroEntry_Astra_Master_Prompt.md`; no legal inference or external legal source is used.
