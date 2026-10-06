-- 0010_permit_evidence_locking.sql
-- Concurrency fix for the default-deny proof (BR-08, BR-09, BR-10, BR-11).
--
-- Before: the guards on crew, gear, gas readings and entries read the permit's status with a plain SELECT. Under READ
-- COMMITTED, a second session could remove the standby (or add an un-geared entrant) while authorise_entry() was
-- deciding, or start an entry while the permit was being closed, and BOTH transactions committed: an AUTHORISED permit
-- whose proof no longer held, or a CLOSED permit with a worker still inside. tests/db/test_concurrency.py reproduces
-- all three cases.
--
-- Now every guard first takes FOR SHARE on the permit row. That lock conflicts with authorise_entry()'s FOR UPDATE and
-- with any UPDATE of the permit, so a change to the evidence and a change of the permit's status are serialised: whoever
-- comes second waits, then re-reads the committed state (each statement in a PL/pgSQL function takes a fresh snapshot
-- under READ COMMITTED) and is refused if it no longer holds.

-- Runs as the owner so row-level security cannot hide the row from the lock (a SELECT ... FOR SHARE is also subject to
-- UPDATE policies). It only locks; it returns nothing, so it reveals nothing about permits the caller cannot see.
CREATE FUNCTION lock_permit(p_permit_id bigint) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  PERFORM 1 FROM entry_permit WHERE permit_id = p_permit_id FOR SHARE;
END $$;

-- BR-09: crew and gear are frozen once the permit leaves DRAFT (unchanged rule, now race-free).
CREATE OR REPLACE FUNCTION freeze_after_authorisation() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_permit_id bigint;
  v_status    text;
BEGIN
  IF TG_OP = 'DELETE' THEN v_permit_id := OLD.permit_id; ELSE v_permit_id := NEW.permit_id; END IF;
  PERFORM lock_permit(v_permit_id);
  SELECT status INTO v_status FROM entry_permit WHERE permit_id = v_permit_id;
  -- Not found only while a draft permit is being deleted and this row goes with it in the cascade: allow that.
  IF FOUND AND v_status <> 'DRAFT' THEN
    RAISE EXCEPTION 'Crew and gear are frozen once a permit is % (cancel and re-issue instead)', v_status
      USING ERRCODE = 'ZE003';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;

-- BR-12 gas readings (unchanged rules, now race-free with a concurrent close/abort).
CREATE OR REPLACE FUNCTION gas_reading_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_status text;
  v_valid  date;
  v_serial text;
  v_role   text;
BEGIN
  PERFORM lock_permit(NEW.permit_id);
  SELECT status INTO v_status FROM entry_permit WHERE permit_id = NEW.permit_id;
  IF v_status IS DISTINCT FROM 'DRAFT' AND v_status IS DISTINCT FROM 'AUTHORISED' THEN
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

-- BR-10 entry log (unchanged rules, now race-free with a concurrent close/abort).
CREATE OR REPLACE FUNCTION entry_log_guard() RETURNS trigger LANGUAGE plpgsql AS $$
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

  PERFORM lock_permit(NEW.permit_id);
  SELECT * INTO p FROM entry_permit WHERE permit_id = NEW.permit_id;
  IF p.status IS DISTINCT FROM 'AUTHORISED' THEN
    RAISE EXCEPTION 'Entries need an AUTHORISED permit; this permit is %', p.status USING ERRCODE = 'ZE003';
  END IF;

  SELECT crew_role INTO v_role FROM permit_crew WHERE permit_id = NEW.permit_id AND worker_id = NEW.worker_id;
  IF v_role IS DISTINCT FROM 'ENTRANT' THEN
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
