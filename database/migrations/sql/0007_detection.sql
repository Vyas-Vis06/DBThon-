-- 0007_detection.sql
-- Shadow-entry detection by absence (PROJECT_SPEC BR-30 .. BR-36).
--
-- The EXPECTED POPULATION is explicit; an alert is the ABSENCE of the records that population should have left.
--   SE1  expected: every complaint RESOLVED with a resolution type that requires evidence ("cleared").
--        expected record: a machine deployment CLEARED, or an authorised+CLOSED permit with a logged entry.
--        Anchored on COMPLAINT, not job, so a complaint resolved with no job at all (the purest shadow entry)
--        is caught, and evidence on ANY of its jobs counts.
--   SE2  expected: every ENTRANT of every CLOSED permit.   expected record: an entry-log row for that entrant.
--
-- Evidence only counts if it was RECORDED (server clock) within the grace window after the anchor event; paperwork
-- created later is "late". Candidates are therefore a pure function of the data (no race with the scan schedule).
-- Late evidence never closes an alert: it moves it to EVIDENCE_RECEIVED and a person decides (BR-31).

CREATE VIEW v_shadow_se1 WITH (security_invoker = true) AS
WITH g AS (SELECT rule_num('shadow_grace_hours')::int AS hours,
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
JOIN resolution_type rt ON rt.code = c.resolution_code AND rt.requires_evidence          -- BR-33: exempt types never appear
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
  AND NOT EXISTS (                                  -- ANTI-JOIN 1: no TIMELY machine clearance on any job
        SELECT 1 FROM job j JOIN machine_deployment d ON d.job_id = j.job_id
         WHERE j.complaint_id = c.complaint_id AND d.outcome = 'CLEARED'
           AND d.recorded_at <= c.resolved_at + g.grace)
  AND NOT EXISTS (                                  -- ANTI-JOIN 2: no TIMELY authorised, closed permit with a logged entry
        SELECT 1 FROM job j JOIN entry_permit p ON p.job_id = j.job_id
         WHERE j.complaint_id = c.complaint_id AND p.status = 'CLOSED' AND p.authorised_at IS NOT NULL
           AND p.ended_at <= c.resolved_at + g.grace
           AND EXISTS (SELECT 1 FROM entry_log e
                        WHERE e.permit_id = p.permit_id AND e.recorded_at <= c.resolved_at + g.grace));

CREATE VIEW v_shadow_se2 WITH (security_invoker = true) AS
WITH g AS (SELECT rule_num('shadow_grace_hours')::int AS hours,
                  make_interval(hours => rule_num('shadow_grace_hours')::int) AS grace)
SELECT j.complaint_id,
       'SE2_ENTRANT_NOT_LOGGED'::text                                              AS rule_code,
       c.manhole_id, m.ulb_id,
       (array_agg(j.contractor_id ORDER BY p.ended_at DESC, p.permit_id DESC))[1]  AS contractor_id,
       (array_agg(j.job_id        ORDER BY p.ended_at DESC, p.permit_id DESC))[1]  AS job_id,
       max(p.ended_at)                                                             AS anchor_at,
       max(p.ended_at + g.grace)                                                   AS evidence_deadline,
       bool_or(EXISTS (SELECT 1 FROM entry_log e WHERE e.permit_id = p.permit_id AND e.worker_id = pc.worker_id))
                                                                                   AS late_evidence_exists,
       format('Permit(s) %s closed with no entry log recorded within %s h for entrant(s): %s.',
              string_agg(DISTINCT p.permit_id::text, ', '), g.hours, string_agg(DISTINCT w.namaste_id, ', ')) AS reason
FROM entry_permit p
JOIN job j       ON j.job_id = p.job_id
JOIN complaint c ON c.complaint_id = j.complaint_id
JOIN manhole m   ON m.manhole_id = c.manhole_id
JOIN permit_crew pc ON pc.permit_id = p.permit_id AND pc.crew_role = 'ENTRANT'
JOIN worker w    ON w.worker_id = pc.worker_id
CROSS JOIN g
WHERE p.status = 'CLOSED' AND p.authorised_at IS NOT NULL
  AND NOT EXISTS (                                  -- ANTI-JOIN: this entrant has no TIMELY entry log on this permit
        SELECT 1 FROM entry_log e
         WHERE e.permit_id = p.permit_id AND e.worker_id = pc.worker_id AND e.recorded_at <= p.ended_at + g.grace)
GROUP BY j.complaint_id, c.manhole_id, m.ulb_id, g.hours, g.grace;

CREATE VIEW v_shadow_candidate WITH (security_invoker = true) AS
SELECT * FROM v_shadow_se1 UNION ALL SELECT * FROM v_shadow_se2;

-- ---------------------------------------------------------------------------------------------
-- Persisted alerts: lifecycle guard, history, and invoice holds. OPEN -> EVIDENCE_RECEIVED -> CONFIRMED | DISMISSED.
-- Only an ENGINEER or ADMIN may decide; CONFIRMED and DISMISSED are final.
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION alert_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_role text;
BEGIN
  IF NEW.complaint_id <> OLD.complaint_id OR NEW.rule_code <> OLD.rule_code THEN
    RAISE EXCEPTION 'An alert''s complaint and rule cannot change' USING ERRCODE = 'ZE003';
  END IF;
  IF OLD.status IN ('CONFIRMED', 'DISMISSED') THEN
    RAISE EXCEPTION 'A % alert is final and cannot be changed', OLD.status USING ERRCODE = 'ZE003';
  END IF;
  IF NEW.status = OLD.status THEN RETURN NEW; END IF;

  IF NOT (OLD.status = 'OPEN' AND NEW.status IN ('EVIDENCE_RECEIVED', 'CONFIRMED', 'DISMISSED')
       OR OLD.status = 'EVIDENCE_RECEIVED' AND NEW.status IN ('CONFIRMED', 'DISMISSED')) THEN
    RAISE EXCEPTION 'An alert cannot change from % to %', OLD.status, NEW.status USING ERRCODE = 'ZE003';
  END IF;

  IF NEW.status IN ('CONFIRMED', 'DISMISSED') THEN
    NEW.reviewed_by := COALESCE(NEW.reviewed_by, app_user_id());
    NEW.reviewed_at := COALESCE(NEW.reviewed_at, now());
    SELECT r.name INTO v_role FROM app_user u JOIN role r ON r.role_id = u.role_id
     WHERE u.user_id = NEW.reviewed_by AND u.is_active;
    IF v_role IS NULL OR v_role NOT IN ('ENGINEER', 'ADMIN') THEN
      RAISE EXCEPTION 'Only an active ENGINEER or ADMIN may decide a shadow-entry alert' USING ERRCODE = 'ZE006';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_alert_guard BEFORE UPDATE ON shadow_entry_alert
  FOR EACH ROW EXECUTE FUNCTION alert_guard();

-- New alert: write history and hold the unpaid invoices on the complaint's jobs (BR-35).
CREATE FUNCTION alert_after_insert() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO shadow_entry_alert_event (alert_id, from_status, to_status, actor_id, note)
  VALUES (NEW.alert_id, NULL, NEW.status, NULL, 'Raised by the absence scan: ' || NEW.reason);
  INSERT INTO invoice_hold (invoice_id, reason, alert_id)
  SELECT i.invoice_id, 'SHADOW_ENTRY', NEW.alert_id
    FROM job j JOIN invoice i ON i.job_id = j.job_id
   WHERE j.complaint_id = NEW.complaint_id AND i.status IN ('SUBMITTED', 'APPROVED')
  ON CONFLICT DO NOTHING;
  RETURN NULL;
END $$;
CREATE TRIGGER trg_alert_after_insert AFTER INSERT ON shadow_entry_alert
  FOR EACH ROW EXECUTE FUNCTION alert_after_insert();

-- Status change: write history; a DISMISSAL releases exactly the holds this alert placed (and no others).
CREATE FUNCTION alert_after_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status = OLD.status THEN RETURN NULL; END IF;
  INSERT INTO shadow_entry_alert_event (alert_id, from_status, to_status, actor_id, note)
  VALUES (NEW.alert_id, OLD.status, NEW.status, NEW.reviewed_by,
          CASE WHEN NEW.status = 'EVIDENCE_RECEIVED'
               THEN 'Evidence picture changed after detection (late records or reclassification): needs human review'
               ELSE NEW.review_note END);
  IF NEW.status = 'DISMISSED' THEN
    UPDATE invoice_hold
       SET released_at = now(), released_by = NEW.reviewed_by,
           release_note = 'Alert #' || NEW.alert_id || ' dismissed: ' || NEW.review_note
     WHERE alert_id = NEW.alert_id AND released_at IS NULL;
  END IF;
  RETURN NULL;
END $$;
CREATE TRIGGER trg_alert_after_update AFTER UPDATE ON shadow_entry_alert
  FOR EACH ROW EXECUTE FUNCTION alert_after_update();

-- ---------------------------------------------------------------------------------------------
-- scan_shadow_entries(): idempotent. Opens alerts for candidates whose evidence deadline has passed (UNIQUE
-- (complaint, rule) + upsert: re-running never duplicates), and moves still-OPEN alerts to EVIDENCE_RECEIVED
-- when late evidence appears or the premise changes. It NEVER closes an alert. p_at is the scan clock.
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION scan_shadow_entries(p_at timestamptz DEFAULT now())
RETURNS TABLE (opened int, moved_to_review int, pending_in_grace int)
LANGUAGE plpgsql AS $$
#variable_conflict use_column
DECLARE
  v_opened  int;
  v_review  int;
  v_pending int;
BEGIN
  WITH ins AS (
    INSERT INTO shadow_entry_alert (complaint_id, rule_code, contractor_id, status, reason, evidence_deadline,
                                    detected_at, last_evaluated_at)
    SELECT v.complaint_id, v.rule_code, v.contractor_id,
           CASE WHEN v.late_evidence_exists THEN 'EVIDENCE_RECEIVED' ELSE 'OPEN' END,
           v.reason, v.evidence_deadline, p_at, p_at
      FROM v_shadow_candidate v
      JOIN detection_rule r ON r.rule_code = v.rule_code AND r.enabled
     WHERE p_at >= v.evidence_deadline
    ON CONFLICT (complaint_id, rule_code) DO UPDATE SET last_evaluated_at = EXCLUDED.last_evaluated_at
      WHERE shadow_entry_alert.status IN ('OPEN', 'EVIDENCE_RECEIVED')
    RETURNING (xmax = 0) AS inserted)
  SELECT count(*) FILTER (WHERE inserted) INTO v_opened FROM ins;

  WITH moved AS (
    UPDATE shadow_entry_alert a SET status = 'EVIDENCE_RECEIVED', last_evaluated_at = p_at
     WHERE a.status = 'OPEN'
       AND (EXISTS (SELECT 1 FROM v_shadow_candidate v WHERE v.complaint_id = a.complaint_id
                       AND v.rule_code = a.rule_code AND v.late_evidence_exists)
         OR NOT EXISTS (SELECT 1 FROM v_shadow_candidate v WHERE v.complaint_id = a.complaint_id
                       AND v.rule_code = a.rule_code))
    RETURNING 1)
  SELECT count(*) INTO v_review FROM moved;

  SELECT count(*) INTO v_pending
    FROM v_shadow_candidate v JOIN detection_rule r ON r.rule_code = v.rule_code AND r.enabled
   WHERE p_at < v.evidence_deadline;

  RETURN QUERY SELECT v_opened, v_review, v_pending;
END $$;

-- The one sanctioned way to decide an alert (ENGINEER or ADMIN, with a written note).
CREATE FUNCTION review_shadow_alert(p_alert_id bigint, p_decision text, p_note text, p_reviewer bigint)
RETURNS shadow_entry_alert LANGUAGE plpgsql AS $$
DECLARE
  a shadow_entry_alert%ROWTYPE;
BEGIN
  IF p_decision NOT IN ('CONFIRMED', 'DISMISSED') THEN
    RAISE EXCEPTION 'Decision must be CONFIRMED or DISMISSED' USING ERRCODE = 'ZE002';
  END IF;
  IF length(btrim(COALESCE(p_note, ''))) < 10 THEN
    RAISE EXCEPTION 'A review needs a written note of at least 10 characters' USING ERRCODE = 'ZE002';
  END IF;
  UPDATE shadow_entry_alert
     SET status = p_decision, reviewed_by = p_reviewer, reviewed_at = now(), review_note = btrim(p_note)
   WHERE alert_id = p_alert_id
  RETURNING * INTO a;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Alert % does not exist', p_alert_id USING ERRCODE = 'ZE004';
  END IF;
  RETURN a;
END $$;

-- The proposal's anti-join view, enriched: what is suspected right now, whether the grace window has passed,
-- and the persisted alert (if any). "past_grace = false" means "pending: records may still arrive".
CREATE VIEW v_suspected_shadow_entry WITH (security_invoker = true) AS
SELECT v.complaint_id, v.rule_code, r.title AS rule_title, v.manhole_id, v.ulb_id, v.contractor_id, v.job_id,
       v.anchor_at, v.evidence_deadline, now() >= v.evidence_deadline AS past_grace,
       v.late_evidence_exists, v.reason, a.alert_id, a.status AS alert_status
FROM v_shadow_candidate v
JOIN detection_rule r ON r.rule_code = v.rule_code AND r.enabled
LEFT JOIN shadow_entry_alert a ON a.complaint_id = v.complaint_id AND a.rule_code = v.rule_code;

COMMENT ON VIEW v_suspected_shadow_entry IS
  'Anti-join detection by absence: expected evidence missing for resolved complaints (SE1) and unlogged entrants (SE2).';
