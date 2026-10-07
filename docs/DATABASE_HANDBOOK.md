# Database handbook

ZeroEntry is a PostgreSQL project about one practical question: when work is recorded as cleared, do the records show the
clearance path the configured safety workflow expects? A second question is preventative: can any client authorize an entry
without the configured safeguards? The database answers both from connected rows, guarded state changes and reviewable
history.

This is an approachable companion for judges and developers. For the exact schema, read the generated
[SCHEMA_REFERENCE.md](SCHEMA_REFERENCE.md). For design decisions and full rule rationale, use
[DATABASE_DESIGN.md](DATABASE_DESIGN.md). The [table guide](TABLE_GUIDE.md) gives a readable map of all 35 tables, and the
[ER diagrams](ER_DIAGRAM.md) show the relationships.

## A useful reading order

For a quick understanding, start with [PROJECT_EXPLAINED.md](guide/PROJECT_EXPLAINED.md), then read this page. Use the
[table guide](TABLE_GUIDE.md) and [ER diagrams](ER_DIAGRAM.md) to see how records fit together. Then inspect
[DATABASE_DESIGN.md](DATABASE_DESIGN.md) for the full invariants and [SCHEMA_REFERENCE.md](SCHEMA_REFERENCE.md) for exact
columns and PostgreSQL objects.

For a live database walkthrough, follow [DEMO_COMMANDS.md](guide/DEMO_COMMANDS.md). For review evidence, read
[SECURITY.md](../SECURITY.md), [TESTING.md](TESTING.md), [EVALUATION.md](EVALUATION.md) and the run-specific
[generated evaluation results](EVALUATION_RESULTS.md). The source-of-truth for business rules and assumptions is
[PROJECT_SPEC.md](../PROJECT_SPEC.md).

## One system, with one rule owner

The interface and API make the workflow usable. PostgreSQL decides whether recorded state is valid.

~~~mermaid
flowchart LR
  B["Browser UI"] -->|"session cookie + CSRF"| A["FastAPI<br/>authenticate · role-check · validate"]
  H["HTTP API clients"] --> A
  A -->|"parameterized SQL · one transaction/request"| Z["ze_app"]
  Z --> P[("PostgreSQL 16<br/>keys · checks · exclusion<br/>functions · triggers · views · RLS")]
  D["SQL / psql demo"] --> O["local owner or ze_app"]
  O --> P
  M["Migrations"] --> P
~~~

The API authenticates people, checks endpoint roles, validates request shapes and translates SQLSTATE errors into responses.
It does not recreate the permit gate in Python. The application connects as **ze_app**, a role that owns no tables and has
limited grants. A raw statement through that role still meets the same database triggers. A local database owner can inspect
all records and run controlled demos, but the owner is privileged and sits outside the runtime security boundary.

The current implementation uses 14 forward-only SQL migrations, revision 0001 through 0014, to create 35 application
tables. PostgreSQL 16 is bundled for local development; a PostgreSQL server version 15 or newer is supported. Alembic runs
the checked-in SQL migrations; the application never creates tables from ORM models.

A complaint's normal path is:

~~~mermaid
flowchart LR
  C["Complaint"] --> J["Contractor job"]
  J --> M{"Machine result"}
  M -->|"cleared"| R["Resolved with machine evidence"]
  M -->|"failed / not possible"| W["Engineer waiver"]
  W --> P["Draft permit"]
  P --> G{"Database gate"}
  G -->|"fails"| P
  G -->|"passes"| E["Authorized entry and logged intervals"]
  E --> R
  R --> X["Time-aware absence scan"]
  X -->|"evidence missing after grace"| A["Alert + source-linked invoice hold"]
  A --> H["Engineer review"]
~~~

That flow exists across separate normalized records. A machine outcome belongs to a deployment; a permit belongs to a job;
a crew assignment belongs to a specific permit; a clearance complaint can have more than one job. This structure lets SE1
look across every job on a complaint instead of treating one unsuccessful job as the whole story.

## Why the tables are normalized

The tables use keys to represent facts once, then link those facts with foreign keys. For example:

- **complaint_id → manhole_id, description, status, resolution fields.** The complaint does not repeat its ULB name. The
  ULB is reached through manhole, so changing the zone label has one source.
- **worker_id → contractor_id, name, NAMASTE id and credential dates.** A permit assignment points to the worker; the
  worker's current employer and qualifications are not copied into every job row.
- **(permit_id, worker_id) → crew_role.** A person's role is specific to a permit, not a permanent attribute of the worker.
  The composite primary key means one person cannot be both STANDBY and ENTRANT on the same permit.
- **role_id → role name.** Accounts reference a role catalogue instead of repeating free-text role labels; a unique email
  and natural registry/licence codes prevent duplicate identities.

The job → complaint → manhole → ULB path is easy to query with joins; see [01_joins.sql](../database/queries/01_joins.sql).
The mapping tables **permit_crew** and **legal_clause_source** express many-to-many relationships with attributes and
constraints rather than arrays or duplicated columns.

There are a few intentional snapshots. **incident.contractor_id** records the employer at the time of an incident, even if
the worker later changes employer. **shadow_entry_alert.reason**, contractor and evidence deadline preserve what the scan
observed when it raised the alert. **permit_authorization_decision.snapshot** preserves the original configured checklist,
source classifications, evidence identifiers and parameter revisions. These values explain a past decision; they are not
accidental duplicates.

For the database's complete functional-dependency discussion and justified exceptions, see
[DATABASE_DESIGN §4](DATABASE_DESIGN.md#4-normalisation-3nf-and-the-deliberate-exceptions).

## What PostgreSQL enforces

PostgreSQL provides several layers of integrity. A CHECK is ideal for one row's internal consistency, foreign keys connect
the record graph, and triggers/functions handle rules that need other rows, current time or a multi-row action.

| Database feature | What it does here | Example |
|---|---|---|
| Primary and unique keys | Give records stable identity and prevent duplicate natural identifiers. | A complaint has one complaint_id; a detector has a unique serial_no; one alert exists per complaint/rule. |
| Foreign keys | Stop a record from pointing to a missing parent. Composite FKs can require a specific relationship. | gear_issue and entry_log reference the exact (permit_id, worker_id) crew pair. An incident's permit/job pair must belong together. |
| CHECK constraints | Keep individual rows internally coherent. | A RESOLVED complaint has both resolution time and resolution code; a compensation status agrees with amount_paid; a hold has exactly one source. |
| Triggers and functions | Enforce state transitions and decisions that involve multiple rows. | An entry_permit cannot be born AUTHORISED; a raw UPDATE to AUTHORISED runs the same clause check as the API. |
| Exclusion constraint | Make overlapping time ranges impossible for the same worker, even when simultaneous clients race. | entry_log uses the GiST constraint ex_entry_no_overlap. |
| Views | Give reports and screens stable, named query interfaces. | v_permit_compliance shows failing clauses; v_suspected_shadow_entry surfaces evidence gaps. |
| Row-level security and grants | Limit what the API role can see or change after the endpoint role check. | A contractor sees only rows joined to that contractor; ze_app cannot write the audit log or run DDL. |

### Authorization uses relational division

A permit requires every entrant to have every catalogue item marked statutory. In set terms, make all required entrant/item pairs, then deny anyone for whom a pair has no matching gear_issue row. This is relational division, commonly written as nested NOT EXISTS. An empty gear catalogue must not make the condition pass by vacuous truth, so ZeroEntry fails closed when no statutory gear is configured.

The same shape checks the expected gas-test population: every permit needs an acceptable latest reading at TOP, MID and BOTTOM. “Latest” matters: an old good reading cannot mask a newer unsafe one. The production function also checks freshness, calibration, and configurable limits and returns one explanation row for each clause.

See [04_division_and_anti_join.sql](../database/queries/04_division_and_anti_join.sql) for the plain SQL examples and the production checklist calls. The API and raw UPDATE are both protected by the same database gate.

### The interval overlap rule is declarative

An entry is stored as a PostgreSQL timestamp range, not two unconnected strings. The GiST exclusion constraint combines that interval with a single-point integer range made from worker_id. Two rows conflict when they represent the same worker and their periods overlap. This moves the “one worker cannot be in two places at once” invariant into PostgreSQL, where concurrent inserts are checked against each other.

Entry triggers handle rules that the range alone cannot express: the permit must still be AUTHORISED, the worker must be an ENTRANT on that permit, the start must be inside the validity window and configured daylight interval, and the work/rest limits must hold. A truthful exit may still be recorded after a stop; a late or excessive exit is retained with safety-event evidence rather than erased.

### Functions, triggers, procedures and views

The principal database call paths are:

| Object | Job in the workflow |
|---|---|
| permit_clause_check | Read-only, explainable checklist for the configured permit clauses, including clause code, pass/fail and detail. |
| authorise_entry | Locks a draft permit, evaluates the gate and performs the transition only if all clauses pass. A trigger independently rechecks the transition. |
| scan_shadow_entries | Persists eligible absence candidates after their grace deadline; idempotent by complaint/rule. Late evidence sends an open alert to review. |
| stop_work / safety maintenance | Stop affected authorized permits when a worker, contractor, detector, reading or time-based condition invalidates the current gate. The periodic sweep also finds expiries and overstays. |
| record_incident | One procedure call for an incident and its configured database consequences; all writes commit or roll back together. |
| record_compensation_payment | Locks one case before adding a payment, preventing concurrent overpayment. |
| release_invoice_hold | Releases incident holds with a note; an alert hold is released through the alert decision path instead. |
| audit_row / append-only guards | Record selected changes and refuse runtime rewrites of evidence, policy history and audit history. |

The main reporting views are:

| View | Meaning |
|---|---|
| v_permit_compliance | Current clause readiness of draft permits. |
| v_shadow_se1 / v_shadow_se2 / v_shadow_candidate | Candidate evidence gaps under the complaint and entrant rules. |
| v_suspected_shadow_entry | Candidate reasons, deadlines, late-evidence flag and any persisted alert status. Candidates still inside grace are visible as pending, not yet ready for a scan-created alert. |
| v_compensation_overdue | Unpaid cases whose configured deadline has passed. |
| v_invoice_status | Invoice status and active hold reasons. |
| v_contractor_risk | A review ranking built from the A-10 illustrative weights; it is not a legal measure. |
| v_ulb_year_kpi | Annual mechanised-job share for each ULB. It uses job.method values, so it is a configured zero-entry proxy rather than proof that no person physically entered. |
| v_ulb_year_incidents | Incidents, fatalities, configured compensation due/paid and mean days to recorded compensation. |

All report views use PostgreSQL security-invoker semantics so they do not silently run with the view owner's privileges and bypass RLS. A missing rule_parameter is an error, not a hard-coded fallback.

## Finding an absence without calling it proof

SE1 defines an expected population in data: complaints resolved with a type marked requires_evidence. Its evidence may be a
cleared machine deployment on any job for that complaint or a closed, authorized permit with a recorded entry. SE2 looks at
each entrant on a closed permit and asks whether a matching entry log exists. Both queries use NOT EXISTS anti-joins against
an explicit expected population. Resolutions such as duplicate, referred out, withdrawn or no blockage found are intentionally
excluded through resolution_type data.

~~~text
expected records
  - timely, matching clearance evidence
  = candidate evidence gap
  -> persisted alert after the grace window
  -> human review
~~~

A candidate is an evidence gap, not proof a person entered. If an eligible complaint has no job at all, it can still be
flagged; anchoring on job would hide that absence. Each alert keeps a reason and evidence deadline. A scan can create it as OPEN or, when late evidence already exists, as
EVIDENCE_RECEIVED. An OPEN alert may move to EVIDENCE_RECEIVED when late evidence appears, or go directly to a human
CONFIRMED/DISMISSED decision; either review state can be decided. Late evidence does not erase the alert: an engineer reviews
it, and a dismissal releases only that alert's invoice holds. Re-running the scan does not duplicate, re-open or auto-close reviewed
alerts. Details of the business-rule interpretation are in [PROJECT_SPEC.md](../PROJECT_SPEC.md#1-problem-statement-and-how-it-was-interpreted).

### Event time, receipt time and policy time

The system records different times for different facts; the distinction is central to the absence query.

- A machine deployment has field/event start and end times, deployment-row receipt recorded_at, and final-outcome receipt
  outcome_recorded_at. A late final result cannot inherit the earlier deployment insertion time. Finalized outcomes and their
  event times are immutable. Where the old audit trail could not establish when an outcome was finalized, the migrated
  outcome_recorded_at remains NULL and is not treated as timely evidence.
- A permit uses its authorization/end times; each entry has a reported period and server-assigned receipt time. SE1 evidence
  must be recorded by the complaint's grace deadline. SE2 uses the closed permit's entrants and the entry records expected
  for them. Entry event time is not substituted for its receipt time.
- The configured grace value lives in rule_parameter. The views materialize the one-row parameter read once per statement
  (migration 0011), rather than calling the parameter function for every joined complaint.

This is selective temporal evidence, not a general temporal database. There are no generic valid-time/system-time versions
for every table and no universal point-in-time restore of business policy. Audit timestamps are transaction-time evidence;
PostgreSQL transaction timestamps are not exact commit receipts. The detection rules use the specific event/receipt columns
they need. The historical backfill leaves uncertain receipts unknown instead of inventing precision.

Policy provenance works similarly. policy_source classifies a source as law, court direction, guidance or product policy and
stores a version, cited clause and applicability note. legal_clause_source connects sources to clauses. When an ADMIN changes
a rule parameter, PostgreSQL assigns a new revision and receipt time and appends the actor, source and required written reason
to rule_parameter_history. Migration 0014 inserted a baseline of current values because earlier revision history was not
present; that baseline does not claim what the policy was before the migration.

On successful authorization, a database trigger writes one immutable JSONB decision snapshot with the gate output, the
specific evidence IDs and values, relevant policy revisions and source metadata. PostgreSQL computes a SHA-256 digest over
the snapshot representation. This makes a later reader able to explain the saved decision even after policy changes. The
digest is local integrity evidence: it is not an external signature, a legal conclusion, or a defense against the database
owner.

## Transactions, isolation and real races

Each API request is one database transaction and commits before the response is returned. A refusal rolls back that request.
The design uses READ COMMITTED plus explicit row locks for operations that must decide against current committed data.

**Permit decision vs. changing evidence.** authorise_entry takes FOR UPDATE on the permit row. Guards for crew, gear, gas
readings and entries take a conflicting FOR SHARE on the same permit. If an entrant is added while authorization runs, one
transaction waits; after the first commits, the waiter reads the new status and refuses the forbidden change. This prevents a
permit from being approved against crew evidence that changed underneath the decision. Dependency-change triggers also
revalidate active permits when a worker credential, contractor license/status or detector calibration changes.

**Invoice payment vs. a new hold.** The common lock order is complaint first, then invoice row. Invoice creation, alert or
incident hold placement, approval and payment serialize on those rows. If payment finishes first, the invoice remains paid
without a retroactive hold. If the hold arrives first, approval/payment is refused. These paths require READ COMMITTED and
return retryable SQLSTATE 40001 at other isolation levels: a REPEATABLE READ snapshot does not refresh simply because the
transaction waited on a lock. A direct caller should retry the full transaction at READ COMMITTED.

**Atomic incident response.** record_incident writes the incident, the configured compensation case/deadline when applicable,
contractor status, permit stops and source-linked invoice holds in the same transaction. If one later CHECK fails, none of the
earlier inserts survive. The sample [06_transactions.sql](../database/queries/06_transactions.sql) demonstrates both a
rolled-back call and a forced failure. Compensation payment likewise locks the case row before testing whether the new amount
would exceed the due amount.

These are real multi-connection database regressions, not only mocked API tests. See
[tests/db/test_concurrency.py](../tests/db/test_concurrency.py) and
[tests/db/test_temporal_evidence_and_invoice_races.py](../tests/db/test_temporal_evidence_and_invoice_races.py).

## Indexes and reporting shape

PostgreSQL does not automatically index the referencing side of a foreign key. The schema adds indexes for FK joins and
selective access paths. The key examples are:

- A partial resolved-complaint index for the SE1 expected population.
- Deployment/job/outcome and final-outcome-receipt indexes for the clearance anti-join.
- Permit/job/status and permit/depth/latest-reading indexes for the gate and evidence lookup.
- Permit/worker and gear-issue indexes for crew lookups and relational division.
- A partial active-hold index for invoice blocking.
- Time and row-key indexes for audit history, plus prefix indexes for worker and manhole search.

The detection view stores the grace parameter in a MATERIALIZED one-row CTE. A measured plan comparison motivated migration
0011: PostgreSQL had inlined the previous CTE, evaluating the same rule lookup repeatedly within a large anti-join. The
materialized version preserves results while reading the configured value once per statement. Current performance numbers
are machine- and workload-specific; consult [EVALUATION.md](EVALUATION.md) and its generated result file rather than copying
old timings into a presentation.

Reporting is designed to expose operational state, not decorate it. It answers questions such as “which permits currently
fail a configured clause?”, “what remains unpaid past a configured deadline?”, “why is this invoice held?”, “how many
jobs were marked mechanised by zone/year?”, and “which evidence gaps are waiting for review?” Zero-entry and risk figures
should always be described as the view's configured calculations; they do not independently validate field reality.

## Security and trust boundary

The application path combines endpoint role guards, parameterized database access, least-privilege grants and row-level
security. The API sets the authenticated identity in transaction-local PostgreSQL settings; worker and contractor policies use
those values to scope rows, and the context disappears at transaction end. Without a request context, scoped rows are hidden
from ze_app. AUDITOR reads relevant evidence without write access.

The project also has a local owner console. It can see all rows and demonstrates that database triggers still run when a user
tries a raw SQL bypass. That is useful for showing that a client cannot skip a trigger; it must not be confused with the
runtime permission boundary. Owners and superusers bypass RLS and can change the schema, disable triggers or alter rows.
Append-only triggers, audit logs and snapshot hashes protect application-managed workflows, not against a hostile database
owner. RLS is defense in depth: it does not make arbitrary SQL under ze_app safe if an attacker can set the transaction-local
identity settings themselves. Parameterized queries and least privilege remain essential.

## Operate, migrate, seed and inspect safely

**Find the current schema state.** The authoritative SQL is in [database/migrations/sql/](../database/migrations/sql/); each
numbered migration has a matching Alembic revision in database/migrations/versions/. Migrations are forward-only. Inspect the
SQL before changing it, never edit one already applied, and add a new migration with `python scripts/db.py new <name>`. The generated [SCHEMA_REFERENCE.md](SCHEMA_REFERENCE.md) comes from the migrated
catalogue; regenerate it with python scripts/gen_docs.py after a schema change rather than editing it by hand.

~~~sh
python scripts/db.py current
python scripts/db.py migrate
~~~

For a local demo, `python run.py` starts the embedded PostgreSQL, applies pending migrations, loads demo data and runs the
maintenance flow. The deterministic synthetic data is authored in [01_base.sql](../database/seeds/01_base.sql) and
[02_scenarios.sql](../database/seeds/02_scenarios.sql); the Python seed wrapper also creates password hashes for demo
accounts. The scenario file runs through the real gate for ordinary examples, with narrow owner-only fixture handling for
historical timeline examples. The demo seeder refuses production. For a separately configured server, see
[SETUP.md](SETUP.md); it documents the owner migration connection and the least-privileged runtime connection. The database
reset command drops data, so reserve it for an isolated development database.

For direct inspection, run a simple SELECT from a table or view through the SQL runner:

~~~sh
python run.py sql "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
python run.py sql "SELECT status, count(*) FROM shadow_entry_alert GROUP BY status ORDER BY status"
python run.py sql "SELECT * FROM v_permit_compliance ORDER BY permit_id"
~~~

The SQL runner talks directly to the demo database; it does not route SQL through FastAPI, and it executes SQL with the
database owner’s privileges. It does not force read-only mode: avoid calling write-capable functions or running mutations while
exploring. In psql, an explicit read-only transaction gives an additional guard against accidental writes:

~~~sql
BEGIN READ ONLY;
SELECT status, count(*) FROM shadow_entry_alert GROUP BY status ORDER BY status;
ROLLBACK;
~~~

`python run.py psql` is the local owner console. `python run.py psql --app` connects as ze_app. The latter has no authenticated
request context when opened interactively, so RLS returns no tenant-scoped rows by default; it does not simulate a signed-in
contractor or worker. A request context is set transaction-locally by the API. Do not use owner credentials to represent the
runtime trust boundary.

The committed [SQL showcase](../database/queries/) includes read-only query files 01–05; 06 demonstrates changes inside
explicit transactions that end in ROLLBACK; 07 catches each refusal and leaves data unchanged. The runnable commands and
individual file links are collected in [DEMO_COMMANDS.md](guide/DEMO_COMMANDS.md).

## Reproduce the database story

Start the app once with **python run.py**. Then use the SQL runner in a second terminal. The query files are committed,
annotated examples and can also be inspected without starting the app.

| Query file | What it demonstrates |
|---|---|
| [01_joins.sql](../database/queries/01_joins.sql) | Follow the complaint-to-ULB dossier; see crew, gear, gas, incidents and source-linked holds. |
| [02_aggregates.sql](../database/queries/02_aggregates.sql) | Aggregate cases and readings; query annual KPI and risk/reporting views. |
| [03_search_and_filter.sql](../database/queries/03_search_and_filter.sql) | Indexed prefixes, common UI filters and audit lookups. |
| [04_division_and_anti_join.sql](../database/queries/04_division_and_anti_join.sql) | Read the two signature set operations and compare plain examples to production views/functions. |
| [05_views_functions_procedures.sql](../database/queries/05_views_functions_procedures.sql) | Inspect reporting views, call signatures, time helpers, functions, procedures, triggers and routines from the catalogue. |
| [06_transactions.sql](../database/queries/06_transactions.sql) | Watch atomicity, rollback and the incident consequence transaction. |
| [07_trigger_refusals.sql](../database/queries/07_trigger_refusals.sql) | Attempt bypasses and see the database's refusal reasons. |

Run the full sequence against the running demo database:

~~~sh
python run.py
python run.py sql
~~~

Or inspect the most DB-centric examples individually:

~~~sh
python run.py sql database/queries/04_division_and_anti_join.sql
python run.py sql database/queries/06_transactions.sql
python run.py sql database/queries/07_trigger_refusals.sql
~~~

The SQL runner uses the local demo server started by run.py. Its demo queries are designed to leave persistent state unchanged:
the read-only files only read, the transaction demonstration ends with ROLLBACK, and trigger-refusal attempts catch each error.
For owner and least-privilege sessions, use **python run.py psql** and **python run.py psql --app** respectively. The
[demo command sheet](guide/DEMO_COMMANDS.md) explains data-directory and port options.

The repository also has a 19-condition disposable showcase (**python run.py showcase**) and database tests. Relevant proofs
include [test_entry_gate.py](../tests/db/test_entry_gate.py), [test_concurrency.py](../tests/db/test_concurrency.py),
[test_consequences.py](../tests/db/test_consequences.py), [test_detection.py](../tests/db/test_detection.py),
[test_rls.py](../tests/db/test_rls.py) and [test_privileges.py](../tests/db/test_privileges.py). The evaluation builds
synthetic evidence-gap labels and invalid-write probes in a throwaway database. Its results measure matching those labels and
refusing the tested write shapes; they are not field accuracy, real-entry ground truth, proof that physical access was blocked,
or evidence that compensation was paid. See the limitations in [EVALUATION.md](EVALUATION.md) before presenting numbers.

## Current boundaries

ZeroEntry is a prototype. Its database enforces and explains the configured rules over data it receives. It cannot verify that
a worker wore the gear, that a typed gas reading matches the air, or that the permit controlled physical access. It uses
synthetic demonstration records and evaluation fixtures, not a field-validated ULB feed or authenticated detector stream.
Some configured thresholds, daylight bounds, compensation timing and catalogue applicability are product assumptions or
guidance choices, and legal applicability remains subject to review. The fixed IST helpers assume Indian operations.

The system also lacks a general valid-time/system-time history for every relation, automatic point-in-time policy replay,
external signature anchor, incremental event-driven scan, GIS integration and ULB-level staff scoping. History on newly
introduced provenance objects begins at migration 0014; older timestamps are not upgraded into certainty. These boundaries
are tracked in [PROJECT_SPEC.md §7](../PROJECT_SPEC.md#7-limitations-and-edge-cases), [SECURITY.md](../SECURITY.md) and the
[ROADMAP](../ROADMAP.md).
