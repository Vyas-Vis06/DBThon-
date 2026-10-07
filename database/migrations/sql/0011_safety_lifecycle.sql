-- 0011_safety_lifecycle.sql
-- Continuing authorization, truthful exit capture, immutable safety events, and Rule 6(3)(k) rest.

-- Rule 6(3)(k)(ii) requires a mandatory 30-minute interval between 90-minute stretches. This is a
-- legal parameter, not a product assumption. The interval is measured from the later of the reported
-- exit instant and the server receipt instant so an old client timestamp cannot shorten the rest.
INSERT INTO rule_parameter (param_key, value, unit, description, legal_ref, is_assumption)
VALUES ('mandatory_rest_minutes', 30, 'minutes', 'Mandatory interval between 90-minute cleaning stretches',
        'Prohibition of Employment as Manual Scavengers and their Rehabilitation Rules, 2013, Rule 6(3)(k)(ii)', false);

-- Keep the real-world exit time and the server's receipt time as separate facts. `recorded_at` is also
-- reset by the trigger on INSERT, because a runtime client must not choose either receipt timestamp.
ALTER TABLE entry_log ADD COLUMN exit_recorded_at timestamptz;
COMMENT ON COLUMN entry_log.exit_recorded_at IS 'Server receipt instant for the reported exit; period upper bound remains the reported event time.';

-- Durable local event evidence. This is a database event record, not a claim of external delivery.
CREATE TABLE permit_safety_event (
  event_id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  permit_id   bigint NOT NULL REFERENCES entry_permit,
  entry_id    bigint REFERENCES entry_log,
  event_key   text NOT NULL UNIQUE CHECK (length(btrim(event_key)) > 0),
  event_type  text NOT NULL CHECK (event_type IN
               ('PERMIT_ABORTED', 'SAFETY_STOP', 'OPEN_ENTRY_OVERSTAY', 'EXIT_VIOLATION')),
  reason_code text NOT NULL CHECK (reason_code = upper(reason_code)),
  detail      jsonb NOT NULL DEFAULT '{}'::jsonb,
  occurred_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE permit_safety_event DROP CONSTRAINT permit_safety_event_entry_id_fkey;
ALTER TABLE permit_safety_event ADD CONSTRAINT permit_safety_event_entry_id_fkey
  FOREIGN KEY (entry_id) REFERENCES entry_log(entry_id) DEFERRABLE INITIALLY DEFERRED;
COMMENT ON TABLE permit_safety_event IS 'Append-only local safety event evidence; it does not assert external delivery.';

CREATE TRIGGER trg_audit AFTER INSERT ON permit_safety_event
  FOR EACH ROW EXECUTE FUNCTION audit_row('event_id');
CREATE TRIGGER trg_append_only BEFORE UPDATE OR DELETE ON permit_safety_event
  FOR EACH ROW EXECUTE FUNCTION forbid_change();

ALTER TABLE permit_safety_event ENABLE ROW LEVEL SECURITY;
CREATE POLICY rls_select ON permit_safety_event FOR SELECT
  USING (app_is_staff() OR worker_on_permit(permit_id) OR contractor_owns_permit(permit_id));

-- Only owner-run triggers/functions insert events. The runtime role may read scoped rows, but cannot
-- invent, rewrite, or delete safety evidence directly.
REVOKE INSERT, UPDATE, DELETE ON permit_safety_event FROM ze_app;
REVOKE ALL ON SEQUENCE permit_safety_event_event_id_seq FROM ze_app;
GRANT SELECT ON permit_safety_event TO ze_app;
REVOKE UPDATE, DELETE ON entry_log FROM ze_app;
GRANT UPDATE (period) ON entry_log TO ze_app;

CREATE FUNCTION append_permit_safety_event(
  p_permit_id bigint,
  p_entry_id bigint,
  p_event_key text,
  p_event_type text,
  p_reason_code text,
  p_detail jsonb
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  INSERT INTO permit_safety_event (permit_id, entry_id, event_key, event_type, reason_code, detail, occurred_at)
  VALUES (p_permit_id, p_entry_id, p_event_key, p_event_type, p_reason_code, COALESCE(p_detail, '{}'::jsonb), clock_timestamp())
  ON CONFLICT (event_key) DO NOTHING;
END $$;
REVOKE ALL ON FUNCTION append_permit_safety_event(bigint, bigint, text, text, text, jsonb) FROM PUBLIC, ze_app;

-- Every completed AUTHORIZED -> ABORTED transition gets a durable lifecycle event, whether the cause
-- was an operator stop, a fatality, an unsafe dependency change, or an automatic sweep.
CREATE FUNCTION permit_abort_event() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  PERFORM append_permit_safety_event(
    NEW.permit_id, NULL, format('permit:%s:aborted', NEW.permit_id), 'PERMIT_ABORTED', 'PERMIT_ABORTED',
    jsonb_build_object('from_status', OLD.status, 'to_status', NEW.status, 'end_reason', NEW.end_reason,
                       'ended_at', NEW.ended_at, 'actor_user_id', app_user_id()));
  RETURN NULL;
END $$;
CREATE TRIGGER trg_permit_abort_event AFTER UPDATE OF status ON entry_permit
  FOR EACH ROW WHEN (OLD.status = 'AUTHORISED' AND NEW.status = 'ABORTED')
  EXECUTE FUNCTION permit_abort_event();
REVOKE ALL ON FUNCTION permit_abort_event() FROM PUBLIC, ze_app;

CREATE FUNCTION stop_permit_for_safety(p_permit_id bigint, p_reason_code text, p_detail jsonb)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  p entry_permit%ROWTYPE;
  v_now timestamptz := clock_timestamp();
  v_reason text;
BEGIN
  SELECT * INTO p FROM entry_permit WHERE permit_id = p_permit_id FOR UPDATE;
  IF NOT FOUND OR p.status <> 'AUTHORISED' THEN RETURN false; END IF;

  IF p_reason_code = 'INCIDENT_RECORDED' THEN
    -- record_incident() changes contractor status before its own permit UPDATE. Preserve the
    -- procedure's incident-specific stop reason for permits on that incident's job; other jobs
    -- for the same contractor still get a contractor-dependency stop.
    v_reason := format('Stop-work: %s recorded (incident #%s)',
                       lower(p_detail ->> 'incident_type'), p_detail ->> 'incident_id');
  ELSE
    v_reason := format('Automatic safety stop (%s): %s', p_reason_code,
                       COALESCE(NULLIF(p_detail ->> 'summary', ''), 'current authorization conditions no longer pass'));
  END IF;
  UPDATE entry_permit
     SET status = 'ABORTED', ended_at = v_now, end_reason = v_reason
   WHERE permit_id = p_permit_id;

  PERFORM append_permit_safety_event(
    p_permit_id, NULL, format('permit:%s:safety-stop', p_permit_id), 'SAFETY_STOP', p_reason_code,
    COALESCE(p_detail, '{}'::jsonb) || jsonb_build_object('stopped_at', v_now, 'end_reason', v_reason));
  RETURN true;
END $$;
REVOKE ALL ON FUNCTION stop_permit_for_safety(bigint, text, jsonb) FROM PUBLIC, ze_app;

-- Re-evaluate the full current clause set and permit time limit while holding the permit row. Caller
-- dependency triggers take the changed worker/contractor/detector row first, then this permit row;
-- entry admission follows the same dependency-before-permit order.
CREATE FUNCTION revalidate_authorised_permit(p_permit_id bigint, p_source text)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  p entry_permit%ROWTYPE;
  v_now timestamptz := clock_timestamp();
  v_failed jsonb;
  v_codes text;
BEGIN
  SELECT * INTO p FROM entry_permit WHERE permit_id = p_permit_id FOR UPDATE;
  IF NOT FOUND OR p.status <> 'AUTHORISED' THEN RETURN false; END IF;

  IF p.valid_until <= v_now THEN
    RETURN stop_permit_for_safety(p_permit_id, 'PERMIT_EXPIRED',
      jsonb_build_object('source', p_source, 'summary', 'permit validity window has expired', 'valid_until', p.valid_until,
                         'evaluated_at', v_now));
  END IF;

  SELECT COALESCE(jsonb_agg(jsonb_build_object('clause_code', c.clause_code, 'detail', c.detail)
                            ORDER BY c.clause_code), '[]'::jsonb),
         string_agg(c.clause_code, ', ' ORDER BY c.clause_code)
    INTO v_failed, v_codes
    FROM permit_clause_check(p_permit_id, v_now) c
   WHERE NOT c.passed;
  IF v_codes IS NULL THEN RETURN false; END IF;

  RETURN stop_permit_for_safety(p_permit_id, 'CURRENT_CLAUSE_FAILED',
    jsonb_build_object('source', p_source, 'summary', 'current authorization clauses failed: ' || v_codes,
                       'failed_clauses', v_failed, 'evaluated_at', v_now));
END $$;
REVOKE ALL ON FUNCTION revalidate_authorised_permit(bigint, text) FROM PUBLIC, ze_app;

-- F1: parent identity may not be moved in place. Checking NEW only misses the old authorised parent.
-- DRAFT rows can still be edited normally, but a row's permit/crew identity is stable for its lifetime.
CREATE OR REPLACE FUNCTION freeze_after_authorisation() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  v_permit_id bigint;
  v_status text;
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF NEW.permit_id IS DISTINCT FROM OLD.permit_id
       OR (TG_TABLE_NAME = 'permit_crew' AND NEW.worker_id IS DISTINCT FROM OLD.worker_id)
       OR (TG_TABLE_NAME = 'gear_issue' AND NEW.worker_id IS DISTINCT FROM OLD.worker_id) THEN
      RAISE EXCEPTION 'Permit and crew parent identifiers are immutable; delete and re-create the row while its permit is DRAFT'
        USING ERRCODE = 'ZE003';
    END IF;
  END IF;

  IF TG_OP = 'DELETE' THEN v_permit_id := OLD.permit_id; ELSE v_permit_id := NEW.permit_id; END IF;
  PERFORM lock_permit(v_permit_id);
  SELECT status INTO v_status FROM entry_permit WHERE permit_id = v_permit_id;
  -- Not found only while a draft permit is being deleted and this row goes with it in the cascade.
  IF FOUND AND v_status <> 'DRAFT' THEN
    RAISE EXCEPTION 'Crew and gear are frozen once a permit is % (cancel and re-issue instead)', v_status
      USING ERRCODE = 'ZE003';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION freeze_after_authorisation() FROM PUBLIC, ze_app;
-- Trigger code needs this owner-only lock helper; direct runtime calls could otherwise lock arbitrary permits.
REVOKE ALL ON FUNCTION lock_permit(bigint) FROM PUBLIC, ze_app;

-- Gas insertions serialize against entry admission, then immediately stop an active authorization if
-- a new latest reading makes any clause fail. A safe new reading leaves the permit authorized.
CREATE OR REPLACE FUNCTION gas_reading_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  v_status text;
  v_valid date;
  v_serial text;
  v_role text;
BEGIN
  SELECT status INTO v_status FROM entry_permit WHERE permit_id = NEW.permit_id FOR UPDATE;
  IF v_status IS DISTINCT FROM 'DRAFT' AND v_status IS DISTINCT FROM 'AUTHORISED' THEN
    RAISE EXCEPTION 'Readings cannot be added to a % permit', v_status USING ERRCODE = 'ZE003';
  END IF;
  SELECT calibration_valid_until, serial_no INTO v_valid, v_serial
    FROM gas_detector WHERE detector_id = NEW.detector_id;
  IF v_valid < local_date(NEW.taken_at) THEN
    RAISE EXCEPTION 'Detector % calibration expired on %: a reading taken on % is refused',
      v_serial, v_valid, local_date(NEW.taken_at) USING ERRCODE = 'ZE002';
  END IF;
  IF NEW.taken_at > clock_timestamp() + interval '5 minutes' THEN
    RAISE EXCEPTION 'A gas reading cannot be dated more than five minutes in the future' USING ERRCODE = 'ZE002';
  END IF;
  SELECT r.name INTO v_role FROM app_user u JOIN role r ON r.role_id = u.role_id
   WHERE u.user_id = NEW.recorded_by AND u.is_active;
  IF v_role IS NULL OR v_role NOT IN ('SUPERVISOR', 'ENGINEER') THEN
    RAISE EXCEPTION 'Only an active SUPERVISOR or ENGINEER may sign off a gas reading' USING ERRCODE = 'ZE006';
  END IF;
  NEW.recorded_at := clock_timestamp();
  RETURN NEW;
END $$;
ALTER FUNCTION gas_reading_guard() SET search_path = public, pg_temp;

CREATE FUNCTION gas_reading_revalidate() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  PERFORM revalidate_authorised_permit(NEW.permit_id, 'gas_reading');
  RETURN NULL;
END $$;
CREATE TRIGGER trg_gas_reading_revalidate AFTER INSERT ON gas_reading
  FOR EACH ROW EXECUTE FUNCTION gas_reading_revalidate();
REVOKE ALL ON FUNCTION gas_reading_revalidate() FROM PUBLIC, ze_app;

-- Database entry behavior has two paths:
--   INSERT / open interval: current-clock admission and current clause recheck. Unsafe authorization is
--     durably aborted, and RETURN NULL suppresses the log row without rolling that stop back.
--   UPDATE / existing open interval: always retain the reported physical exit, even after abort, expiry,
--     gas-feed loss, a daylight overrun, or >90 minutes. Append violation evidence with server receipt time.
CREATE OR REPLACE FUNCTION entry_log_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  p entry_permit%ROWTYPE;
  v_role text;
  v_now timestamptz := clock_timestamp();
  v_max interval := make_interval(mins => rule_num('max_continuous_minutes')::int);
  v_rest interval := make_interval(mins => rule_num('mandatory_rest_minutes')::int);
  v_d_from int := (rule_num('daylight_start_hour') * 60)::int;
  v_d_to int := (rule_num('daylight_end_hour') * 60)::int;
  v_ls timestamp;
  v_le timestamp;
  v_minute_now int;
  v_duration interval;
  v_exit_received timestamptz;
  v_violations jsonb := '[]'::jsonb;
  v_violation_count int := 0;
  v_reported_end timestamptz;
  v_recorded_duration interval;
  v_rest_until timestamptz;
  v_is_historical boolean;
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF NEW.permit_id IS DISTINCT FROM OLD.permit_id OR NEW.worker_id IS DISTINCT FROM OLD.worker_id
       OR lower(NEW.period) IS DISTINCT FROM lower(OLD.period)
       OR NEW.recorded_by IS DISTINCT FROM OLD.recorded_by
       OR NEW.recorded_at IS DISTINCT FROM OLD.recorded_at
       OR NEW.exit_recorded_at IS DISTINCT FROM OLD.exit_recorded_at THEN
      RAISE EXCEPTION 'Only the exit time of an open entry can be recorded' USING ERRCODE = 'ZE003';
    END IF;
    IF NOT upper_inf(OLD.period) THEN
      RAISE EXCEPTION 'This entry is already closed' USING ERRCODE = 'ZE003';
    END IF;
    IF upper_inf(NEW.period) THEN
      RAISE EXCEPTION 'An exit time is required to close an open entry' USING ERRCODE = 'ZE002';
    END IF;

    -- Exit closure must not wait for (or undo) a concurrent stop. The entry row itself is locked by
    -- PostgreSQL, while the permit status is observed for evidence only.
    SELECT * INTO p FROM entry_permit WHERE permit_id = NEW.permit_id;
    IF upper(NEW.period) <= lower(NEW.period) THEN
      RAISE EXCEPTION 'An exit must be after the entry time' USING ERRCODE = 'ZE002';
    END IF;

    v_exit_received := clock_timestamp();
    NEW.exit_recorded_at := v_exit_received;
    v_reported_end := upper(NEW.period);
    IF v_reported_end > v_exit_received + interval '5 minutes' THEN
      RAISE EXCEPTION 'An exit time cannot be more than five minutes ahead of the server clock' USING ERRCODE = 'ZE002';
    END IF;
    v_recorded_duration := v_exit_received - OLD.recorded_at;
    v_duration := v_reported_end - lower(NEW.period);
    v_ls := local_ts(lower(NEW.period));
    v_le := local_ts(v_reported_end);

    IF v_reported_end > v_exit_received THEN
      v_violation_count := v_violation_count + 1;
      v_violations := v_violations || jsonb_build_array(jsonb_build_object(
        'reason_code', 'EXIT_TIME_AHEAD_OF_RECEIPT', 'reported_exit_at', v_reported_end,
        'exit_recorded_at', v_exit_received,
        'ahead_seconds', round(extract(epoch FROM v_reported_end - v_exit_received))));
      PERFORM append_permit_safety_event(NEW.permit_id, OLD.entry_id,
        format('entry:%s:exit:EXIT_TIME_AHEAD_OF_RECEIPT', OLD.entry_id), 'EXIT_VIOLATION', 'EXIT_TIME_AHEAD_OF_RECEIPT',
        jsonb_build_object('reported_exit_at', v_reported_end, 'exit_recorded_at', v_exit_received,
                           'ahead_seconds', round(extract(epoch FROM v_reported_end - v_exit_received))));
    END IF;

    IF v_duration > v_max OR v_recorded_duration > v_max THEN
      v_violation_count := v_violation_count + 1;
      v_violations := v_violations || jsonb_build_array(jsonb_build_object(
        'reason_code', 'DURATION_OVERRUN', 'reported_minutes', round(extract(epoch FROM v_duration) / 60),
        'server_observed_minutes', round(extract(epoch FROM v_recorded_duration) / 60),
        'limit_minutes', round(extract(epoch FROM v_max) / 60)));
      PERFORM append_permit_safety_event(NEW.permit_id, OLD.entry_id,
        format('entry:%s:exit:DURATION_OVERRUN', OLD.entry_id), 'EXIT_VIOLATION', 'DURATION_OVERRUN',
        jsonb_build_object('reported_entry_at', lower(NEW.period), 'reported_exit_at', v_reported_end,
                           'entry_recorded_at', OLD.recorded_at, 'exit_recorded_at', v_exit_received,
                           'reported_minutes', round(extract(epoch FROM v_duration) / 60),
                           'server_observed_minutes', round(extract(epoch FROM v_recorded_duration) / 60),
                           'limit_minutes', round(extract(epoch FROM v_max) / 60)));
    END IF;

    IF lower(NEW.period) < p.authorised_at OR lower(NEW.period) >= p.valid_until
       OR v_reported_end > p.valid_until THEN
      v_violation_count := v_violation_count + 1;
      v_violations := v_violations || jsonb_build_array(jsonb_build_object(
        'reason_code', 'PERMIT_WINDOW_OVERRUN', 'authorised_at', p.authorised_at, 'valid_until', p.valid_until,
        'reported_entry_at', lower(NEW.period), 'reported_exit_at', v_reported_end, 'exit_recorded_at', v_exit_received));
      PERFORM append_permit_safety_event(NEW.permit_id, OLD.entry_id,
        format('entry:%s:exit:PERMIT_WINDOW_OVERRUN', OLD.entry_id), 'EXIT_VIOLATION', 'PERMIT_WINDOW_OVERRUN',
        jsonb_build_object('authorised_at', p.authorised_at, 'valid_until', p.valid_until,
                           'reported_entry_at', lower(NEW.period), 'reported_exit_at', v_reported_end,
                           'exit_recorded_at', v_exit_received));
    END IF;

    IF v_ls::date <> v_le::date
       OR extract(hour FROM v_ls)::int * 60 + extract(minute FROM v_ls)::int < v_d_from
       OR extract(hour FROM v_le)::int * 60 + extract(minute FROM v_le)::int > v_d_to THEN
      v_violation_count := v_violation_count + 1;
      v_violations := v_violations || jsonb_build_array(jsonb_build_object(
        'reason_code', 'DAYLIGHT_OVERRUN', 'reported_entry_at', lower(NEW.period), 'reported_exit_at', v_reported_end,
        'exit_recorded_at', v_exit_received, 'daylight_start_minute', v_d_from, 'daylight_end_minute', v_d_to));
      PERFORM append_permit_safety_event(NEW.permit_id, OLD.entry_id,
        format('entry:%s:exit:DAYLIGHT_OVERRUN', OLD.entry_id), 'EXIT_VIOLATION', 'DAYLIGHT_OVERRUN',
        jsonb_build_object('reported_entry_at', lower(NEW.period), 'reported_exit_at', v_reported_end,
                           'exit_recorded_at', v_exit_received, 'daylight_start_minute', v_d_from,
                           'daylight_end_minute', v_d_to));
    END IF;

    IF p.status <> 'AUTHORISED' THEN
      PERFORM append_permit_safety_event(NEW.permit_id, OLD.entry_id,
        format('entry:%s:exit:AFTER_PERMIT_STOP', OLD.entry_id), 'EXIT_VIOLATION', 'EXIT_AFTER_PERMIT_STOP',
        jsonb_build_object('permit_status', p.status, 'permit_end_reason', p.end_reason,
                           'reported_exit_at', v_reported_end, 'exit_recorded_at', v_exit_received));
    END IF;

    IF v_violation_count > 0 AND p.status = 'AUTHORISED' THEN
      -- The permit remains AUTHORIZED/CLOSED/ABORTED as recorded. The event classifies a real overrun;
      -- it never rewrites the permit's state or its stop reason.
      PERFORM append_permit_safety_event(NEW.permit_id, OLD.entry_id,
        format('entry:%s:exit:VIOLATIONS', OLD.entry_id), 'EXIT_VIOLATION', 'ENTRY_EXIT_OVERRUN',
        jsonb_build_object('violations', v_violations, 'reported_entry_at', lower(NEW.period),
                           'reported_exit_at', v_reported_end, 'exit_recorded_at', v_exit_received));
    END IF;
    RETURN NEW;
  END IF;

  -- Both open admissions and completed historical reports retain crew identity and role checks.
  -- A closed INSERT is an imported/reported past interval; it is not a way to manufacture a current
  -- admission. The API always creates an open row first, so a new entry must pass the live gate below.
  PERFORM 1 FROM worker WHERE worker_id = NEW.worker_id FOR UPDATE;
  SELECT * INTO p FROM entry_permit WHERE permit_id = NEW.permit_id FOR UPDATE;
  IF p.permit_id IS NULL THEN
    RAISE EXCEPTION 'Permit % does not exist', NEW.permit_id USING ERRCODE = 'ZE004';
  END IF;
  SELECT crew_role INTO v_role FROM permit_crew WHERE permit_id = NEW.permit_id AND worker_id = NEW.worker_id;
  IF v_role IS DISTINCT FROM 'ENTRANT' THEN
    RAISE EXCEPTION 'Only a crew member with the ENTRANT role may enter (this worker is %)', v_role USING ERRCODE = 'ZE002';
  END IF;

  v_now := clock_timestamp();
  v_is_historical := NOT upper_inf(NEW.period);
  IF v_is_historical THEN
    IF p.status IS DISTINCT FROM 'AUTHORISED' THEN
      RAISE EXCEPTION 'Completed historical reports need an AUTHORISED permit; this permit is %', p.status USING ERRCODE = 'ZE003';
    END IF;
    IF upper(NEW.period) > v_now THEN
      RAISE EXCEPTION 'A completed historical report cannot end in the future; create an open entry for a new admission'
        USING ERRCODE = 'ZE002';
    END IF;
  ELSE
    -- Serialize new admissions by worker first (worker dependency changes use the same order), then by permit.
    -- This path uses server time for safety. Client timestamps are only a reported event-time fact.
    IF p.status IS DISTINCT FROM 'AUTHORISED' THEN
      RAISE EXCEPTION 'New entries need an AUTHORISED permit; this permit is %', p.status USING ERRCODE = 'ZE003';
    END IF;
    -- Revalidate first: an expired permit or changed clause must leave durable stop evidence even
    -- when the request itself is rejected. RETURN NULL commits the stop without admitting a row.
    IF revalidate_authorised_permit(NEW.permit_id, 'entry_admission') THEN
      PERFORM set_config('zeroentry.entry_admission_stopped', 'true', true);
      RETURN NULL;
    END IF;
    IF v_now < p.authorised_at OR v_now >= p.valid_until THEN
      RAISE EXCEPTION 'New entries require a currently valid permit (% to % IST)',
        to_char(local_ts(p.authorised_at), 'YYYY-MM-DD HH24:MI'), to_char(local_ts(p.valid_until), 'YYYY-MM-DD HH24:MI')
        USING ERRCODE = 'ZE002';
    END IF;
    IF lower(NEW.period) < v_now - interval '5 minutes' OR lower(NEW.period) > v_now + interval '5 minutes' THEN
      RAISE EXCEPTION 'An open entry start must be within five minutes of the server clock' USING ERRCODE = 'ZE002';
    END IF;
    IF lower(NEW.period) < p.authorised_at OR lower(NEW.period) >= p.valid_until THEN
      RAISE EXCEPTION 'The reported entry is outside the permit validity window (% to % IST)',
        to_char(local_ts(p.authorised_at), 'YYYY-MM-DD HH24:MI'), to_char(local_ts(p.valid_until), 'YYYY-MM-DD HH24:MI')
        USING ERRCODE = 'ZE002';
    END IF;

    v_minute_now := extract(hour FROM local_ts(v_now))::int * 60 + extract(minute FROM local_ts(v_now))::int;
    v_ls := local_ts(lower(NEW.period));
    IF v_ls::date <> local_date(v_now)
       OR extract(hour FROM v_ls)::int * 60 + extract(minute FROM v_ls)::int < v_d_from
       OR extract(hour FROM v_ls)::int * 60 + extract(minute FROM v_ls)::int >= v_d_to THEN
      RAISE EXCEPTION 'A new entry must start in daylight (% to % IST)',
        lpad((v_d_from / 60)::text, 2, '0') || ':' || lpad((v_d_from % 60)::text, 2, '0'),
        lpad((v_d_to / 60)::text, 2, '0') || ':' || lpad((v_d_to % 60)::text, 2, '0') USING ERRCODE = 'ZE002';
    END IF;
    IF v_minute_now < v_d_from OR v_minute_now >= v_d_to THEN
      RAISE EXCEPTION 'New entries are allowed in daylight only (% to % IST)',
        lpad((v_d_from / 60)::text, 2, '0') || ':' || lpad((v_d_from % 60)::text, 2, '0'),
        lpad((v_d_to / 60)::text, 2, '0') || ':' || lpad((v_d_to % 60)::text, 2, '0') USING ERRCODE = 'ZE002';
    END IF;

    -- Rule 6(3)(k)(ii): a worker needs a 30-minute interval after a full 90-minute stretch. Start the
    -- rest clock at the later of event-time exit and server receipt; old timestamps cannot shorten it.
    SELECT GREATEST(upper(e.period), COALESCE(e.exit_recorded_at, upper(e.period))) + v_rest
      INTO v_rest_until
      FROM entry_log e
     WHERE e.worker_id = NEW.worker_id AND NOT upper_inf(e.period)
       AND upper(e.period) - lower(e.period) >= v_max
     ORDER BY upper(e.period) DESC, e.entry_id DESC LIMIT 1;
    IF v_rest_until IS NOT NULL AND v_now < v_rest_until THEN
      RAISE EXCEPTION 'This worker must rest for % minutes after a 90-minute stretch; the next stretch is allowed after % IST',
        rule_num('mandatory_rest_minutes'), to_char(local_ts(v_rest_until), 'YYYY-MM-DD HH24:MI') USING ERRCODE = 'ZE002';
    END IF;
  END IF;

  NEW.recorded_at := v_now;
  IF v_is_historical THEN
    NEW.exit_recorded_at := v_now;
    v_reported_end := upper(NEW.period);
    v_duration := v_reported_end - lower(NEW.period);
    v_ls := local_ts(lower(NEW.period));
    v_le := local_ts(v_reported_end);
    v_violations := '[]'::jsonb;
    IF upper(NEW.period) <= lower(NEW.period) THEN
      RAISE EXCEPTION 'An exit must be after the entry time' USING ERRCODE = 'ZE002';
    END IF;
    IF v_duration > v_max THEN
      v_violations := v_violations || jsonb_build_array(jsonb_build_object('reason_code', 'DURATION_OVERRUN',
        'reported_minutes', round(extract(epoch FROM v_duration) / 60), 'limit_minutes', round(extract(epoch FROM v_max) / 60)));
      PERFORM append_permit_safety_event(NEW.permit_id, NEW.entry_id,
        format('entry:%s:exit:DURATION_OVERRUN', NEW.entry_id), 'EXIT_VIOLATION', 'DURATION_OVERRUN',
        jsonb_build_object('reported_entry_at', lower(NEW.period), 'reported_exit_at', v_reported_end,
                           'entry_recorded_at', NEW.recorded_at, 'exit_recorded_at', v_now,
                           'reported_minutes', round(extract(epoch FROM v_duration) / 60),
                           'limit_minutes', round(extract(epoch FROM v_max) / 60)));
    END IF;
    IF lower(NEW.period) < p.authorised_at OR lower(NEW.period) >= p.valid_until OR upper(NEW.period) > p.valid_until THEN
      v_violations := v_violations || jsonb_build_array(jsonb_build_object('reason_code', 'PERMIT_WINDOW_OVERRUN',
        'authorised_at', p.authorised_at, 'valid_until', p.valid_until,
        'reported_entry_at', lower(NEW.period), 'reported_exit_at', upper(NEW.period)));
      PERFORM append_permit_safety_event(NEW.permit_id, NEW.entry_id,
        format('entry:%s:exit:PERMIT_WINDOW_OVERRUN', NEW.entry_id), 'EXIT_VIOLATION', 'PERMIT_WINDOW_OVERRUN',
        jsonb_build_object('authorised_at', p.authorised_at, 'valid_until', p.valid_until,
                           'reported_entry_at', lower(NEW.period), 'reported_exit_at', upper(NEW.period),
                           'exit_recorded_at', v_now));
    END IF;
    IF v_ls::date <> v_le::date
       OR extract(hour FROM v_ls)::int * 60 + extract(minute FROM v_ls)::int < v_d_from
       OR extract(hour FROM v_le)::int * 60 + extract(minute FROM v_le)::int > v_d_to THEN
      v_violations := v_violations || jsonb_build_array(jsonb_build_object('reason_code', 'DAYLIGHT_OVERRUN',
        'reported_entry_at', lower(NEW.period), 'reported_exit_at', upper(NEW.period),
        'daylight_start_minute', v_d_from, 'daylight_end_minute', v_d_to));
      PERFORM append_permit_safety_event(NEW.permit_id, NEW.entry_id,
        format('entry:%s:exit:DAYLIGHT_OVERRUN', NEW.entry_id), 'EXIT_VIOLATION', 'DAYLIGHT_OVERRUN',
        jsonb_build_object('reported_entry_at', lower(NEW.period), 'reported_exit_at', upper(NEW.period),
                           'exit_recorded_at', v_now, 'daylight_start_minute', v_d_from, 'daylight_end_minute', v_d_to));
    END IF;
    IF jsonb_array_length(v_violations) > 0 THEN
      PERFORM append_permit_safety_event(NEW.permit_id, NEW.entry_id,
        format('entry:%s:exit:VIOLATIONS', NEW.entry_id), 'EXIT_VIOLATION', 'ENTRY_EXIT_OVERRUN',
        jsonb_build_object('violations', v_violations, 'reported_entry_at', lower(NEW.period),
                           'reported_exit_at', upper(NEW.period), 'exit_recorded_at', v_now));
    END IF;
  ELSE
    NEW.exit_recorded_at := NULL;
  END IF;
  RETURN NEW;
END $$;
ALTER FUNCTION entry_log_guard() SET search_path = public, pg_temp;

-- Dependency changes synchronously stop any currently-authorized permit whose full current clause set
-- no longer passes. The changed dependency row is already locked before this AFTER trigger runs; entry
-- admissions lock worker -> permit and never take dependency locks after the permit, avoiding inversion.
CREATE FUNCTION revalidate_changed_safety_dependency() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  v_incident_id bigint;
  v_incident_type text;
  r record;
BEGIN
  IF TG_TABLE_NAME = 'worker' THEN
    FOR r IN SELECT DISTINCT p.permit_id FROM entry_permit p JOIN permit_crew pc USING (permit_id)
              WHERE p.status IN ('DRAFT', 'AUTHORISED') AND pc.worker_id = NEW.worker_id ORDER BY p.permit_id LOOP
      IF TG_OP = 'UPDATE' AND OLD.contractor_id IS DISTINCT FROM NEW.contractor_id THEN
        PERFORM stop_permit_for_safety(r.permit_id, 'WORKER_AFFILIATION_CHANGED',
          jsonb_build_object('source', 'worker', 'summary', 'a crew member changed contractor affiliation',
                             'worker_id', NEW.worker_id, 'old_contractor_id', OLD.contractor_id,
                             'new_contractor_id', NEW.contractor_id));
      ELSE
        PERFORM revalidate_authorised_permit(r.permit_id, 'worker');
      END IF;
    END LOOP;
  ELSIF TG_TABLE_NAME = 'contractor' THEN
    FOR r IN SELECT DISTINCT p.permit_id, j.job_id FROM entry_permit p JOIN job j USING (job_id)
              WHERE p.status IN ('DRAFT', 'AUTHORISED') AND j.contractor_id = NEW.contractor_id ORDER BY p.permit_id LOOP
      SELECT i.incident_id, i.incident_type INTO v_incident_id, v_incident_type
        FROM incident i
       WHERE i.job_id = r.job_id AND i.contractor_id = NEW.contractor_id
         AND i.recorded_at = transaction_timestamp()
       ORDER BY i.incident_id DESC LIMIT 1;
      IF FOUND THEN
        PERFORM stop_permit_for_safety(r.permit_id, 'INCIDENT_RECORDED',
          jsonb_build_object('source', 'record_incident', 'summary', 'an incident was recorded on this job',
                             'incident_id', v_incident_id, 'incident_type', v_incident_type, 'job_id', r.job_id));
      ELSE
        PERFORM revalidate_authorised_permit(r.permit_id, 'contractor');
      END IF;
    END LOOP;
  ELSIF TG_TABLE_NAME = 'gas_detector' THEN
    FOR r IN SELECT DISTINCT p.permit_id FROM entry_permit p JOIN gas_reading gr USING (permit_id)
              WHERE p.status IN ('DRAFT', 'AUTHORISED') AND gr.detector_id = NEW.detector_id ORDER BY p.permit_id LOOP
      PERFORM revalidate_authorised_permit(r.permit_id, 'gas_detector');
    END LOOP;
  ELSIF TG_TABLE_NAME = 'job' THEN
    FOR r IN SELECT p.permit_id FROM entry_permit p
              WHERE p.status IN ('DRAFT', 'AUTHORISED') AND p.job_id = NEW.job_id ORDER BY p.permit_id LOOP
      PERFORM stop_permit_for_safety(r.permit_id, 'JOB_CONTRACTOR_CHANGED',
        jsonb_build_object('source', 'job', 'summary', 'the job contractor changed after authorization',
                           'job_id', NEW.job_id, 'old_contractor_id', OLD.contractor_id,
                           'new_contractor_id', NEW.contractor_id));
    END LOOP;
  END IF;
  RETURN NULL;
END $$;
CREATE TRIGGER trg_worker_safety_revalidate AFTER UPDATE OF is_active, medical_fit_until, trained_until, contractor_id ON worker
  FOR EACH ROW WHEN (OLD.is_active IS DISTINCT FROM NEW.is_active OR OLD.medical_fit_until IS DISTINCT FROM NEW.medical_fit_until
                     OR OLD.trained_until IS DISTINCT FROM NEW.trained_until OR OLD.contractor_id IS DISTINCT FROM NEW.contractor_id)
  EXECUTE FUNCTION revalidate_changed_safety_dependency();
CREATE TRIGGER trg_contractor_safety_revalidate AFTER UPDATE OF status, licence_valid_until ON contractor
  FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status OR OLD.licence_valid_until IS DISTINCT FROM NEW.licence_valid_until)
  EXECUTE FUNCTION revalidate_changed_safety_dependency();
CREATE TRIGGER trg_detector_safety_revalidate AFTER UPDATE OF calibration_valid_until ON gas_detector
  FOR EACH ROW WHEN (OLD.calibration_valid_until IS DISTINCT FROM NEW.calibration_valid_until)
  EXECUTE FUNCTION revalidate_changed_safety_dependency();
CREATE TRIGGER trg_job_contractor_safety_revalidate AFTER UPDATE OF contractor_id ON job
  FOR EACH ROW WHEN (OLD.contractor_id IS DISTINCT FROM NEW.contractor_id)
  EXECUTE FUNCTION revalidate_changed_safety_dependency();
REVOKE ALL ON FUNCTION revalidate_changed_safety_dependency() FROM PUBLIC, ze_app;

-- Callable with no arguments by the maintenance process. The timestamped implementation is kept
-- private so an application caller cannot manufacture an early sweep or a false clock reading.
CREATE FUNCTION sweep_permit_safety_at(p_at timestamptz) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  r record;
  e record;
  v_count integer := 0;
  v_max interval := make_interval(mins => rule_num('max_continuous_minutes')::int);
  v_d_from int := (rule_num('daylight_start_hour') * 60)::int;
  v_d_to int := (rule_num('daylight_end_hour') * 60)::int;
  v_minute int;
  v_open_entries jsonb;
  v_overdue_count integer;
  v_stopped boolean;
BEGIN
  FOR r IN SELECT permit_id FROM entry_permit WHERE status = 'AUTHORISED' ORDER BY permit_id LOOP
    -- Revalidation takes the same permit lock as entry, dependency writes, and stop-work.
    IF revalidate_authorised_permit(r.permit_id, 'safety_sweep') THEN
      v_count := v_count + 1;
      CONTINUE;
    END IF;

    v_minute := extract(hour FROM local_ts(p_at))::int * 60 + extract(minute FROM local_ts(p_at))::int;
    SELECT COALESCE(jsonb_agg(jsonb_build_object('entry_id', el.entry_id, 'worker_id', el.worker_id,
          'reported_entry_at', lower(el.period), 'entry_recorded_at', el.recorded_at,
          'reported_minutes', round(extract(epoch FROM p_at - lower(el.period)) / 60),
          'server_observed_minutes', round(extract(epoch FROM p_at - el.recorded_at) / 60)) ORDER BY el.entry_id), '[]'::jsonb),
           count(*)
      INTO v_open_entries, v_overdue_count
      FROM entry_log el
     WHERE el.permit_id = r.permit_id AND upper_inf(el.period)
       AND p_at - LEAST(lower(el.period), el.recorded_at) >= v_max;

    IF v_overdue_count > 0 THEN
      v_stopped := stop_permit_for_safety(r.permit_id, 'OPEN_ENTRY_OVERSTAY',
        jsonb_build_object('source', 'safety_sweep', 'summary', 'one or more open entries reached the 90-minute limit',
                           'evaluated_at', p_at, 'open_entries', v_open_entries));
      IF v_stopped THEN v_count := v_count + 1; END IF;
      FOR e IN SELECT entry_id, worker_id, lower(period) AS entered_at, recorded_at
                 FROM entry_log
                WHERE permit_id = r.permit_id AND upper_inf(period)
                  AND p_at - LEAST(lower(period), recorded_at) >= v_max ORDER BY entry_id LOOP
        PERFORM append_permit_safety_event(r.permit_id, e.entry_id,
          format('entry:%s:overstay', e.entry_id), 'OPEN_ENTRY_OVERSTAY', 'MAX_CONTINUOUS_DURATION',
          jsonb_build_object('worker_id', e.worker_id, 'reported_entry_at', e.entered_at,
                             'entry_recorded_at', e.recorded_at, 'evaluated_at', p_at,
                             'max_continuous_minutes', round(extract(epoch FROM v_max) / 60)));
      END LOOP;
      CONTINUE;
    END IF;

    IF v_minute < v_d_from OR v_minute >= v_d_to THEN
      SELECT COALESCE(jsonb_agg(jsonb_build_object('entry_id', entry_id, 'worker_id', worker_id,
                    'reported_entry_at', lower(period), 'entry_recorded_at', recorded_at) ORDER BY entry_id), '[]'::jsonb)
        INTO v_open_entries FROM entry_log WHERE permit_id = r.permit_id AND upper_inf(period);
      IF jsonb_array_length(v_open_entries) > 0 THEN
        v_stopped := stop_permit_for_safety(r.permit_id, 'DAYLIGHT_WINDOW_ENDED',
          jsonb_build_object('source', 'safety_sweep', 'summary', 'daylight ended while a worker was still inside',
                             'evaluated_at', p_at, 'open_entries', v_open_entries));
        IF v_stopped THEN v_count := v_count + 1; END IF;
      END IF;
    END IF;
  END LOOP;
  RETURN v_count;
END $$;
REVOKE ALL ON FUNCTION sweep_permit_safety_at(timestamptz) FROM PUBLIC, ze_app;

CREATE FUNCTION sweep_permit_safety() RETURNS integer
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT sweep_permit_safety_at(clock_timestamp())
$$;
REVOKE ALL ON FUNCTION sweep_permit_safety() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sweep_permit_safety() TO ze_app;
