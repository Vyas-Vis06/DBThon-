# ZeroEntry entity relationship model

This model covers the 35 application tables in migrations `0001`–`0014`. The sections below split the database by domain so
the relationships remain readable; the [single-page Mermaid source](diagrams/zeroentry-er.mmd) puts all 35 tables in one graph.
For exact column types, nullability, constraints, indexes, triggers and row-level security policies, use the generated
[SCHEMA_REFERENCE.md](SCHEMA_REFERENCE.md). The design rationale is in [DATABASE_DESIGN.md](DATABASE_DESIGN.md).

The ER diagrams are checked against the migrated catalogue by [`tests/db/test_docs_in_sync.py`](../tests/db/test_docs_in_sync.py):
each application table is named, each relationship line corresponds to a real foreign key, and every non-actor foreign-key
relationship appears. The diagrams omit action columns that reference `app_user` (such as `created_by`, `recorded_by`,
`approved_by` and `reviewed_by`) to keep the operational model legible. Account ownership/scope links and the required
`app_user` → `user_session` link remain visible. `audit_log.actor_user_id` is intentionally not a foreign key, so audit history
can outlive a user row.

Read each end's symbol as the allowed number of rows from that named table for one row at the opposite end. `||` means exactly
one, `|o` means zero or one, and `o{` means zero or more. For `manhole ||--o{ complaint`, every complaint points to exactly
one manhole, while a manhole may have no complaints or many. A nullable foreign key appears as `|o` beside its referenced
parent: the referencing child row may point to zero or one parent. A unique foreign key appears as `o|` beside the referencing
child: a parent can have at most one such child. Every connector is an enforced foreign key; a line does not mean that the
relationship is required in both directions.

## Table map

| Area | Tables | Count |
|---|---|---:|
| Identity and access | `role`, `app_user`, `user_session`, `ulb`, `contractor`, `worker`, `audit_log` | 7 |
| Complaints and mechanised work | `manhole`, `resolution_type`, `complaint`, `job`, `machine`, `machine_deployment` | 6 |
| Permit and safety evidence | `entry_permit`, `permit_crew`, `gear_item`, `gear_issue`, `gas_detector`, `gas_reading`, `entry_log`, `permit_safety_event`, `permit_authorization_decision`, `mechanisation_waiver` | 10 |
| Detection and review | `detection_rule`, `shadow_entry_alert`, `shadow_entry_alert_event` | 3 |
| Incidents and money | `incident`, `compensation_case`, `invoice`, `invoice_hold` | 4 |
| Policy and provenance | `legal_clause`, `policy_source`, `legal_clause_source`, `rule_parameter`, `rule_parameter_history` | 5 |
| **Total** | **35 application tables** | **35** |

## Safety evidence and decision provenance (0012–0014)

```mermaid
erDiagram
  entry_permit ||--o{ permit_safety_event : "retains safety history"
  entry_log |o--o{ permit_safety_event : "identifies physical interval"
  entry_permit ||--o| permit_authorization_decision : "preserves original authorization"
  policy_source ||--o{ legal_clause_source : "classifies citation"
  legal_clause ||--o{ legal_clause_source : "references source"
  policy_source ||--o{ rule_parameter : "explains active value"
  rule_parameter ||--o{ rule_parameter_history : "retains revisions"
  policy_source ||--o{ rule_parameter_history : "explains historical value"

  permit_safety_event {
    bigint event_id PK
    bigint permit_id FK
    bigint entry_id FK "optional"
    text event_key UK
    text event_type
    jsonb detail
  }
  permit_authorization_decision {
    bigint decision_id PK
    bigint permit_id FK, UK
    jsonb snapshot
    text snapshot_sha256
  }
  policy_source {
    text source_code PK
    text source_type
    text citation_clause
    text applicability
  }
  legal_clause_source {
    text clause_code PK, FK
    text source_code PK, FK
  }
  rule_parameter_history {
    bigint history_id PK
    text param_key FK
    integer revision
    text source_code FK
    timestamptz effective_at
  }
```

## 1. Identity, access and the organisations

```mermaid
erDiagram
  role ||--o{ app_user : "grants"
  ulb |o--o{ app_user : "home zone of"
  contractor |o--o{ app_user : "scopes a CONTRACTOR login"
  worker |o--o| app_user : "scopes a WORKER login"
  app_user ||--o{ user_session : "signs in through"
  contractor ||--o{ worker : "employs"

  app_user {
    bigint user_id PK
    smallint role_id FK
    bigint contractor_id FK "CONTRACTOR scoping"
    bigint worker_id FK, UK "WORKER scoping"
    text email UK
    text password_hash "bcrypt"
  }
  user_session {
    bigint session_id PK
    bigint user_id FK
    bytea token_hash UK "SHA-256 of the token"
    timestamptz expires_at
  }
  contractor {
    bigint contractor_id PK
    text licence_no UK
    date licence_valid_until
    text status "ACTIVE | SUSPENDED | BLACKLISTED"
  }
  worker {
    bigint worker_id PK
    bigint contractor_id FK
    text namaste_id UK
    date medical_fit_until
    date trained_until
  }
```

## 2. Complaints, jobs and mechanised evidence

```mermaid
erDiagram
  ulb ||--o{ manhole : "contains"
  ulb ||--o{ machine : "owns"
  manhole ||--o{ complaint : "raised against"
  resolution_type |o--o{ complaint : "resolved as"
  complaint ||--o{ job : "worked by"
  contractor ||--o{ job : "assigned"
  job ||--o{ machine_deployment : "tried with"
  machine ||--o{ machine_deployment : "used in"
  job ||--o| mechanisation_waiver : "exempted by"

  complaint {
    bigint complaint_id PK
    bigint manhole_id FK
    text status "OPEN | IN_PROGRESS | RESOLVED"
    timestamptz resolved_at
    text resolution_code FK
  }
  resolution_type {
    text code PK
    boolean requires_evidence "false = intentionally absent"
  }
  job {
    bigint job_id PK
    bigint complaint_id FK
    bigint contractor_id FK
    text method "MECHANISED | MANUAL_EXCEPTION"
  }
  machine_deployment {
    bigint deploy_id PK
    bigint job_id FK
    bigint machine_id FK
    text outcome "CLEARED | FAILED"
    timestamptz recorded_at "server clock: timely evidence"
  }
  mechanisation_waiver {
    bigint waiver_id PK
    bigint job_id FK, UK
    text reason_code
    text justification "at least 50 characters"
  }
```

## 3. The entry gate: permits, crew, gear, gas, entries

`legal_clause` and `rule_parameter` have no foreign keys: the gate function `permit_clause_check()` reads them by key. They are
the law expressed as data (titles, legal references, thresholds).

```mermaid
erDiagram
  job ||--o{ entry_permit : "needs"
  entry_permit ||--o{ permit_crew : "crewed by"
  worker ||--o{ permit_crew : "serves on"
  permit_crew ||--o{ gear_issue : "is issued"
  gear_item ||--o{ gear_issue : "catalogue item"
  entry_permit ||--o{ gas_reading : "tested by"
  gas_detector ||--o{ gas_reading : "measured with"
  permit_crew ||--o{ entry_log : "goes underground"

  entry_permit {
    bigint permit_id PK
    bigint job_id FK
    text status "DRAFT > AUTHORISED > CLOSED | ABORTED; DRAFT > CANCELLED"
    timestamptz authorised_at
    timestamptz valid_until
  }
  permit_crew {
    bigint permit_id PK, FK
    bigint worker_id PK, FK
    text crew_role "ENTRANT | STANDBY | SUPERVISOR"
  }
  gear_issue {
    bigint issue_id PK
    bigint permit_id FK "with worker_id: FK to permit_crew"
    bigint worker_id FK
    text gear_code FK
    text serial_no
  }
  gas_reading {
    bigint reading_id PK
    bigint permit_id FK
    bigint detector_id FK
    text depth_level "TOP | MID | BOTTOM"
    numeric o2_pct
    numeric h2s_ppm
    timestamptz taken_at
  }
  entry_log {
    bigint entry_id PK
    bigint permit_id FK "with worker_id: FK to permit_crew"
    bigint worker_id FK
    tstzrange period "no overlap per worker (EXCLUDE)"
  }
  legal_clause {
    text clause_code PK
    text legal_ref
  }
  rule_parameter {
    text param_key PK
    numeric value
    boolean is_assumption
  }
```

## 4. Consequences and detection by absence

`audit_log` has deliberately **no** foreign key (history must outlive the rows and users it describes).

```mermaid
erDiagram
  manhole ||--o{ incident : "site of"
  worker ||--o{ incident : "victim"
  contractor ||--o{ incident : "employer at the time"
  job |o--o{ incident : "during"
  entry_permit |o--o{ incident : "under"
  permit_crew |o--o{ incident : "crew member on"
  incident ||--o| compensation_case : "owes"
  job ||--o{ invoice : "billed as"
  invoice ||--o{ invoice_hold : "blocked by"
  shadow_entry_alert |o--o{ invoice_hold : "placed"
  incident |o--o{ invoice_hold : "placed"
  complaint ||--o{ shadow_entry_alert : "suspected for"
  detection_rule ||--o{ shadow_entry_alert : "fired"
  contractor |o--o{ shadow_entry_alert : "responsible"
  shadow_entry_alert ||--o{ shadow_entry_alert_event : "history"

  incident {
    bigint incident_id PK
    text incident_type "FATALITY | DISABILITY | NEAR_MISS"
    bigint worker_id FK
    bigint contractor_id FK "snapshot"
    bigint permit_id FK
  }
  compensation_case {
    bigint case_id PK
    bigint incident_id FK, UK
    numeric amount_due
    numeric amount_paid
    date due_by
  }
  invoice_hold {
    bigint hold_id PK
    bigint invoice_id FK
    text reason "SHADOW_ENTRY | INCIDENT"
    bigint alert_id FK "exactly one source"
    bigint incident_id FK "exactly one source"
    timestamptz released_at
  }
  shadow_entry_alert {
    bigint alert_id PK
    bigint complaint_id FK "UK with rule_code"
    text rule_code FK
    text status "OPEN > EVIDENCE_RECEIVED > CONFIRMED | DISMISSED"
    timestamptz evidence_deadline
  }
  audit_log {
    bigint log_id PK
    text table_name
    text row_pk
    jsonb old_data
    jsonb new_data
  }
```

## How the records fit together

**From a complaint to a work decision.** A complaint belongs to one manhole and may have one or more jobs. A job is assigned to
a contractor. The machine-first path records machine deployments and their final outcome receipt. If a manual exception is
needed, the job may have at most one approved `mechanisation_waiver`; the database requires that waiver before a permit can be
drafted. A job can have multiple permit attempts, each with its own crew, issued gear, gas readings and entry records.

**From draft to safety evidence.** An `entry_permit` moves through `DRAFT → AUTHORISED → CLOSED`, or to `ABORTED` after
authorisation; an unused draft can become `CANCELLED`. The gate checks stored evidence before it allows the transition. A
successful transition creates one immutable `permit_authorization_decision` containing the clause results, relevant evidence
and policy revisions. Crew membership is a many-to-many relationship between permits and workers, implemented by
`permit_crew`; its composite primary key `(permit_id, worker_id)` makes one worker's role unique within a permit. `gear_issue`
and `entry_log` point back to that exact crew pair, so records cannot attach to a worker who was never assigned to that permit.
Safety stops, expiry and overstay evidence are retained in `permit_safety_event`.

**From an evidence gap to review.** Detection evaluates only its explicit expected population. A candidate creates a persisted
`shadow_entry_alert` for a complaint and rule; the unique `(complaint_id, rule_code)` key prevents duplicate alerts. Alert
changes are recorded in `shadow_entry_alert_event`. Late evidence can move an open alert to `EVIDENCE_RECEIVED`, which still
requires a reviewer. An alert hold and an incident hold both use `invoice_hold`, whose check requires exactly one source; an
invoice may have multiple holds, and each source governs its own release.

**From an incident to financial consequences.** An incident always identifies the worker, the contractor responsible at the
time, and the manhole. The contractor is stored as a snapshot because a worker's current contractor can change. Job and permit
context are optional. An incident may have at most one `compensation_case`; near misses need no case. `record_incident()` applies
the incident, contractor, permit and invoice consequences in one transaction.

**From policy to an explainable decision.** `policy_source` classifies citations; `legal_clause_source` links clauses and
sources many-to-many. Current `rule_parameter` rows are the inputs to the gate, and `rule_parameter_history` appends each
change with its source and reason. These rows preserve current configuration and its change history; they do not replay past
decisions. The schema does not add direct foreign keys from a permit to every policy row it reads; the immutable decision
snapshot preserves the policy and evidence used at authorization time.

## Keys and scope

`permit_crew` and `legal_clause_source` are composite-key bridge tables. `mechanisation_waiver.job_id`,
`permit_authorization_decision.permit_id` and `compensation_case.incident_id` are unique foreign keys, giving each parent zero
or one such child. The alert key `(complaint_id, rule_code)` is unique across the pair, so a complaint can still have alerts
for multiple rules. `invoice_hold` has optional `alert_id` and `incident_id` foreign keys; a row-level check makes the two
mutually exclusive and requires one to be present.

The drawings show relationships declared by foreign keys. They do not add implied links inferred from common IDs, trigger
logic or query joins. Each entity block highlights its key and selected domain fields; consult the generated schema reference
for the full table definition and for foreign keys to `app_user` that are omitted from the drawings.
