-- 0009_row_level_security.sql
-- Row-level security: the database's own answer to "who may see / change this row", independent of the API.
-- Identity comes from the transaction-local settings the API sets for every request (app.user_id / app.role /
-- app.contractor_id / app.worker_id, see 0001). NO context means NO rows and NO writes (default deny).
--
-- Honest scope: RLS defends against API bugs and against one tenant reading or changing another's rows. It does
-- NOT defend against SQL injection or a stolen database login: whoever can run SQL as ze_app can set those
-- settings themselves. Parameterised queries and the least-privilege role (0008) are the controls for that.
-- The table owner and superusers bypass RLS (migrations, seeds, DBA); ze_app is neither (NOBYPASSRLS).

-- ---------------------------------------------------------------------------------------------
-- Helpers. The SECURITY DEFINER ones read RLS-protected tables as the owner on purpose: they answer a single
-- yes/no question about the CALLER's identity, and using them in policies avoids infinite policy recursion
-- (job <-> entry_permit <-> permit_crew would otherwise reference each other's policies).
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION app_is_staff() RETURNS boolean LANGUAGE sql STABLE
AS $$ SELECT COALESCE(app_role() IN ('ADMIN', 'ENGINEER', 'SUPERVISOR', 'AUDITOR'), false) $$;

CREATE FUNCTION app_has_role(VARIADIC roles text[]) RETURNS boolean LANGUAGE sql STABLE
AS $$ SELECT COALESCE(app_role() = ANY (roles), false) $$;

CREATE FUNCTION worker_on_permit(p_permit_id bigint) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, pg_temp
AS $$ SELECT EXISTS (SELECT 1 FROM permit_crew WHERE permit_id = p_permit_id AND worker_id = app_worker_id()) $$;

CREATE FUNCTION worker_on_job(p_job_id bigint) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, pg_temp
AS $$ SELECT EXISTS (SELECT 1 FROM entry_permit p JOIN permit_crew c ON c.permit_id = p.permit_id
                      WHERE p.job_id = p_job_id AND c.worker_id = app_worker_id()) $$;

CREATE FUNCTION worker_on_complaint(p_complaint_id bigint) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, pg_temp
AS $$ SELECT EXISTS (SELECT 1 FROM job j JOIN entry_permit p ON p.job_id = j.job_id
                       JOIN permit_crew c ON c.permit_id = p.permit_id
                      WHERE j.complaint_id = p_complaint_id AND c.worker_id = app_worker_id()) $$;

-- A worker may see the people they share a permit with (the crew list is part of their own permit).
CREATE FUNCTION worker_shares_permit(p_worker_id bigint) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, pg_temp
AS $$ SELECT EXISTS (SELECT 1 FROM permit_crew a JOIN permit_crew b ON b.permit_id = a.permit_id
                      WHERE a.worker_id = p_worker_id AND b.worker_id = app_worker_id()) $$;

CREATE FUNCTION contractor_owns_permit(p_permit_id bigint) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, pg_temp
AS $$ SELECT EXISTS (SELECT 1 FROM entry_permit p JOIN job j ON j.job_id = p.job_id
                      WHERE p.permit_id = p_permit_id AND j.contractor_id = app_contractor_id()) $$;

-- May the caller change this permit and its crew, gear, readings, entries? A supervisor only their own; an engineer any.
CREATE FUNCTION permit_writer(p_permit_id bigint) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, pg_temp
AS $$ SELECT COALESCE(app_role() = 'ENGINEER', false)
          OR EXISTS (SELECT 1 FROM entry_permit WHERE permit_id = p_permit_id
                       AND app_role() = 'SUPERVISOR' AND supervisor_id = app_user_id()) $$;

-- ---------------------------------------------------------------------------------------------
-- Functions that legitimately cross role boundaries run as the owner; each does its own authorisation inside.
-- ---------------------------------------------------------------------------------------------
-- A fatality must blacklist the contractor and hold invoices whichever authorised role recorded it (the procedure
-- checks that role itself). Under RLS an invoker-rights UPDATE would silently touch zero rows.
ALTER PROCEDURE record_incident(text, timestamptz, bigint, bigint, text, bigint, bigint, bigint, bigint)
  SECURITY DEFINER SET search_path = public, pg_temp;

-- Audit rows are written by the trigger as the owner, so the application role needs no INSERT right on audit_log
-- at all: even a fully compromised application cannot forge an audit entry directly.
ALTER FUNCTION audit_row() SECURITY DEFINER SET search_path = public, pg_temp;
REVOKE INSERT ON audit_log FROM ze_app;

-- A contractor submitting an invoice must get the holds that already apply to that job, though contractors cannot
-- see alerts or write holds themselves.
ALTER FUNCTION invoice_auto_hold() SECURITY DEFINER SET search_path = public, pg_temp;

-- A crew member's right to refuse: the one write a WORKER may cause, narrowed to "stop the permit I am crewed on".
CREATE FUNCTION stop_work(p_permit_id bigint, p_reason text) RETURNS entry_permit
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  v_role text := app_role();
  p      entry_permit%ROWTYPE;
BEGIN
  IF app_user_id() IS NULL OR v_role IS NULL THEN
    RAISE EXCEPTION 'Sign-in context is missing' USING ERRCODE = 'ZE006';
  END IF;
  IF v_role NOT IN ('WORKER', 'SUPERVISOR', 'ENGINEER') THEN
    RAISE EXCEPTION 'The % role cannot stop work', v_role USING ERRCODE = 'ZE006';
  END IF;
  IF length(btrim(COALESCE(p_reason, ''))) < 5 THEN
    RAISE EXCEPTION 'Stopping work needs a reason of at least 5 characters' USING ERRCODE = 'ZE002';
  END IF;
  SELECT * INTO p FROM entry_permit WHERE permit_id = p_permit_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Permit % does not exist', p_permit_id USING ERRCODE = 'ZE004';
  END IF;
  IF v_role = 'WORKER' AND NOT EXISTS (SELECT 1 FROM permit_crew WHERE permit_id = p_permit_id AND worker_id = app_worker_id()) THEN
    RAISE EXCEPTION 'You are not on the crew of permit %', p_permit_id USING ERRCODE = 'ZE006';
  END IF;
  IF v_role = 'SUPERVISOR' AND p.supervisor_id <> app_user_id() THEN
    RAISE EXCEPTION 'Permit % belongs to another supervisor', p_permit_id USING ERRCODE = 'ZE006';
  END IF;
  IF p.status NOT IN ('DRAFT', 'AUTHORISED') THEN
    RAISE EXCEPTION 'Permit % is already %', p_permit_id, p.status USING ERRCODE = 'ZE003';
  END IF;
  UPDATE entry_permit
     SET status = CASE WHEN p.status = 'DRAFT' THEN 'CANCELLED' ELSE 'ABORTED' END,
         end_reason = format('Stop-work by %s: %s', lower(v_role), btrim(p_reason))
   WHERE permit_id = p_permit_id
  RETURNING * INTO p;
  RETURN p;
END $$;

-- ---------------------------------------------------------------------------------------------
-- Policies, generated from one table so the matrix is readable in one place and cannot drift between tables.
--   read_expr  : who may SELECT which rows
--   ins/upd/del: roles allowed to INSERT / UPDATE / DELETE (empty = nobody, because there is no policy at all)
--   scope      : extra row condition the writer must also satisfy (WITH CHECK / USING), '' for none
-- ---------------------------------------------------------------------------------------------
DO $$
DECLARE
  t record;
BEGIN
  FOR t IN SELECT * FROM (VALUES
    ('contractor', 'app_is_staff() OR contractor_id = app_contractor_id()',
        '{ADMIN,ENGINEER}', '{ADMIN,ENGINEER}', '{ADMIN}', ''),
    ('worker', 'app_is_staff() OR contractor_id = app_contractor_id() OR worker_id = app_worker_id() OR worker_shares_permit(worker_id)',
        '{ADMIN,ENGINEER}', '{ADMIN,ENGINEER}', '{ADMIN}', ''),
    ('job', 'app_is_staff() OR contractor_id = app_contractor_id() OR worker_on_job(job_id)',
        '{ADMIN,ENGINEER}', '{ADMIN,ENGINEER}', '{}', ''),
    ('complaint', $r$app_is_staff() OR worker_on_complaint(complaint_id)
        OR EXISTS (SELECT 1 FROM job j WHERE j.complaint_id = complaint.complaint_id AND j.contractor_id = app_contractor_id())$r$,
        '{ADMIN,ENGINEER}', '{ADMIN,ENGINEER}', '{}', ''),
    ('machine_deployment', $r$app_is_staff()
        OR EXISTS (SELECT 1 FROM job j WHERE j.job_id = machine_deployment.job_id AND j.contractor_id = app_contractor_id())$r$,
        '{ADMIN,ENGINEER}', '{ADMIN,ENGINEER}', '{}', ''),
    ('mechanisation_waiver', $r$app_is_staff() OR worker_on_job(job_id)
        OR EXISTS (SELECT 1 FROM job j WHERE j.job_id = mechanisation_waiver.job_id AND j.contractor_id = app_contractor_id())$r$,
        '{ENGINEER}', '{}', '{}', ''),
    ('entry_permit', $r$app_is_staff() OR worker_on_permit(permit_id)
        OR EXISTS (SELECT 1 FROM job j WHERE j.job_id = entry_permit.job_id AND j.contractor_id = app_contractor_id())$r$,
        '{SUPERVISOR}', '{SUPERVISOR,ENGINEER}', '{SUPERVISOR}', 'permit_writer(permit_id)'),
    ('permit_crew', 'app_is_staff() OR worker_on_permit(permit_id) OR contractor_owns_permit(permit_id)',
        '{SUPERVISOR}', '{SUPERVISOR}', '{SUPERVISOR}', 'permit_writer(permit_id)'),
    ('gear_issue', 'app_is_staff() OR worker_on_permit(permit_id) OR contractor_owns_permit(permit_id)',
        '{SUPERVISOR}', '{SUPERVISOR}', '{SUPERVISOR}', 'permit_writer(permit_id)'),
    ('gas_reading', 'app_is_staff() OR worker_on_permit(permit_id) OR contractor_owns_permit(permit_id)',
        '{SUPERVISOR,ENGINEER}', '{}', '{}', 'permit_writer(permit_id)'),
    ('entry_log', 'app_is_staff() OR worker_on_permit(permit_id) OR contractor_owns_permit(permit_id)',
        '{SUPERVISOR}', '{SUPERVISOR}', '{}', 'permit_writer(permit_id)'),
    ('incident', 'app_is_staff() OR contractor_id = app_contractor_id()',
        '{ADMIN,ENGINEER,SUPERVISOR}', '{}', '{}', ''),
    ('compensation_case', $r$app_is_staff()
        OR EXISTS (SELECT 1 FROM incident i WHERE i.incident_id = compensation_case.incident_id AND i.contractor_id = app_contractor_id())$r$,
        '{ADMIN,ENGINEER}', '{ADMIN,ENGINEER}', '{}', ''),
    ('invoice', $r$app_is_staff()
        OR EXISTS (SELECT 1 FROM job j WHERE j.job_id = invoice.job_id AND j.contractor_id = app_contractor_id())$r$,
        '{ADMIN,ENGINEER}', '{ADMIN,ENGINEER}', '{}', ''),
    ('invoice_hold', $r$app_has_role('ADMIN', 'ENGINEER', 'AUDITOR') OR EXISTS (
          SELECT 1 FROM invoice i JOIN job j ON j.job_id = i.job_id
           WHERE i.invoice_id = invoice_hold.invoice_id AND j.contractor_id = app_contractor_id())$r$,
        '{ADMIN,ENGINEER}', '{ADMIN,ENGINEER}', '{}', ''),
    ('shadow_entry_alert', $r$app_has_role('ADMIN', 'ENGINEER', 'AUDITOR')$r$,
        '{ADMIN,ENGINEER}', '{ADMIN,ENGINEER}', '{}', ''),
    ('shadow_entry_alert_event', $r$app_has_role('ADMIN', 'ENGINEER', 'AUDITOR')$r$,
        '{ADMIN,ENGINEER}', '{}', '{}', ''),
    ('audit_log', $r$app_has_role('ADMIN', 'AUDITOR')$r$, '{}', '{}', '{}', ''),
    -- "law as data" and the gear / detector catalogues decide who may enter a sewer: only an ADMIN may change them
    ('rule_parameter', 'true', '{}', '{ADMIN}', '{}', ''),
    ('detection_rule', 'true', '{}', '{ADMIN}', '{}', ''),
    ('gear_item',      'true', '{ADMIN}', '{ADMIN}', '{ADMIN}', ''),
    ('gas_detector',   'true', '{ADMIN}', '{ADMIN}', '{ADMIN}', '')
  ) AS x(tbl, read_expr, ins, upd, del, scope)
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t.tbl);
    EXECUTE format('CREATE POLICY rls_select ON %I FOR SELECT USING (%s)', t.tbl, t.read_expr);
    IF t.ins <> '{}' THEN
      EXECUTE format('CREATE POLICY rls_insert ON %I FOR INSERT WITH CHECK (app_has_role(VARIADIC %L::text[])%s)',
                     t.tbl, t.ins, CASE WHEN t.scope <> '' THEN ' AND ' || t.scope ELSE '' END);
    END IF;
    IF t.upd <> '{}' THEN
      EXECUTE format('CREATE POLICY rls_update ON %I FOR UPDATE USING (app_has_role(VARIADIC %L::text[])%s) '
                     'WITH CHECK (app_has_role(VARIADIC %L::text[])%s)', t.tbl, t.upd,
                     CASE WHEN t.scope <> '' THEN ' AND ' || t.scope ELSE '' END, t.upd,
                     CASE WHEN t.scope <> '' THEN ' AND ' || t.scope ELSE '' END);
    END IF;
    IF t.del <> '{}' THEN
      EXECUTE format('CREATE POLICY rls_delete ON %I FOR DELETE USING (app_has_role(VARIADIC %L::text[])%s)',
                     t.tbl, t.del, CASE WHEN t.scope <> '' THEN ' AND ' || t.scope ELSE '' END);
    END IF;
  END LOOP;
END $$;

-- A NEW permit cannot be looked up by id yet (the row does not exist while its policy is evaluated), so its insert
-- check is on the row itself: a supervisor may only create a permit supervised by themselves.
DROP POLICY rls_insert ON entry_permit;
CREATE POLICY rls_insert ON entry_permit FOR INSERT
  WITH CHECK (app_role() = 'SUPERVISOR' AND supervisor_id = app_user_id());

-- A contractor may submit invoices, but only for its own jobs.
CREATE POLICY rls_insert_contractor ON invoice FOR INSERT
  WITH CHECK (app_role() = 'CONTRACTOR'
              AND EXISTS (SELECT 1 FROM job j WHERE j.job_id = invoice.job_id AND j.contractor_id = app_contractor_id()));
