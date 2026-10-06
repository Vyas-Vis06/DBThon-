-- 0004_audit_and_guards.sql
-- Law-as-data accessor, the generic audit trigger, and append-only protection for evidence tables.
-- Error codes (SQLSTATE class ZE) are documented in src/zeroentry/errors.py:
--   ZE001 gate denied · ZE002 value breaks a rule · ZE003 not allowed in this state · ZE004 not found
--   ZE005 rule parameter missing · ZE006 role not permitted

-- ---------------------------------------------------------------------------------------------
-- rule_num(): the ONLY way functions read a statutory number. A missing parameter is an error,
-- never a silent default (a silent default would be a silent hole in the law).
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION rule_num(p_key text) RETURNS numeric LANGUAGE plpgsql STABLE AS $$
DECLARE
  v numeric;
BEGIN
  SELECT value INTO v FROM rule_parameter WHERE param_key = p_key;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Rule parameter "%" is not configured', p_key USING ERRCODE = 'ZE005';
  END IF;
  RETURN v;
END $$;

-- ---------------------------------------------------------------------------------------------
-- Audit trail. One trigger function for every audited table.
--   TG_ARGV[0]  comma-separated primary-key column(s)
--   TG_ARGV[1]  optional comma-separated columns to REDACT (never written to the log; a change to a
--               redacted column is recorded as the marker "[changed]" so it is still visible)
-- The actor comes from the request context (app_user_id()); NULL means a DBA / migration session.
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION audit_row() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_pk_cols text[] := string_to_array(TG_ARGV[0], ',');
  v_redact  text[] := COALESCE(string_to_array(NULLIF(TG_ARGV[1], ''), ','), ARRAY[]::text[]);
  v_old jsonb;
  v_new jsonb;
  v_col text;
  v_pk  text;
BEGIN
  IF TG_OP <> 'INSERT' THEN v_old := to_jsonb(OLD) - v_redact; END IF;
  IF TG_OP <> 'DELETE' THEN v_new := to_jsonb(NEW) - v_redact; END IF;

  IF TG_OP = 'UPDATE' THEN
    FOREACH v_col IN ARRAY v_redact LOOP
      IF (to_jsonb(OLD) -> v_col) IS DISTINCT FROM (to_jsonb(NEW) -> v_col) THEN
        v_new := v_new || jsonb_build_object(v_col, '[changed]');
      END IF;
    END LOOP;
    IF v_old = v_new THEN RETURN NULL; END IF;       -- a no-op UPDATE is not an event
  END IF;

  SELECT string_agg(COALESCE(v_new, v_old) ->> k, '|' ORDER BY ord)
    INTO v_pk FROM unnest(v_pk_cols) WITH ORDINALITY AS u(k, ord);

  INSERT INTO audit_log (actor_user_id, action, table_name, row_pk, old_data, new_data)
  VALUES (app_user_id(), TG_OP, TG_TABLE_NAME, v_pk, v_old, v_new);
  RETURN NULL;
END $$;

DO $$
DECLARE
  t record;
BEGIN
  FOR t IN SELECT * FROM (VALUES
      ('complaint',            'complaint_id'),
      ('job',                  'job_id'),
      ('machine_deployment',   'deploy_id'),
      ('mechanisation_waiver', 'waiver_id'),
      ('entry_permit',         'permit_id'),
      ('permit_crew',          'permit_id,worker_id'),
      ('gear_issue',           'issue_id'),
      ('gas_reading',          'reading_id'),
      ('entry_log',            'entry_id'),
      ('incident',             'incident_id'),
      ('compensation_case',    'case_id'),
      ('invoice',              'invoice_id'),
      ('invoice_hold',         'hold_id'),
      ('contractor',           'contractor_id'),
      ('worker',               'worker_id'),
      ('gas_detector',         'detector_id'),
      ('gear_item',            'gear_code'),
      ('detection_rule',       'rule_code'),
      ('rule_parameter',       'param_key')
    ) AS x(tbl, pk)
  LOOP
    EXECUTE format('CREATE TRIGGER trg_audit AFTER INSERT OR UPDATE OR DELETE ON %I '
                   'FOR EACH ROW EXECUTE FUNCTION audit_row(%L)', t.tbl, t.pk);
  END LOOP;
END $$;

-- Accounts: only security-relevant column changes are events (a failed-login counter is not);
-- the password hash is redacted but a change to it is still visible.
CREATE TRIGGER trg_audit
  AFTER INSERT OR DELETE OR UPDATE OF role_id, is_active, password_hash, contractor_id, worker_id, ulb_id
  ON app_user FOR EACH ROW EXECUTE FUNCTION audit_row('user_id', 'password_hash');

-- ---------------------------------------------------------------------------------------------
-- Append-only tables. REVOKE (final migration) stops the application role; these triggers also stop
-- the table owner. Only a superuser can bypass them, and doing so leaves no way to hide it from the
-- statement log.
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is append-only: % is not allowed', TG_TABLE_NAME, TG_OP USING ERRCODE = 'ZE003';
END $$;

CREATE TRIGGER trg_append_only BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TRIGGER trg_append_only BEFORE UPDATE OR DELETE ON gas_reading           -- a correction is a NEW reading
  FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TRIGGER trg_append_only BEFORE UPDATE OR DELETE ON mechanisation_waiver
  FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TRIGGER trg_append_only BEFORE UPDATE OR DELETE ON incident
  FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TRIGGER trg_append_only BEFORE UPDATE OR DELETE ON shadow_entry_alert_event
  FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TRIGGER trg_no_delete BEFORE DELETE ON entry_log                        -- UPDATE only closes an open entry
  FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TRIGGER trg_no_delete BEFORE DELETE ON shadow_entry_alert
  FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TRIGGER trg_no_delete BEFORE DELETE ON compensation_case
  FOR EACH ROW EXECUTE FUNCTION forbid_change();
