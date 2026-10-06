-- 0006_consequences.sql
-- What the database does when something goes wrong or money moves: the atomic fatality transaction,
-- invoice holds with provenance, compensation payments, and the report views.
-- All views are security_invoker: they run with the CALLER's privileges and row-level security
-- (a default view would run as its owner and silently bypass RLS). Requires PostgreSQL 15+.

-- ---------------------------------------------------------------------------------------------
-- Invoices. Status moves SUBMITTED -> APPROVED -> PAID (or REJECTED). An invoice with an unreleased
-- hold can be neither approved nor paid (BR-23).
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION invoice_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_holds text;
BEGIN
  IF NEW.job_id <> OLD.job_id OR NEW.invoice_no <> OLD.invoice_no OR NEW.amount_inr <> OLD.amount_inr THEN
    RAISE EXCEPTION 'An invoice''s job, number and amount are fixed once submitted' USING ERRCODE = 'ZE003';
  END IF;
  IF NEW.status = OLD.status THEN RETURN NEW; END IF;

  IF NOT ((OLD.status = 'SUBMITTED' AND NEW.status IN ('APPROVED', 'REJECTED'))
       OR (OLD.status = 'APPROVED'  AND NEW.status IN ('PAID', 'REJECTED'))) THEN
    RAISE EXCEPTION 'An invoice cannot change from % to %', OLD.status, NEW.status USING ERRCODE = 'ZE003';
  END IF;

  IF NEW.status IN ('APPROVED', 'PAID') THEN
    SELECT string_agg(DISTINCT reason, ', ') INTO v_holds
      FROM invoice_hold WHERE invoice_id = NEW.invoice_id AND released_at IS NULL;
    IF v_holds IS NOT NULL THEN
      RAISE EXCEPTION 'Invoice % is on hold (%) and cannot be %', NEW.invoice_no, v_holds, lower(NEW.status)
        USING ERRCODE = 'ZE003';
    END IF;
  END IF;

  IF NEW.status IN ('APPROVED', 'REJECTED') THEN
    NEW.decided_by := COALESCE(NEW.decided_by, app_user_id());
    NEW.decided_at := COALESCE(NEW.decided_at, now());
  ELSIF NEW.status = 'PAID' THEN
    NEW.paid_at := COALESCE(NEW.paid_at, now());
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_invoice_guard BEFORE UPDATE ON invoice
  FOR EACH ROW EXECUTE FUNCTION invoice_guard();

-- An invoice submitted AFTER an alert or fatality on its job is held from the start.
CREATE FUNCTION invoice_auto_hold() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO invoice_hold (invoice_id, reason, alert_id)
  SELECT NEW.invoice_id, 'SHADOW_ENTRY', a.alert_id
    FROM job j JOIN shadow_entry_alert a ON a.complaint_id = j.complaint_id
   WHERE j.job_id = NEW.job_id AND a.status <> 'DISMISSED';
  INSERT INTO invoice_hold (invoice_id, reason, incident_id)
  SELECT NEW.invoice_id, 'INCIDENT', i.incident_id
    FROM incident i
   WHERE i.job_id = NEW.job_id AND i.incident_type IN ('FATALITY', 'DISABILITY');
  RETURN NULL;
END $$;
CREATE TRIGGER trg_invoice_auto_hold AFTER INSERT ON invoice
  FOR EACH ROW EXECUTE FUNCTION invoice_auto_hold();

-- A hold is released only by its source. An alert hold goes when its alert is dismissed (0007); an incident
-- hold is released here, by a person, with a written note.
CREATE FUNCTION release_invoice_hold(p_hold_id bigint, p_actor_id bigint, p_note text) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
  h invoice_hold%ROWTYPE;
BEGIN
  SELECT * INTO h FROM invoice_hold WHERE hold_id = p_hold_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Hold % does not exist', p_hold_id USING ERRCODE = 'ZE004';
  END IF;
  IF h.released_at IS NOT NULL THEN
    RAISE EXCEPTION 'Hold % was already released', p_hold_id USING ERRCODE = 'ZE003';
  END IF;
  IF h.reason = 'SHADOW_ENTRY' THEN
    RAISE EXCEPTION 'A shadow-entry hold is released by dismissing its alert, not by hand' USING ERRCODE = 'ZE003';
  END IF;
  IF length(btrim(COALESCE(p_note, ''))) < 10 THEN
    RAISE EXCEPTION 'Releasing a hold needs a written note of at least 10 characters' USING ERRCODE = 'ZE002';
  END IF;
  UPDATE invoice_hold SET released_at = now(), released_by = p_actor_id, release_note = btrim(p_note)
   WHERE hold_id = p_hold_id;
END $$;

-- ---------------------------------------------------------------------------------------------
-- Compensation payments. Row-locked so two clerks paying at once cannot overpay.
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION record_compensation_payment(p_case_id bigint, p_amount numeric, p_at timestamptz DEFAULT now())
RETURNS compensation_case LANGUAGE plpgsql AS $$
DECLARE
  c      compensation_case%ROWTYPE;
  v_paid numeric;
BEGIN
  SELECT * INTO c FROM compensation_case WHERE case_id = p_case_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Compensation case % does not exist', p_case_id USING ERRCODE = 'ZE004';
  END IF;
  IF p_amount IS NULL OR p_amount <= 0 THEN
    RAISE EXCEPTION 'A payment must be a positive amount' USING ERRCODE = 'ZE002';
  END IF;
  v_paid := c.amount_paid + p_amount;
  IF v_paid > c.amount_due THEN
    RAISE EXCEPTION 'A payment of % would exceed the amount due (% still outstanding)', p_amount, c.amount_due - c.amount_paid
      USING ERRCODE = 'ZE002';
  END IF;
  UPDATE compensation_case
     SET amount_paid = v_paid,
         status  = CASE WHEN v_paid = amount_due THEN 'PAID' ELSE 'PARTIAL' END,
         paid_at = CASE WHEN v_paid = amount_due THEN p_at END
   WHERE case_id = p_case_id
  RETURNING * INTO c;
  RETURN c;
END $$;

-- ---------------------------------------------------------------------------------------------
-- record_incident(): the consequence transaction (BR-20, BR-21). ONE procedure call = ONE atomic unit:
-- incident, compensation case with deadline, contractor sanction, stop-work on the job's permits, and
-- invoice holds either all happen or none do. A failure anywhere (for example a mis-set compensation
-- parameter violating a CHECK after the incident row is written) rolls the whole thing back.
-- Call it with  CALL record_incident('FATALITY', ..., NULL);  the INOUT parameter returns the new id.
-- ---------------------------------------------------------------------------------------------
CREATE PROCEDURE record_incident(
  p_type        text,
  p_occurred_at timestamptz,
  p_worker_id   bigint,
  p_manhole_id  bigint,
  p_description text,
  p_recorded_by bigint,
  p_permit_id   bigint DEFAULT NULL,
  p_job_id      bigint DEFAULT NULL,
  INOUT p_incident_id bigint DEFAULT NULL)
LANGUAGE plpgsql AS $$
DECLARE
  v_contractor bigint;
  v_job        bigint := p_job_id;
  v_permit_job bigint;
  v_role       text;
  v_amount     numeric;
BEGIN
  IF p_type NOT IN ('FATALITY', 'DISABILITY', 'NEAR_MISS') THEN
    RAISE EXCEPTION 'Unknown incident type %', p_type USING ERRCODE = 'ZE002';
  END IF;
  SELECT r.name INTO v_role FROM app_user u JOIN role r ON r.role_id = u.role_id
   WHERE u.user_id = p_recorded_by AND u.is_active;
  IF v_role IS NULL OR v_role NOT IN ('ADMIN', 'ENGINEER', 'SUPERVISOR') THEN
    RAISE EXCEPTION 'Only an active ADMIN, ENGINEER or SUPERVISOR may record an incident' USING ERRCODE = 'ZE006';
  END IF;
  SELECT contractor_id INTO v_contractor FROM worker WHERE worker_id = p_worker_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Worker % does not exist', p_worker_id USING ERRCODE = 'ZE004';
  END IF;
  IF p_permit_id IS NOT NULL THEN
    SELECT job_id INTO v_permit_job FROM entry_permit WHERE permit_id = p_permit_id;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Permit % does not exist', p_permit_id USING ERRCODE = 'ZE004';
    END IF;
    IF v_job IS NOT NULL AND v_job <> v_permit_job THEN
      RAISE EXCEPTION 'Permit % belongs to job %, not job %', p_permit_id, v_permit_job, v_job USING ERRCODE = 'ZE002';
    END IF;
    v_job := v_permit_job;
  END IF;

  INSERT INTO incident (incident_type, occurred_at, manhole_id, worker_id, contractor_id, job_id, permit_id,
                        description, recorded_by)
  VALUES (p_type, p_occurred_at, p_manhole_id, p_worker_id, v_contractor, v_job, p_permit_id,
          p_description, p_recorded_by)
  RETURNING incident_id INTO p_incident_id;

  IF p_type = 'NEAR_MISS' THEN RETURN; END IF;               -- recorded, no case, no sanction

  v_amount := CASE p_type WHEN 'FATALITY' THEN rule_num('compensation_fatality_inr')
                          ELSE rule_num('compensation_disability_inr') END;
  INSERT INTO compensation_case (incident_id, amount_due, due_by)
  VALUES (p_incident_id, v_amount, local_date(p_occurred_at) + rule_num('compensation_due_days')::int);

  UPDATE contractor
     SET status = CASE p_type WHEN 'FATALITY' THEN 'BLACKLISTED' ELSE 'SUSPENDED' END
   WHERE contractor_id = v_contractor AND status <> 'BLACKLISTED' AND (p_type = 'FATALITY' OR status = 'ACTIVE');

  IF v_job IS NOT NULL THEN
    UPDATE entry_permit SET status = 'ABORTED',
           end_reason = format('Stop-work: %s recorded (incident #%s)', lower(p_type), p_incident_id)
     WHERE job_id = v_job AND status = 'AUTHORISED';
    UPDATE entry_permit SET status = 'CANCELLED',
           end_reason = format('Cancelled: %s recorded (incident #%s)', lower(p_type), p_incident_id)
     WHERE job_id = v_job AND status = 'DRAFT';
    INSERT INTO invoice_hold (invoice_id, reason, incident_id)
    SELECT invoice_id, 'INCIDENT', p_incident_id FROM invoice
     WHERE job_id = v_job AND status IN ('SUBMITTED', 'APPROVED')
    ON CONFLICT DO NOTHING;
  END IF;
END $$;

-- ---------------------------------------------------------------------------------------------
-- Views
-- ---------------------------------------------------------------------------------------------
-- Live readiness of every DRAFT permit: which clauses fail right now.
CREATE VIEW v_permit_compliance WITH (security_invoker = true) AS
SELECT p.permit_id, p.job_id, p.supervisor_id,
       count(*)                                   AS clauses_total,
       count(*) FILTER (WHERE NOT c.passed)       AS clauses_failed,
       bool_and(c.passed)                         AS ready_to_authorise,
       string_agg(c.clause_code, ', ' ORDER BY c.clause_code) FILTER (WHERE NOT c.passed) AS failing_clauses
FROM entry_permit p
CROSS JOIN LATERAL permit_clause_check(p.permit_id, now()) AS c
WHERE p.status = 'DRAFT'
GROUP BY p.permit_id;

CREATE VIEW v_compensation_overdue WITH (security_invoker = true) AS
SELECT cc.case_id, cc.incident_id, i.incident_type, i.occurred_at, i.worker_id, i.contractor_id,
       ct.name AS contractor_name, m.ulb_id,
       cc.amount_due, cc.amount_paid, cc.amount_due - cc.amount_paid AS amount_outstanding,
       cc.due_by, local_date(now()) - cc.due_by AS days_overdue
FROM compensation_case cc
JOIN incident   i  ON i.incident_id   = cc.incident_id
JOIN contractor ct ON ct.contractor_id = i.contractor_id
JOIN manhole    m  ON m.manhole_id     = i.manhole_id
WHERE cc.status <> 'PAID' AND cc.due_by < local_date(now());

CREATE VIEW v_invoice_status WITH (security_invoker = true) AS
SELECT i.invoice_id, i.job_id, j.contractor_id, i.invoice_no, i.amount_inr, i.status, i.submitted_at,
       EXISTS (SELECT 1 FROM invoice_hold h WHERE h.invoice_id = i.invoice_id AND h.released_at IS NULL) AS on_hold,
       (SELECT string_agg(DISTINCT h.reason, ', ') FROM invoice_hold h
         WHERE h.invoice_id = i.invoice_id AND h.released_at IS NULL) AS hold_reasons
FROM invoice i JOIN job j ON j.job_id = i.job_id;

-- Contractor risk score = 10 x deaths + 5 x disabilities + 3 x confirmed shadow entries + 1 x open alerts
-- + 2 x overdue compensation cases. The weights are illustrative (PROJECT_SPEC assumption A-10).
CREATE VIEW v_contractor_risk WITH (security_invoker = true) AS
SELECT c.contractor_id, c.name, c.status,
       COALESCE(i.fatalities, 0)    AS fatalities,
       COALESCE(i.disabilities, 0)  AS disabilities,
       COALESCE(a.confirmed, 0)     AS confirmed_alerts,
       COALESCE(a.open_alerts, 0)   AS open_alerts,
       COALESCE(o.overdue, 0)       AS overdue_cases,
       10 * COALESCE(i.fatalities, 0) + 5 * COALESCE(i.disabilities, 0) + 3 * COALESCE(a.confirmed, 0)
         + COALESCE(a.open_alerts, 0) + 2 * COALESCE(o.overdue, 0) AS risk_score
FROM contractor c
LEFT JOIN (SELECT contractor_id,
                  count(*) FILTER (WHERE incident_type = 'FATALITY')   AS fatalities,
                  count(*) FILTER (WHERE incident_type = 'DISABILITY') AS disabilities
           FROM incident GROUP BY contractor_id) i ON i.contractor_id = c.contractor_id
LEFT JOIN (SELECT contractor_id,
                  count(*) FILTER (WHERE status = 'CONFIRMED')                     AS confirmed,
                  count(*) FILTER (WHERE status IN ('OPEN', 'EVIDENCE_RECEIVED'))  AS open_alerts
           FROM shadow_entry_alert WHERE contractor_id IS NOT NULL GROUP BY contractor_id) a ON a.contractor_id = c.contractor_id
LEFT JOIN (SELECT contractor_id, count(*) AS overdue FROM v_compensation_overdue GROUP BY contractor_id) o
       ON o.contractor_id = c.contractor_id;

-- Zero-entry rate per ULB per year: the share of (non-cancelled) jobs that stayed mechanised.
CREATE VIEW v_ulb_year_kpi WITH (security_invoker = true) AS
SELECT u.ulb_id, u.name AS ulb_name,
       extract(year FROM local_ts(j.created_at))::int AS year,
       count(*)                                              AS jobs,
       count(*) FILTER (WHERE j.method = 'MECHANISED')       AS mechanised_jobs,
       count(*) FILTER (WHERE j.method = 'MANUAL_EXCEPTION') AS manual_exception_jobs,
       round(100.0 * count(*) FILTER (WHERE j.method = 'MECHANISED') / count(*), 1) AS zero_entry_rate_pct
FROM job j
JOIN complaint c ON c.complaint_id = j.complaint_id
JOIN manhole   m ON m.manhole_id   = c.manhole_id
JOIN ulb       u ON u.ulb_id       = m.ulb_id
WHERE j.status <> 'CANCELLED'
GROUP BY u.ulb_id, u.name, 3;

-- Incidents, deaths and mean days to compensation per ULB per year.
CREATE VIEW v_ulb_year_incidents WITH (security_invoker = true) AS
SELECT u.ulb_id, u.name AS ulb_name,
       extract(year FROM local_ts(i.occurred_at))::int AS year,
       count(*)                                              AS incidents,
       count(*) FILTER (WHERE i.incident_type = 'FATALITY')  AS deaths,
       COALESCE(sum(cc.amount_due), 0)                       AS compensation_due,
       COALESCE(sum(cc.amount_paid), 0)                      AS compensation_paid,
       round(avg(extract(epoch FROM cc.paid_at - i.occurred_at) / 86400) FILTER (WHERE cc.status = 'PAID'), 1)
                                                             AS mean_days_to_compensation
FROM incident i
JOIN manhole m ON m.manhole_id = i.manhole_id
JOIN ulb     u ON u.ulb_id     = m.ulb_id
LEFT JOIN compensation_case cc ON cc.incident_id = i.incident_id
GROUP BY u.ulb_id, u.name, 3;
