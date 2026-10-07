-- 0013_temporal_evidence_invoice_serialization.sql
-- Preserve the server receipt time of a machine outcome separately from its field/event end time (BR-31),
-- and serialize invoice decisions with source-linked hold placement (BR-23, BR-35).

-- `recorded_at` is when the deployment row first arrived. It cannot establish when an unfinished deployment
-- acquired an outcome. Backfill from the last append-only audit event that actually set the outcome (including a
-- finalized INSERT). audit_log.occurred_at is PostgreSQL's transaction timestamp, not commit time; this is the best
-- database-side historical evidence available, but legacy rows cannot prove the exact finalization/commit instant.
-- If an old row has no such event, leave it NULL: its original row receipt is not proof that a later outcome was known.
ALTER TABLE machine_deployment ADD COLUMN outcome_recorded_at timestamptz;

WITH outcome_events AS (
  SELECT a.row_pk,
         a.occurred_at,
         a.new_data ->> 'outcome' AS outcome,
         a.log_id
    FROM audit_log a
   WHERE a.table_name = 'machine_deployment'
     AND a.new_data ->> 'outcome' IS NOT NULL
     AND (a.action = 'INSERT'
       OR (a.action = 'UPDATE' AND (a.old_data ->> 'outcome') IS DISTINCT FROM (a.new_data ->> 'outcome')))
), last_outcome_event AS (
  SELECT DISTINCT ON (row_pk) row_pk, occurred_at, outcome
    FROM outcome_events
   ORDER BY row_pk, occurred_at DESC, log_id DESC
)
UPDATE machine_deployment d
   SET outcome_recorded_at = e.occurred_at
  FROM last_outcome_event e
 WHERE e.row_pk = d.deploy_id::text
   AND e.outcome = d.outcome;

ALTER TABLE machine_deployment
  ADD CONSTRAINT ck_deployment_unfinished_has_no_outcome_receipt
  CHECK (outcome IS NOT NULL OR outcome_recorded_at IS NULL);

COMMENT ON COLUMN machine_deployment.recorded_at IS
  'Server receipt time for the deployment row; not proof of when a later outcome was recorded.';
COMMENT ON COLUMN machine_deployment.outcome_recorded_at IS
  'Server receipt time of the final outcome. NULL for unfinished rows and legacy outcomes with no auditable finalization event.';

-- The SE1 anti-join looks for a timely CLEARED outcome per job. Keep that lookup bounded as deployment history grows.
CREATE INDEX ix_deployment_cleared_receipt
  ON machine_deployment (job_id, outcome_recorded_at)
  WHERE outcome = 'CLEARED' AND outcome_recorded_at IS NOT NULL;

CREATE FUNCTION machine_deployment_outcome_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.outcome IS NULL THEN
      NEW.outcome_recorded_at := NULL;
    ELSE
      -- Ignore every supplied timestamp. The application role can only receive a server clock value here.
      NEW.outcome_recorded_at := clock_timestamp();
    END IF;
    RETURN NEW;
  END IF;

  IF OLD.outcome IS NOT NULL
     AND (NEW.outcome IS DISTINCT FROM OLD.outcome OR NEW.ended_at IS DISTINCT FROM OLD.ended_at) THEN
    RAISE EXCEPTION 'A finalized machine outcome and its event time are immutable; record a new deployment to correct them'
      USING ERRCODE = 'ZE003';
  END IF;

  IF NEW.outcome IS DISTINCT FROM OLD.outcome THEN
    IF NEW.outcome IS NULL THEN
      NEW.outcome_recorded_at := NULL;
    ELSE
      NEW.outcome_recorded_at := clock_timestamp();
    END IF;
  ELSIF NEW.outcome_recorded_at IS DISTINCT FROM OLD.outcome_recorded_at THEN
    RAISE EXCEPTION 'A machine outcome receipt time is server-assigned and cannot be changed'
      USING ERRCODE = 'ZE003';
  END IF;

  RETURN NEW;
END $$;
CREATE TRIGGER trg_machine_deployment_outcome_guard
  BEFORE INSERT OR UPDATE ON machine_deployment
  FOR EACH ROW EXECUTE FUNCTION machine_deployment_outcome_guard();

-- A shared complaint-row lock orders source creation against invoice submission. Sources lock before insertion;
-- invoices lock before insertion, then their existing auto-hold trigger sees committed sources. If a source wins,
-- it sees the newly committed invoice and holds it. This also covers invoices created after an alert or incident.
CREATE FUNCTION invoice_complaint_lock() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  v_complaint_id bigint;
  v_contractor_id bigint;
BEGIN
  SELECT j.complaint_id, j.contractor_id INTO v_complaint_id, v_contractor_id
    FROM job j WHERE j.job_id = NEW.job_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Job % does not exist', NEW.job_id USING ERRCODE = 'ZE004';
  END IF;

  IF session_user = 'ze_app'
     AND NOT (app_role() IN ('ADMIN', 'ENGINEER')
          OR (app_role() = 'CONTRACTOR' AND app_contractor_id() = v_contractor_id)) THEN
    RAISE EXCEPTION 'The current role may not submit an invoice for this job' USING ERRCODE = 'ZE006';
  END IF;

  PERFORM 1 FROM complaint WHERE complaint_id = v_complaint_id FOR UPDATE;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_invoice_complaint_lock
  BEFORE INSERT ON invoice
  FOR EACH ROW EXECUTE FUNCTION invoice_complaint_lock();

CREATE FUNCTION alert_complaint_lock() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  PERFORM 1 FROM complaint WHERE complaint_id = NEW.complaint_id FOR UPDATE;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_alert_complaint_lock
  BEFORE INSERT ON shadow_entry_alert
  FOR EACH ROW EXECUTE FUNCTION alert_complaint_lock();

CREATE FUNCTION incident_complaint_lock() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  v_complaint_id bigint;
BEGIN
  IF NEW.job_id IS NOT NULL THEN
    SELECT complaint_id INTO v_complaint_id FROM job WHERE job_id = NEW.job_id;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Job % does not exist', NEW.job_id USING ERRCODE = 'ZE004';
    END IF;
    PERFORM 1 FROM complaint WHERE complaint_id = v_complaint_id FOR UPDATE;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_incident_complaint_lock
  BEFORE INSERT ON incident
  FOR EACH ROW EXECUTE FUNCTION incident_complaint_lock();

-- Hold placement and invoice approval/payment share the invoice row lock. The trigger waits for any in-flight
-- invoice decision, then re-reads the committed status. A payment that wins leaves a historical PAID invoice
-- without a hold; a hold that wins makes approval/payment observe the active hold and fail.
CREATE FUNCTION invoice_hold_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  v_status text;
BEGIN
  SELECT status INTO v_status FROM invoice WHERE invoice_id = NEW.invoice_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Invoice % does not exist', NEW.invoice_id USING ERRCODE = 'ZE004';
  END IF;
  IF v_status NOT IN ('SUBMITTED', 'APPROVED') THEN
    RETURN NULL; -- a paid/rejected invoice is historical and is never retroactively held
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_invoice_hold_guard
  BEFORE INSERT ON invoice_hold
  FOR EACH ROW EXECUTE FUNCTION invoice_hold_guard();

-- Keep server-owned outcome receipts out of direct runtime writes. The BEFORE trigger also ignores any attempted
-- INSERT value, but column grants make the boundary explicit and keep `recorded_at` server-assigned as well.
REVOKE INSERT ON machine_deployment FROM ze_app;
GRANT INSERT (job_id, machine_id, started_at, ended_at, outcome, recorded_by) ON machine_deployment TO ze_app;
REVOKE UPDATE ON machine_deployment FROM ze_app;
GRANT UPDATE (ended_at, outcome) ON machine_deployment TO ze_app;

-- The lock functions above are trigger-only. A trigger does not require its caller to have EXECUTE permission on the
-- trigger function; no extra callable SECURITY DEFINER lock helper is exposed to the runtime role.
REVOKE ALL ON FUNCTION invoice_complaint_lock() FROM PUBLIC, ze_app;
REVOKE ALL ON FUNCTION alert_complaint_lock() FROM PUBLIC, ze_app;
REVOKE ALL ON FUNCTION incident_complaint_lock() FROM PUBLIC, ze_app;
REVOKE ALL ON FUNCTION invoice_hold_guard() FROM PUBLIC, ze_app;

-- SE1 must use the time the clearance result was actually finalized, not the earlier deployment-row receipt.
CREATE OR REPLACE VIEW v_shadow_se1 WITH (security_invoker = true) AS
WITH g AS MATERIALIZED (SELECT rule_num('shadow_grace_hours')::int AS hours,
                               make_interval(hours => rule_num('shadow_grace_hours')::int) AS grace)
SELECT c.complaint_id,
       'SE1_NO_CLEARANCE_EVIDENCE'::text            AS rule_code,
       c.manhole_id, m.ulb_id,
       lj.contractor_id, lj.job_id,
       c.resolved_at                                AS anchor_at,
       c.resolved_at + g.grace                      AS evidence_deadline,
       (st.cleared > 0 OR st.logged_permits > 0)    AS late_evidence_exists,
       format('Resolved %s as %s, but no clearance evidence was recorded within %s h. Jobs: %s. Machine deployments: '
              '%s cleared, %s failed, %s unfinished. Closed permits with a logged entry: %s.',
              to_char(local_ts(c.resolved_at), 'YYYY-MM-DD HH24:MI'), c.resolution_code, g.hours,
              st.jobs, st.cleared, st.failed, st.unfinished, st.logged_permits) AS reason
FROM complaint c
CROSS JOIN g
JOIN manhole m          ON m.manhole_id = c.manhole_id
JOIN resolution_type rt ON rt.code = c.resolution_code AND rt.requires_evidence
LEFT JOIN LATERAL (SELECT j.job_id, j.contractor_id FROM job j WHERE j.complaint_id = c.complaint_id
                   ORDER BY j.created_at DESC, j.job_id DESC LIMIT 1) lj ON true
CROSS JOIN LATERAL (
  SELECT (SELECT count(*) FROM job j WHERE j.complaint_id = c.complaint_id) AS jobs,
         (SELECT count(*) FROM job j JOIN machine_deployment d ON d.job_id = j.job_id
           WHERE j.complaint_id = c.complaint_id AND d.outcome = 'CLEARED') AS cleared,
         (SELECT count(*) FROM job j JOIN machine_deployment d ON d.job_id = j.job_id
           WHERE j.complaint_id = c.complaint_id AND d.outcome = 'FAILED')  AS failed,
         (SELECT count(*) FROM job j JOIN machine_deployment d ON d.job_id = j.job_id
           WHERE j.complaint_id = c.complaint_id AND d.outcome IS NULL)     AS unfinished,
         (SELECT count(*) FROM job j JOIN entry_permit p ON p.job_id = j.job_id
           WHERE j.complaint_id = c.complaint_id AND p.status = 'CLOSED' AND p.authorised_at IS NOT NULL
             AND EXISTS (SELECT 1 FROM entry_log e WHERE e.permit_id = p.permit_id)) AS logged_permits) st
WHERE c.status = 'RESOLVED'
  AND NOT EXISTS (
        SELECT 1 FROM job j JOIN machine_deployment d ON d.job_id = j.job_id
         WHERE j.complaint_id = c.complaint_id AND d.outcome = 'CLEARED'
           AND d.outcome_recorded_at IS NOT NULL
           AND d.outcome_recorded_at <= c.resolved_at + g.grace)
  AND NOT EXISTS (
        SELECT 1 FROM job j JOIN entry_permit p ON p.job_id = j.job_id
         WHERE j.complaint_id = c.complaint_id AND p.status = 'CLOSED' AND p.authorised_at IS NOT NULL
           AND p.ended_at <= c.resolved_at + g.grace
           AND EXISTS (SELECT 1 FROM entry_log e
                        WHERE e.permit_id = p.permit_id AND e.recorded_at <= c.resolved_at + g.grace));

COMMENT ON VIEW v_shadow_se1 IS
  'SE1 clearance evidence is timely only when its final outcome receipt or permit/entry record is within the complaint grace window.';

-- Recreate dependent views so they retain the original view's security-invoker semantics after replacement.
CREATE OR REPLACE VIEW v_shadow_candidate WITH (security_invoker = true) AS
SELECT * FROM v_shadow_se1 UNION ALL SELECT * FROM v_shadow_se2;

CREATE OR REPLACE VIEW v_suspected_shadow_entry WITH (security_invoker = true) AS
SELECT v.complaint_id, v.rule_code, r.title AS rule_title, v.manhole_id, v.ulb_id, v.contractor_id, v.job_id,
       v.anchor_at, v.evidence_deadline, now() >= v.evidence_deadline AS past_grace,
       v.late_evidence_exists, v.reason, a.alert_id, a.status AS alert_status
FROM v_shadow_candidate v
JOIN detection_rule r ON r.rule_code = v.rule_code AND r.enabled
LEFT JOIN shadow_entry_alert a ON a.complaint_id = v.complaint_id AND a.rule_code = v.rule_code;

COMMENT ON VIEW v_suspected_shadow_entry IS
  'Anti-join detection by absence: expected evidence missing for resolved complaints (SE1) and unlogged entrants (SE2).';

-- The common complaint/invoice row locks make the source-vs-payment protocol linearizable only when
-- each post-wait statement can take a fresh READ COMMITTED snapshot. Under REPEATABLE READ, a waiter
-- can acquire an unchanged complaint/invoice row while still seeing pre-wait alert/incident/hold rows.
-- Fail these writes with a retryable serialization error instead of accepting stale decisions.
CREATE FUNCTION require_read_committed_financialrace() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  IF current_setting('transaction_isolation') <> 'read committed' THEN
    RAISE EXCEPTION 'Invoice and source serialization requires READ COMMITTED isolation; retry with READ COMMITTED'
      USING ERRCODE = '40001';
  END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION require_read_committed_financialrace() FROM PUBLIC, ze_app;
COMMENT ON FUNCTION require_read_committed_financialrace() IS
  'Guard for the invoice/source row-lock protocol: READ COMMITTED is required for post-wait statements to see committed holds; other isolation levels fail with retryable SQLSTATE 40001.';

CREATE TRIGGER trg_00_invoice_insert_isolation
  BEFORE INSERT ON invoice FOR EACH ROW EXECUTE FUNCTION require_read_committed_financialrace();
CREATE TRIGGER trg_00_invoice_status_isolation
  BEFORE UPDATE OF status ON invoice FOR EACH ROW EXECUTE FUNCTION require_read_committed_financialrace();
CREATE TRIGGER trg_00_alert_insert_isolation
  BEFORE INSERT ON shadow_entry_alert FOR EACH ROW EXECUTE FUNCTION require_read_committed_financialrace();
CREATE TRIGGER trg_00_incident_insert_isolation
  BEFORE INSERT ON incident FOR EACH ROW EXECUTE FUNCTION require_read_committed_financialrace();
CREATE TRIGGER trg_00_invoice_hold_insert_isolation
  BEFORE INSERT ON invoice_hold FOR EACH ROW EXECUTE FUNCTION require_read_committed_financialrace();
