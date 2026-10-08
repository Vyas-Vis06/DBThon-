# ER diagrams

## ZE-2 evidence, replay and unregistered incident intake (0015–0016)

```mermaid
erDiagram
  ulb ||--o{ ulb_contractor_scope : "records governed allocation"
  contractor ||--o{ ulb_contractor_scope : "is allocated to scope"
  ulb ||--o{ ulb_detector_scope : "records instrument allocation"
  gas_detector ||--o{ ulb_detector_scope : "is allocated to scope"
  gear_item ||--o{ gear_asset : "classifies serial asset"
  ulb ||--o{ gear_asset : "owns serial inventory"
  gear_asset |o--o{ gear_issue : "identifies issued asset"
  entry_permit ||--o{ permit_site_gear : "assigns shared equipment"
  gear_asset ||--o{ permit_site_gear : "identifies shared asset"
  entry_permit ||--o{ permit_readiness : "retains readiness observations"
  entry_permit ||--o{ permit_resource_reservation : "occupies resources"
  worker |o--o{ permit_resource_reservation : "reserves actual crew"
  gear_asset |o--o{ permit_resource_reservation : "reserves serial asset"
  entry_permit ||--o{ permit_decision_receipt : "retains all decisions"
  permit_decision_receipt |o--o{ entry_log : "optionally binds supplied decision"
  ulb ||--o{ completion_claim : "identifies source scope"
  job |o--o{ completion_claim : "optionally matches external claim"
  job ||--o| completion_projection : "projects review gaps"
  ulb ||--o| outbox_scope_counter : "serializes scope sequence"
  ulb ||--o{ outbox_event : "retains committed notifications"
  ulb ||--o{ incident_report : "scopes standalone report"
  job |o--o{ incident_report : "optionally links registered work"
  entry_permit |o--o{ incident_report : "optionally links permission"
  contractor |o--o{ incident_report : "optionally links contractor"
  incident_report ||--o{ incident_report_victim : "records affected people"
  worker |o--o{ incident_report_victim : "optional registry identity"
  incident_report_victim ||--o| incident_assessment_case : "opens pending assessment"
  incident_report |o--o{ invoice_hold : "preserves report provenance"
  command_dedup {
    bigint dedup_id PK
    bigint actor_user_id FK
    text operation
    uuid idempotency_key
    text body_sha256
    jsonb response_json
  }
```

`command_dedup` references `app_user`; the identity edges remain omitted under the diagram convention below.
Outbox `entity_id` is a typed notification identifier, not an invented foreign key. Read the current generated schema
for complete constraints and optionality.

The tables are drawn in smaller diagrams that share entities. Column-level detail
(every type, constraint, index, trigger and policy) is in the generated [SCHEMA_REFERENCE.md](SCHEMA_REFERENCE.md); the reasons
behind the design are in [DATABASE_DESIGN.md](DATABASE_DESIGN.md).

**Kept in sync by a test** (`tests/db/test_docs_in_sync.py`): every table appears below, every relationship line is a real
foreign key, and every foreign key is drawn, except the "who did it" columns that point at `app_user`
(`created_by`, `recorded_by`, `approved_by`, `decided_by`, `reviewed_by`, ...), which are left out so the pictures stay readable.

Notation (crow's foot): `||` exactly one · `|o` zero or one · `o{` zero or more. GitHub renders these diagrams; elsewhere paste
them into <https://mermaid.live>.

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
