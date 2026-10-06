-- 0002_core_schema.sql
-- Tables, keys, constraints and indexes. Behaviour (triggers, functions, views, policies) comes later.
-- Design notes live in DATABASE_DESIGN.md; business-rule IDs (BR-nn) in PROJECT_SPEC.md.
-- Conventions: bigint identity keys; money is numeric(12,2) INR; all instants are timestamptz.

-- =============================================================================================
-- Identity and access
-- =============================================================================================
CREATE TABLE role (
  role_id     smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name        text NOT NULL UNIQUE CHECK (name = upper(name)),
  description text NOT NULL
);

-- Geography ---------------------------------------------------------------------------------
CREATE TABLE ulb (                       -- urban local body / municipal zone
  ulb_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name     text NOT NULL UNIQUE,
  district text NOT NULL,
  state    text NOT NULL
);

CREATE TABLE contractor (
  contractor_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name                text NOT NULL,
  licence_no          text NOT NULL UNIQUE,
  licence_valid_until date NOT NULL,
  status              text NOT NULL DEFAULT 'ACTIVE'
                      CONSTRAINT ck_contractor_status CHECK (status IN ('ACTIVE', 'SUSPENDED', 'BLACKLISTED')),
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE worker (
  worker_id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  contractor_id     bigint NOT NULL REFERENCES contractor,
  full_name         text NOT NULL CHECK (length(btrim(full_name)) > 0),
  namaste_id        text NOT NULL UNIQUE,            -- NAMASTE scheme registry id
  medical_fit_until date NOT NULL,
  trained_until     date NOT NULL,
  is_active         boolean NOT NULL DEFAULT true
);

CREATE TABLE app_user (
  user_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  role_id       smallint NOT NULL REFERENCES role,
  ulb_id        bigint REFERENCES ulb,
  contractor_id bigint REFERENCES contractor,        -- set for CONTRACTOR logins (row scoping)
  worker_id     bigint UNIQUE REFERENCES worker,     -- set for WORKER logins (row scoping)
  email         text NOT NULL UNIQUE
                CONSTRAINT ck_email_form CHECK (email = lower(email) AND position('@' IN email) > 1),
  full_name     text NOT NULL CHECK (length(btrim(full_name)) > 0),
  password_hash text NOT NULL,                       -- bcrypt only; never the password
  is_active     boolean NOT NULL DEFAULT true,
  failed_logins smallint NOT NULL DEFAULT 0 CHECK (failed_logins >= 0),
  locked_until  timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_session (                -- opaque server-side sessions: real logout, real revocation
  session_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id    bigint NOT NULL REFERENCES app_user ON DELETE CASCADE,
  token_hash bytea NOT NULL UNIQUE,        -- SHA-256 of the cookie token; the token itself is never stored
  csrf_token text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  CONSTRAINT ck_session_lifetime CHECK (expires_at > created_at)
);

-- =============================================================================================
-- Assets, complaints, jobs
-- =============================================================================================
CREATE TABLE manhole (
  manhole_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ulb_id     bigint NOT NULL REFERENCES ulb,
  code       text NOT NULL UNIQUE,
  kind       text NOT NULL CHECK (kind IN ('SEWER', 'SEPTIC')),
  depth_m    numeric(5,2) NOT NULL CONSTRAINT ck_manhole_depth CHECK (depth_m > 0),
  lat        numeric(9,6) NOT NULL CHECK (lat BETWEEN -90 AND 90),
  lng        numeric(9,6) NOT NULL CHECK (lng BETWEEN -180 AND 180),
  address    text
);

-- Which resolutions are expected to leave clearance evidence. "Intentionally absent" is data, not code (BR-33).
CREATE TABLE resolution_type (
  code              text PRIMARY KEY CHECK (code = upper(code)),
  description       text NOT NULL,
  requires_evidence boolean NOT NULL
);

CREATE TABLE complaint (
  complaint_id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  manhole_id      bigint NOT NULL REFERENCES manhole,
  description     text NOT NULL CHECK (length(btrim(description)) > 0),
  raised_at       timestamptz NOT NULL DEFAULT now(),
  status          text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED')),
  resolved_at     timestamptz,
  resolution_code text REFERENCES resolution_type,
  resolved_by     bigint REFERENCES app_user,
  CONSTRAINT ck_complaint_resolution_complete
    CHECK ((status = 'RESOLVED') = (resolved_at IS NOT NULL) AND (status = 'RESOLVED') = (resolution_code IS NOT NULL)),
  CONSTRAINT ck_complaint_resolved_after_raised CHECK (resolved_at IS NULL OR resolved_at >= raised_at)
);

CREATE TABLE machine (
  machine_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ulb_id     bigint NOT NULL REFERENCES ulb,
  code       text NOT NULL UNIQUE,
  kind       text NOT NULL CHECK (kind IN ('JETTING', 'SUCTION', 'ROBOT')),
  status     text NOT NULL DEFAULT 'AVAILABLE' CHECK (status IN ('AVAILABLE', 'IN_USE', 'MAINTENANCE'))
);

CREATE TABLE job (
  job_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  complaint_id  bigint NOT NULL REFERENCES complaint,
  contractor_id bigint NOT NULL REFERENCES contractor,
  method        text NOT NULL DEFAULT 'MECHANISED' CHECK (method IN ('MECHANISED', 'MANUAL_EXCEPTION')),
  status        text NOT NULL DEFAULT 'PLANNED'
                CHECK (status IN ('PLANNED', 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'CANCELLED')),
  created_by    bigint REFERENCES app_user,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE machine_deployment (
  deploy_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id      bigint NOT NULL REFERENCES job,
  machine_id  bigint NOT NULL REFERENCES machine,
  started_at  timestamptz NOT NULL,
  ended_at    timestamptz,
  outcome     text CHECK (outcome IN ('CLEARED', 'FAILED')),
  recorded_by bigint REFERENCES app_user,
  recorded_at timestamptz NOT NULL DEFAULT now(),   -- server-assigned; basis of the "timely evidence" test (BR-31)
  CONSTRAINT ck_deployment_outcome_matches_end CHECK ((ended_at IS NULL) = (outcome IS NULL)),
  CONSTRAINT ck_deployment_order CHECK (ended_at IS NULL OR ended_at >= started_at)
);

-- Manual entry is an exception the RSA records in writing (BR-01, BR-02). 1:1 with job.
CREATE TABLE mechanisation_waiver (
  waiver_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id        bigint NOT NULL UNIQUE REFERENCES job,
  reason_code   text NOT NULL CHECK (reason_code IN
                ('MACHINE_FAILED', 'NO_MACHINE_ACCESS', 'STRUCTURAL_CONSTRAINT', 'NO_MACHINE_AVAILABLE', 'OTHER')),
  justification text NOT NULL CONSTRAINT ck_waiver_justification_min_50 CHECK (length(btrim(justification)) >= 50),
  approved_by   bigint NOT NULL REFERENCES app_user,
  approved_at   timestamptz NOT NULL DEFAULT now()
);

-- =============================================================================================
-- Entry permits (the zero-entry gate)
-- =============================================================================================
CREATE TABLE entry_permit (
  permit_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id        bigint NOT NULL REFERENCES job,
  supervisor_id bigint NOT NULL REFERENCES app_user,
  status        text NOT NULL DEFAULT 'DRAFT'
                CHECK (status IN ('DRAFT', 'AUTHORISED', 'CLOSED', 'ABORTED', 'CANCELLED')),
  created_at    timestamptz NOT NULL DEFAULT now(),
  authorised_at timestamptz,
  authorised_by bigint REFERENCES app_user,
  valid_until   timestamptz,
  ended_at      timestamptz,
  end_reason    text,
  UNIQUE (permit_id, job_id),                         -- target of incident's composite FK
  CONSTRAINT ck_permit_authorised_matches_status
    CHECK ((status IN ('AUTHORISED', 'CLOSED', 'ABORTED')) = (authorised_at IS NOT NULL)),
  CONSTRAINT ck_permit_authorisation_complete
    CHECK ((authorised_at IS NULL) = (valid_until IS NULL) AND (authorised_at IS NULL) = (authorised_by IS NULL)),
  CONSTRAINT ck_permit_validity_after_authorisation CHECK (valid_until IS NULL OR valid_until > authorised_at),
  CONSTRAINT ck_permit_ended_matches_status
    CHECK ((status IN ('CLOSED', 'ABORTED', 'CANCELLED')) = (ended_at IS NOT NULL))
);

CREATE TABLE permit_crew (
  permit_id bigint NOT NULL REFERENCES entry_permit ON DELETE CASCADE,
  worker_id bigint NOT NULL REFERENCES worker,
  crew_role text NOT NULL CHECK (crew_role IN ('ENTRANT', 'STANDBY', 'SUPERVISOR')),
  PRIMARY KEY (permit_id, worker_id)                  -- one role per worker per permit: standby can never be an entrant
);

CREATE TABLE gear_item (
  gear_code text PRIMARY KEY CHECK (gear_code = upper(gear_code)),
  name      text NOT NULL,
  statutory boolean NOT NULL DEFAULT false,
  legal_ref text
);

CREATE TABLE gear_issue (                             -- gear issued to a specific crew member for a specific permit
  issue_id  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  permit_id bigint NOT NULL,
  worker_id bigint NOT NULL,
  gear_code text NOT NULL REFERENCES gear_item,
  serial_no text NOT NULL CHECK (length(btrim(serial_no)) > 0),
  issued_by bigint REFERENCES app_user,
  issued_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (permit_id, worker_id, gear_code),
  FOREIGN KEY (permit_id, worker_id) REFERENCES permit_crew (permit_id, worker_id) ON DELETE CASCADE
);

CREATE TABLE gas_detector (
  detector_id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  serial_no              text NOT NULL UNIQUE,
  model                  text NOT NULL,
  calibration_valid_until date NOT NULL
);

CREATE TABLE gas_reading (                            -- append-only evidence (trigger)
  reading_id  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  permit_id   bigint NOT NULL REFERENCES entry_permit,
  detector_id bigint NOT NULL REFERENCES gas_detector,
  depth_level text NOT NULL CHECK (depth_level IN ('TOP', 'MID', 'BOTTOM')),
  o2_pct      numeric(4,1) NOT NULL CONSTRAINT ck_o2_range CHECK (o2_pct BETWEEN 0 AND 100),
  h2s_ppm     numeric(6,2) NOT NULL CHECK (h2s_ppm >= 0),
  lel_pct     numeric(5,2) NOT NULL CHECK (lel_pct BETWEEN 0 AND 100),
  co_ppm      numeric(6,2) NOT NULL CHECK (co_ppm >= 0),
  taken_at    timestamptz NOT NULL,
  recorded_by bigint NOT NULL REFERENCES app_user,    -- the supervisor's digital sign-off
  recorded_at timestamptz NOT NULL DEFAULT now()
);

-- A worker's time underground. Open entry = worker still inside (upper bound NULL).
-- The exclusion constraint makes two overlapping entries for one worker impossible (BR-10). It uses a
-- single-point int8range for the equality half so no btree_gist extension is needed on any build.
CREATE TABLE entry_log (
  entry_id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  permit_id   bigint NOT NULL,
  worker_id   bigint NOT NULL,
  period      tstzrange NOT NULL,
  recorded_by bigint NOT NULL REFERENCES app_user,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (permit_id, worker_id) REFERENCES permit_crew (permit_id, worker_id),
  CONSTRAINT ck_entry_period_shape CHECK (NOT isempty(period) AND NOT lower_inf(period) AND lower_inc(period)),
  CONSTRAINT ex_entry_no_overlap
    EXCLUDE USING gist (int8range(worker_id, worker_id, '[]') WITH &&, period WITH &&)
);

-- =============================================================================================
-- Consequences
-- =============================================================================================
CREATE TABLE incident (
  incident_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  incident_type text NOT NULL CHECK (incident_type IN ('FATALITY', 'DISABILITY', 'NEAR_MISS')),
  occurred_at   timestamptz NOT NULL,
  manhole_id    bigint NOT NULL REFERENCES manhole,
  worker_id     bigint NOT NULL REFERENCES worker,
  contractor_id bigint NOT NULL REFERENCES contractor,  -- employer AT THE TIME: a deliberate snapshot, workers change contractor
  job_id        bigint REFERENCES job,
  permit_id     bigint,
  description   text NOT NULL CHECK (length(btrim(description)) > 0),
  recorded_by   bigint NOT NULL REFERENCES app_user,
  recorded_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (worker_id, occurred_at, incident_type),       -- a double-click cannot record the same death twice
  FOREIGN KEY (permit_id, job_id) REFERENCES entry_permit (permit_id, job_id),
  FOREIGN KEY (permit_id, worker_id) REFERENCES permit_crew (permit_id, worker_id)  -- skipped when permit_id IS NULL
);

CREATE TABLE compensation_case (
  case_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  incident_id bigint NOT NULL UNIQUE REFERENCES incident,
  amount_due  numeric(12,2) NOT NULL CHECK (amount_due > 0),
  amount_paid numeric(12,2) NOT NULL DEFAULT 0 CHECK (amount_paid >= 0),
  due_by      date NOT NULL,
  status      text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'PARTIAL', 'PAID')),
  opened_at   timestamptz NOT NULL DEFAULT now(),
  paid_at     timestamptz,
  CONSTRAINT ck_case_not_overpaid CHECK (amount_paid <= amount_due),
  CONSTRAINT ck_case_status_matches_payments CHECK (
       (status = 'OPEN'    AND amount_paid = 0                                  AND paid_at IS NULL)
    OR (status = 'PARTIAL' AND amount_paid > 0 AND amount_paid < amount_due     AND paid_at IS NULL)
    OR (status = 'PAID'    AND amount_paid = amount_due                         AND paid_at IS NOT NULL))
);

CREATE TABLE invoice (
  invoice_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id       bigint NOT NULL REFERENCES job,
  invoice_no   text NOT NULL UNIQUE,
  amount_inr   numeric(12,2) NOT NULL CHECK (amount_inr > 0),
  status       text NOT NULL DEFAULT 'SUBMITTED' CHECK (status IN ('SUBMITTED', 'APPROVED', 'PAID', 'REJECTED')),
  submitted_at timestamptz NOT NULL DEFAULT now(),
  decided_by   bigint REFERENCES app_user,
  decided_at   timestamptz,
  paid_at      timestamptz,
  CONSTRAINT ck_invoice_decider CHECK ((status = 'SUBMITTED') = (decided_by IS NULL)),
  CONSTRAINT ck_invoice_paid_at CHECK ((status = 'PAID') = (paid_at IS NOT NULL))
);

-- =============================================================================================
-- Detection by absence
-- =============================================================================================
CREATE TABLE detection_rule (
  rule_code   text PRIMARY KEY CHECK (rule_code ~ '^SE[0-9]+_[A-Z_]+$'),
  title       text NOT NULL,
  description text NOT NULL,
  enabled     boolean NOT NULL DEFAULT true
);

CREATE TABLE shadow_entry_alert (
  alert_id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  complaint_id      bigint NOT NULL REFERENCES complaint,
  rule_code         text NOT NULL REFERENCES detection_rule,
  contractor_id     bigint REFERENCES contractor,       -- responsible contractor when the alert was raised (NULL: no job at all)
  status            text NOT NULL DEFAULT 'OPEN'
                    CHECK (status IN ('OPEN', 'EVIDENCE_RECEIVED', 'CONFIRMED', 'DISMISSED')),
  reason            text NOT NULL,                      -- the absence, in words, with counts (evidence snapshot)
  evidence_deadline timestamptz NOT NULL,               -- resolved_at + grace: evidence recorded later is "late"
  detected_at       timestamptz NOT NULL DEFAULT now(),
  last_evaluated_at timestamptz NOT NULL DEFAULT now(),
  reviewed_by       bigint REFERENCES app_user,
  reviewed_at       timestamptz,
  review_note       text,
  CONSTRAINT uq_alert_per_complaint_rule UNIQUE (complaint_id, rule_code),     -- BR-34: no duplicate detections
  CONSTRAINT ck_alert_review_complete CHECK (
    (status IN ('CONFIRMED', 'DISMISSED')) = (reviewed_at IS NOT NULL)
    AND (status NOT IN ('CONFIRMED', 'DISMISSED')
         OR (reviewed_by IS NOT NULL AND length(btrim(coalesce(review_note, ''))) >= 10)))
);

CREATE TABLE shadow_entry_alert_event (               -- BR-36: append-only lifecycle history
  event_id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  alert_id    bigint NOT NULL REFERENCES shadow_entry_alert ON DELETE CASCADE,
  from_status text,
  to_status   text NOT NULL,
  actor_id    bigint REFERENCES app_user,               -- NULL = the scan itself
  note        text,
  occurred_at timestamptz NOT NULL DEFAULT now()
);

-- Holds are first-class facts with provenance (BR-23). An invoice is on hold while any hold is unreleased.
CREATE TABLE invoice_hold (
  hold_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  invoice_id   bigint NOT NULL REFERENCES invoice,
  reason       text NOT NULL CHECK (reason IN ('SHADOW_ENTRY', 'INCIDENT')),
  alert_id     bigint REFERENCES shadow_entry_alert,
  incident_id  bigint REFERENCES incident,
  placed_at    timestamptz NOT NULL DEFAULT now(),
  released_at  timestamptz,
  released_by  bigint REFERENCES app_user,
  release_note text,
  CONSTRAINT ck_hold_has_exactly_one_source CHECK (
       (reason = 'SHADOW_ENTRY' AND alert_id IS NOT NULL AND incident_id IS NULL)
    OR (reason = 'INCIDENT'     AND incident_id IS NOT NULL AND alert_id IS NULL)),
  CONSTRAINT ck_hold_release_complete CHECK ((released_at IS NULL) = (release_note IS NULL))
);
CREATE UNIQUE INDEX uq_hold_invoice_alert    ON invoice_hold (invoice_id, alert_id)    WHERE alert_id IS NOT NULL;
CREATE UNIQUE INDEX uq_hold_invoice_incident ON invoice_hold (invoice_id, incident_id) WHERE incident_id IS NOT NULL;

-- =============================================================================================
-- Law as data, and the audit trail
-- =============================================================================================
CREATE TABLE rule_parameter (
  param_key     text PRIMARY KEY CHECK (param_key ~ '^[a-z0-9_]+$'),
  value         numeric NOT NULL,
  unit          text NOT NULL,
  description   text NOT NULL,
  legal_ref     text NOT NULL,
  is_assumption boolean NOT NULL DEFAULT false,       -- shown as such in the admin screen (PROJECT_SPEC section 6)
  updated_by    bigint REFERENCES app_user,
  updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE legal_clause (                           -- titles and legal references for the entry-gate checklist
  clause_code text PRIMARY KEY CHECK (clause_code = upper(clause_code)),
  title       text NOT NULL,
  legal_ref   text NOT NULL,
  sort_order  smallint NOT NULL UNIQUE
);

CREATE TABLE audit_log (                              -- append-only (trigger + revoked privileges)
  log_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  occurred_at   timestamptz NOT NULL DEFAULT now(),
  actor_user_id bigint,                               -- deliberately no FK: history must outlive users
  action        text NOT NULL CHECK (action IN ('INSERT', 'UPDATE', 'DELETE')),
  table_name    text NOT NULL,
  row_pk        text NOT NULL,
  old_data      jsonb,
  new_data      jsonb
);

-- =============================================================================================
-- Indexes (PostgreSQL does not index foreign-key columns automatically)
-- =============================================================================================
CREATE INDEX ix_manhole_ulb              ON manhole (ulb_id);
CREATE INDEX ix_manhole_code_prefix      ON manhole (code text_pattern_ops);
CREATE INDEX ix_worker_contractor        ON worker (contractor_id);
CREATE INDEX ix_worker_namaste_prefix    ON worker (namaste_id text_pattern_ops);
CREATE INDEX ix_worker_name_prefix       ON worker (lower(full_name) text_pattern_ops);
CREATE INDEX ix_user_session_user        ON user_session (user_id);
CREATE INDEX ix_complaint_manhole        ON complaint (manhole_id);
CREATE INDEX ix_complaint_status_raised  ON complaint (status, raised_at DESC);
CREATE INDEX ix_complaint_resolved       ON complaint (resolved_at) WHERE status = 'RESOLVED';   -- SE1 population
CREATE INDEX ix_job_complaint            ON job (complaint_id);
CREATE INDEX ix_job_contractor           ON job (contractor_id);
CREATE INDEX ix_deployment_job_outcome   ON machine_deployment (job_id, outcome);               -- SE1 anti-join
CREATE INDEX ix_permit_job               ON entry_permit (job_id, status);                      -- SE1 anti-join
CREATE INDEX ix_permit_supervisor        ON entry_permit (supervisor_id);
CREATE INDEX ix_crew_worker              ON permit_crew (worker_id);
CREATE INDEX ix_gear_issue_permit_worker ON gear_issue (permit_id, worker_id);                  -- gear division
CREATE INDEX ix_reading_permit_depth     ON gas_reading (permit_id, depth_level, taken_at DESC);-- latest reading per depth
CREATE INDEX ix_entry_permit_worker      ON entry_log (permit_id, worker_id);
CREATE INDEX ix_incident_contractor      ON incident (contractor_id, occurred_at);
CREATE INDEX ix_invoice_job              ON invoice (job_id);
CREATE INDEX ix_hold_active              ON invoice_hold (invoice_id) WHERE released_at IS NULL;
CREATE INDEX ix_alert_status             ON shadow_entry_alert (status, detected_at DESC);
CREATE INDEX ix_alert_event_alert        ON shadow_entry_alert_event (alert_id, occurred_at);
CREATE INDEX ix_audit_row                ON audit_log (table_name, row_pk, occurred_at DESC);
CREATE INDEX ix_audit_time               ON audit_log (occurred_at DESC);

-- =============================================================================================
-- Table comments (visible in psql \d+ and used by DATABASE_DESIGN.md)
-- =============================================================================================
COMMENT ON TABLE role                  IS 'The six application roles.';
COMMENT ON TABLE app_user              IS 'Login accounts; contractor_id / worker_id scope CONTRACTOR and WORKER users.';
COMMENT ON TABLE user_session          IS 'Opaque server-side sessions; only a SHA-256 of the cookie token is stored.';
COMMENT ON TABLE ulb                   IS 'Urban local body / municipal zone.';
COMMENT ON TABLE manhole               IS 'A sewer or septic access point.';
COMMENT ON TABLE resolution_type       IS 'How a complaint was resolved and whether that resolution must leave evidence.';
COMMENT ON TABLE complaint             IS 'Blockage complaint against a manhole.';
COMMENT ON TABLE contractor            IS 'Licensed contractor; status ACTIVE/SUSPENDED/BLACKLISTED.';
COMMENT ON TABLE worker                IS 'Sanitation worker registered under NAMASTE.';
COMMENT ON TABLE machine               IS 'Mechanised cleaning equipment.';
COMMENT ON TABLE job                   IS 'Work order for a complaint, assigned to a contractor.';
COMMENT ON TABLE machine_deployment    IS 'A machine used on a job and its outcome (clearance evidence).';
COMMENT ON TABLE mechanisation_waiver  IS 'Written reason, approved by the RSA, why a machine cannot do the job.';
COMMENT ON TABLE entry_permit          IS 'Permit to enter; AUTHORISED only through the clause gate.';
COMMENT ON TABLE permit_crew           IS 'Crew of a permit with exactly one role per worker.';
COMMENT ON TABLE gear_item             IS 'Protective-gear catalogue; statutory items are mandatory for entrants.';
COMMENT ON TABLE gear_issue            IS 'Gear issued to a crew member for a permit, with serial number.';
COMMENT ON TABLE gas_detector          IS 'Gas detector with calibration expiry.';
COMMENT ON TABLE gas_reading           IS 'Atmosphere reading at a depth level (append-only).';
COMMENT ON TABLE entry_log             IS 'A worker''s time underground; overlaps are excluded.';
COMMENT ON TABLE incident              IS 'Fatality, disability or near miss.';
COMMENT ON TABLE compensation_case     IS 'Compensation owed for an incident, with deadline and payments.';
COMMENT ON TABLE invoice               IS 'Contractor invoice for a job.';
COMMENT ON TABLE invoice_hold          IS 'Reason an invoice cannot be approved or paid, with provenance.';
COMMENT ON TABLE detection_rule        IS 'Catalogue of absence-detection rules (SE1, SE2); can be disabled.';
COMMENT ON TABLE shadow_entry_alert    IS 'Persisted suspicion that an entry happened unrecorded.';
COMMENT ON TABLE shadow_entry_alert_event IS 'Append-only lifecycle history of alerts.';
COMMENT ON TABLE rule_parameter        IS 'Statutory thresholds and policy numbers as editable, audited data.';
COMMENT ON TABLE legal_clause          IS 'Titles and legal references for each entry-gate clause.';
COMMENT ON TABLE audit_log             IS 'Append-only record of every change to key tables.';
