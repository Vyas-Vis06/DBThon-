-- evaluation.sql: objects used ONLY by scripts/evaluate.py, in a throwaway database. Never a migration: nothing here is
-- part of the shipped schema. docs/EVALUATION.md explains the method.

-- ---------------------------------------------------------------------------------------------
-- THE CONVENTIONAL BASELINE for detection: the anti-join exactly as the team's own proposal first wrote it
-- (docs/proposal/ZeroEntry_DBThon2026_Proposal.md section 6.3c). Job-anchored (inner join), no list of exempt
-- resolutions, no grace window, no clock, and any CLOSED permit counts as evidence whether or not anyone logged an entry.
-- ---------------------------------------------------------------------------------------------
CREATE VIEW eval_naive_shadow AS
SELECT c.complaint_id, c.manhole_id, j.contractor_id, c.resolved_at
FROM complaint c JOIN job j ON j.complaint_id = c.complaint_id
WHERE c.status = 'RESOLVED'
  AND NOT EXISTS (SELECT 1 FROM machine_deployment m
                  WHERE m.job_id = j.job_id AND m.outcome = 'CLEARED')
  AND NOT EXISTS (SELECT 1 FROM entry_permit p
                  WHERE p.job_id = j.job_id AND p.status = 'CLOSED');

-- ---------------------------------------------------------------------------------------------
-- eval_add_history(n): append n resolved complaints of synthetic history, through every trigger (nothing is bypassed).
--   * 3 %  resolved NO_BLOCKAGE_FOUND (intentionally absent evidence, BR-33)
--   * 5 %  cleared by a lawful manual entry: waiver, permit, 4 crew, statutory gear, 3 gas readings, authorise_entry(),
--          two logged entries, closed (so entry_permit, permit_crew, gear_issue, gas_reading and entry_log grow too)
--   * the rest cleared by a machine, except about 2 % left with no evidence at all (shadow-entry candidates)
-- Everything happens in the past and well outside the 24 h grace window. Permits are spaced in daylight slots so the
-- entry rules (window, daylight, 90 minutes, no overlap per worker) all hold. Returns the number of permits created.
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION eval_add_history(p_n int) RETURNS int LANGUAGE plpgsql AS $$
DECLARE
  v_ulb bigint; v_contractor bigint; v_machine bigint; v_detector bigint; v_sup bigint; v_eng bigint;
  v_mh bigint[]; v_pool bigint[];
  v_base   timestamptz := from_local(date_trunc('day', local_ts(now()))::timestamp) - interval '6 years';
  v_k0     int;
  v_manual int := p_n / 20;
  v_at timestamptz; v_c bigint; v_j bigint; v_p bigint; v_crew bigint[];
BEGIN
  SELECT ulb_id INTO v_ulb FROM ulb WHERE name = 'Evaluation ULB';
  IF NOT FOUND THEN                                     -- first call: the fixed cast (one ULB, 500 manholes, 400 workers)
    INSERT INTO ulb (name, district, state) VALUES ('Evaluation ULB', 'Chennai', 'Tamil Nadu') RETURNING ulb_id INTO v_ulb;
    INSERT INTO manhole (ulb_id, code, kind, depth_m, lat, lng)
    SELECT v_ulb, 'EVAL-MH-' || g, 'SEWER', 3.5, 13.0, 80.2 FROM generate_series(1, 500) g;
    INSERT INTO contractor (name, licence_no, licence_valid_until) VALUES ('Evaluation Contractor', 'EVAL-LIC-1', '2099-12-31');
    INSERT INTO machine (ulb_id, code, kind) VALUES (v_ulb, 'EVAL-MC-1', 'JETTING');
    INSERT INTO gas_detector (serial_no, model, calibration_valid_until) VALUES ('EVAL-GD-1', 'Synthetic 4-gas', '2099-12-31');
    INSERT INTO app_user (role_id, email, full_name, password_hash)
    SELECT role_id, lower(name) || '.eval@zeroentry.example', 'Evaluation ' || lower(name), 'not-a-real-hash'
      FROM role WHERE name IN ('SUPERVISOR', 'ENGINEER');
    INSERT INTO worker (contractor_id, full_name, namaste_id, medical_fit_until, trained_until)
    SELECT (SELECT contractor_id FROM contractor WHERE licence_no = 'EVAL-LIC-1'), 'Evaluation worker ' || g,
           'NAM-EVAL-' || lpad(g::text, 4, '0'), '2099-12-31', '2099-12-31'
      FROM generate_series(1, 400) g;
  END IF;
  SELECT contractor_id INTO v_contractor FROM contractor WHERE licence_no = 'EVAL-LIC-1';
  SELECT machine_id INTO v_machine FROM machine WHERE code = 'EVAL-MC-1';
  SELECT detector_id INTO v_detector FROM gas_detector WHERE serial_no = 'EVAL-GD-1';
  SELECT user_id INTO v_sup FROM app_user WHERE email = 'supervisor.eval@zeroentry.example';
  SELECT user_id INTO v_eng FROM app_user WHERE email = 'engineer.eval@zeroentry.example';
  v_mh   := ARRAY(SELECT manhole_id FROM manhole WHERE ulb_id = v_ulb ORDER BY manhole_id);
  v_pool := ARRAY(SELECT worker_id FROM worker WHERE namaste_id LIKE 'NAM-EVAL-%' ORDER BY worker_id);
  SELECT count(*) INTO v_k0 FROM entry_permit;

  -- Mechanised and exempt history, set-based. Resolution instants are spread over the five years before the last month.
  WITH c AS (
    INSERT INTO complaint (manhole_id, description, raised_at, status, resolved_at, resolution_code)
    SELECT v_mh[1 + g % 500], 'Synthetic history', t - interval '1 day', 'RESOLVED', t,
           CASE WHEN g % 100 < 3 THEN 'NO_BLOCKAGE_FOUND' ELSE 'CLEARED' END
      FROM generate_series(1, p_n - v_manual) g
     CROSS JOIN LATERAL (SELECT v_base + interval '1 year' + ((g * 7919) % 1800) * interval '1 day'
                                + ((g * 31) % 600) * interval '1 minute' AS t) x
    RETURNING complaint_id, resolved_at, resolution_code),
  j AS (
    INSERT INTO job (complaint_id, contractor_id) SELECT complaint_id, v_contractor FROM c RETURNING job_id, complaint_id)
  INSERT INTO machine_deployment (job_id, machine_id, started_at, ended_at, outcome, recorded_at)
  SELECT j.job_id, v_machine, c.resolved_at - interval '3 hours', c.resolved_at - interval '2 hours', 'CLEARED',
         c.resolved_at - interval '1 hour'
    FROM j JOIN c USING (complaint_id)
   WHERE c.resolution_code = 'CLEARED' AND c.complaint_id % 50 <> 0;

  -- Lawful manual entries, one at a time through the real gate. Slot k: day k/4 at 07:00, 09:00, 11:00 or 13:00 IST.
  FOR k IN v_k0 .. v_k0 + v_manual - 1 LOOP
    v_at := v_base + (k / 4) * interval '1 day' + (7 + 2 * (k % 4)) * interval '1 hour';
    v_crew := ARRAY[v_pool[1 + (4 * k) % 400], v_pool[1 + (4 * k + 1) % 400], v_pool[1 + (4 * k + 2) % 400],
                    v_pool[1 + (4 * k + 3) % 400]];
    INSERT INTO complaint (manhole_id, description, raised_at)
    VALUES (v_mh[1 + k % 500], 'Synthetic history (manual)', v_at - interval '1 day') RETURNING complaint_id INTO v_c;
    INSERT INTO job (complaint_id, contractor_id) VALUES (v_c, v_contractor) RETURNING job_id INTO v_j;
    INSERT INTO mechanisation_waiver (job_id, reason_code, justification, approved_by)
    VALUES (v_j, 'NO_MACHINE_ACCESS', 'Narrow chamber with no vehicle access; jetting and suction units cannot reach it.', v_eng);
    INSERT INTO entry_permit (job_id, supervisor_id) VALUES (v_j, v_sup) RETURNING permit_id INTO v_p;
    INSERT INTO permit_crew (permit_id, worker_id, crew_role)
    VALUES (v_p, v_crew[1], 'ENTRANT'), (v_p, v_crew[2], 'ENTRANT'), (v_p, v_crew[3], 'STANDBY'), (v_p, v_crew[4], 'SUPERVISOR');
    INSERT INTO gear_issue (permit_id, worker_id, gear_code, serial_no, issued_by)
    SELECT v_p, e, gear_code, 'SN-' || gear_code, v_sup FROM gear_item, unnest(v_crew[1:2]) e WHERE statutory;
    INSERT INTO gas_reading (permit_id, detector_id, depth_level, o2_pct, h2s_ppm, lel_pct, co_ppm, taken_at, recorded_by)
    SELECT v_p, v_detector, lv, 20.9, 0, 0, 0, v_at - interval '5 minutes', v_sup FROM unnest(ARRAY['TOP', 'MID', 'BOTTOM']) lv;
    PERFORM * FROM authorise_entry(v_p, v_sup, v_at);
    INSERT INTO entry_log (permit_id, worker_id, period, recorded_by, recorded_at)
    SELECT v_p, e, tstzrange(v_at + interval '10 minutes', v_at + interval '40 minutes'), v_sup, v_at + interval '45 minutes'
      FROM unnest(v_crew[1:2]) e;                       -- fails loudly if authorise_entry() had denied the permit
    UPDATE entry_permit SET status = 'CLOSED', ended_at = v_at + interval '1 hour' WHERE permit_id = v_p;
    UPDATE complaint SET status = 'RESOLVED', resolved_at = v_at + interval '3 hours', resolution_code = 'CLEARED'
     WHERE complaint_id = v_c;
  END LOOP;
  RETURN v_manual;
END $$;
