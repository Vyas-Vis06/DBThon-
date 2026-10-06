-- 02_scenarios.sql: SYNTHETIC demo scenarios, written through the same triggers and gate as real data.
-- Runs after 01_base.sql AND after the demo users exist (src/zeroentry/seed.py orders it that way). Idempotent: every
-- complaint this file creates starts with "[seed]", and the whole block is skipped if one exists. Times are relative to
-- "now", so the story is the same whenever it is loaded:
--
--   S0  normal mechanised job                     (no alert)               S6  intentionally absent (duplicate, no blockage)
--   S1  resolved with no evidence at all          (alert, invoice held)    S7  resolved 3 h ago, records may still arrive (pending)
--   S2  machine FAILED yet "cleared"              (alert, invoice held)    S8  lawful manual clearance through the real gate
--   S3  resolved with no job at all               (alert)                  S9  a DRAFT permit the gate will DENY (the live demo)
--   S4  resolved, approved invoice, no evidence   (alert, invoice held)    S10 history: a death, a disability, a near miss
--   S5  evidence recorded days late               (needs human review)
--
-- Complaint descriptions are fictional. No real person, contractor, licence or place is represented.

CREATE FUNCTION pg_temp.mh(p_code text) RETURNS bigint LANGUAGE sql AS $$ SELECT manhole_id FROM manhole WHERE code = p_code $$;
CREATE FUNCTION pg_temp.cid(p_lic text) RETURNS bigint LANGUAGE sql AS $$ SELECT contractor_id FROM contractor WHERE licence_no = p_lic $$;
CREATE FUNCTION pg_temp.wid(p_nam text) RETURNS bigint LANGUAGE sql AS $$ SELECT worker_id FROM worker WHERE namaste_id = p_nam $$;
CREATE FUNCTION pg_temp.uid(p_login text) RETURNS bigint LANGUAGE sql
AS $$ SELECT user_id FROM app_user WHERE email = p_login || '@zeroentry.example' $$;

CREATE FUNCTION pg_temp.complaint(p_manhole text, p_desc text, p_raised interval, p_resolved interval, p_code text) RETURNS bigint
LANGUAGE sql AS $$
  INSERT INTO complaint (manhole_id, description, raised_at, status, resolved_at, resolution_code, resolved_by)
  VALUES (pg_temp.mh(p_manhole), '[seed] ' || p_desc, now() - p_raised,
          CASE WHEN p_resolved IS NULL THEN 'OPEN' ELSE 'RESOLVED' END,
          CASE WHEN p_resolved IS NULL THEN NULL ELSE now() - p_resolved END, p_code,
          CASE WHEN p_resolved IS NULL THEN NULL ELSE pg_temp.uid('engineer') END)
  RETURNING complaint_id
$$;

CREATE FUNCTION pg_temp.job(p_complaint bigint, p_lic text) RETURNS bigint LANGUAGE sql
AS $$ INSERT INTO job (complaint_id, contractor_id, created_by) VALUES (p_complaint, pg_temp.cid(p_lic), pg_temp.uid('engineer')) RETURNING job_id $$;

-- A machine deployment whose server-side "recorded_at" is set explicitly, because whether evidence was recorded in time is
-- exactly what the detector measures.
CREATE FUNCTION pg_temp.deploy(p_job bigint, p_machine text, p_started interval, p_ended interval, p_outcome text, p_recorded interval) RETURNS void
LANGUAGE sql AS $$
  INSERT INTO machine_deployment (job_id, machine_id, started_at, ended_at, outcome, recorded_by, recorded_at)
  SELECT p_job, m.machine_id, now() - p_started, CASE WHEN p_outcome IS NULL THEN NULL ELSE now() - p_ended END, p_outcome,
         pg_temp.uid('engineer'), now() - p_recorded
    FROM machine m WHERE m.code = p_machine
$$;

CREATE FUNCTION pg_temp.invoice(p_job bigint, p_no text, p_amount numeric, p_status text) RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE i bigint;
BEGIN
  INSERT INTO invoice (job_id, invoice_no, amount_inr) VALUES (p_job, p_no, p_amount) RETURNING invoice_id INTO i;
  IF p_status IN ('APPROVED', 'PAID') THEN
    UPDATE invoice SET status = 'APPROVED', decided_by = pg_temp.uid('engineer') WHERE invoice_id = i;
  END IF;
  IF p_status = 'PAID' THEN UPDATE invoice SET status = 'PAID' WHERE invoice_id = i; END IF;
  RETURN i;
END $$;

DO $seed$
DECLARE
  v_eng bigint := pg_temp.uid('engineer');
  v_sup bigint := pg_temp.uid('supervisor');
  v_at  timestamptz := from_local(date_trunc('day', local_ts(now())) - interval '1 day' + interval '10 hours');  -- yesterday 10:00 IST
  v_c bigint; v_j bigint; v_p bigint; v_inc bigint; v_case bigint;
BEGIN
  IF EXISTS (SELECT 1 FROM complaint WHERE description LIKE '[seed]%') THEN RETURN; END IF;

  -- S0 normal: a suction unit cleared it, recorded the same day, invoice paid --------------------------------------------
  v_c := pg_temp.complaint('CHN-ADY-001', 'Sewage overflowing outside the bus stop', interval '5 days', interval '3 days', 'CLEARED');
  v_j := pg_temp.job(v_c, 'TN-SAN-2026-001');
  PERFORM pg_temp.deploy(v_j, 'SUC-ADY-01', interval '3 days 5 hours', interval '3 days 4 hours', 'CLEARED', interval '3 days 4 hours');
  UPDATE job SET status = 'COMPLETED' WHERE job_id = v_j;
  PERFORM pg_temp.invoice(v_j, 'MSS/2026/101', 48500, 'PAID');

  -- S1 genuinely missing: closed as cleared, nothing recorded ------------------------------------------------------------
  v_c := pg_temp.complaint('CHN-ADY-002', 'Foul smell and slow flow near the school gate', interval '6 days', interval '4 days', 'CLEARED');
  v_j := pg_temp.job(v_c, 'TN-SAN-2026-002');
  PERFORM pg_temp.invoice(v_j, 'CDW/2026/033', 62000, 'SUBMITTED');

  -- S2 conflicting: the machine reported FAILURE, yet the complaint was closed as cleared -------------------------------
  v_c := pg_temp.complaint('CHN-ADY-003', 'Manhole cover surcharging after rain', interval '6 days', interval '3 days', 'CLEARED');
  v_j := pg_temp.job(v_c, 'TN-SAN-2026-003');
  PERFORM pg_temp.deploy(v_j, 'ROB-ADY-01', interval '3 days 6 hours', interval '3 days 5 hours', 'FAILED', interval '3 days 5 hours');
  PERFORM pg_temp.invoice(v_j, 'PIC/2026/017', 75000, 'SUBMITTED');

  -- S3 the purest shadow entry: closed as cleared with no job on file at all --------------------------------------------
  PERFORM pg_temp.complaint('CHN-ADY-004', 'Blockage in the lane behind the temple', interval '5 days', interval '2 days', 'CLEARED');

  -- S4 an invoice was already approved for work with no clearance evidence -------------------------------------------------
  v_c := pg_temp.complaint('CHN-ADY-005', 'Septic tank overflowing into the street drain', interval '8 days', interval '5 days', 'CLEARED');
  v_j := pg_temp.job(v_c, 'TN-SAN-2026-005');
  PERFORM pg_temp.invoice(v_j, 'CCW/2026/009', 91000, 'APPROVED');

  -- S5 late arrival: the machine log was entered three days after the complaint was closed -------------------------------
  v_c := pg_temp.complaint('CHN-ADY-006', 'Overflow at the market junction', interval '8 days', interval '4 days', 'CLEARED');
  v_j := pg_temp.job(v_c, 'TN-SAN-2026-001');
  PERFORM pg_temp.deploy(v_j, 'SUC-ADY-01', interval '4 days 5 hours', interval '4 days 4 hours', 'CLEARED', interval '1 day');
  PERFORM pg_temp.invoice(v_j, 'MSS/2026/102', 38250, 'SUBMITTED');

  -- S6 intentionally absent: exempt resolutions are never flagged -----------------------------------------------------------
  PERFORM pg_temp.complaint('CHN-ADY-007', 'Duplicate of the market-junction complaint', interval '8 days', interval '4 days', 'DUPLICATE_COMPLAINT');
  PERFORM pg_temp.complaint('CHN-ADY-008', 'Reported blockage; inspection found the line flowing freely', interval '7 days', interval '5 days', 'NO_BLOCKAGE_FOUND');

  -- S7 resolved three hours ago: its records may still arrive, so it is pending, not an alert ---------------------------
  v_c := pg_temp.complaint('CHN-ADY-009', 'Slow drain at the clinic entrance', interval '2 days', interval '3 hours', 'CLEARED');
  v_j := pg_temp.job(v_c, 'TN-SAN-2026-002');

  -- S8 a lawful manual clearance, end to end, through the real gate: waiver, crew, gear, readings, authorise, entries, close ---
  v_c := pg_temp.complaint('CHN-TEY-001', 'Chamber blocked by tree roots; machines could not reach it', interval '6 days', NULL, NULL);
  v_j := pg_temp.job(v_c, 'TN-SAN-2026-002');
  PERFORM pg_temp.deploy(v_j, 'JET-TEY-01', interval '5 days 6 hours', interval '5 days 5 hours', 'FAILED', interval '5 days 5 hours');
  INSERT INTO mechanisation_waiver (job_id, reason_code, justification, approved_by, approved_at)
  VALUES (v_j, 'MACHINE_FAILED', 'The jetting unit failed twice on a root mass; the chamber is too narrow for the suction unit, so a manual clearance is unavoidable.',
          v_eng, now() - interval '5 days 4 hours');
  INSERT INTO entry_permit (job_id, supervisor_id) VALUES (v_j, v_sup) RETURNING permit_id INTO v_p;
  INSERT INTO permit_crew (permit_id, worker_id, crew_role) VALUES
    (v_p, pg_temp.wid('NAM-TN-100009'), 'ENTRANT'), (v_p, pg_temp.wid('NAM-TN-100010'), 'ENTRANT'),
    (v_p, pg_temp.wid('NAM-TN-100011'), 'STANDBY'), (v_p, pg_temp.wid('NAM-TN-100012'), 'SUPERVISOR');
  INSERT INTO gear_issue (permit_id, worker_id, gear_code, serial_no, issued_by)
  SELECT v_p, pc.worker_id, g.gear_code, 'SN-' || g.gear_code || '-' || pc.worker_id, v_sup
    FROM permit_crew pc CROSS JOIN gear_item g WHERE pc.permit_id = v_p AND pc.crew_role = 'ENTRANT' AND g.statutory;
  INSERT INTO gas_reading (permit_id, detector_id, depth_level, o2_pct, h2s_ppm, lel_pct, co_ppm, taken_at, recorded_by)
  SELECT v_p, d.detector_id, lv, 20.9, 0, 0, 0, v_at - interval '5 minutes', v_sup
    FROM gas_detector d CROSS JOIN unnest(ARRAY['TOP', 'MID', 'BOTTOM']) AS lv WHERE d.serial_no = 'GD-4G-0001';
  PERFORM 1 FROM authorise_entry(v_p, v_sup, v_at);
  IF (SELECT status FROM entry_permit WHERE permit_id = v_p) <> 'AUTHORISED' THEN
    RAISE EXCEPTION 'seed: the lawful permit scenario was not authorised by the gate';
  END IF;
  INSERT INTO entry_log (permit_id, worker_id, period, recorded_by, recorded_at) VALUES
    (v_p, pg_temp.wid('NAM-TN-100009'), tstzrange(v_at + interval '10 minutes', v_at + interval '55 minutes'), v_sup, v_at + interval '1 hour'),
    (v_p, pg_temp.wid('NAM-TN-100010'), tstzrange(v_at + interval '15 minutes', v_at + interval '60 minutes'), v_sup, v_at + interval '1 hour');
  UPDATE entry_permit SET status = 'CLOSED', ended_at = v_at + interval '2 hours' WHERE permit_id = v_p;
  UPDATE job SET status = 'COMPLETED' WHERE job_id = v_j;
  UPDATE complaint SET status = 'RESOLVED', resolved_at = v_at + interval '3 hours', resolution_code = 'CLEARED', resolved_by = v_eng WHERE complaint_id = v_c;
  PERFORM pg_temp.invoice(v_j, 'CDW/2026/034', 120000, 'APPROVED');

  -- S9 the live demo: a DRAFT permit with three deliberate gaps (no standby; one entrant short of two gear items; no gas readings) --
  v_c := pg_temp.complaint('CHN-ADY-010', 'Septic tank overflowing into the lane (live demo)', interval '1 day', NULL, NULL);
  v_j := pg_temp.job(v_c, 'TN-SAN-2026-001');
  PERFORM pg_temp.deploy(v_j, 'ROB-ADY-01', interval '3 hours', interval '2 hours', 'FAILED', interval '2 hours');
  INSERT INTO mechanisation_waiver (job_id, reason_code, justification, approved_by, approved_at)
  VALUES (v_j, 'MACHINE_FAILED', 'The robot could not clear the septic tank and no vehicle can reach it; a manual entry is the only remaining option.',
          v_eng, now() - interval '90 minutes');
  INSERT INTO entry_permit (job_id, supervisor_id) VALUES (v_j, v_sup) RETURNING permit_id INTO v_p;
  INSERT INTO permit_crew (permit_id, worker_id, crew_role) VALUES
    (v_p, pg_temp.wid('NAM-TN-100001'), 'ENTRANT'), (v_p, pg_temp.wid('NAM-TN-100002'), 'ENTRANT'), (v_p, pg_temp.wid('NAM-TN-100004'), 'SUPERVISOR');
  INSERT INTO gear_issue (permit_id, worker_id, gear_code, serial_no, issued_by)
  SELECT v_p, pc.worker_id, g.gear_code, 'SN-' || g.gear_code || '-' || pc.worker_id, v_sup
    FROM permit_crew pc CROSS JOIN gear_item g
   WHERE pc.permit_id = v_p AND pc.crew_role = 'ENTRANT' AND g.statutory
     AND NOT (pc.worker_id = pg_temp.wid('NAM-TN-100002') AND g.gear_code IN ('SAFETY_HARNESS', 'BREATHING_APPARATUS'));

  -- S10 history, for the dashboards: a death (contractor blacklisted, compensation overdue and part-paid), a disability, a near miss --
  CALL record_incident('FATALITY', now() - interval '120 days', pg_temp.wid('NAM-TN-100025'), pg_temp.mh('CHN-TON-003'),
                       'Synthetic history: a worker collapsed after entering a chamber with no permit on file.', v_eng, NULL, NULL, v_inc);
  SELECT case_id INTO v_case FROM compensation_case WHERE incident_id = v_inc;
  PERFORM record_compensation_payment(v_case, 1000000, now() - interval '20 days');
  CALL record_incident('DISABILITY', now() - interval '60 days', pg_temp.wid('NAM-TN-100033'), pg_temp.mh('CHN-TON-007'),
                       'Synthetic history: a hand injury while removing a manhole cover.', v_eng, NULL, NULL, v_inc);
  CALL record_incident('NEAR_MISS', now() - interval '10 days', pg_temp.wid('NAM-TN-100010'), pg_temp.mh('CHN-TEY-004'),
                       'Synthetic history: a worker slipped on the ladder and was caught by the harness.', v_sup, NULL, NULL, v_inc);
END $seed$;
