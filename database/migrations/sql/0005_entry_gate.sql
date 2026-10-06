-- 0005_entry_gate.sql
-- Zero-entry, default-deny: an entry permit becomes AUTHORISED only if relational division proves that every
-- statutory safeguard has a matching record. The proof is one function, permit_clause_check(), called by
-- BOTH authorise_entry() (for the explainable checklist) and a BEFORE UPDATE trigger (for every other client),
-- so there is no code path that reaches AUTHORISED without it. See PROJECT_SPEC.md BR-01 .. BR-12.

-- ---------------------------------------------------------------------------------------------
-- permit_clause_check(): one row per legal clause with pass/fail and a human-readable detail.
-- STABLE, side-effect free, evaluated "as of" p_at so it is testable and reproducible.
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION permit_clause_check(p_permit_id bigint, p_at timestamptz DEFAULT now())
RETURNS TABLE (clause_code text, passed boolean, detail text)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
DECLARE
  v_job_id        bigint;
  v_contractor_id bigint;
  v_today         date     := local_date(p_at);
  v_min_crew      int      := rule_num('min_crew_size')::int;
  v_max_age       interval := make_interval(mins => rule_num('gas_max_age_min')::int);
  v_o2_min        numeric  := rule_num('gas_o2_min');
  v_o2_max        numeric  := rule_num('gas_o2_max');
  v_h2s_max       numeric  := rule_num('gas_h2s_max_ppm');
  v_lel_max       numeric  := rule_num('gas_lel_max_pct');
  v_co_max        numeric  := rule_num('gas_co_max_ppm');
  v_entrants int; v_standby int; v_supervisors int; v_total int; v_statutory int;
BEGIN
  SELECT p.job_id, j.contractor_id INTO v_job_id, v_contractor_id
    FROM entry_permit p JOIN job j ON j.job_id = p.job_id WHERE p.permit_id = p_permit_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Permit % does not exist', p_permit_id USING ERRCODE = 'ZE004';
  END IF;

  -- BR-01: mechanised cleaning ruled out in writing -------------------------------------------------
  RETURN QUERY
  SELECT 'MECH_WAIVER'::text, w.waiver_id IS NOT NULL,
         CASE WHEN w.waiver_id IS NULL THEN 'No written mechanisation waiver is on file for this job'
              ELSE format('Waiver #%s (%s) approved on %s', w.waiver_id, w.reason_code, local_date(w.approved_at)) END
  FROM (SELECT 1) AS one LEFT JOIN mechanisation_waiver w ON w.job_id = v_job_id;

  -- BR-05: contractor active and licensed -----------------------------------------------------------
  RETURN QUERY
  SELECT 'CONTRACTOR_OK'::text, c.status = 'ACTIVE' AND c.licence_valid_until >= v_today,
         CASE WHEN c.status <> 'ACTIVE' THEN format('Contractor %s is %s', c.name, c.status)
              WHEN c.licence_valid_until < v_today THEN format('Contractor %s: licence expired on %s', c.name, c.licence_valid_until)
              ELSE format('Contractor %s is active; licence valid until %s', c.name, c.licence_valid_until) END
  FROM contractor c WHERE c.contractor_id = v_contractor_id;

  -- BR-03: crew composition. One role per worker per permit is structural (PK), so a standby can never
  -- also be an entrant; only presence and size need checking. -------------------------------------------
  SELECT count(*) FILTER (WHERE crew_role = 'ENTRANT'), count(*) FILTER (WHERE crew_role = 'STANDBY'),
         count(*) FILTER (WHERE crew_role = 'SUPERVISOR'), count(*)
    INTO v_entrants, v_standby, v_supervisors, v_total
    FROM permit_crew WHERE permit_id = p_permit_id;

  RETURN QUERY VALUES
    ('CREW_ENTRANT'::text,    v_entrants >= 1,    format('%s entrant(s) assigned', v_entrants)),
    ('CREW_SUPERVISOR'::text, v_supervisors >= 1, format('%s supervisor(s) in the crew', v_supervisors)),
    ('CREW_STANDBY'::text,    v_standby >= 1,     format('%s standby (top man) assigned', v_standby)),
    ('CREW_SIZE'::text,       v_total >= v_min_crew, format('%s of the required %s crew members assigned', v_total, v_min_crew));

  -- BR-04: every crew member fit and trained on the day ------------------------------------------------
  RETURN QUERY
  SELECT 'CREW_FIT'::text, count(*) = 0,
         CASE WHEN count(*) = 0 THEN 'Every crew member is active, medically fit and trained'
              ELSE string_agg(format('%s: %s', w.namaste_id, concat_ws(' and ',
                     CASE WHEN NOT w.is_active THEN 'not active' END,
                     CASE WHEN w.medical_fit_until < v_today THEN format('medical fitness expired on %s', w.medical_fit_until) END,
                     CASE WHEN w.trained_until < v_today THEN format('training expired on %s', w.trained_until) END)),
                     '; ' ORDER BY w.namaste_id) END
  FROM permit_crew pc JOIN worker w ON w.worker_id = pc.worker_id
  WHERE pc.permit_id = p_permit_id
    AND (NOT w.is_active OR w.medical_fit_until < v_today OR w.trained_until < v_today);

  -- BR-06: RELATIONAL DIVISION. "Every entrant holds every statutory gear item" is
  --   NOT EXISTS (entrant e, statutory item g such that NOT EXISTS (issue of g to e)).
  -- Guarded against vacuous truth: with no statutory item defined the clause FAILS, it does not pass.
  SELECT count(*) INTO v_statutory FROM gear_item WHERE statutory;
  RETURN QUERY
  WITH missing AS (
    SELECT w.namaste_id, string_agg(g.name, ', ' ORDER BY g.name) AS items
    FROM permit_crew pc
    JOIN worker w ON w.worker_id = pc.worker_id
    CROSS JOIN gear_item g
    WHERE pc.permit_id = p_permit_id AND pc.crew_role = 'ENTRANT' AND g.statutory
      AND NOT EXISTS (SELECT 1 FROM gear_issue gi
                      WHERE gi.permit_id = pc.permit_id AND gi.worker_id = pc.worker_id AND gi.gear_code = g.gear_code)
    GROUP BY w.namaste_id)
  SELECT 'GEAR_ALL'::text,
         v_statutory > 0 AND NOT EXISTS (SELECT 1 FROM missing),
         CASE WHEN v_statutory = 0 THEN 'No statutory gear item is defined, so entry cannot be authorised'
              WHEN EXISTS (SELECT 1 FROM missing)
                THEN (SELECT string_agg(format('%s missing: %s', m.namaste_id, m.items), '; ' ORDER BY m.namaste_id) FROM missing m)
              ELSE format('Every entrant holds all %s statutory items', v_statutory) END;

  -- BR-07: RELATIONAL DIVISION over the three depth levels. The LATEST reading at each level governs,
  -- so a bad reading taken after a good one cannot be hidden behind it. -----------------------------------
  RETURN QUERY
  SELECT ('GAS_' || lv.level)::text,
         x.problems IS NULL,
         COALESCE(x.problems,
                  format('%s: %s min old; O2 %s%%, H2S %s ppm, LEL %s%%, CO %s ppm (detector %s)', lv.level,
                         round(extract(epoch FROM p_at - r.taken_at) / 60), r.o2_pct, r.h2s_ppm, r.lel_pct, r.co_ppm, r.serial_no))
  FROM (VALUES ('TOP'), ('MID'), ('BOTTOM')) AS lv(level)
  LEFT JOIN LATERAL (
    SELECT gr.reading_id, gr.taken_at, gr.o2_pct, gr.h2s_ppm, gr.lel_pct, gr.co_ppm, d.serial_no, d.calibration_valid_until
    FROM gas_reading gr JOIN gas_detector d ON d.detector_id = gr.detector_id
    WHERE gr.permit_id = p_permit_id AND gr.depth_level = lv.level AND gr.taken_at <= p_at
    ORDER BY gr.taken_at DESC, gr.reading_id DESC LIMIT 1) r ON true
  CROSS JOIN LATERAL (
    SELECT NULLIF(concat_ws('; ',
      CASE WHEN r.reading_id IS NULL THEN format('No %s reading has been logged', lv.level) END,
      CASE WHEN r.reading_id IS NOT NULL AND p_at - r.taken_at > v_max_age
           THEN format('Latest %s reading is %s min old (limit %s)', lv.level,
                       round(extract(epoch FROM p_at - r.taken_at) / 60), round(extract(epoch FROM v_max_age) / 60)) END,
      CASE WHEN r.reading_id IS NOT NULL AND r.calibration_valid_until < local_date(r.taken_at)
           THEN format('Detector %s calibration had expired on %s', r.serial_no, r.calibration_valid_until) END,
      CASE WHEN r.reading_id IS NOT NULL AND r.o2_pct NOT BETWEEN v_o2_min AND v_o2_max
           THEN format('O2 %s%% is outside %s-%s%%', r.o2_pct, v_o2_min, v_o2_max) END,
      CASE WHEN r.reading_id IS NOT NULL AND r.h2s_ppm >= v_h2s_max
           THEN format('H2S %s ppm is not below %s', r.h2s_ppm, v_h2s_max) END,
      CASE WHEN r.reading_id IS NOT NULL AND r.lel_pct >= v_lel_max
           THEN format('Combustibles %s%% LEL is not below %s%%', r.lel_pct, v_lel_max) END,
      CASE WHEN r.reading_id IS NOT NULL AND r.co_ppm >= v_co_max
           THEN format('CO %s ppm is not below %s', r.co_ppm, v_co_max) END), '') AS problems) x;
END $$;

-- ---------------------------------------------------------------------------------------------
-- authorise_entry(): the explainable front door. Locks the permit row (concurrent crew/gear/reading
-- inserts take FOR KEY SHARE on it and therefore wait), evaluates once, and either authorises or
-- leaves the permit DRAFT. Returns the full checklist either way so a denial is a compliance report.
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION authorise_entry(p_permit_id bigint, p_actor_id bigint, p_at timestamptz DEFAULT now())
RETURNS TABLE (clause_code text, title text, legal_ref text, passed boolean, detail text, permit_status text)
LANGUAGE plpgsql AS $$
#variable_conflict use_column
DECLARE
  v_status text;
  v_rows   jsonb;
  v_ok     boolean;
BEGIN
  SELECT p.status INTO v_status FROM entry_permit p WHERE p.permit_id = p_permit_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Permit % does not exist', p_permit_id USING ERRCODE = 'ZE004';
  END IF;
  IF v_status <> 'DRAFT' THEN
    RAISE EXCEPTION 'Permit % is % and can no longer be authorised', p_permit_id, v_status USING ERRCODE = 'ZE003';
  END IF;

  SELECT jsonb_agg(jsonb_build_object('clause_code', r.clause_code, 'passed', r.passed, 'detail', r.detail)),
         bool_and(r.passed)
    INTO v_rows, v_ok
    FROM permit_clause_check(p_permit_id, p_at) r;

  IF v_ok THEN
    UPDATE entry_permit SET status = 'AUTHORISED', authorised_at = p_at, authorised_by = p_actor_id
     WHERE permit_id = p_permit_id;                      -- the BEFORE UPDATE gate re-proves it
    v_status := 'AUTHORISED';
  END IF;

  RETURN QUERY
  SELECT x.clause_code, l.title, l.legal_ref, x.passed, x.detail, v_status
    FROM jsonb_to_recordset(v_rows) AS x(clause_code text, passed boolean, detail text)
    JOIN legal_clause l ON l.clause_code = x.clause_code
   ORDER BY l.sort_order;
END $$;

-- ---------------------------------------------------------------------------------------------
-- Permit creation guard: a permit can only be born DRAFT, with a waiver, on a live job, under a
-- SUPERVISOR. Without this an INSERT ... status = 'AUTHORISED' would walk around the UPDATE gate.
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION permit_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_role   text;
  v_jstate text;
BEGIN
  IF NEW.status <> 'DRAFT' OR NEW.authorised_at IS NOT NULL OR NEW.authorised_by IS NOT NULL
     OR NEW.valid_until IS NOT NULL OR NEW.ended_at IS NOT NULL THEN
    RAISE EXCEPTION 'A permit is created as DRAFT; AUTHORISED is reachable only through the clause gate'
      USING ERRCODE = 'ZE003';
  END IF;
  SELECT r.name INTO v_role FROM app_user u JOIN role r ON r.role_id = u.role_id
   WHERE u.user_id = NEW.supervisor_id AND u.is_active;
  IF v_role IS DISTINCT FROM 'SUPERVISOR' THEN
    RAISE EXCEPTION 'The permit supervisor must be an active user with the SUPERVISOR role' USING ERRCODE = 'ZE006';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM mechanisation_waiver WHERE job_id = NEW.job_id) THEN
    RAISE EXCEPTION 'No entry permit without a written mechanisation waiver for the job (mechanised cleaning comes first)'
      USING ERRCODE = 'ZE002';
  END IF;
  SELECT status INTO v_jstate FROM job WHERE job_id = NEW.job_id;
  IF v_jstate NOT IN ('PLANNED', 'IN_PROGRESS') THEN
    RAISE EXCEPTION 'Job % is % and cannot take a new entry permit', NEW.job_id, v_jstate USING ERRCODE = 'ZE003';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_permit_insert_guard BEFORE INSERT ON entry_permit
  FOR EACH ROW EXECUTE FUNCTION permit_insert_guard();

-- ---------------------------------------------------------------------------------------------
-- Permit state machine and THE GATE. DRAFT -> AUTHORISED | CANCELLED; AUTHORISED -> CLOSED | ABORTED.
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION permit_guard() RETURNS trigger LANGUAGE plpgsql AS $$
#variable_conflict use_column
DECLARE
  v_denied text;
  v_role   text;
BEGIN
  IF NEW.job_id <> OLD.job_id THEN
    RAISE EXCEPTION 'A permit cannot be moved to another job' USING ERRCODE = 'ZE003';
  END IF;

  IF NEW.status = OLD.status THEN
    -- Only a DRAFT may be edited in place. An authorised permit is a signed proof and a finished one is evidence:
    -- not even its end_reason (a worker's stop-work reason!) may be rewritten afterwards.
    IF OLD.status <> 'DRAFT' AND NEW IS DISTINCT FROM OLD THEN
      RAISE EXCEPTION 'A % permit cannot be altered', OLD.status USING ERRCODE = 'ZE003';
    END IF;
    RETURN NEW;
  END IF;

  IF NOT ((OLD.status = 'DRAFT' AND NEW.status IN ('AUTHORISED', 'CANCELLED'))
       OR (OLD.status = 'AUTHORISED' AND NEW.status IN ('CLOSED', 'ABORTED'))) THEN
    RAISE EXCEPTION 'A permit cannot change from % to %', OLD.status, NEW.status USING ERRCODE = 'ZE003';
  END IF;

  IF NEW.status = 'AUTHORISED' THEN
    NEW.authorised_at := COALESCE(NEW.authorised_at, now());
    NEW.authorised_by := COALESCE(NEW.authorised_by, app_user_id());
    NEW.valid_until   := NEW.authorised_at + make_interval(mins => rule_num('permit_valid_minutes')::int);

    SELECT r.name INTO v_role FROM app_user u JOIN role r ON r.role_id = u.role_id
     WHERE u.user_id = NEW.authorised_by AND u.is_active;
    IF v_role IS NULL OR v_role NOT IN ('SUPERVISOR', 'ENGINEER') THEN
      RAISE EXCEPTION 'Only an active SUPERVISOR or ENGINEER may authorise an entry' USING ERRCODE = 'ZE006';
    END IF;

    -- THE GATE: any unmet clause denies, whichever client issued the UPDATE.
    SELECT string_agg(format('- %s: %s', l.title, c.detail), E'\n' ORDER BY l.sort_order)
      INTO v_denied
      FROM permit_clause_check(NEW.permit_id, NEW.authorised_at) c
      JOIN legal_clause l ON l.clause_code = c.clause_code
     WHERE NOT c.passed;
    IF v_denied IS NOT NULL THEN
      RAISE EXCEPTION E'Entry denied. Unmet legal clauses:\n%', v_denied USING ERRCODE = 'ZE001';
    END IF;

  ELSIF NEW.status = 'CLOSED' THEN
    IF EXISTS (SELECT 1 FROM entry_log WHERE permit_id = NEW.permit_id AND upper_inf(period)) THEN
      RAISE EXCEPTION 'The permit cannot be closed while a worker is still inside' USING ERRCODE = 'ZE003';
    END IF;
    NEW.ended_at := COALESCE(NEW.ended_at, now());
  ELSE
    NEW.ended_at := COALESCE(NEW.ended_at, now());       -- ABORTED / CANCELLED
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_permit_guard BEFORE UPDATE ON entry_permit
  FOR EACH ROW EXECUTE FUNCTION permit_guard();

-- Only a never-authorised draft with no readings may be deleted (readings are RESTRICTed by their FK).
CREATE FUNCTION permit_delete_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status <> 'DRAFT' THEN
    RAISE EXCEPTION 'A % permit is evidence and cannot be deleted; only drafts can', OLD.status USING ERRCODE = 'ZE003';
  END IF;
  RETURN OLD;
END $$;
CREATE TRIGGER trg_permit_delete_guard BEFORE DELETE ON entry_permit
  FOR EACH ROW EXECUTE FUNCTION permit_delete_guard();

-- ---------------------------------------------------------------------------------------------
-- BR-09: crew and gear are frozen once the permit leaves DRAFT; otherwise the standby could be
-- removed after authorisation and the proof would no longer describe reality.
-- (When a draft permit is deleted the parent row is already gone during the cascade: allow that.)
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION freeze_after_authorisation() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_permit_id bigint;
  v_status    text;
BEGIN
  IF TG_OP = 'DELETE' THEN v_permit_id := OLD.permit_id; ELSE v_permit_id := NEW.permit_id; END IF;
  SELECT status INTO v_status FROM entry_permit WHERE permit_id = v_permit_id;
  IF FOUND AND v_status <> 'DRAFT' THEN
    RAISE EXCEPTION 'Crew and gear are frozen once a permit is % (cancel and re-issue instead)', v_status
      USING ERRCODE = 'ZE003';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_freeze BEFORE INSERT OR UPDATE OR DELETE ON permit_crew
  FOR EACH ROW EXECUTE FUNCTION freeze_after_authorisation();
CREATE TRIGGER trg_freeze BEFORE INSERT OR UPDATE OR DELETE ON gear_issue
  FOR EACH ROW EXECUTE FUNCTION freeze_after_authorisation();

-- ---------------------------------------------------------------------------------------------
-- BR-12 gas readings: the detector must have been in calibration ON THE DAY OF THE READING, the
-- reading cannot be dated in the future, the recorder must be a supervisor or engineer (digital
-- sign-off), and the permit must still be open. Readings are append-only (0004).
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION gas_reading_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_status text;
  v_valid  date;
  v_serial text;
  v_role   text;
BEGIN
  SELECT status INTO v_status FROM entry_permit WHERE permit_id = NEW.permit_id;
  IF v_status NOT IN ('DRAFT', 'AUTHORISED') THEN
    RAISE EXCEPTION 'Readings cannot be added to a % permit', v_status USING ERRCODE = 'ZE003';
  END IF;
  SELECT calibration_valid_until, serial_no INTO v_valid, v_serial FROM gas_detector WHERE detector_id = NEW.detector_id;
  IF v_valid < local_date(NEW.taken_at) THEN
    RAISE EXCEPTION 'Detector % calibration expired on %: a reading taken on % is refused', v_serial, v_valid, local_date(NEW.taken_at)
      USING ERRCODE = 'ZE002';
  END IF;
  IF NEW.taken_at > now() + interval '5 minutes' THEN
    RAISE EXCEPTION 'A gas reading cannot be dated in the future' USING ERRCODE = 'ZE002';
  END IF;
  SELECT r.name INTO v_role FROM app_user u JOIN role r ON r.role_id = u.role_id
   WHERE u.user_id = NEW.recorded_by AND u.is_active;
  IF v_role IS NULL OR v_role NOT IN ('SUPERVISOR', 'ENGINEER') THEN
    RAISE EXCEPTION 'Only an active SUPERVISOR or ENGINEER may sign off a gas reading' USING ERRCODE = 'ZE006';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_gas_reading_guard BEFORE INSERT ON gas_reading
  FOR EACH ROW EXECUTE FUNCTION gas_reading_guard();

-- ---------------------------------------------------------------------------------------------
-- BR-10 entry log: permit AUTHORISED and inside its validity window, worker is an ENTRANT, at most
-- max_continuous_minutes, daylight only (both ends, same IST day). Overlap for one worker is the
-- exclusion constraint's job, not this trigger's. UPDATE may only set the exit time of an open entry.
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION entry_log_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  p        entry_permit%ROWTYPE;
  v_role   text;
  v_max    interval := make_interval(mins => rule_num('max_continuous_minutes')::int);
  v_ls     timestamp;
  v_le     timestamp;
  v_d_from int := (rule_num('daylight_start_hour') * 60)::int;
  v_d_to   int := (rule_num('daylight_end_hour') * 60)::int;
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF NEW.permit_id <> OLD.permit_id OR NEW.worker_id <> OLD.worker_id OR lower(NEW.period) <> lower(OLD.period) THEN
      RAISE EXCEPTION 'Only the exit time of an open entry can be recorded' USING ERRCODE = 'ZE003';
    END IF;
    IF NOT upper_inf(OLD.period) THEN
      RAISE EXCEPTION 'This entry is already closed' USING ERRCODE = 'ZE003';
    END IF;
  END IF;

  SELECT * INTO p FROM entry_permit WHERE permit_id = NEW.permit_id;
  IF p.status <> 'AUTHORISED' THEN
    RAISE EXCEPTION 'Entries need an AUTHORISED permit; this permit is %', p.status USING ERRCODE = 'ZE003';
  END IF;

  SELECT crew_role INTO v_role FROM permit_crew WHERE permit_id = NEW.permit_id AND worker_id = NEW.worker_id;
  IF v_role <> 'ENTRANT' THEN
    RAISE EXCEPTION 'Only a crew member with the ENTRANT role may enter (this worker is %)', v_role USING ERRCODE = 'ZE002';
  END IF;

  IF lower(NEW.period) < p.authorised_at OR lower(NEW.period) >= p.valid_until
     OR (NOT upper_inf(NEW.period) AND upper(NEW.period) > p.valid_until) THEN
    RAISE EXCEPTION 'The entry is outside the permit validity window (% to % IST)',
      to_char(local_ts(p.authorised_at), 'YYYY-MM-DD HH24:MI'), to_char(local_ts(p.valid_until), 'YYYY-MM-DD HH24:MI')
      USING ERRCODE = 'ZE002';
  END IF;

  IF NOT upper_inf(NEW.period) AND upper(NEW.period) - lower(NEW.period) > v_max THEN
    RAISE EXCEPTION 'An entry of % minutes exceeds the % minute continuous-work limit',
      round(extract(epoch FROM upper(NEW.period) - lower(NEW.period)) / 60), round(extract(epoch FROM v_max) / 60)
      USING ERRCODE = 'ZE002';
  END IF;

  v_ls := local_ts(lower(NEW.period));
  v_le := local_ts(COALESCE(upper(NEW.period), lower(NEW.period)));
  IF v_ls::date <> v_le::date
     OR extract(hour FROM v_ls) * 60 + extract(minute FROM v_ls) < v_d_from
     OR extract(hour FROM v_le) * 60 + extract(minute FROM v_le) > v_d_to THEN
    RAISE EXCEPTION 'Entries are allowed in daylight only (% to % IST)',
      lpad((v_d_from / 60)::text, 2, '0') || ':' || lpad((v_d_from % 60)::text, 2, '0'),
      lpad((v_d_to / 60)::text, 2, '0') || ':' || lpad((v_d_to % 60)::text, 2, '0')
      USING ERRCODE = 'ZE002';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_entry_log_guard BEFORE INSERT OR UPDATE ON entry_log
  FOR EACH ROW EXECUTE FUNCTION entry_log_guard();

-- ---------------------------------------------------------------------------------------------
-- BR-01 / BR-02 waivers and job method. The job becomes MANUAL_EXCEPTION only through a waiver.
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION waiver_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_role      text;
  v_jstatus   text;
  v_complaint bigint;
BEGIN
  SELECT r.name INTO v_role FROM app_user u JOIN role r ON r.role_id = u.role_id
   WHERE u.user_id = NEW.approved_by AND u.is_active;
  IF v_role IS DISTINCT FROM 'ENGINEER' THEN
    RAISE EXCEPTION 'Only the Responsible Sanitation Authority (an active ENGINEER) may approve a mechanisation waiver'
      USING ERRCODE = 'ZE006';
  END IF;
  SELECT status, complaint_id INTO v_jstatus, v_complaint FROM job WHERE job_id = NEW.job_id;
  IF v_jstatus NOT IN ('PLANNED', 'IN_PROGRESS') THEN
    RAISE EXCEPTION 'Job % is % and cannot take a waiver', NEW.job_id, v_jstatus USING ERRCODE = 'ZE003';
  END IF;
  IF NEW.reason_code = 'MACHINE_FAILED' AND NOT EXISTS (
       SELECT 1 FROM machine_deployment d JOIN job j ON j.job_id = d.job_id
        WHERE j.complaint_id = v_complaint AND d.outcome = 'FAILED') THEN
    RAISE EXCEPTION 'Reason MACHINE_FAILED needs a recorded FAILED machine deployment for this complaint'
      USING ERRCODE = 'ZE002';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_waiver_guard BEFORE INSERT ON mechanisation_waiver
  FOR EACH ROW EXECUTE FUNCTION waiver_guard();

CREATE FUNCTION waiver_apply() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  UPDATE job SET method = 'MANUAL_EXCEPTION' WHERE job_id = NEW.job_id;
  RETURN NULL;
END $$;
CREATE TRIGGER trg_waiver_apply AFTER INSERT ON mechanisation_waiver
  FOR EACH ROW EXECUTE FUNCTION waiver_apply();

CREATE FUNCTION job_method_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.method = 'MANUAL_EXCEPTION' AND NOT EXISTS (SELECT 1 FROM mechanisation_waiver WHERE job_id = NEW.job_id) THEN
    RAISE EXCEPTION 'A job becomes MANUAL_EXCEPTION only through a written waiver' USING ERRCODE = 'ZE003';
  END IF;
  IF NEW.method = 'MECHANISED' AND OLD.method = 'MANUAL_EXCEPTION' THEN
    RAISE EXCEPTION 'A job with a waiver cannot revert to MECHANISED' USING ERRCODE = 'ZE003';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_job_method_guard BEFORE UPDATE OF method ON job
  FOR EACH ROW EXECUTE FUNCTION job_method_guard();

-- BR-22: a suspended or blacklisted contractor cannot be given new work; jobs start MECHANISED.
CREATE FUNCTION job_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  c contractor%ROWTYPE;
BEGIN
  IF NEW.method <> 'MECHANISED' THEN
    RAISE EXCEPTION 'A job starts MECHANISED; manual entry needs a waiver' USING ERRCODE = 'ZE003';
  END IF;
  SELECT * INTO c FROM contractor WHERE contractor_id = NEW.contractor_id;
  IF c.status <> 'ACTIVE' THEN
    RAISE EXCEPTION 'Contractor % is % and cannot be assigned jobs', c.name, c.status USING ERRCODE = 'ZE003';
  END IF;
  IF c.licence_valid_until < local_date(now()) THEN
    RAISE EXCEPTION 'Contractor %: licence expired on %', c.name, c.licence_valid_until USING ERRCODE = 'ZE003';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_job_insert_guard BEFORE INSERT ON job
  FOR EACH ROW EXECUTE FUNCTION job_insert_guard();

-- ---------------------------------------------------------------------------------------------
-- Row scoping must be well-formed or row-level security would silently show the wrong rows:
-- CONTRACTOR logins carry a contractor, WORKER logins carry a worker, nobody else carries either.
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION app_user_scope_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_role text;
BEGIN
  SELECT name INTO v_role FROM role WHERE role_id = NEW.role_id;
  IF v_role = 'CONTRACTOR' AND (NEW.contractor_id IS NULL OR NEW.worker_id IS NOT NULL) THEN
    RAISE EXCEPTION 'A CONTRACTOR user must be linked to exactly a contractor' USING ERRCODE = 'ZE002';
  ELSIF v_role = 'WORKER' AND (NEW.worker_id IS NULL OR NEW.contractor_id IS NOT NULL) THEN
    RAISE EXCEPTION 'A WORKER user must be linked to exactly a worker' USING ERRCODE = 'ZE002';
  ELSIF v_role NOT IN ('CONTRACTOR', 'WORKER') AND (NEW.contractor_id IS NOT NULL OR NEW.worker_id IS NOT NULL) THEN
    RAISE EXCEPTION 'Only CONTRACTOR and WORKER users are linked to a contractor or worker' USING ERRCODE = 'ZE002';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_app_user_scope_guard BEFORE INSERT OR UPDATE OF role_id, contractor_id, worker_id ON app_user
  FOR EACH ROW EXECUTE FUNCTION app_user_scope_guard();
