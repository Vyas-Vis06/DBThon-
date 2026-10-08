# Schema reference (generated)

> **Generated** by `python scripts/gen_docs.py` from the migrated database catalogue. **Do not edit by hand**; a test
> fails when this file is out of date. The reasoning behind the design is in [DATABASE_DESIGN.md](DATABASE_DESIGN.md) and the
> diagrams are in [ER_DIAGRAM.md](ER_DIAGRAM.md).

Schema revision: `0016` · PostgreSQL 16 · 50 application tables.

How to read it: *a foreign key with no `ON DELETE` clause is `NO ACTION`: deleting the referenced row is refused while
dependants exist.* Check, unique and exclusion constraints are shown exactly as PostgreSQL stores them. Row-level security
policies and triggers are listed per table.


| Table | Purpose |
|---|---|
| [`app_user`](#app_user) | Login accounts; contractor_id / worker_id scope CONTRACTOR and WORKER users. |
| [`audit_log`](#audit_log) | Append-only record of every change to key tables. |
| [`command_dedup`](#command_dedup) | Transactional idempotency response cache keyed by trusted actor, operation and client UUID; business effects commit atomically with the saved response. |
| [`compensation_case`](#compensation_case) | Compensation owed for an incident, with deadline and payments. |
| [`complaint`](#complaint) | Blockage complaint against a manhole. |
| [`completion_claim`](#completion_claim) |  |
| [`completion_projection`](#completion_projection) |  |
| [`contractor`](#contractor) | Licensed contractor; status ACTIVE/SUSPENDED/BLACKLISTED. |
| [`detection_rule`](#detection_rule) | Catalogue of absence-detection rules (SE1, SE2); can be disabled. |
| [`entry_log`](#entry_log) | A worker's time underground; overlaps are excluded. |
| [`entry_permit`](#entry_permit) | Permit to enter; AUTHORISED only through the clause gate. |
| [`gas_detector`](#gas_detector) | Gas detector with calibration expiry. |
| [`gas_reading`](#gas_reading) | Atmosphere reading at a depth level (append-only). |
| [`gear_asset`](#gear_asset) |  |
| [`gear_issue`](#gear_issue) | Gear issued to a crew member for a permit, with serial number. |
| [`gear_item`](#gear_item) | Protective-gear catalogue; statutory items are mandatory for entrants. |
| [`incident`](#incident) | Fatality, disability or near miss. |
| [`incident_assessment_case`](#incident_assessment_case) | Pending internal assessment and reference values; not a legal award, blacklist or payment record. |
| [`incident_report`](#incident_report) | Standalone review intake; linked assets are optional and classification remains review-required until external review. |
| [`incident_report_victim`](#incident_report_victim) | Victim-specific report detail; worker registry linkage is optional and aliases can preserve unregistered people. |
| [`invoice`](#invoice) | Contractor invoice for a job. |
| [`invoice_hold`](#invoice_hold) | Reason an invoice cannot be approved or paid, with provenance. |
| [`job`](#job) | Work order for a complaint, assigned to a contractor. |
| [`legal_clause`](#legal_clause) | Titles and legal references for each entry-gate clause. |
| [`legal_clause_source`](#legal_clause_source) | One or more classified source/applicability records for each entry checklist clause. |
| [`machine`](#machine) | Mechanised cleaning equipment. |
| [`machine_deployment`](#machine_deployment) | A machine used on a job and its outcome (clearance evidence). |
| [`manhole`](#manhole) | A sewer or septic access point. |
| [`mechanisation_waiver`](#mechanisation_waiver) | Written reason, approved by the RSA, why a machine cannot do the job. |
| [`outbox_event`](#outbox_event) | Durable, privacy-minimised events ordered per ULB by a transactional counter row; event_id identity is not a replay cursor. |
| [`outbox_scope_counter`](#outbox_scope_counter) |  |
| [`permit_authorization_decision`](#permit_authorization_decision) | Immutable database-created JSONB snapshot for each successful authorization transition; not a formal proof or owner-resistant signature. |
| [`permit_crew`](#permit_crew) | Crew of a permit with exactly one role per worker. |
| [`permit_decision_receipt`](#permit_decision_receipt) |  |
| [`permit_readiness`](#permit_readiness) |  |
| [`permit_resource_reservation`](#permit_resource_reservation) |  |
| [`permit_safety_event`](#permit_safety_event) | Append-only local safety event evidence; it does not assert external delivery. |
| [`permit_site_gear`](#permit_site_gear) |  |
| [`policy_source`](#policy_source) | Migration-managed source metadata; source type distinguishes law, court directions, guidance and product policy. |
| [`resolution_type`](#resolution_type) | How a complaint was resolved and whether that resolution must leave evidence. |
| [`role`](#role) | The six application roles. |
| [`rule_parameter`](#rule_parameter) | Statutory thresholds and policy numbers as editable, audited data. |
| [`rule_parameter_history`](#rule_parameter_history) | Append-only current-value change history with actor/reason/source; not a historical rule-replay engine. |
| [`shadow_entry_alert`](#shadow_entry_alert) | Persisted suspicion that an entry happened unrecorded. |
| [`shadow_entry_alert_event`](#shadow_entry_alert_event) | Append-only lifecycle history of alerts. |
| [`ulb`](#ulb) | Urban local body / municipal zone. |
| [`ulb_contractor_scope`](#ulb_contractor_scope) |  |
| [`ulb_detector_scope`](#ulb_detector_scope) |  |
| [`user_session`](#user_session) | Opaque server-side sessions; only a SHA-256 of the cookie token is stored. |
| [`worker`](#worker) | Sanitation worker registered under NAMASTE. |

## app_user

Login accounts; contractor_id / worker_id scope CONTRACTOR and WORKER users.

| Column | Type | Null? | Default |
|---|---|---|---|
| `user_id` | bigint | NOT NULL | `generated always as identity` |
| `role_id` | smallint | NOT NULL |  |
| `ulb_id` | bigint | nullable |  |
| `contractor_id` | bigint | nullable |  |
| `worker_id` | bigint | nullable |  |
| `email` | text | NOT NULL |  |
| `full_name` | text | NOT NULL |  |
| `password_hash` | text | NOT NULL |  |
| `is_active` | boolean | NOT NULL | `true` |
| `failed_logins` | smallint | NOT NULL | `0` |
| `locked_until` | timestamp with time zone | nullable |  |
| `created_at` | timestamp with time zone | NOT NULL | `now()` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `app_user_pkey` | `PRIMARY KEY (user_id)` |
| Unique | `app_user_email_key` | `UNIQUE (email)` |
| Unique | `app_user_worker_id_key` | `UNIQUE (worker_id)` |
| Foreign key | `app_user_contractor_id_fkey` | `FOREIGN KEY (contractor_id) REFERENCES contractor(contractor_id)` |
| Foreign key | `app_user_role_id_fkey` | `FOREIGN KEY (role_id) REFERENCES role(role_id)` |
| Foreign key | `app_user_ulb_id_fkey` | `FOREIGN KEY (ulb_id) REFERENCES ulb(ulb_id)` |
| Foreign key | `app_user_worker_id_fkey` | `FOREIGN KEY (worker_id) REFERENCES worker(worker_id)` |
| Check | `app_user_failed_logins_check` | `CHECK ((failed_logins >= 0))` |
| Check | `app_user_full_name_check` | `CHECK ((length(btrim(full_name)) > 0))` |
| Check | `ck_email_form` | `CHECK (((email = lower(email)) AND (POSITION(('@'::text) IN (email)) > 1)))` |

**Triggers**

- `trg_app_user_scope_guard`: `BEFORE INSERT OR UPDATE OF role_id, contractor_id, worker_id ... app_user_scope_guard()`
- `trg_audit`: `AFTER INSERT OR DELETE OR UPDATE OF role_id, is_active, password_hash, contractor_id, worker_id, ulb_id ... audit_row('user_id', 'password_hash')`

## audit_log

Append-only record of every change to key tables.

| Column | Type | Null? | Default |
|---|---|---|---|
| `log_id` | bigint | NOT NULL | `generated always as identity` |
| `occurred_at` | timestamp with time zone | NOT NULL | `now()` |
| `actor_user_id` | bigint | nullable |  |
| `action` | text | NOT NULL |  |
| `table_name` | text | NOT NULL |  |
| `row_pk` | text | NOT NULL |  |
| `old_data` | jsonb | nullable |  |
| `new_data` | jsonb | nullable |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `audit_log_pkey` | `PRIMARY KEY (log_id)` |
| Check | `audit_log_action_check` | `CHECK ((action = ANY (ARRAY['INSERT'::text, 'UPDATE'::text, 'DELETE'::text])))` |

**Indexes** (beyond those that back the constraints above)

- `ix_audit_row`: `btree (table_name, row_pk, occurred_at DESC)`
- `ix_audit_time`: `btree (occurred_at DESC)`

**Triggers**

- `trg_append_only`: `BEFORE DELETE OR UPDATE ... forbid_change()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_select` for SELECT: USING `app_has_role(VARIADIC ARRAY['ADMIN'::text, 'AUDITOR'::text])`

## command_dedup

Transactional idempotency response cache keyed by trusted actor, operation and client UUID; business effects commit atomically with the saved response.

| Column | Type | Null? | Default |
|---|---|---|---|
| `dedup_id` | bigint | NOT NULL | `generated always as identity` |
| `actor_user_id` | bigint | NOT NULL |  |
| `operation` | text | NOT NULL |  |
| `idempotency_key` | uuid | NOT NULL |  |
| `body_sha256` | text | NOT NULL |  |
| `response_status` | smallint | NOT NULL |  |
| `response_json` | jsonb | NOT NULL |  |
| `created_at` | timestamp with time zone | NOT NULL | `now()` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `command_dedup_pkey` | `PRIMARY KEY (dedup_id)` |
| Unique | `command_dedup_actor_user_id_operation_idempotency_key_key` | `UNIQUE (actor_user_id, operation, idempotency_key)` |
| Foreign key | `command_dedup_actor_user_id_fkey` | `FOREIGN KEY (actor_user_id) REFERENCES app_user(user_id) ON DELETE RESTRICT` |
| Check | `command_dedup_body_sha256_check` | `CHECK ((body_sha256 ~ '^[0-9a-f]{64}$'::text))` |
| Check | `command_dedup_operation_check` | `CHECK (((length(btrim(operation)) >= 1) AND (length(btrim(operation)) <= 120)))` |
| Check | `command_dedup_response_status_check` | `CHECK (((response_status >= 100) AND (response_status <= 599)))` |

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_insert_actor` for INSERT:  WITH CHECK `(actor_user_id = app_user_id())`
- `rls_select_actor` for SELECT: USING `(actor_user_id = app_user_id())`

## compensation_case

Compensation owed for an incident, with deadline and payments.

| Column | Type | Null? | Default |
|---|---|---|---|
| `case_id` | bigint | NOT NULL | `generated always as identity` |
| `incident_id` | bigint | NOT NULL |  |
| `amount_due` | numeric(12,2) | NOT NULL |  |
| `amount_paid` | numeric(12,2) | NOT NULL | `0` |
| `due_by` | date | NOT NULL |  |
| `status` | text | NOT NULL | `'OPEN'::text` |
| `opened_at` | timestamp with time zone | NOT NULL | `now()` |
| `paid_at` | timestamp with time zone | nullable |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `compensation_case_pkey` | `PRIMARY KEY (case_id)` |
| Unique | `compensation_case_incident_id_key` | `UNIQUE (incident_id)` |
| Foreign key | `compensation_case_incident_id_fkey` | `FOREIGN KEY (incident_id) REFERENCES incident(incident_id)` |
| Check | `ck_case_not_overpaid` | `CHECK ((amount_paid <= amount_due))` |
| Check | `ck_case_status_matches_payments` | `CHECK ((((status = 'OPEN'::text) AND (amount_paid = (0)::numeric) AND (paid_at IS NULL)) OR ((status = 'PARTIAL'::text) AND (amount_paid > (0)::numeric) AND (amount_paid < amount_due) AND (paid_at IS NULL)) OR ((status = 'PAID'::text) AND (amount_paid = amount_due) AND (paid_at IS NOT NULL))))` |
| Check | `compensation_case_amount_due_check` | `CHECK ((amount_due > (0)::numeric))` |
| Check | `compensation_case_amount_paid_check` | `CHECK ((amount_paid >= (0)::numeric))` |
| Check | `compensation_case_status_check` | `CHECK ((status = ANY (ARRAY['OPEN'::text, 'PARTIAL'::text, 'PAID'::text])))` |

**Triggers**

- `trg_audit`: `AFTER INSERT OR DELETE OR UPDATE ... audit_row('case_id')`
- `trg_no_delete`: `BEFORE DELETE ... forbid_change()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('incident'::text, incident_id)` WITH CHECK `staff_scope_row('incident'::text, incident_id)`
- `rls_insert` for INSERT:  WITH CHECK `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])`
- `rls_select` for SELECT: USING `(app_is_staff() OR (EXISTS ( SELECT 1
   FROM incident i
  WHERE ((i.incident_id = compensation_case.incident_id) AND (i.contractor_id = app_contractor_id())))))`
- `rls_update` for UPDATE: USING `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])` WITH CHECK `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])`

## complaint

Blockage complaint against a manhole.

| Column | Type | Null? | Default |
|---|---|---|---|
| `complaint_id` | bigint | NOT NULL | `generated always as identity` |
| `manhole_id` | bigint | NOT NULL |  |
| `description` | text | NOT NULL |  |
| `raised_at` | timestamp with time zone | NOT NULL | `now()` |
| `status` | text | NOT NULL | `'OPEN'::text` |
| `resolved_at` | timestamp with time zone | nullable |  |
| `resolution_code` | text | nullable |  |
| `resolved_by` | bigint | nullable |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `complaint_pkey` | `PRIMARY KEY (complaint_id)` |
| Foreign key | `complaint_manhole_id_fkey` | `FOREIGN KEY (manhole_id) REFERENCES manhole(manhole_id)` |
| Foreign key | `complaint_resolution_code_fkey` | `FOREIGN KEY (resolution_code) REFERENCES resolution_type(code)` |
| Foreign key | `complaint_resolved_by_fkey` | `FOREIGN KEY (resolved_by) REFERENCES app_user(user_id)` |
| Check | `ck_complaint_resolution_complete` | `CHECK ((((status = 'RESOLVED'::text) = (resolved_at IS NOT NULL)) AND ((status = 'RESOLVED'::text) = (resolution_code IS NOT NULL))))` |
| Check | `ck_complaint_resolved_after_raised` | `CHECK (((resolved_at IS NULL) OR (resolved_at >= raised_at)))` |
| Check | `complaint_description_check` | `CHECK ((length(btrim(description)) > 0))` |
| Check | `complaint_status_check` | `CHECK ((status = ANY (ARRAY['OPEN'::text, 'IN_PROGRESS'::text, 'RESOLVED'::text])))` |

**Indexes** (beyond those that back the constraints above)

- `ix_complaint_manhole`: `btree (manhole_id)`
- `ix_complaint_resolved`: `btree (resolved_at) WHERE (status = 'RESOLVED'::text)`
- `ix_complaint_status_raised`: `btree (status, raised_at DESC)`

**Triggers**

- `trg_audit`: `AFTER INSERT OR DELETE OR UPDATE ... audit_row('complaint_id')`
- `trg_completion_projection_complaint`: `AFTER INSERT OR UPDATE OF status, resolved_at, resolution_code ... completion_projection_source_changed()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('manhole'::text, manhole_id)` WITH CHECK `staff_scope_row('manhole'::text, manhole_id)`
- `rls_insert` for INSERT:  WITH CHECK `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])`
- `rls_select` for SELECT: USING `(app_is_staff() OR worker_on_complaint(complaint_id) OR (EXISTS ( SELECT 1
   FROM job j
  WHERE ((j.complaint_id = complaint.complaint_id) AND (j.contractor_id = app_contractor_id())))))`
- `rls_update` for UPDATE: USING `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])` WITH CHECK `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])`

## completion_claim



| Column | Type | Null? | Default |
|---|---|---|---|
| `claim_id` | bigint | NOT NULL | `generated always as identity` |
| `source_ulb_id` | bigint | NOT NULL |  |
| `source` | text | NOT NULL |  |
| `external_id` | text | NOT NULL |  |
| `external_job_ref` | text | NOT NULL |  |
| `matched_job_id` | bigint | nullable |  |
| `claimed_status` | text | NOT NULL |  |
| `claimed_at` | timestamp with time zone | NOT NULL |  |
| `received_at` | timestamp with time zone | NOT NULL | `clock_timestamp()` |
| `payload` | jsonb | NOT NULL | `'{}'::jsonb` |
| `match_status` | text | NOT NULL | `'UNMATCHED'::text` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `completion_claim_pkey` | `PRIMARY KEY (claim_id)` |
| Unique | `uq_completion_claim_scope_source_external` | `UNIQUE (source_ulb_id, source, external_id)` |
| Foreign key | `completion_claim_matched_job_id_fkey` | `FOREIGN KEY (matched_job_id) REFERENCES job(job_id)` |
| Foreign key | `completion_claim_source_ulb_id_fkey` | `FOREIGN KEY (source_ulb_id) REFERENCES ulb(ulb_id)` |
| Check | `completion_claim_check` | `CHECK (((matched_job_id IS NULL) = (match_status <> 'MATCHED'::text)))` |
| Check | `completion_claim_external_id_check` | `CHECK ((length(btrim(external_id)) > 0))` |
| Check | `completion_claim_external_job_ref_check` | `CHECK ((length(btrim(external_job_ref)) > 0))` |
| Check | `completion_claim_match_status_check` | `CHECK ((match_status = ANY (ARRAY['MATCHED'::text, 'UNMATCHED'::text, 'AMBIGUOUS'::text])))` |
| Check | `completion_claim_source_check` | `CHECK ((length(btrim(source)) > 0))` |

**Indexes** (beyond those that back the constraints above)

- `ix_completion_claim_job`: `btree (matched_job_id, claimed_status) WHERE (matched_job_id IS NOT NULL)`

**Triggers**

- `trg_completion_claim_scope`: `BEFORE INSERT OR UPDATE OF matched_job_id, source_ulb_id ... completion_claim_scope_guard()`
- `trg_completion_projection_claim`: `AFTER INSERT OR DELETE OR UPDATE ... completion_projection_source_changed()`
- `trg_outbox_completion_claim`: `AFTER INSERT OR UPDATE ... outbox_for_completion_claim()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_ulb(source_ulb_id)` WITH CHECK `staff_scope_ulb(source_ulb_id)`
- `rls_insert` for INSERT:  WITH CHECK `app_has_role(VARIADIC ARRAY['ADMIN'::text, 'ENGINEER'::text])`
- `rls_insert_claim_staff` for INSERT:  WITH CHECK `((app_role() = ANY (ARRAY['ADMIN'::text, 'ENGINEER'::text])) AND staff_scope_row('ulb'::text, source_ulb_id))`
- `rls_select` for SELECT: USING `(app_is_staff() OR ((matched_job_id IS NOT NULL) AND contractor_owns_job(matched_job_id)))`
- `rls_select_claim_staff` for SELECT: USING `(app_role() = ANY (ARRAY['ADMIN'::text, 'ENGINEER'::text, 'SUPERVISOR'::text, 'AUDITOR'::text]))`

## completion_projection



| Column | Type | Null? | Default |
|---|---|---|---|
| `job_id` | bigint | NOT NULL |  |
| `evidence_revision` | bigint | NOT NULL | `0` |
| `gap_codes` | jsonb | NOT NULL | `'[]'::jsonb` |
| `has_gap` | boolean | NOT NULL | `false` |
| `disposition` | text | NOT NULL | `'REVIEW_REQUIRED'::text` |
| `computed_at` | timestamp with time zone | NOT NULL | `clock_timestamp()` |
| `reviewed_by` | bigint | nullable |  |
| `review_reason` | text | nullable |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `completion_projection_pkey` | `PRIMARY KEY (job_id)` |
| Foreign key | `completion_projection_job_id_fkey` | `FOREIGN KEY (job_id) REFERENCES job(job_id)` |
| Foreign key | `completion_projection_reviewed_by_fkey` | `FOREIGN KEY (reviewed_by) REFERENCES app_user(user_id)` |
| Check | `completion_projection_check` | `CHECK (((reviewed_by IS NULL) = (review_reason IS NULL)))` |
| Check | `completion_projection_disposition_check` | `CHECK ((disposition = ANY (ARRAY['REVIEW_REQUIRED'::text, 'RESOLVED'::text, 'EXCEPTION_RECORDED'::text])))` |
| Check | `completion_projection_evidence_revision_check` | `CHECK ((evidence_revision >= 0))` |

**Triggers**

- `trg_outbox_completion_projection`: `AFTER INSERT OR UPDATE ... outbox_for_evidence_fact()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('job'::text, job_id)` WITH CHECK `staff_scope_row('job'::text, job_id)`
- `rls_select` for SELECT: USING `(app_is_staff() OR contractor_owns_job(job_id))`
- `rls_select_projection_staff` for SELECT: USING `(app_role() = ANY (ARRAY['ADMIN'::text, 'ENGINEER'::text, 'SUPERVISOR'::text, 'AUDITOR'::text]))`

## contractor

Licensed contractor; status ACTIVE/SUSPENDED/BLACKLISTED.

| Column | Type | Null? | Default |
|---|---|---|---|
| `contractor_id` | bigint | NOT NULL | `generated always as identity` |
| `name` | text | NOT NULL |  |
| `licence_no` | text | NOT NULL |  |
| `licence_valid_until` | date | NOT NULL |  |
| `status` | text | NOT NULL | `'ACTIVE'::text` |
| `created_at` | timestamp with time zone | NOT NULL | `now()` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `contractor_pkey` | `PRIMARY KEY (contractor_id)` |
| Unique | `contractor_licence_no_key` | `UNIQUE (licence_no)` |
| Check | `ck_contractor_status` | `CHECK ((status = ANY (ARRAY['ACTIVE'::text, 'SUSPENDED'::text, 'BLACKLISTED'::text])))` |

**Triggers**

- `trg_audit`: `AFTER INSERT OR DELETE OR UPDATE ... audit_row('contractor_id')`
- `trg_contractor_safety_revalidate`: `AFTER UPDATE OF status, licence_valid_until ... revalidate_changed_safety_dependency()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('contractor'::text, contractor_id)` WITH CHECK `((app_ulb_id() IS NOT NULL) OR (app_role() <> ALL (ARRAY['ENGINEER'::text, 'SUPERVISOR'::text])))`
- `rls_delete` for DELETE: USING `app_has_role(VARIADIC '{ADMIN}'::text[])`
- `rls_insert` for INSERT:  WITH CHECK `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])`
- `rls_select` for SELECT: USING `(app_is_staff() OR (contractor_id = app_contractor_id()))`
- `rls_update` for UPDATE: USING `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])` WITH CHECK `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])`

## detection_rule

Catalogue of absence-detection rules (SE1, SE2); can be disabled.

| Column | Type | Null? | Default |
|---|---|---|---|
| `rule_code` | text | NOT NULL |  |
| `title` | text | NOT NULL |  |
| `description` | text | NOT NULL |  |
| `enabled` | boolean | NOT NULL | `true` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `detection_rule_pkey` | `PRIMARY KEY (rule_code)` |
| Check | `detection_rule_rule_code_check` | `CHECK ((rule_code ~ '^SE[0-9]+_[A-Z_]+$'::text))` |

**Triggers**

- `trg_audit`: `AFTER INSERT OR DELETE OR UPDATE ... audit_row('rule_code')`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_select` for SELECT: USING `true`
- `rls_update` for UPDATE: USING `app_has_role(VARIADIC '{ADMIN}'::text[])` WITH CHECK `app_has_role(VARIADIC '{ADMIN}'::text[])`

## entry_log

A worker's time underground; overlaps are excluded.

| Column | Type | Null? | Default |
|---|---|---|---|
| `entry_id` | bigint | NOT NULL | `generated always as identity` |
| `permit_id` | bigint | NOT NULL |  |
| `worker_id` | bigint | NOT NULL |  |
| `period` | tstzrange | NOT NULL |  |
| `recorded_by` | bigint | NOT NULL |  |
| `recorded_at` | timestamp with time zone | NOT NULL | `now()` |
| `exit_recorded_at` | timestamp with time zone | nullable |  |
| `receipt_id` | bigint | nullable |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `entry_log_pkey` | `PRIMARY KEY (entry_id)` |
| Foreign key | `entry_log_permit_id_worker_id_fkey` | `FOREIGN KEY (permit_id, worker_id) REFERENCES permit_crew(permit_id, worker_id)` |
| Foreign key | `entry_log_receipt_id_fkey` | `FOREIGN KEY (receipt_id) REFERENCES permit_decision_receipt(receipt_id)` |
| Foreign key | `entry_log_recorded_by_fkey` | `FOREIGN KEY (recorded_by) REFERENCES app_user(user_id)` |
| Check | `ck_entry_period_shape` | `CHECK (((NOT isempty(period)) AND (NOT lower_inf(period)) AND lower_inc(period)))` |
| Exclusion | `ex_entry_no_overlap` | `EXCLUDE USING gist (int8range(worker_id, worker_id, '[]'::text) WITH &&, period WITH &&)` |

**Indexes** (beyond those that back the constraints above)

- `ix_entry_permit_worker`: `btree (permit_id, worker_id)`

**Triggers**

- `trg_00_entry_receipt`: `BEFORE INSERT ... require_current_permit_receipt()`
- `trg_audit`: `AFTER INSERT OR DELETE OR UPDATE ... audit_row('entry_id')`
- `trg_completion_projection_entry`: `AFTER INSERT OR DELETE OR UPDATE ... completion_projection_source_changed()`
- `trg_entry_log_guard`: `BEFORE INSERT OR UPDATE ... entry_log_guard()`
- `trg_no_delete`: `BEFORE DELETE ... forbid_change()`
- `trg_resource_release_exit`: `AFTER UPDATE OF period ... release_when_clear()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('entry_permit'::text, permit_id)` WITH CHECK `staff_scope_row('entry_permit'::text, permit_id)`
- `rls_insert` for INSERT:  WITH CHECK `(app_has_role(VARIADIC '{SUPERVISOR}'::text[]) AND permit_writer(permit_id))`
- `rls_select` for SELECT: USING `(app_is_staff() OR worker_on_permit(permit_id) OR contractor_owns_permit(permit_id))`
- `rls_update` for UPDATE: USING `(app_has_role(VARIADIC '{SUPERVISOR}'::text[]) AND permit_writer(permit_id))` WITH CHECK `(app_has_role(VARIADIC '{SUPERVISOR}'::text[]) AND permit_writer(permit_id))`

## entry_permit

Permit to enter; AUTHORISED only through the clause gate.

| Column | Type | Null? | Default |
|---|---|---|---|
| `permit_id` | bigint | NOT NULL | `generated always as identity` |
| `job_id` | bigint | NOT NULL |  |
| `supervisor_id` | bigint | NOT NULL |  |
| `status` | text | NOT NULL | `'DRAFT'::text` |
| `created_at` | timestamp with time zone | NOT NULL | `now()` |
| `authorised_at` | timestamp with time zone | nullable |  |
| `authorised_by` | bigint | nullable |  |
| `valid_until` | timestamp with time zone | nullable |  |
| `ended_at` | timestamp with time zone | nullable |  |
| `end_reason` | text | nullable |  |
| `evidence_revision` | bigint | NOT NULL | `0` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `entry_permit_pkey` | `PRIMARY KEY (permit_id)` |
| Unique | `entry_permit_permit_id_job_id_key` | `UNIQUE (permit_id, job_id)` |
| Foreign key | `entry_permit_authorised_by_fkey` | `FOREIGN KEY (authorised_by) REFERENCES app_user(user_id)` |
| Foreign key | `entry_permit_job_id_fkey` | `FOREIGN KEY (job_id) REFERENCES job(job_id)` |
| Foreign key | `entry_permit_supervisor_id_fkey` | `FOREIGN KEY (supervisor_id) REFERENCES app_user(user_id)` |
| Check | `ck_permit_authorisation_complete` | `CHECK ((((authorised_at IS NULL) = (valid_until IS NULL)) AND ((authorised_at IS NULL) = (authorised_by IS NULL))))` |
| Check | `ck_permit_authorised_matches_status` | `CHECK (((status = ANY (ARRAY['AUTHORISED'::text, 'CLOSED'::text, 'ABORTED'::text])) = (authorised_at IS NOT NULL)))` |
| Check | `ck_permit_ended_matches_status` | `CHECK (((status = ANY (ARRAY['CLOSED'::text, 'ABORTED'::text, 'CANCELLED'::text])) = (ended_at IS NOT NULL)))` |
| Check | `ck_permit_validity_after_authorisation` | `CHECK (((valid_until IS NULL) OR (valid_until > authorised_at)))` |
| Check | `entry_permit_evidence_revision_check` | `CHECK ((evidence_revision >= 0))` |
| Check | `entry_permit_status_check` | `CHECK ((status = ANY (ARRAY['DRAFT'::text, 'AUTHORISED'::text, 'CLOSED'::text, 'ABORTED'::text, 'CANCELLED'::text])))` |

**Indexes** (beyond those that back the constraints above)

- `ix_permit_job`: `btree (job_id, status)`
- `ix_permit_supervisor`: `btree (supervisor_id)`

**Triggers**

- `trg_00_lock_authorization_policy`: `BEFORE UPDATE ... lock_authorization_policy()`
- `trg_00_permit_additive_gate`: `BEFORE UPDATE OF status ... permit_additive_gate_guard()`
- `trg_01_reserve_permit_resources`: `BEFORE UPDATE OF status ... reserve_permit_resources()`
- `trg_01_runtime_authorization_clock`: `BEFORE UPDATE ... stamp_runtime_authorization_clock()`
- `trg_audit`: `AFTER INSERT OR DELETE OR UPDATE ... audit_row('permit_id')`
- `trg_completion_projection_permit`: `AFTER INSERT OR UPDATE OF status, ended_at ... completion_projection_source_changed()`
- `trg_permit_abort_event`: `AFTER UPDATE OF status ... permit_abort_event()`
- `trg_permit_authorization_snapshot`: `AFTER UPDATE ... capture_permit_authorization_decision()`
- `trg_permit_delete_guard`: `BEFORE DELETE ... permit_delete_guard()`
- `trg_permit_guard`: `BEFORE UPDATE ... permit_guard()`
- `trg_permit_insert_guard`: `BEFORE INSERT ... permit_insert_guard()`
- `trg_permit_receipt`: `AFTER UPDATE OF status ... record_permit_receipt()`
- `trg_resource_release_permit`: `AFTER UPDATE OF status ... release_when_clear()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('job'::text, job_id)` WITH CHECK `staff_scope_row('job'::text, job_id)`
- `rls_delete` for DELETE: USING `(app_has_role(VARIADIC '{SUPERVISOR}'::text[]) AND permit_writer(permit_id))`
- `rls_insert` for INSERT:  WITH CHECK `((app_role() = 'SUPERVISOR'::text) AND (supervisor_id = app_user_id()))`
- `rls_select` for SELECT: USING `(app_is_staff() OR worker_on_permit(permit_id) OR (EXISTS ( SELECT 1
   FROM job j
  WHERE ((j.job_id = entry_permit.job_id) AND (j.contractor_id = app_contractor_id())))))`
- `rls_update` for UPDATE: USING `(app_has_role(VARIADIC '{SUPERVISOR,ENGINEER}'::text[]) AND permit_writer(permit_id))` WITH CHECK `(app_has_role(VARIADIC '{SUPERVISOR,ENGINEER}'::text[]) AND permit_writer(permit_id))`

## gas_detector

Gas detector with calibration expiry.

| Column | Type | Null? | Default |
|---|---|---|---|
| `detector_id` | bigint | NOT NULL | `generated always as identity` |
| `serial_no` | text | NOT NULL |  |
| `model` | text | NOT NULL |  |
| `calibration_valid_until` | date | NOT NULL |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `gas_detector_pkey` | `PRIMARY KEY (detector_id)` |
| Unique | `gas_detector_serial_no_key` | `UNIQUE (serial_no)` |

**Triggers**

- `trg_audit`: `AFTER INSERT OR DELETE OR UPDATE ... audit_row('detector_id')`
- `trg_detector_safety_revalidate`: `AFTER UPDATE OF calibration_valid_until ... revalidate_changed_safety_dependency()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('gas_detector'::text, detector_id)` WITH CHECK `(app_role() <> ALL (ARRAY['ENGINEER'::text, 'SUPERVISOR'::text]))`
- `rls_delete` for DELETE: USING `app_has_role(VARIADIC '{ADMIN}'::text[])`
- `rls_insert` for INSERT:  WITH CHECK `app_has_role(VARIADIC '{ADMIN}'::text[])`
- `rls_select` for SELECT: USING `true`
- `rls_update` for UPDATE: USING `app_has_role(VARIADIC '{ADMIN}'::text[])` WITH CHECK `app_has_role(VARIADIC '{ADMIN}'::text[])`

## gas_reading

Atmosphere reading at a depth level (append-only).

| Column | Type | Null? | Default |
|---|---|---|---|
| `reading_id` | bigint | NOT NULL | `generated always as identity` |
| `permit_id` | bigint | NOT NULL |  |
| `detector_id` | bigint | NOT NULL |  |
| `depth_level` | text | NOT NULL |  |
| `o2_pct` | numeric(4,1) | nullable |  |
| `h2s_ppm` | numeric(6,2) | nullable |  |
| `lel_pct` | numeric(5,2) | nullable |  |
| `co_ppm` | numeric(6,2) | nullable |  |
| `taken_at` | timestamp with time zone | NOT NULL |  |
| `recorded_by` | bigint | NOT NULL |  |
| `recorded_at` | timestamp with time zone | NOT NULL | `now()` |
| `source_mode` | text | NOT NULL | `'TYPED'::text` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `gas_reading_pkey` | `PRIMARY KEY (reading_id)` |
| Foreign key | `gas_reading_detector_id_fkey` | `FOREIGN KEY (detector_id) REFERENCES gas_detector(detector_id)` |
| Foreign key | `gas_reading_permit_id_fkey` | `FOREIGN KEY (permit_id) REFERENCES entry_permit(permit_id)` |
| Foreign key | `gas_reading_recorded_by_fkey` | `FOREIGN KEY (recorded_by) REFERENCES app_user(user_id)` |
| Check | `ck_o2_range` | `CHECK (((o2_pct >= (0)::numeric) AND (o2_pct <= (100)::numeric)))` |
| Check | `gas_reading_co_ppm_check` | `CHECK ((co_ppm >= (0)::numeric))` |
| Check | `gas_reading_depth_level_check` | `CHECK ((depth_level = ANY (ARRAY['TOP'::text, 'MID'::text, 'BOTTOM'::text])))` |
| Check | `gas_reading_h2s_ppm_check` | `CHECK ((h2s_ppm >= (0)::numeric))` |
| Check | `gas_reading_lel_pct_check` | `CHECK (((lel_pct >= (0)::numeric) AND (lel_pct <= (100)::numeric)))` |
| Check | `gas_reading_source_mode_check` | `CHECK ((source_mode = ANY (ARRAY['SIMULATED'::text, 'TYPED'::text, 'HARDWARE_RAW'::text])))` |

**Indexes** (beyond those that back the constraints above)

- `ix_reading_permit_depth`: `btree (permit_id, depth_level, taken_at DESC)`

**Triggers**

- `trg_00_gas_revision`: `AFTER INSERT ... bump_permit_evidence()`
- `trg_append_only`: `BEFORE DELETE OR UPDATE ... forbid_change()`
- `trg_audit`: `AFTER INSERT OR DELETE OR UPDATE ... audit_row('reading_id')`
- `trg_gas_reading_guard`: `BEFORE INSERT ... gas_reading_guard()`
- `trg_gas_reading_revalidate`: `AFTER INSERT ... gas_reading_revalidate()`
- `trg_gas_receipt_refresh`: `AFTER INSERT ... refresh_current_receipt()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('entry_permit'::text, permit_id)` WITH CHECK `staff_scope_row('entry_permit'::text, permit_id)`
- `rls_insert` for INSERT:  WITH CHECK `(app_has_role(VARIADIC '{SUPERVISOR,ENGINEER}'::text[]) AND permit_writer(permit_id))`
- `rls_select` for SELECT: USING `(app_is_staff() OR worker_on_permit(permit_id) OR contractor_owns_permit(permit_id))`

## gear_asset



| Column | Type | Null? | Default |
|---|---|---|---|
| `gear_asset_id` | bigint | NOT NULL | `generated always as identity` |
| `ulb_id` | bigint | NOT NULL |  |
| `gear_code` | text | NOT NULL |  |
| `serial_no` | text | NOT NULL |  |
| `status` | text | NOT NULL | `'USABLE'::text` |
| `inspection_valid_until` | date | nullable |  |
| `created_at` | timestamp with time zone | NOT NULL | `clock_timestamp()` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `gear_asset_pkey` | `PRIMARY KEY (gear_asset_id)` |
| Unique | `gear_asset_serial_no_key` | `UNIQUE (serial_no)` |
| Foreign key | `gear_asset_gear_code_fkey` | `FOREIGN KEY (gear_code) REFERENCES gear_item(gear_code)` |
| Foreign key | `gear_asset_ulb_id_fkey` | `FOREIGN KEY (ulb_id) REFERENCES ulb(ulb_id)` |
| Check | `gear_asset_serial_no_check` | `CHECK ((length(btrim(serial_no)) > 0))` |
| Check | `gear_asset_status_check` | `CHECK ((status = ANY (ARRAY['USABLE'::text, 'OUT_OF_SERVICE'::text, 'RETIRED'::text])))` |

**Triggers**

- `trg_gear_asset_change_effects`: `AFTER UPDATE OF status, inspection_valid_until, ulb_id, gear_code, serial_no ... gear_asset_change_effects()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_ulb(ulb_id)` WITH CHECK `staff_scope_ulb(ulb_id)`
- `rls_insert_asset_officer` for INSERT:  WITH CHECK `((app_role() = ANY (ARRAY['ADMIN'::text, 'ENGINEER'::text])) AND staff_scope_ulb(ulb_id))`
- `rls_select` for SELECT: USING `app_is_staff()`
- `rls_select_asset_staff` for SELECT: USING `(app_role() = ANY (ARRAY['ADMIN'::text, 'ENGINEER'::text, 'SUPERVISOR'::text, 'AUDITOR'::text]))`
- `rls_update_asset_officer` for UPDATE: USING `((app_role() = ANY (ARRAY['ADMIN'::text, 'ENGINEER'::text])) AND staff_scope_ulb(ulb_id))` WITH CHECK `((app_role() = ANY (ARRAY['ADMIN'::text, 'ENGINEER'::text])) AND staff_scope_ulb(ulb_id))`

## gear_issue

Gear issued to a crew member for a permit, with serial number.

| Column | Type | Null? | Default |
|---|---|---|---|
| `issue_id` | bigint | NOT NULL | `generated always as identity` |
| `permit_id` | bigint | NOT NULL |  |
| `worker_id` | bigint | NOT NULL |  |
| `gear_code` | text | NOT NULL |  |
| `serial_no` | text | NOT NULL |  |
| `issued_by` | bigint | nullable |  |
| `issued_at` | timestamp with time zone | NOT NULL | `now()` |
| `gear_asset_id` | bigint | nullable |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `gear_issue_pkey` | `PRIMARY KEY (issue_id)` |
| Unique | `gear_issue_permit_id_worker_id_gear_code_key` | `UNIQUE (permit_id, worker_id, gear_code)` |
| Foreign key | `gear_issue_gear_asset_id_fkey` | `FOREIGN KEY (gear_asset_id) REFERENCES gear_asset(gear_asset_id)` |
| Foreign key | `gear_issue_gear_code_fkey` | `FOREIGN KEY (gear_code) REFERENCES gear_item(gear_code)` |
| Foreign key | `gear_issue_issued_by_fkey` | `FOREIGN KEY (issued_by) REFERENCES app_user(user_id)` |
| Foreign key | `gear_issue_permit_id_worker_id_fkey` | `FOREIGN KEY (permit_id, worker_id) REFERENCES permit_crew(permit_id, worker_id) ON DELETE CASCADE` |
| Check | `gear_issue_serial_no_check` | `CHECK ((length(btrim(serial_no)) > 0))` |

**Indexes** (beyond those that back the constraints above)

- `ix_gear_issue_asset`: `btree (gear_asset_id)`
- `ix_gear_issue_permit_worker`: `btree (permit_id, worker_id)`
- `uq_gear_issue_permit_asset`: `btree (permit_id, gear_asset_id) WHERE (gear_asset_id IS NOT NULL)`

**Triggers**

- `trg_audit`: `AFTER INSERT OR DELETE OR UPDATE ... audit_row('issue_id')`
- `trg_freeze`: `BEFORE INSERT OR DELETE OR UPDATE ... freeze_after_authorisation()`
- `trg_gear_issue_asset_bind`: `BEFORE INSERT OR UPDATE OF gear_code, serial_no, gear_asset_id ... gear_issue_asset_bind()`
- `trg_gear_revision`: `AFTER INSERT OR DELETE OR UPDATE ... bump_permit_evidence()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('entry_permit'::text, permit_id)` WITH CHECK `staff_scope_row('entry_permit'::text, permit_id)`
- `rls_delete` for DELETE: USING `(app_has_role(VARIADIC '{SUPERVISOR}'::text[]) AND permit_writer(permit_id))`
- `rls_insert` for INSERT:  WITH CHECK `(app_has_role(VARIADIC '{SUPERVISOR}'::text[]) AND permit_writer(permit_id))`
- `rls_select` for SELECT: USING `(app_is_staff() OR worker_on_permit(permit_id) OR contractor_owns_permit(permit_id))`
- `rls_update` for UPDATE: USING `(app_has_role(VARIADIC '{SUPERVISOR}'::text[]) AND permit_writer(permit_id))` WITH CHECK `(app_has_role(VARIADIC '{SUPERVISOR}'::text[]) AND permit_writer(permit_id))`

## gear_item

Protective-gear catalogue; statutory items are mandatory for entrants.

| Column | Type | Null? | Default |
|---|---|---|---|
| `gear_code` | text | NOT NULL |  |
| `name` | text | NOT NULL |  |
| `statutory` | boolean | NOT NULL | `false` |
| `legal_ref` | text | nullable |  |
| `requirement_scope` | text | NOT NULL | `'ENTRANT'::text` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `gear_item_pkey` | `PRIMARY KEY (gear_code)` |
| Check | `gear_item_gear_code_check` | `CHECK ((gear_code = upper(gear_code)))` |
| Check | `gear_item_requirement_scope_check` | `CHECK ((requirement_scope = ANY (ARRAY['ENTRANT'::text, 'SITE'::text])))` |

**Triggers**

- `trg_audit`: `AFTER INSERT OR DELETE OR UPDATE ... audit_row('gear_code')`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_delete` for DELETE: USING `app_has_role(VARIADIC '{ADMIN}'::text[])`
- `rls_insert` for INSERT:  WITH CHECK `app_has_role(VARIADIC '{ADMIN}'::text[])`
- `rls_select` for SELECT: USING `true`
- `rls_update` for UPDATE: USING `app_has_role(VARIADIC '{ADMIN}'::text[])` WITH CHECK `app_has_role(VARIADIC '{ADMIN}'::text[])`

## incident

Fatality, disability or near miss.

| Column | Type | Null? | Default |
|---|---|---|---|
| `incident_id` | bigint | NOT NULL | `generated always as identity` |
| `incident_type` | text | NOT NULL |  |
| `occurred_at` | timestamp with time zone | NOT NULL |  |
| `manhole_id` | bigint | NOT NULL |  |
| `worker_id` | bigint | NOT NULL |  |
| `contractor_id` | bigint | NOT NULL |  |
| `job_id` | bigint | nullable |  |
| `permit_id` | bigint | nullable |  |
| `description` | text | NOT NULL |  |
| `recorded_by` | bigint | NOT NULL |  |
| `recorded_at` | timestamp with time zone | NOT NULL | `now()` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `incident_pkey` | `PRIMARY KEY (incident_id)` |
| Unique | `incident_worker_id_occurred_at_incident_type_key` | `UNIQUE (worker_id, occurred_at, incident_type)` |
| Foreign key | `incident_contractor_id_fkey` | `FOREIGN KEY (contractor_id) REFERENCES contractor(contractor_id)` |
| Foreign key | `incident_job_id_fkey` | `FOREIGN KEY (job_id) REFERENCES job(job_id)` |
| Foreign key | `incident_manhole_id_fkey` | `FOREIGN KEY (manhole_id) REFERENCES manhole(manhole_id)` |
| Foreign key | `incident_permit_id_job_id_fkey` | `FOREIGN KEY (permit_id, job_id) REFERENCES entry_permit(permit_id, job_id)` |
| Foreign key | `incident_permit_id_worker_id_fkey` | `FOREIGN KEY (permit_id, worker_id) REFERENCES permit_crew(permit_id, worker_id)` |
| Foreign key | `incident_recorded_by_fkey` | `FOREIGN KEY (recorded_by) REFERENCES app_user(user_id)` |
| Foreign key | `incident_worker_id_fkey` | `FOREIGN KEY (worker_id) REFERENCES worker(worker_id)` |
| Check | `incident_description_check` | `CHECK ((length(btrim(description)) > 0))` |
| Check | `incident_incident_type_check` | `CHECK ((incident_type = ANY (ARRAY['FATALITY'::text, 'DISABILITY'::text, 'NEAR_MISS'::text])))` |

**Indexes** (beyond those that back the constraints above)

- `ix_incident_contractor`: `btree (contractor_id, occurred_at)`

**Triggers**

- `trg_00_incident_insert_isolation`: `BEFORE INSERT ... require_read_committed_financialrace()`
- `trg_append_only`: `BEFORE DELETE OR UPDATE ... forbid_change()`
- `trg_audit`: `AFTER INSERT OR DELETE OR UPDATE ... audit_row('incident_id')`
- `trg_incident_complaint_lock`: `BEFORE INSERT ... incident_complaint_lock()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('manhole'::text, manhole_id)` WITH CHECK `staff_scope_row('manhole'::text, manhole_id)`
- `rls_insert` for INSERT:  WITH CHECK `app_has_role(VARIADIC '{ADMIN,ENGINEER,SUPERVISOR}'::text[])`
- `rls_select` for SELECT: USING `(app_is_staff() OR (contractor_id = app_contractor_id()))`

## incident_assessment_case

Pending internal assessment and reference values; not a legal award, blacklist or payment record.

| Column | Type | Null? | Default |
|---|---|---|---|
| `assessment_case_id` | bigint | NOT NULL | `generated always as identity` |
| `victim_id` | bigint | NOT NULL |  |
| `status` | text | NOT NULL | `'PENDING_REVIEW'::text` |
| `reference_amount` | numeric(12,2) | nullable |  |
| `claimed_amount` | numeric(12,2) | nullable |  |
| `awarded_amount` | numeric(12,2) | nullable |  |
| `paid_amount` | numeric(12,2) | NOT NULL | `0` |
| `review_due_at` | timestamp with time zone | nullable |  |
| `notes` | text | nullable |  |
| `created_at` | timestamp with time zone | NOT NULL | `now()` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `incident_assessment_case_pkey` | `PRIMARY KEY (assessment_case_id)` |
| Unique | `incident_assessment_case_victim_id_key` | `UNIQUE (victim_id)` |
| Foreign key | `incident_assessment_case_victim_id_fkey` | `FOREIGN KEY (victim_id) REFERENCES incident_report_victim(victim_id) ON DELETE RESTRICT` |
| Check | `incident_assessment_case_awarded_amount_check` | `CHECK (((awarded_amount IS NULL) OR (awarded_amount >= (0)::numeric)))` |
| Check | `incident_assessment_case_claimed_amount_check` | `CHECK (((claimed_amount IS NULL) OR (claimed_amount >= (0)::numeric)))` |
| Check | `incident_assessment_case_paid_amount_check` | `CHECK ((paid_amount >= (0)::numeric))` |
| Check | `incident_assessment_case_reference_amount_check` | `CHECK (((reference_amount IS NULL) OR (reference_amount >= (0)::numeric)))` |
| Check | `incident_assessment_case_status_check` | `CHECK ((status = ANY (ARRAY['PENDING_REVIEW'::text, 'ASSESSED'::text, 'EXTERNAL_AWARD_RECORDED'::text, 'EXTERNAL_PAYMENT_RECORDED'::text])))` |

**Indexes** (beyond those that back the constraints above)

- `ix_incident_assessment_status`: `btree (status, review_due_at)`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_select_report_case` for SELECT: USING `(EXISTS ( SELECT 1
   FROM incident_report_victim v
  WHERE (v.victim_id = incident_assessment_case.victim_id)))`

## incident_report

Standalone review intake; linked assets are optional and classification remains review-required until external review.

| Column | Type | Null? | Default |
|---|---|---|---|
| `report_id` | bigint | NOT NULL | `generated always as identity` |
| `ulb_id` | bigint | NOT NULL |  |
| `job_id` | bigint | nullable |  |
| `permit_id` | bigint | nullable |  |
| `contractor_id` | bigint | nullable |  |
| `occurred_at` | timestamp with time zone | NOT NULL |  |
| `site_label` | text | NOT NULL |  |
| `hazard_type` | text | NOT NULL |  |
| `description` | text | NOT NULL |  |
| `reported_sections` | text | nullable |  |
| `reported_by` | bigint | NOT NULL |  |
| `classification_status` | text | NOT NULL | `'REVIEW_REQUIRED'::text` |
| `source_mode` | text | NOT NULL | `'MANUAL'::text` |
| `created_at` | timestamp with time zone | NOT NULL | `now()` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `incident_report_pkey` | `PRIMARY KEY (report_id)` |
| Foreign key | `incident_report_contractor_id_fkey` | `FOREIGN KEY (contractor_id) REFERENCES contractor(contractor_id) ON DELETE RESTRICT` |
| Foreign key | `incident_report_job_id_fkey` | `FOREIGN KEY (job_id) REFERENCES job(job_id) ON DELETE RESTRICT` |
| Foreign key | `incident_report_permit_id_fkey` | `FOREIGN KEY (permit_id) REFERENCES entry_permit(permit_id) ON DELETE RESTRICT` |
| Foreign key | `incident_report_reported_by_fkey` | `FOREIGN KEY (reported_by) REFERENCES app_user(user_id) ON DELETE RESTRICT` |
| Foreign key | `incident_report_ulb_id_fkey` | `FOREIGN KEY (ulb_id) REFERENCES ulb(ulb_id) ON DELETE RESTRICT` |
| Check | `incident_report_classification_status_check` | `CHECK ((classification_status = ANY (ARRAY['REVIEW_REQUIRED'::text, 'UNDER_REVIEW'::text, 'REFERRED'::text])))` |
| Check | `incident_report_description_check` | `CHECK (((length(btrim(description)) >= 1) AND (length(btrim(description)) <= 2000)))` |
| Check | `incident_report_hazard_type_check` | `CHECK (((length(btrim(hazard_type)) >= 1) AND (length(btrim(hazard_type)) <= 100)))` |
| Check | `incident_report_reported_sections_check` | `CHECK (((reported_sections IS NULL) OR (length(reported_sections) <= 500)))` |
| Check | `incident_report_site_label_check` | `CHECK (((length(btrim(site_label)) >= 1) AND (length(btrim(site_label)) <= 300)))` |
| Check | `incident_report_source_mode_check` | `CHECK ((source_mode = ANY (ARRAY['MANUAL'::text, 'IMPORTED'::text])))` |

**Indexes** (beyond those that back the constraints above)

- `ix_incident_report_job`: `btree (job_id) WHERE (job_id IS NOT NULL)`
- `ix_incident_report_scope_time`: `btree (ulb_id, occurred_at DESC, report_id DESC)`

**Triggers**

- `trg_00_incident_report_read_committed`: `BEFORE INSERT ... require_read_committed_incident_report()`
- `trg_incident_report_complaint_lock`: `BEFORE INSERT ... incident_report_complaint_lock()`
- `trg_outbox_incident_report`: `AFTER INSERT ... outbox_for_incident_report()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_select_incident_scope` for SELECT: USING `((app_role() = ANY (ARRAY['ADMIN'::text, 'AUDITOR'::text])) OR ((app_role() = ANY (ARRAY['ENGINEER'::text, 'SUPERVISOR'::text, 'AUDITOR'::text])) AND (ulb_id = app_ulb_id())))`

## incident_report_victim

Victim-specific report detail; worker registry linkage is optional and aliases can preserve unregistered people.

| Column | Type | Null? | Default |
|---|---|---|---|
| `victim_id` | bigint | NOT NULL | `generated always as identity` |
| `report_id` | bigint | NOT NULL |  |
| `victim_key` | text | NOT NULL |  |
| `worker_id` | bigint | nullable |  |
| `display_alias` | text | NOT NULL |  |
| `outcome` | text | NOT NULL |  |
| `created_at` | timestamp with time zone | NOT NULL | `now()` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `incident_report_victim_pkey` | `PRIMARY KEY (victim_id)` |
| Unique | `incident_report_victim_report_id_victim_key_key` | `UNIQUE (report_id, victim_key)` |
| Foreign key | `incident_report_victim_report_id_fkey` | `FOREIGN KEY (report_id) REFERENCES incident_report(report_id) ON DELETE RESTRICT` |
| Foreign key | `incident_report_victim_worker_id_fkey` | `FOREIGN KEY (worker_id) REFERENCES worker(worker_id) ON DELETE RESTRICT` |
| Check | `incident_report_victim_display_alias_check` | `CHECK (((length(btrim(display_alias)) >= 1) AND (length(btrim(display_alias)) <= 200)))` |
| Check | `incident_report_victim_outcome_check` | `CHECK ((outcome = ANY (ARRAY['FATAL'::text, 'INJURY'::text, 'OTHER'::text])))` |
| Check | `incident_report_victim_victim_key_check` | `CHECK (((length(btrim(victim_key)) >= 1) AND (length(btrim(victim_key)) <= 100)))` |

**Indexes** (beyond those that back the constraints above)

- `ix_incident_report_victim_worker`: `btree (worker_id) WHERE (worker_id IS NOT NULL)`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_select_report_victim` for SELECT: USING `(EXISTS ( SELECT 1
   FROM incident_report r
  WHERE (r.report_id = incident_report_victim.report_id)))`

## invoice

Contractor invoice for a job.

| Column | Type | Null? | Default |
|---|---|---|---|
| `invoice_id` | bigint | NOT NULL | `generated always as identity` |
| `job_id` | bigint | NOT NULL |  |
| `invoice_no` | text | NOT NULL |  |
| `amount_inr` | numeric(12,2) | NOT NULL |  |
| `status` | text | NOT NULL | `'SUBMITTED'::text` |
| `submitted_at` | timestamp with time zone | NOT NULL | `now()` |
| `decided_by` | bigint | nullable |  |
| `decided_at` | timestamp with time zone | nullable |  |
| `paid_at` | timestamp with time zone | nullable |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `invoice_pkey` | `PRIMARY KEY (invoice_id)` |
| Unique | `invoice_invoice_no_key` | `UNIQUE (invoice_no)` |
| Foreign key | `invoice_decided_by_fkey` | `FOREIGN KEY (decided_by) REFERENCES app_user(user_id)` |
| Foreign key | `invoice_job_id_fkey` | `FOREIGN KEY (job_id) REFERENCES job(job_id)` |
| Check | `ck_invoice_decider` | `CHECK (((status = 'SUBMITTED'::text) = (decided_by IS NULL)))` |
| Check | `ck_invoice_paid_at` | `CHECK (((status = 'PAID'::text) = (paid_at IS NOT NULL)))` |
| Check | `invoice_amount_inr_check` | `CHECK ((amount_inr > (0)::numeric))` |
| Check | `invoice_status_check` | `CHECK ((status = ANY (ARRAY['SUBMITTED'::text, 'APPROVED'::text, 'PAID'::text, 'REJECTED'::text])))` |

**Indexes** (beyond those that back the constraints above)

- `ix_invoice_job`: `btree (job_id)`

**Triggers**

- `trg_00_invoice_insert_isolation`: `BEFORE INSERT ... require_read_committed_financialrace()`
- `trg_00_invoice_status_isolation`: `BEFORE UPDATE OF status ... require_read_committed_financialrace()`
- `trg_audit`: `AFTER INSERT OR DELETE OR UPDATE ... audit_row('invoice_id')`
- `trg_completion_projection_invoice`: `AFTER INSERT OR DELETE OR UPDATE ... completion_projection_source_changed()`
- `trg_invoice_auto_hold`: `AFTER INSERT ... invoice_auto_hold()`
- `trg_invoice_complaint_lock`: `BEFORE INSERT ... invoice_complaint_lock()`
- `trg_invoice_guard`: `BEFORE UPDATE ... invoice_guard()`
- `trg_invoice_hold_for_prior_reports`: `AFTER INSERT ... hold_new_invoice_for_prior_reports()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('job'::text, job_id)` WITH CHECK `staff_scope_row('job'::text, job_id)`
- `rls_insert` for INSERT:  WITH CHECK `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])`
- `rls_insert_contractor` for INSERT:  WITH CHECK `((app_role() = 'CONTRACTOR'::text) AND (EXISTS ( SELECT 1
   FROM job j
  WHERE ((j.job_id = invoice.job_id) AND (j.contractor_id = app_contractor_id())))))`
- `rls_select` for SELECT: USING `(app_is_staff() OR (EXISTS ( SELECT 1
   FROM job j
  WHERE ((j.job_id = invoice.job_id) AND (j.contractor_id = app_contractor_id())))))`
- `rls_update` for UPDATE: USING `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])` WITH CHECK `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])`

## invoice_hold

Reason an invoice cannot be approved or paid, with provenance.

| Column | Type | Null? | Default |
|---|---|---|---|
| `hold_id` | bigint | NOT NULL | `generated always as identity` |
| `invoice_id` | bigint | NOT NULL |  |
| `reason` | text | NOT NULL |  |
| `alert_id` | bigint | nullable |  |
| `incident_id` | bigint | nullable |  |
| `placed_at` | timestamp with time zone | NOT NULL | `now()` |
| `released_at` | timestamp with time zone | nullable |  |
| `released_by` | bigint | nullable |  |
| `release_note` | text | nullable |  |
| `report_id` | bigint | nullable |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `invoice_hold_pkey` | `PRIMARY KEY (hold_id)` |
| Foreign key | `invoice_hold_alert_id_fkey` | `FOREIGN KEY (alert_id) REFERENCES shadow_entry_alert(alert_id)` |
| Foreign key | `invoice_hold_incident_id_fkey` | `FOREIGN KEY (incident_id) REFERENCES incident(incident_id)` |
| Foreign key | `invoice_hold_invoice_id_fkey` | `FOREIGN KEY (invoice_id) REFERENCES invoice(invoice_id)` |
| Foreign key | `invoice_hold_released_by_fkey` | `FOREIGN KEY (released_by) REFERENCES app_user(user_id)` |
| Foreign key | `invoice_hold_report_id_fkey` | `FOREIGN KEY (report_id) REFERENCES incident_report(report_id) ON DELETE RESTRICT` |
| Check | `ck_hold_has_exactly_one_source` | `CHECK ((((reason = 'SHADOW_ENTRY'::text) AND (alert_id IS NOT NULL) AND (incident_id IS NULL) AND (report_id IS NULL)) OR ((reason = 'INCIDENT'::text) AND (num_nonnulls(incident_id, report_id) = 1) AND (alert_id IS NULL))))` |
| Check | `ck_hold_release_complete` | `CHECK (((released_at IS NULL) = (release_note IS NULL)))` |
| Check | `invoice_hold_reason_check` | `CHECK ((reason = ANY (ARRAY['SHADOW_ENTRY'::text, 'INCIDENT'::text])))` |

**Indexes** (beyond those that back the constraints above)

- `ix_hold_active`: `btree (invoice_id) WHERE (released_at IS NULL)`
- `uq_hold_invoice_alert`: `btree (invoice_id, alert_id) WHERE (alert_id IS NOT NULL)`
- `uq_hold_invoice_incident`: `btree (invoice_id, incident_id) WHERE (incident_id IS NOT NULL)`
- `uq_hold_invoice_report`: `btree (invoice_id, report_id) WHERE (report_id IS NOT NULL)`

**Triggers**

- `trg_00_invoice_hold_insert_isolation`: `BEFORE INSERT ... require_read_committed_financialrace()`
- `trg_audit`: `AFTER INSERT OR DELETE OR UPDATE ... audit_row('hold_id')`
- `trg_completion_projection_hold`: `AFTER INSERT OR DELETE OR UPDATE ... completion_projection_source_changed()`
- `trg_invoice_hold_guard`: `BEFORE INSERT ... invoice_hold_guard()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('invoice_hold'::text, hold_id)` WITH CHECK `staff_scope_row('invoice'::text, invoice_id)`
- `rls_insert` for INSERT:  WITH CHECK `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])`
- `rls_select` for SELECT: USING `(app_has_role(VARIADIC ARRAY['ADMIN'::text, 'ENGINEER'::text, 'AUDITOR'::text]) OR (EXISTS ( SELECT 1
   FROM (invoice i
     JOIN job j ON ((j.job_id = i.job_id)))
  WHERE ((i.invoice_id = invoice_hold.invoice_id) AND (j.contractor_id = app_contractor_id())))))`
- `rls_update` for UPDATE: USING `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])` WITH CHECK `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])`

## job

Work order for a complaint, assigned to a contractor.

| Column | Type | Null? | Default |
|---|---|---|---|
| `job_id` | bigint | NOT NULL | `generated always as identity` |
| `complaint_id` | bigint | NOT NULL |  |
| `contractor_id` | bigint | NOT NULL |  |
| `method` | text | NOT NULL | `'MECHANISED'::text` |
| `status` | text | NOT NULL | `'PLANNED'::text` |
| `created_by` | bigint | nullable |  |
| `created_at` | timestamp with time zone | NOT NULL | `now()` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `job_pkey` | `PRIMARY KEY (job_id)` |
| Foreign key | `job_complaint_id_fkey` | `FOREIGN KEY (complaint_id) REFERENCES complaint(complaint_id)` |
| Foreign key | `job_contractor_id_fkey` | `FOREIGN KEY (contractor_id) REFERENCES contractor(contractor_id)` |
| Foreign key | `job_created_by_fkey` | `FOREIGN KEY (created_by) REFERENCES app_user(user_id)` |
| Check | `job_method_check` | `CHECK ((method = ANY (ARRAY['MECHANISED'::text, 'MANUAL_EXCEPTION'::text])))` |
| Check | `job_status_check` | `CHECK ((status = ANY (ARRAY['PLANNED'::text, 'IN_PROGRESS'::text, 'COMPLETED'::text, 'FAILED'::text, 'CANCELLED'::text])))` |

**Indexes** (beyond those that back the constraints above)

- `ix_job_complaint`: `btree (complaint_id)`
- `ix_job_contractor`: `btree (contractor_id)`

**Triggers**

- `trg_audit`: `AFTER INSERT OR DELETE OR UPDATE ... audit_row('job_id')`
- `trg_job_contractor_safety_revalidate`: `AFTER UPDATE OF contractor_id ... revalidate_changed_safety_dependency()`
- `trg_job_insert_guard`: `BEFORE INSERT ... job_insert_guard()`
- `trg_job_method_guard`: `BEFORE UPDATE OF method ... job_method_guard()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('complaint'::text, complaint_id)` WITH CHECK `staff_scope_row('complaint'::text, complaint_id)`
- `rls_insert` for INSERT:  WITH CHECK `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])`
- `rls_select` for SELECT: USING `(app_is_staff() OR (contractor_id = app_contractor_id()) OR worker_on_job(job_id))`
- `rls_update` for UPDATE: USING `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])` WITH CHECK `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])`

## legal_clause

Titles and legal references for each entry-gate clause.

| Column | Type | Null? | Default |
|---|---|---|---|
| `clause_code` | text | NOT NULL |  |
| `title` | text | NOT NULL |  |
| `legal_ref` | text | NOT NULL |  |
| `sort_order` | smallint | NOT NULL |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `legal_clause_pkey` | `PRIMARY KEY (clause_code)` |
| Unique | `legal_clause_sort_order_key` | `UNIQUE (sort_order)` |
| Check | `legal_clause_clause_code_check` | `CHECK ((clause_code = upper(clause_code)))` |

## legal_clause_source

One or more classified source/applicability records for each entry checklist clause.

| Column | Type | Null? | Default |
|---|---|---|---|
| `clause_code` | text | NOT NULL |  |
| `source_code` | text | NOT NULL |  |
| `sort_order` | smallint | NOT NULL |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `legal_clause_source_pkey` | `PRIMARY KEY (clause_code, source_code)` |
| Unique | `legal_clause_source_clause_code_sort_order_key` | `UNIQUE (clause_code, sort_order)` |
| Foreign key | `legal_clause_source_clause_code_fkey` | `FOREIGN KEY (clause_code) REFERENCES legal_clause(clause_code)` |
| Foreign key | `legal_clause_source_source_code_fkey` | `FOREIGN KEY (source_code) REFERENCES policy_source(source_code)` |
| Check | `legal_clause_source_sort_order_check` | `CHECK ((sort_order > 0))` |

**Triggers**

- `trg_legal_clause_source_immutable`: `BEFORE DELETE OR UPDATE ... immutable_policy_record()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_select` for SELECT: USING `true`

## machine

Mechanised cleaning equipment.

| Column | Type | Null? | Default |
|---|---|---|---|
| `machine_id` | bigint | NOT NULL | `generated always as identity` |
| `ulb_id` | bigint | NOT NULL |  |
| `code` | text | NOT NULL |  |
| `kind` | text | NOT NULL |  |
| `status` | text | NOT NULL | `'AVAILABLE'::text` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `machine_pkey` | `PRIMARY KEY (machine_id)` |
| Unique | `machine_code_key` | `UNIQUE (code)` |
| Foreign key | `machine_ulb_id_fkey` | `FOREIGN KEY (ulb_id) REFERENCES ulb(ulb_id)` |
| Check | `machine_kind_check` | `CHECK ((kind = ANY (ARRAY['JETTING'::text, 'SUCTION'::text, 'ROBOT'::text])))` |
| Check | `machine_status_check` | `CHECK ((status = ANY (ARRAY['AVAILABLE'::text, 'IN_USE'::text, 'MAINTENANCE'::text])))` |

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_ulb(ulb_id)` WITH CHECK `staff_scope_ulb(ulb_id)`
- `rls_insert_machine_officer` for INSERT:  WITH CHECK `((app_role() = ANY (ARRAY['ADMIN'::text, 'ENGINEER'::text])) AND staff_scope_ulb(ulb_id))`
- `rls_select_machine_staff` for SELECT: USING `app_is_staff()`
- `rls_update_machine_officer` for UPDATE: USING `((app_role() = ANY (ARRAY['ADMIN'::text, 'ENGINEER'::text])) AND staff_scope_ulb(ulb_id))` WITH CHECK `((app_role() = ANY (ARRAY['ADMIN'::text, 'ENGINEER'::text])) AND staff_scope_ulb(ulb_id))`

## machine_deployment

A machine used on a job and its outcome (clearance evidence).

| Column | Type | Null? | Default |
|---|---|---|---|
| `deploy_id` | bigint | NOT NULL | `generated always as identity` |
| `job_id` | bigint | NOT NULL |  |
| `machine_id` | bigint | NOT NULL |  |
| `started_at` | timestamp with time zone | NOT NULL |  |
| `ended_at` | timestamp with time zone | nullable |  |
| `outcome` | text | nullable |  |
| `recorded_by` | bigint | nullable |  |
| `recorded_at` | timestamp with time zone | NOT NULL | `now()` |
| `outcome_recorded_at` | timestamp with time zone | nullable |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `machine_deployment_pkey` | `PRIMARY KEY (deploy_id)` |
| Foreign key | `machine_deployment_job_id_fkey` | `FOREIGN KEY (job_id) REFERENCES job(job_id)` |
| Foreign key | `machine_deployment_machine_id_fkey` | `FOREIGN KEY (machine_id) REFERENCES machine(machine_id)` |
| Foreign key | `machine_deployment_recorded_by_fkey` | `FOREIGN KEY (recorded_by) REFERENCES app_user(user_id)` |
| Check | `ck_deployment_order` | `CHECK (((ended_at IS NULL) OR (ended_at >= started_at)))` |
| Check | `ck_deployment_outcome_matches_end` | `CHECK (((ended_at IS NULL) = (outcome IS NULL)))` |
| Check | `ck_deployment_unfinished_has_no_outcome_receipt` | `CHECK (((outcome IS NOT NULL) OR (outcome_recorded_at IS NULL)))` |
| Check | `machine_deployment_outcome_check` | `CHECK ((outcome = ANY (ARRAY['CLEARED'::text, 'FAILED'::text])))` |

**Indexes** (beyond those that back the constraints above)

- `ix_deployment_cleared_receipt`: `btree (job_id, outcome_recorded_at) WHERE ((outcome = 'CLEARED'::text) AND (outcome_recorded_at IS NOT NULL))`
- `ix_deployment_job_outcome`: `btree (job_id, outcome)`

**Triggers**

- `trg_audit`: `AFTER INSERT OR DELETE OR UPDATE ... audit_row('deploy_id')`
- `trg_completion_projection_machine`: `AFTER INSERT OR DELETE OR UPDATE ... completion_projection_source_changed()`
- `trg_machine_deployment_outcome_guard`: `BEFORE INSERT OR UPDATE ... machine_deployment_outcome_guard()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('job'::text, job_id)` WITH CHECK `staff_scope_row('job'::text, job_id)`
- `rls_insert` for INSERT:  WITH CHECK `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])`
- `rls_select` for SELECT: USING `(app_is_staff() OR (EXISTS ( SELECT 1
   FROM job j
  WHERE ((j.job_id = machine_deployment.job_id) AND (j.contractor_id = app_contractor_id())))))`
- `rls_update` for UPDATE: USING `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])` WITH CHECK `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])`

## manhole

A sewer or septic access point.

| Column | Type | Null? | Default |
|---|---|---|---|
| `manhole_id` | bigint | NOT NULL | `generated always as identity` |
| `ulb_id` | bigint | NOT NULL |  |
| `code` | text | NOT NULL |  |
| `kind` | text | NOT NULL |  |
| `depth_m` | numeric(5,2) | NOT NULL |  |
| `lat` | numeric(9,6) | NOT NULL |  |
| `lng` | numeric(9,6) | NOT NULL |  |
| `address` | text | nullable |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `manhole_pkey` | `PRIMARY KEY (manhole_id)` |
| Unique | `manhole_code_key` | `UNIQUE (code)` |
| Foreign key | `manhole_ulb_id_fkey` | `FOREIGN KEY (ulb_id) REFERENCES ulb(ulb_id)` |
| Check | `ck_manhole_depth` | `CHECK ((depth_m > (0)::numeric))` |
| Check | `manhole_kind_check` | `CHECK ((kind = ANY (ARRAY['SEWER'::text, 'SEPTIC'::text])))` |
| Check | `manhole_lat_check` | `CHECK (((lat >= ('-90'::integer)::numeric) AND (lat <= (90)::numeric)))` |
| Check | `manhole_lng_check` | `CHECK (((lng >= ('-180'::integer)::numeric) AND (lng <= (180)::numeric)))` |

**Indexes** (beyond those that back the constraints above)

- `ix_manhole_code_prefix`: `btree (code text_pattern_ops)`
- `ix_manhole_ulb`: `btree (ulb_id)`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_ulb(ulb_id)` WITH CHECK `staff_scope_ulb(ulb_id)`
- `rls_delete_manhole_admin` for DELETE: USING `(app_role() = 'ADMIN'::text)`
- `rls_insert_manhole_officer` for INSERT:  WITH CHECK `((app_role() = ANY (ARRAY['ADMIN'::text, 'ENGINEER'::text])) AND staff_scope_ulb(ulb_id))`
- `rls_select_manhole_scope` for SELECT: USING `(app_is_staff() OR (EXISTS ( SELECT 1
   FROM (complaint c
     JOIN job j USING (complaint_id))
  WHERE ((c.manhole_id = manhole.manhole_id) AND ((j.contractor_id = app_contractor_id()) OR worker_on_job(j.job_id))))))`
- `rls_update_manhole_officer` for UPDATE: USING `((app_role() = ANY (ARRAY['ADMIN'::text, 'ENGINEER'::text])) AND staff_scope_ulb(ulb_id))` WITH CHECK `((app_role() = ANY (ARRAY['ADMIN'::text, 'ENGINEER'::text])) AND staff_scope_ulb(ulb_id))`

## mechanisation_waiver

Written reason, approved by the RSA, why a machine cannot do the job.

| Column | Type | Null? | Default |
|---|---|---|---|
| `waiver_id` | bigint | NOT NULL | `generated always as identity` |
| `job_id` | bigint | NOT NULL |  |
| `reason_code` | text | NOT NULL |  |
| `justification` | text | NOT NULL |  |
| `approved_by` | bigint | NOT NULL |  |
| `approved_at` | timestamp with time zone | NOT NULL | `now()` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `mechanisation_waiver_pkey` | `PRIMARY KEY (waiver_id)` |
| Unique | `mechanisation_waiver_job_id_key` | `UNIQUE (job_id)` |
| Foreign key | `mechanisation_waiver_approved_by_fkey` | `FOREIGN KEY (approved_by) REFERENCES app_user(user_id)` |
| Foreign key | `mechanisation_waiver_job_id_fkey` | `FOREIGN KEY (job_id) REFERENCES job(job_id)` |
| Check | `ck_waiver_justification_min_50` | `CHECK ((length(btrim(justification)) >= 50))` |
| Check | `mechanisation_waiver_reason_code_check` | `CHECK ((reason_code = ANY (ARRAY['MACHINE_FAILED'::text, 'NO_MACHINE_ACCESS'::text, 'STRUCTURAL_CONSTRAINT'::text, 'NO_MACHINE_AVAILABLE'::text, 'OTHER'::text])))` |

**Triggers**

- `trg_append_only`: `BEFORE DELETE OR UPDATE ... forbid_change()`
- `trg_audit`: `AFTER INSERT OR DELETE OR UPDATE ... audit_row('waiver_id')`
- `trg_waiver_apply`: `AFTER INSERT ... waiver_apply()`
- `trg_waiver_guard`: `BEFORE INSERT ... waiver_guard()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('job'::text, job_id)` WITH CHECK `staff_scope_row('job'::text, job_id)`
- `rls_insert` for INSERT:  WITH CHECK `app_has_role(VARIADIC '{ENGINEER}'::text[])`
- `rls_select` for SELECT: USING `(app_is_staff() OR worker_on_job(job_id) OR (EXISTS ( SELECT 1
   FROM job j
  WHERE ((j.job_id = mechanisation_waiver.job_id) AND (j.contractor_id = app_contractor_id())))))`

## outbox_event

Durable, privacy-minimised events ordered per ULB by a transactional counter row; event_id identity is not a replay cursor.

| Column | Type | Null? | Default |
|---|---|---|---|
| `event_id` | bigint | NOT NULL | `generated always as identity` |
| `ulb_id` | bigint | NOT NULL |  |
| `event_seq` | bigint | NOT NULL |  |
| `event_type` | text | NOT NULL |  |
| `entity_type` | text | NOT NULL |  |
| `entity_id` | bigint | nullable |  |
| `payload` | jsonb | NOT NULL | `'{}'::jsonb` |
| `occurred_at` | timestamp with time zone | NOT NULL | `now()` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `outbox_event_pkey` | `PRIMARY KEY (event_id)` |
| Unique | `outbox_event_ulb_id_event_seq_key` | `UNIQUE (ulb_id, event_seq)` |
| Foreign key | `outbox_event_ulb_id_fkey` | `FOREIGN KEY (ulb_id) REFERENCES ulb(ulb_id) ON DELETE RESTRICT` |
| Check | `outbox_event_entity_type_check` | `CHECK ((entity_type = ANY (ARRAY['permit'::text, 'job'::text, 'incident_report'::text, 'completion_claim'::text])))` |
| Check | `outbox_event_event_seq_check` | `CHECK ((event_seq > 0))` |
| Check | `outbox_event_event_type_check` | `CHECK ((event_type = ANY (ARRAY['PERMIT_DECISION'::text, 'PERMIT_READINESS'::text, 'PERMIT_SAFETY'::text, 'COMPLETION_RECONCILED'::text, 'COMPLETION_CLAIM'::text, 'INCIDENT_RECORDED'::text])))` |
| Check | `outbox_event_payload_check` | `CHECK ((jsonb_typeof(payload) = 'object'::text))` |

**Indexes** (beyond those that back the constraints above)

- `ix_outbox_event_scope_sequence`: `btree (ulb_id, event_seq)`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_select_outbox_scope` for SELECT: USING `((app_role() = ANY (ARRAY['ADMIN'::text, 'AUDITOR'::text])) OR ((app_role() = ANY (ARRAY['ENGINEER'::text, 'SUPERVISOR'::text])) AND (app_ulb_id() IS NOT NULL) AND (ulb_id = app_ulb_id())))`

## outbox_scope_counter



| Column | Type | Null? | Default |
|---|---|---|---|
| `ulb_id` | bigint | NOT NULL |  |
| `last_seq` | bigint | NOT NULL | `0` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `outbox_scope_counter_pkey` | `PRIMARY KEY (ulb_id)` |
| Foreign key | `outbox_scope_counter_ulb_id_fkey` | `FOREIGN KEY (ulb_id) REFERENCES ulb(ulb_id) ON DELETE RESTRICT` |
| Check | `outbox_scope_counter_last_seq_check` | `CHECK ((last_seq >= 0))` |

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)


## permit_authorization_decision

Immutable database-created JSONB snapshot for each successful authorization transition; not a formal proof or owner-resistant signature.

| Column | Type | Null? | Default |
|---|---|---|---|
| `decision_id` | bigint | NOT NULL | `generated always as identity` |
| `permit_id` | bigint | NOT NULL |  |
| `decision_kind` | text | NOT NULL |  |
| `decision_at` | timestamp with time zone | NOT NULL |  |
| `actor_user_id` | bigint | NOT NULL |  |
| `snapshot_format` | smallint | NOT NULL | `1` |
| `snapshot` | jsonb | NOT NULL |  |
| `snapshot_sha256` | text | NOT NULL |  |
| `captured_at` | timestamp with time zone | NOT NULL | `clock_timestamp()` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `permit_authorization_decision_pkey` | `PRIMARY KEY (decision_id)` |
| Unique | `permit_authorization_decision_permit_id_key` | `UNIQUE (permit_id)` |
| Foreign key | `permit_authorization_decision_permit_id_fkey` | `FOREIGN KEY (permit_id) REFERENCES entry_permit(permit_id) ON DELETE RESTRICT` |
| Check | `permit_authorization_decision_decision_kind_check` | `CHECK ((decision_kind = 'AUTHORIZATION'::text))` |
| Check | `permit_authorization_decision_snapshot_format_check` | `CHECK ((snapshot_format = 1))` |
| Check | `permit_authorization_decision_snapshot_sha256_check` | `CHECK ((snapshot_sha256 ~ '^[0-9a-f]{64}$'::text))` |

**Triggers**

- `trg_permit_authorization_decision_immutable`: `BEFORE DELETE OR UPDATE ... immutable_policy_record()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('entry_permit'::text, permit_id)` WITH CHECK `staff_scope_row('entry_permit'::text, permit_id)`
- `rls_select` for SELECT: USING `(app_is_staff() OR worker_on_permit(permit_id) OR contractor_owns_permit(permit_id))`

## permit_crew

Crew of a permit with exactly one role per worker.

| Column | Type | Null? | Default |
|---|---|---|---|
| `permit_id` | bigint | NOT NULL |  |
| `worker_id` | bigint | NOT NULL |  |
| `crew_role` | text | NOT NULL |  |
| `acknowledged_at` | timestamp with time zone | nullable |  |
| `acknowledged_by` | bigint | nullable |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `permit_crew_pkey` | `PRIMARY KEY (permit_id, worker_id)` |
| Foreign key | `permit_crew_acknowledged_by_fkey` | `FOREIGN KEY (acknowledged_by) REFERENCES app_user(user_id)` |
| Foreign key | `permit_crew_permit_id_fkey` | `FOREIGN KEY (permit_id) REFERENCES entry_permit(permit_id) ON DELETE CASCADE` |
| Foreign key | `permit_crew_worker_id_fkey` | `FOREIGN KEY (worker_id) REFERENCES worker(worker_id)` |
| Check | `ck_crew_ack_pair` | `CHECK (((acknowledged_at IS NULL) = (acknowledged_by IS NULL)))` |
| Check | `permit_crew_crew_role_check` | `CHECK ((crew_role = ANY (ARRAY['ENTRANT'::text, 'STANDBY'::text, 'SUPERVISOR'::text])))` |

**Indexes** (beyond those that back the constraints above)

- `ix_crew_worker`: `btree (worker_id)`

**Triggers**

- `trg_audit`: `AFTER INSERT OR DELETE OR UPDATE ... audit_row('permit_id,worker_id')`
- `trg_crew_ack_guard`: `BEFORE INSERT OR UPDATE OF acknowledged_at, acknowledged_by ... permit_crew_ack_guard()`
- `trg_crew_revision`: `AFTER INSERT OR DELETE OR UPDATE ... bump_permit_evidence()`
- `trg_freeze`: `BEFORE INSERT OR DELETE OR UPDATE ... freeze_after_authorisation()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('entry_permit'::text, permit_id)` WITH CHECK `staff_scope_row('entry_permit'::text, permit_id)`
- `rls_delete` for DELETE: USING `(app_has_role(VARIADIC '{SUPERVISOR}'::text[]) AND permit_writer(permit_id))`
- `rls_insert` for INSERT:  WITH CHECK `(app_has_role(VARIADIC '{SUPERVISOR}'::text[]) AND permit_writer(permit_id))`
- `rls_select` for SELECT: USING `(app_is_staff() OR worker_on_permit(permit_id) OR contractor_owns_permit(permit_id))`
- `rls_update` for UPDATE: USING `(app_has_role(VARIADIC '{SUPERVISOR}'::text[]) AND permit_writer(permit_id))` WITH CHECK `(app_has_role(VARIADIC '{SUPERVISOR}'::text[]) AND permit_writer(permit_id))`
- `rls_worker_ack_update` for UPDATE: USING `((app_role() = 'WORKER'::text) AND (worker_id = app_worker_id()))` WITH CHECK `((app_role() = 'WORKER'::text) AND (worker_id = app_worker_id()))`

## permit_decision_receipt



| Column | Type | Null? | Default |
|---|---|---|---|
| `receipt_id` | bigint | NOT NULL | `generated always as identity` |
| `permit_id` | bigint | NOT NULL |  |
| `evidence_revision` | bigint | NOT NULL |  |
| `decision` | text | NOT NULL |  |
| `evaluated_at` | timestamp with time zone | NOT NULL | `clock_timestamp()` |
| `expires_at` | timestamp with time zone | nullable |  |
| `failures` | jsonb | NOT NULL | `'[]'::jsonb` |
| `snapshot` | jsonb | NOT NULL | `'{}'::jsonb` |
| `snapshot_sha256` | text | NOT NULL |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `permit_decision_receipt_pkey` | `PRIMARY KEY (receipt_id)` |
| Foreign key | `permit_decision_receipt_permit_id_fkey` | `FOREIGN KEY (permit_id) REFERENCES entry_permit(permit_id)` |
| Check | `permit_decision_receipt_check` | `CHECK (((decision = 'AUTHORISED'::text) = (expires_at IS NOT NULL)))` |
| Check | `permit_decision_receipt_check1` | `CHECK (((expires_at IS NULL) OR (expires_at > evaluated_at)))` |
| Check | `permit_decision_receipt_decision_check` | `CHECK ((decision = ANY (ARRAY['AUTHORISED'::text, 'DENIED'::text])))` |
| Check | `permit_decision_receipt_evidence_revision_check` | `CHECK ((evidence_revision >= 0))` |
| Check | `permit_decision_receipt_snapshot_sha256_check` | `CHECK ((snapshot_sha256 ~ '^[0-9a-f]{64}$'::text))` |

**Indexes** (beyond those that back the constraints above)

- `ix_decision_receipt_current`: `btree (permit_id, evidence_revision DESC, evaluated_at DESC, receipt_id DESC)`

**Triggers**

- `trg_outbox_permit_receipt`: `AFTER INSERT ... outbox_for_evidence_fact()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('entry_permit'::text, permit_id)` WITH CHECK `staff_scope_row('entry_permit'::text, permit_id)`
- `rls_select` for SELECT: USING `(app_is_staff() OR worker_on_permit(permit_id) OR contractor_owns_permit(permit_id))`
- `rls_select_receipt_staff` for SELECT: USING `(app_role() = ANY (ARRAY['ADMIN'::text, 'ENGINEER'::text, 'SUPERVISOR'::text, 'AUDITOR'::text]))`

## permit_readiness



| Column | Type | Null? | Default |
|---|---|---|---|
| `readiness_id` | bigint | NOT NULL | `generated always as identity` |
| `permit_id` | bigint | NOT NULL |  |
| `kind` | text | NOT NULL |  |
| `passed` | boolean | NOT NULL |  |
| `recorded_by` | bigint | NOT NULL |  |
| `recorded_at` | timestamp with time zone | NOT NULL | `clock_timestamp()` |
| `expires_at` | timestamp with time zone | NOT NULL |  |
| `details` | jsonb | NOT NULL | `'{}'::jsonb` |
| `source_mode` | text | NOT NULL | `'TYPED'::text` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `permit_readiness_pkey` | `PRIMARY KEY (readiness_id)` |
| Foreign key | `permit_readiness_permit_id_fkey` | `FOREIGN KEY (permit_id) REFERENCES entry_permit(permit_id)` |
| Foreign key | `permit_readiness_recorded_by_fkey` | `FOREIGN KEY (recorded_by) REFERENCES app_user(user_id)` |
| Check | `permit_readiness_check` | `CHECK ((expires_at > recorded_at))` |
| Check | `permit_readiness_kind_check` | `CHECK ((kind = ANY (ARRAY['STRUCTURE'::text, 'ISOLATION'::text, 'VENTILATION'::text, 'RESCUE'::text, 'COMMUNICATION'::text, 'TRAFFIC'::text, 'MEDICAL'::text])))` |
| Check | `permit_readiness_source_mode_check` | `CHECK ((source_mode = ANY (ARRAY['SIMULATED'::text, 'TYPED'::text, 'HARDWARE_RAW'::text])))` |

**Indexes** (beyond those that back the constraints above)

- `ix_permit_readiness_latest`: `btree (permit_id, kind, recorded_at DESC, readiness_id DESC)`

**Triggers**

- `trg_00_readiness_revision`: `AFTER INSERT ... bump_permit_evidence()`
- `trg_outbox_permit_readiness`: `AFTER INSERT ... outbox_for_evidence_fact()`
- `trg_permit_readiness_guard`: `BEFORE INSERT ... permit_readiness_guard()`
- `trg_readiness_effects`: `AFTER INSERT ... readiness_effects()`
- `trg_readiness_receipt_refresh`: `AFTER INSERT ... refresh_current_receipt()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('entry_permit'::text, permit_id)` WITH CHECK `staff_scope_row('entry_permit'::text, permit_id)`
- `rls_insert` for INSERT:  WITH CHECK `(permit_writer(permit_id) AND (recorded_by = app_user_id()))`
- `rls_insert_readiness_supervisor` for INSERT:  WITH CHECK `((app_role() = 'SUPERVISOR'::text) AND permit_writer(permit_id))`
- `rls_select` for SELECT: USING `(app_is_staff() OR worker_on_permit(permit_id) OR contractor_owns_permit(permit_id))`
- `rls_select_readiness_staff` for SELECT: USING `(app_role() = ANY (ARRAY['ADMIN'::text, 'ENGINEER'::text, 'SUPERVISOR'::text, 'AUDITOR'::text]))`

## permit_resource_reservation



| Column | Type | Null? | Default |
|---|---|---|---|
| `reservation_id` | bigint | NOT NULL | `generated always as identity` |
| `permit_id` | bigint | NOT NULL |  |
| `worker_id` | bigint | nullable |  |
| `gear_asset_id` | bigint | nullable |  |
| `acquired_at` | timestamp with time zone | NOT NULL | `clock_timestamp()` |
| `released_at` | timestamp with time zone | nullable |  |
| `release_reason` | text | nullable |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `permit_resource_reservation_pkey` | `PRIMARY KEY (reservation_id)` |
| Foreign key | `permit_resource_reservation_gear_asset_id_fkey` | `FOREIGN KEY (gear_asset_id) REFERENCES gear_asset(gear_asset_id)` |
| Foreign key | `permit_resource_reservation_permit_id_fkey` | `FOREIGN KEY (permit_id) REFERENCES entry_permit(permit_id)` |
| Foreign key | `permit_resource_reservation_worker_id_fkey` | `FOREIGN KEY (worker_id) REFERENCES worker(worker_id)` |
| Check | `permit_resource_reservation_check` | `CHECK ((num_nonnulls(worker_id, gear_asset_id) = 1))` |
| Check | `permit_resource_reservation_check1` | `CHECK (((released_at IS NULL) = (release_reason IS NULL)))` |
| Check | `permit_resource_reservation_check2` | `CHECK (((released_at IS NULL) OR (released_at >= acquired_at)))` |

**Indexes** (beyond those that back the constraints above)

- `ix_resource_permit_open`: `btree (permit_id) WHERE (released_at IS NULL)`
- `uq_resource_asset_occupied`: `btree (gear_asset_id) WHERE ((gear_asset_id IS NOT NULL) AND (released_at IS NULL))`
- `uq_resource_worker_occupied`: `btree (worker_id) WHERE ((worker_id IS NOT NULL) AND (released_at IS NULL))`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('entry_permit'::text, permit_id)` WITH CHECK `staff_scope_row('entry_permit'::text, permit_id)`
- `rls_select` for SELECT: USING `(app_is_staff() OR worker_on_permit(permit_id) OR contractor_owns_permit(permit_id))`
- `rls_select_reservation_staff` for SELECT: USING `(app_role() = ANY (ARRAY['ADMIN'::text, 'ENGINEER'::text, 'SUPERVISOR'::text, 'AUDITOR'::text]))`

## permit_safety_event

Append-only local safety event evidence; it does not assert external delivery.

| Column | Type | Null? | Default |
|---|---|---|---|
| `event_id` | bigint | NOT NULL | `generated always as identity` |
| `permit_id` | bigint | NOT NULL |  |
| `entry_id` | bigint | nullable |  |
| `event_key` | text | NOT NULL |  |
| `event_type` | text | NOT NULL |  |
| `reason_code` | text | NOT NULL |  |
| `detail` | jsonb | NOT NULL | `'{}'::jsonb` |
| `occurred_at` | timestamp with time zone | NOT NULL | `clock_timestamp()` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `permit_safety_event_pkey` | `PRIMARY KEY (event_id)` |
| Unique | `permit_safety_event_event_key_key` | `UNIQUE (event_key)` |
| Foreign key | `permit_safety_event_entry_id_fkey` | `FOREIGN KEY (entry_id) REFERENCES entry_log(entry_id) DEFERRABLE INITIALLY DEFERRED` |
| Foreign key | `permit_safety_event_permit_id_fkey` | `FOREIGN KEY (permit_id) REFERENCES entry_permit(permit_id)` |
| Check | `permit_safety_event_event_key_check` | `CHECK ((length(btrim(event_key)) > 0))` |
| Check | `permit_safety_event_event_type_check` | `CHECK ((event_type = ANY (ARRAY['PERMIT_ABORTED'::text, 'SAFETY_STOP'::text, 'OPEN_ENTRY_OVERSTAY'::text, 'EXIT_VIOLATION'::text])))` |
| Check | `permit_safety_event_reason_code_check` | `CHECK ((reason_code = upper(reason_code)))` |

**Triggers**

- `trg_append_only`: `BEFORE DELETE OR UPDATE ... forbid_change()`
- `trg_audit`: `AFTER INSERT ... audit_row('event_id')`
- `trg_outbox_permit_safety`: `AFTER INSERT ... outbox_for_evidence_fact()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('entry_permit'::text, permit_id)` WITH CHECK `staff_scope_row('entry_permit'::text, permit_id)`
- `rls_select` for SELECT: USING `(app_is_staff() OR worker_on_permit(permit_id) OR contractor_owns_permit(permit_id))`

## permit_site_gear



| Column | Type | Null? | Default |
|---|---|---|---|
| `site_gear_id` | bigint | NOT NULL | `generated always as identity` |
| `permit_id` | bigint | NOT NULL |  |
| `gear_asset_id` | bigint | NOT NULL |  |
| `issued_by` | bigint | nullable |  |
| `issued_at` | timestamp with time zone | NOT NULL | `clock_timestamp()` |
| `returned_at` | timestamp with time zone | nullable |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `permit_site_gear_pkey` | `PRIMARY KEY (site_gear_id)` |
| Unique | `permit_site_gear_permit_id_gear_asset_id_key` | `UNIQUE (permit_id, gear_asset_id)` |
| Foreign key | `permit_site_gear_gear_asset_id_fkey` | `FOREIGN KEY (gear_asset_id) REFERENCES gear_asset(gear_asset_id)` |
| Foreign key | `permit_site_gear_issued_by_fkey` | `FOREIGN KEY (issued_by) REFERENCES app_user(user_id)` |
| Foreign key | `permit_site_gear_permit_id_fkey` | `FOREIGN KEY (permit_id) REFERENCES entry_permit(permit_id)` |
| Check | `permit_site_gear_check` | `CHECK (((returned_at IS NULL) OR (returned_at >= issued_at)))` |

**Triggers**

- `trg_site_gear_scope`: `BEFORE INSERT OR UPDATE ... site_gear_scope_guard()`
- `trg_site_revision`: `AFTER INSERT OR DELETE OR UPDATE ... bump_permit_evidence()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('entry_permit'::text, permit_id)` WITH CHECK `staff_scope_row('entry_permit'::text, permit_id)`
- `rls_insert_site_gear` for INSERT:  WITH CHECK `permit_writer(permit_id)`
- `rls_insert_site_gear_supervisor` for INSERT:  WITH CHECK `((app_role() = 'SUPERVISOR'::text) AND permit_writer(permit_id))`
- `rls_select` for SELECT: USING `(app_is_staff() OR worker_on_permit(permit_id) OR contractor_owns_permit(permit_id))`
- `rls_select_site_gear_staff` for SELECT: USING `(app_role() = ANY (ARRAY['ADMIN'::text, 'ENGINEER'::text, 'SUPERVISOR'::text, 'AUDITOR'::text]))`
- `rls_update_site_gear` for UPDATE: USING `permit_writer(permit_id)` WITH CHECK `permit_writer(permit_id)`

## policy_source

Migration-managed source metadata; source type distinguishes law, court directions, guidance and product policy.

| Column | Type | Null? | Default |
|---|---|---|---|
| `source_code` | text | NOT NULL |  |
| `source_type` | text | NOT NULL |  |
| `title` | text | NOT NULL |  |
| `source_url` | text | nullable |  |
| `source_version` | text | NOT NULL |  |
| `citation_clause` | text | NOT NULL |  |
| `applicability` | text | NOT NULL |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `policy_source_pkey` | `PRIMARY KEY (source_code)` |
| Check | `policy_source_source_code_check` | `CHECK ((source_code ~ '^[A-Z0-9_]+$'::text))` |
| Check | `policy_source_source_type_check` | `CHECK ((source_type = ANY (ARRAY['LAW'::text, 'COURT_DIRECTION'::text, 'GUIDANCE'::text, 'PRODUCT_POLICY'::text])))` |

**Triggers**

- `trg_policy_source_immutable`: `BEFORE DELETE OR UPDATE ... immutable_policy_record()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_select` for SELECT: USING `true`

## resolution_type

How a complaint was resolved and whether that resolution must leave evidence.

| Column | Type | Null? | Default |
|---|---|---|---|
| `code` | text | NOT NULL |  |
| `description` | text | NOT NULL |  |
| `requires_evidence` | boolean | NOT NULL |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `resolution_type_pkey` | `PRIMARY KEY (code)` |
| Check | `resolution_type_code_check` | `CHECK ((code = upper(code)))` |

## role

The six application roles.

| Column | Type | Null? | Default |
|---|---|---|---|
| `role_id` | smallint | NOT NULL | `generated always as identity` |
| `name` | text | NOT NULL |  |
| `description` | text | NOT NULL |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `role_pkey` | `PRIMARY KEY (role_id)` |
| Unique | `role_name_key` | `UNIQUE (name)` |
| Check | `role_name_check` | `CHECK ((name = upper(name)))` |

## rule_parameter

Statutory thresholds and policy numbers as editable, audited data.

| Column | Type | Null? | Default |
|---|---|---|---|
| `param_key` | text | NOT NULL |  |
| `value` | numeric | NOT NULL |  |
| `unit` | text | NOT NULL |  |
| `description` | text | NOT NULL |  |
| `legal_ref` | text | NOT NULL |  |
| `is_assumption` | boolean | NOT NULL | `false` |
| `updated_by` | bigint | nullable |  |
| `updated_at` | timestamp with time zone | NOT NULL | `now()` |
| `revision` | integer | NOT NULL | `1` |
| `source_code` | text | NOT NULL |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `rule_parameter_pkey` | `PRIMARY KEY (param_key)` |
| Foreign key | `rule_parameter_source_code_fkey` | `FOREIGN KEY (source_code) REFERENCES policy_source(source_code)` |
| Foreign key | `rule_parameter_updated_by_fkey` | `FOREIGN KEY (updated_by) REFERENCES app_user(user_id)` |
| Check | `rule_parameter_param_key_check` | `CHECK ((param_key ~ '^[a-z0-9_]+$'::text))` |
| Check | `rule_parameter_revision_check` | `CHECK ((revision > 0))` |

**Triggers**

- `trg_audit`: `AFTER INSERT OR DELETE OR UPDATE ... audit_row('param_key')`
- `trg_rule_parameter_revision`: `BEFORE UPDATE ... record_rule_parameter_revision()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_select` for SELECT: USING `true`
- `rls_update` for UPDATE: USING `app_has_role(VARIADIC '{ADMIN}'::text[])` WITH CHECK `app_has_role(VARIADIC '{ADMIN}'::text[])`

## rule_parameter_history

Append-only current-value change history with actor/reason/source; not a historical rule-replay engine.

| Column | Type | Null? | Default |
|---|---|---|---|
| `history_id` | bigint | NOT NULL | `generated always as identity` |
| `param_key` | text | NOT NULL |  |
| `revision` | integer | NOT NULL |  |
| `value` | numeric | NOT NULL |  |
| `unit` | text | NOT NULL |  |
| `description` | text | NOT NULL |  |
| `legal_ref` | text | NOT NULL |  |
| `is_assumption` | boolean | NOT NULL |  |
| `source_code` | text | NOT NULL |  |
| `effective_at` | timestamp with time zone | NOT NULL |  |
| `actor_user_id` | bigint | nullable |  |
| `change_reason` | text | NOT NULL |  |
| `recorded_at` | timestamp with time zone | NOT NULL | `clock_timestamp()` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `rule_parameter_history_pkey` | `PRIMARY KEY (history_id)` |
| Unique | `rule_parameter_history_param_key_revision_key` | `UNIQUE (param_key, revision)` |
| Foreign key | `rule_parameter_history_param_key_fkey` | `FOREIGN KEY (param_key) REFERENCES rule_parameter(param_key) ON DELETE RESTRICT` |
| Foreign key | `rule_parameter_history_source_code_fkey` | `FOREIGN KEY (source_code) REFERENCES policy_source(source_code)` |
| Check | `rule_parameter_history_change_reason_check` | `CHECK ((length(btrim(change_reason)) >= 10))` |
| Check | `rule_parameter_history_revision_check` | `CHECK ((revision > 0))` |

**Triggers**

- `trg_rule_parameter_history_immutable`: `BEFORE DELETE OR UPDATE ... immutable_policy_record()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_select` for SELECT: USING `true`

## shadow_entry_alert

Persisted suspicion that an entry happened unrecorded.

| Column | Type | Null? | Default |
|---|---|---|---|
| `alert_id` | bigint | NOT NULL | `generated always as identity` |
| `complaint_id` | bigint | NOT NULL |  |
| `rule_code` | text | NOT NULL |  |
| `contractor_id` | bigint | nullable |  |
| `status` | text | NOT NULL | `'OPEN'::text` |
| `reason` | text | NOT NULL |  |
| `evidence_deadline` | timestamp with time zone | NOT NULL |  |
| `detected_at` | timestamp with time zone | NOT NULL | `now()` |
| `last_evaluated_at` | timestamp with time zone | NOT NULL | `now()` |
| `reviewed_by` | bigint | nullable |  |
| `reviewed_at` | timestamp with time zone | nullable |  |
| `review_note` | text | nullable |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `shadow_entry_alert_pkey` | `PRIMARY KEY (alert_id)` |
| Unique | `uq_alert_per_complaint_rule` | `UNIQUE (complaint_id, rule_code)` |
| Foreign key | `shadow_entry_alert_complaint_id_fkey` | `FOREIGN KEY (complaint_id) REFERENCES complaint(complaint_id)` |
| Foreign key | `shadow_entry_alert_contractor_id_fkey` | `FOREIGN KEY (contractor_id) REFERENCES contractor(contractor_id)` |
| Foreign key | `shadow_entry_alert_reviewed_by_fkey` | `FOREIGN KEY (reviewed_by) REFERENCES app_user(user_id)` |
| Foreign key | `shadow_entry_alert_rule_code_fkey` | `FOREIGN KEY (rule_code) REFERENCES detection_rule(rule_code)` |
| Check | `ck_alert_review_complete` | `CHECK ((((status = ANY (ARRAY['CONFIRMED'::text, 'DISMISSED'::text])) = (reviewed_at IS NOT NULL)) AND ((status <> ALL (ARRAY['CONFIRMED'::text, 'DISMISSED'::text])) OR ((reviewed_by IS NOT NULL) AND (length(btrim(COALESCE(review_note, ''::text))) >= 10)))))` |
| Check | `shadow_entry_alert_status_check` | `CHECK ((status = ANY (ARRAY['OPEN'::text, 'EVIDENCE_RECEIVED'::text, 'CONFIRMED'::text, 'DISMISSED'::text])))` |

**Indexes** (beyond those that back the constraints above)

- `ix_alert_status`: `btree (status, detected_at DESC)`

**Triggers**

- `trg_00_alert_insert_isolation`: `BEFORE INSERT ... require_read_committed_financialrace()`
- `trg_alert_after_insert`: `AFTER INSERT ... alert_after_insert()`
- `trg_alert_after_update`: `AFTER UPDATE ... alert_after_update()`
- `trg_alert_complaint_lock`: `BEFORE INSERT ... alert_complaint_lock()`
- `trg_alert_guard`: `BEFORE UPDATE ... alert_guard()`
- `trg_no_delete`: `BEFORE DELETE ... forbid_change()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('complaint'::text, complaint_id)` WITH CHECK `staff_scope_row('complaint'::text, complaint_id)`
- `rls_insert` for INSERT:  WITH CHECK `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])`
- `rls_select` for SELECT: USING `app_has_role(VARIADIC ARRAY['ADMIN'::text, 'ENGINEER'::text, 'AUDITOR'::text])`
- `rls_update` for UPDATE: USING `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])` WITH CHECK `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])`

## shadow_entry_alert_event

Append-only lifecycle history of alerts.

| Column | Type | Null? | Default |
|---|---|---|---|
| `event_id` | bigint | NOT NULL | `generated always as identity` |
| `alert_id` | bigint | NOT NULL |  |
| `from_status` | text | nullable |  |
| `to_status` | text | NOT NULL |  |
| `actor_id` | bigint | nullable |  |
| `note` | text | nullable |  |
| `occurred_at` | timestamp with time zone | NOT NULL | `now()` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `shadow_entry_alert_event_pkey` | `PRIMARY KEY (event_id)` |
| Foreign key | `shadow_entry_alert_event_actor_id_fkey` | `FOREIGN KEY (actor_id) REFERENCES app_user(user_id)` |
| Foreign key | `shadow_entry_alert_event_alert_id_fkey` | `FOREIGN KEY (alert_id) REFERENCES shadow_entry_alert(alert_id) ON DELETE CASCADE` |

**Indexes** (beyond those that back the constraints above)

- `ix_alert_event_alert`: `btree (alert_id, occurred_at)`

**Triggers**

- `trg_append_only`: `BEFORE DELETE OR UPDATE ... forbid_change()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('shadow_entry_alert'::text, alert_id)` WITH CHECK `staff_scope_row('shadow_entry_alert'::text, alert_id)`
- `rls_insert` for INSERT:  WITH CHECK `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])`
- `rls_select` for SELECT: USING `app_has_role(VARIADIC ARRAY['ADMIN'::text, 'ENGINEER'::text, 'AUDITOR'::text])`

## ulb

Urban local body / municipal zone.

| Column | Type | Null? | Default |
|---|---|---|---|
| `ulb_id` | bigint | NOT NULL | `generated always as identity` |
| `name` | text | NOT NULL |  |
| `district` | text | NOT NULL |  |
| `state` | text | NOT NULL |  |
| `policy_mode` | text | NOT NULL | `'REVIEW_REQUIRED'::text` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `ulb_pkey` | `PRIMARY KEY (ulb_id)` |
| Unique | `ulb_name_key` | `UNIQUE (name)` |
| Check | `ulb_policy_mode_check` | `CHECK ((policy_mode = ANY (ARRAY['EDUCATIONAL'::text, 'DENIED'::text, 'REVIEW_REQUIRED'::text])))` |

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_ulb_admin_delete` for DELETE: USING `(app_role() = 'ADMIN'::text)`
- `rls_ulb_admin_insert` for INSERT:  WITH CHECK `(app_role() = 'ADMIN'::text)`
- `rls_ulb_authenticated_read` for SELECT: USING `(app_role() IS NOT NULL)`
- `rls_ulb_admin_update` for UPDATE: USING `(app_role() = 'ADMIN'::text)` WITH CHECK `(app_role() = 'ADMIN'::text)`

## ulb_contractor_scope



| Column | Type | Null? | Default |
|---|---|---|---|
| `ulb_id` | bigint | NOT NULL |  |
| `contractor_id` | bigint | NOT NULL |  |
| `assigned_by` | bigint | NOT NULL |  |
| `assigned_at` | timestamp with time zone | NOT NULL | `clock_timestamp()` |
| `assignment_reason` | text | NOT NULL |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `ulb_contractor_scope_pkey` | `PRIMARY KEY (ulb_id, contractor_id)` |
| Foreign key | `ulb_contractor_scope_assigned_by_fkey` | `FOREIGN KEY (assigned_by) REFERENCES app_user(user_id) ON DELETE RESTRICT` |
| Foreign key | `ulb_contractor_scope_contractor_id_fkey` | `FOREIGN KEY (contractor_id) REFERENCES contractor(contractor_id) ON DELETE RESTRICT` |
| Foreign key | `ulb_contractor_scope_ulb_id_fkey` | `FOREIGN KEY (ulb_id) REFERENCES ulb(ulb_id) ON DELETE RESTRICT` |
| Check | `ulb_contractor_scope_assignment_reason_check` | `CHECK (((length(btrim(assignment_reason)) >= 20) AND (length(btrim(assignment_reason)) <= 500)))` |

**Indexes** (beyond those that back the constraints above)

- `ix_ulb_contractor_scope_contractor`: `btree (contractor_id, ulb_id)`

**Triggers**

- `audit_ulb_contractor_scope`: `AFTER INSERT ... audit_row('ulb_id,contractor_id')`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_insert_contractor_scope` for INSERT:  WITH CHECK `((app_role() = 'ADMIN'::text) OR ((app_role() = 'ENGINEER'::text) AND staff_scope_ulb(ulb_id)))`
- `rls_select_contractor_scope` for SELECT: USING `((app_role() = ANY (ARRAY['ADMIN'::text, 'AUDITOR'::text])) OR ((app_role() = ANY (ARRAY['ENGINEER'::text, 'SUPERVISOR'::text])) AND staff_scope_ulb(ulb_id)))`

## ulb_detector_scope



| Column | Type | Null? | Default |
|---|---|---|---|
| `ulb_id` | bigint | NOT NULL |  |
| `detector_id` | bigint | NOT NULL |  |
| `assigned_by` | bigint | NOT NULL |  |
| `assigned_at` | timestamp with time zone | NOT NULL | `clock_timestamp()` |
| `assignment_reason` | text | NOT NULL |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `ulb_detector_scope_pkey` | `PRIMARY KEY (ulb_id, detector_id)` |
| Foreign key | `ulb_detector_scope_assigned_by_fkey` | `FOREIGN KEY (assigned_by) REFERENCES app_user(user_id) ON DELETE RESTRICT` |
| Foreign key | `ulb_detector_scope_detector_id_fkey` | `FOREIGN KEY (detector_id) REFERENCES gas_detector(detector_id) ON DELETE RESTRICT` |
| Foreign key | `ulb_detector_scope_ulb_id_fkey` | `FOREIGN KEY (ulb_id) REFERENCES ulb(ulb_id) ON DELETE RESTRICT` |
| Check | `ulb_detector_scope_assignment_reason_check` | `CHECK (((length(btrim(assignment_reason)) >= 20) AND (length(btrim(assignment_reason)) <= 500)))` |

**Indexes** (beyond those that back the constraints above)

- `ix_ulb_detector_scope_detector`: `btree (detector_id, ulb_id)`

**Triggers**

- `audit_ulb_detector_scope`: `AFTER INSERT ... audit_row('ulb_id,detector_id')`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_insert_detector_scope` for INSERT:  WITH CHECK `(app_role() = 'ADMIN'::text)`
- `rls_select_detector_scope` for SELECT: USING `((app_role() = ANY (ARRAY['ADMIN'::text, 'AUDITOR'::text])) OR ((app_role() = ANY (ARRAY['ENGINEER'::text, 'SUPERVISOR'::text])) AND staff_scope_ulb(ulb_id)))`

## user_session

Opaque server-side sessions; only a SHA-256 of the cookie token is stored.

| Column | Type | Null? | Default |
|---|---|---|---|
| `session_id` | bigint | NOT NULL | `generated always as identity` |
| `user_id` | bigint | NOT NULL |  |
| `token_hash` | bytea | NOT NULL |  |
| `csrf_token` | text | NOT NULL |  |
| `created_at` | timestamp with time zone | NOT NULL | `now()` |
| `expires_at` | timestamp with time zone | NOT NULL |  |
| `revoked_at` | timestamp with time zone | nullable |  |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `user_session_pkey` | `PRIMARY KEY (session_id)` |
| Unique | `user_session_token_hash_key` | `UNIQUE (token_hash)` |
| Foreign key | `user_session_user_id_fkey` | `FOREIGN KEY (user_id) REFERENCES app_user(user_id) ON DELETE CASCADE` |
| Check | `ck_session_lifetime` | `CHECK ((expires_at > created_at))` |

**Indexes** (beyond those that back the constraints above)

- `ix_user_session_user`: `btree (user_id)`

## worker

Sanitation worker registered under NAMASTE.

| Column | Type | Null? | Default |
|---|---|---|---|
| `worker_id` | bigint | NOT NULL | `generated always as identity` |
| `contractor_id` | bigint | NOT NULL |  |
| `full_name` | text | NOT NULL |  |
| `namaste_id` | text | NOT NULL |  |
| `medical_fit_until` | date | NOT NULL |  |
| `trained_until` | date | NOT NULL |  |
| `is_active` | boolean | NOT NULL | `true` |

**Constraints**

| Kind | Name | Definition |
|---|---|---|
| Primary key | `worker_pkey` | `PRIMARY KEY (worker_id)` |
| Unique | `worker_namaste_id_key` | `UNIQUE (namaste_id)` |
| Foreign key | `worker_contractor_id_fkey` | `FOREIGN KEY (contractor_id) REFERENCES contractor(contractor_id)` |
| Check | `worker_full_name_check` | `CHECK ((length(btrim(full_name)) > 0))` |

**Indexes** (beyond those that back the constraints above)

- `ix_worker_contractor`: `btree (contractor_id)`
- `ix_worker_namaste_prefix`: `btree (namaste_id text_pattern_ops)`
- `ix_worker_name_prefix`: `btree (lower(full_name) text_pattern_ops)`

**Triggers**

- `trg_audit`: `AFTER INSERT OR DELETE OR UPDATE ... audit_row('worker_id')`
- `trg_worker_safety_revalidate`: `AFTER UPDATE OF is_active, medical_fit_until, trained_until, contractor_id ... revalidate_changed_safety_dependency()`

**Row-level security** is ENABLED (the table owner and superusers bypass it; the application role does not)

- `rls_staff_ulb_scope` for ALL: USING `staff_scope_row('contractor'::text, contractor_id)` WITH CHECK `((app_ulb_id() IS NOT NULL) OR (app_role() <> ALL (ARRAY['ENGINEER'::text, 'SUPERVISOR'::text])))`
- `rls_delete` for DELETE: USING `app_has_role(VARIADIC '{ADMIN}'::text[])`
- `rls_insert` for INSERT:  WITH CHECK `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])`
- `rls_select` for SELECT: USING `(app_is_staff() OR (contractor_id = app_contractor_id()) OR (worker_id = app_worker_id()) OR worker_shares_permit(worker_id))`
- `rls_update` for UPDATE: USING `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])` WITH CHECK `app_has_role(VARIADIC '{ADMIN,ENGINEER}'::text[])`
