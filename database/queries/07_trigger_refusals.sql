-- 07_trigger_refusals.sql: try to break each rule and watch the database refuse. SAFE: every attempt is wrapped so that a
-- refusal is printed as a NOTICE (the statement is rolled back); nothing here changes data. Needs the demo data (seeds).
-- Run with:  python scripts/run_sql.py database/queries/07_trigger_refusals.sql   (notices are printed)

DO $$
DECLARE
  v_draft    bigint := (SELECT max(permit_id) FROM entry_permit WHERE status = 'DRAFT');
  v_closed   bigint := (SELECT max(permit_id) FROM entry_permit WHERE status = 'CLOSED');
  v_sup      bigint := (SELECT user_id FROM app_user WHERE email = 'supervisor@zeroentry.example');
  v_det_exp  bigint := (SELECT detector_id FROM gas_detector WHERE serial_no = 'GD-4G-0002');   -- calibration lapsed in the seed
  v_bad      bigint := (SELECT contractor_id FROM contractor WHERE status = 'BLACKLISTED' LIMIT 1);
  v_msg      text;
BEGIN
  -- 1. THE GATE: a raw UPDATE cannot authorise a permit whose clauses are not all satisfied.
  BEGIN
    UPDATE entry_permit SET status = 'AUTHORISED', authorised_by = v_sup WHERE permit_id = v_draft;
  EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_msg = MESSAGE_TEXT; RAISE NOTICE '1 gate refused: %', replace(v_msg, E'\n', ' | '); END;

  -- 2. Calibration: a reading from an out-of-calibration detector is refused.
  BEGIN
    INSERT INTO gas_reading (permit_id, detector_id, depth_level, o2_pct, h2s_ppm, lel_pct, co_ppm, taken_at, recorded_by)
    VALUES (v_draft, v_det_exp, 'TOP', 20.9, 0, 0, 0, now(), v_sup);
  EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_msg = MESSAGE_TEXT; RAISE NOTICE '2 calibration refused: %', v_msg; END;

  -- 3. Append-only evidence: a gas reading cannot be edited afterwards.
  BEGIN
    UPDATE gas_reading SET o2_pct = 20.9 WHERE permit_id = v_closed;
  EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_msg = MESSAGE_TEXT; RAISE NOTICE '3 append-only refused: %', v_msg; END;

  -- 4. Append-only audit trail, even for the table owner.
  BEGIN
    DELETE FROM audit_log;
  EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_msg = MESSAGE_TEXT; RAISE NOTICE '4 audit refused: %', v_msg; END;

  -- 5. A finished permit is evidence: its recorded reason cannot be rewritten.
  BEGIN
    UPDATE entry_permit SET end_reason = 'rewritten' WHERE permit_id = v_closed;
  EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_msg = MESSAGE_TEXT; RAISE NOTICE '5 final permit refused: %', v_msg; END;

  -- 6. A blacklisted contractor cannot be given new work.
  BEGIN
    INSERT INTO job (complaint_id, contractor_id) VALUES ((SELECT min(complaint_id) FROM complaint), v_bad);
  EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_msg = MESSAGE_TEXT; RAISE NOTICE '6 blacklist refused: %', v_msg; END;

  -- 7. Only the Responsible Sanitation Authority (an ENGINEER) may approve a waiver.
  BEGIN
    INSERT INTO mechanisation_waiver (job_id, reason_code, justification, approved_by)
    VALUES ((SELECT min(job_id) FROM job), 'OTHER', repeat('A supervisor must not approve this waiver. ', 2), v_sup);
  EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_msg = MESSAGE_TEXT; RAISE NOTICE '7 waiver role refused: %', v_msg; END;

  -- 8. Exclusion constraint: the same worker cannot be in two entries at once (needs an authorised permit; here it is refused earlier).
  BEGIN
    INSERT INTO entry_log (permit_id, worker_id, period, recorded_by)
    SELECT v_draft, worker_id, tstzrange(now(), now() + interval '30 minutes'), v_sup FROM permit_crew WHERE permit_id = v_draft AND crew_role = 'ENTRANT' LIMIT 1;
  EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_msg = MESSAGE_TEXT; RAISE NOTICE '8 entry on a draft refused: %', v_msg; END;

  -- 9. Paying an invoice that is on hold.
  BEGIN
    UPDATE invoice SET status = 'APPROVED', decided_by = v_sup
    WHERE invoice_id = (SELECT h.invoice_id FROM invoice_hold h JOIN invoice i ON i.invoice_id = h.invoice_id
                         WHERE h.released_at IS NULL AND i.status = 'SUBMITTED' LIMIT 1);
  EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_msg = MESSAGE_TEXT; RAISE NOTICE '9 held invoice refused: %', v_msg; END;
END $$;
