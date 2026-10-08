-- 0016_durable_commands_and_incident_intake.sql
-- Transactional command receipts, commit-ordered event replay, and standalone multi-victim intake.

CREATE FUNCTION app_ulb_id() RETURNS bigint LANGUAGE sql STABLE
AS $$ SELECT NULLIF(current_setting('app.ulb_id', true), '')::bigint $$;
CREATE FUNCTION staff_scope_ulb(p_ulb_id bigint) RETURNS boolean LANGUAGE sql STABLE
AS $$ SELECT CASE WHEN app_role() IN ('ENGINEER','SUPERVISOR')
                  THEN app_ulb_id() IS NOT NULL AND p_ulb_id=app_ulb_id()
                  ELSE true END $$;

-- Contractor and detector catalogues predate tenant ownership. Explicit append-only scope mappings
-- provide a governed onboarding bridge without allowing engineers to enumerate another municipality.
CREATE TABLE ulb_contractor_scope (
  ulb_id bigint NOT NULL REFERENCES ulb ON DELETE RESTRICT,
  contractor_id bigint NOT NULL REFERENCES contractor ON DELETE RESTRICT,
  assigned_by bigint NOT NULL REFERENCES app_user ON DELETE RESTRICT,
  assigned_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  assignment_reason text NOT NULL CHECK(length(btrim(assignment_reason)) BETWEEN 20 AND 500),
  PRIMARY KEY (ulb_id,contractor_id)
);
CREATE INDEX ix_ulb_contractor_scope_contractor ON ulb_contractor_scope(contractor_id,ulb_id);
CREATE TABLE ulb_detector_scope (
  ulb_id bigint NOT NULL REFERENCES ulb ON DELETE RESTRICT,
  detector_id bigint NOT NULL REFERENCES gas_detector ON DELETE RESTRICT,
  assigned_by bigint NOT NULL REFERENCES app_user ON DELETE RESTRICT,
  assigned_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  assignment_reason text NOT NULL CHECK(length(btrim(assignment_reason)) BETWEEN 20 AND 500),
  PRIMARY KEY (ulb_id,detector_id)
);
CREATE INDEX ix_ulb_detector_scope_detector ON ulb_detector_scope(detector_id,ulb_id);
-- Historical job linkage remains a read compatibility fallback in staff_scope_row; no migration-time actor
-- is fabricated for a relationship that was not explicitly assigned through this new governance path.
ALTER TABLE ulb_contractor_scope ENABLE ROW LEVEL SECURITY;
CREATE POLICY rls_select_contractor_scope ON ulb_contractor_scope FOR SELECT TO ze_app
  USING (app_role() IN ('ADMIN','AUDITOR') OR (app_role() IN ('ENGINEER','SUPERVISOR') AND staff_scope_ulb(ulb_id)));
CREATE POLICY rls_insert_contractor_scope ON ulb_contractor_scope FOR INSERT TO ze_app
  WITH CHECK (app_role()='ADMIN' OR (app_role()='ENGINEER' AND staff_scope_ulb(ulb_id)));
ALTER TABLE ulb_detector_scope ENABLE ROW LEVEL SECURITY;
CREATE POLICY rls_select_detector_scope ON ulb_detector_scope FOR SELECT TO ze_app
  USING (app_role() IN ('ADMIN','AUDITOR') OR (app_role() IN ('ENGINEER','SUPERVISOR') AND staff_scope_ulb(ulb_id)));
CREATE POLICY rls_insert_detector_scope ON ulb_detector_scope FOR INSERT TO ze_app
  WITH CHECK (app_role()='ADMIN');
GRANT SELECT ON ulb_contractor_scope,ulb_detector_scope TO ze_app;
REVOKE INSERT,UPDATE,DELETE ON ulb_contractor_scope,ulb_detector_scope FROM ze_app;
CREATE TRIGGER audit_ulb_contractor_scope AFTER INSERT ON ulb_contractor_scope
  FOR EACH ROW EXECUTE FUNCTION audit_row('ulb_id,contractor_id');
CREATE TRIGGER audit_ulb_detector_scope AFTER INSERT ON ulb_detector_scope
  FOR EACH ROW EXECUTE FUNCTION audit_row('ulb_id,detector_id');

-- ADMIN and AUDITOR retain their documented cross-scope powers. ENGINEER and SUPERVISOR rows
-- must resolve to the non-null ULB stored on their authenticated account.
CREATE FUNCTION staff_scope_row(p_entity text, p_id bigint) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  v_ulb bigint;
BEGIN
  IF app_role() NOT IN ('ENGINEER','SUPERVISOR') THEN RETURN true; END IF;
  IF app_ulb_id() IS NULL OR p_id IS NULL THEN RETURN false; END IF;
  CASE p_entity
    WHEN 'ulb' THEN SELECT ulb_id INTO v_ulb FROM ulb WHERE ulb_id=p_id;
    WHEN 'manhole' THEN SELECT ulb_id INTO v_ulb FROM manhole WHERE manhole_id=p_id;
    WHEN 'complaint' THEN SELECT m.ulb_id INTO v_ulb FROM complaint c JOIN manhole m USING (manhole_id) WHERE c.complaint_id=p_id;
    WHEN 'job' THEN SELECT m.ulb_id INTO v_ulb FROM job j JOIN complaint c USING (complaint_id) JOIN manhole m USING (manhole_id) WHERE j.job_id=p_id;
    WHEN 'machine' THEN SELECT ulb_id INTO v_ulb FROM machine WHERE machine_id=p_id;
    WHEN 'machine_deployment' THEN SELECT m.ulb_id INTO v_ulb FROM machine_deployment d JOIN job j USING (job_id) JOIN complaint c USING (complaint_id) JOIN manhole m USING (manhole_id) WHERE d.deploy_id=p_id;
    WHEN 'mechanisation_waiver' THEN SELECT m.ulb_id INTO v_ulb FROM mechanisation_waiver w JOIN job j USING (job_id) JOIN complaint c USING (complaint_id) JOIN manhole m USING (manhole_id) WHERE w.waiver_id=p_id;
    WHEN 'entry_permit' THEN SELECT m.ulb_id INTO v_ulb FROM entry_permit p JOIN job j USING (job_id) JOIN complaint c USING (complaint_id) JOIN manhole m USING (manhole_id) WHERE p.permit_id=p_id;
    WHEN 'permit_crew' THEN SELECT m.ulb_id INTO v_ulb FROM permit_crew pc JOIN entry_permit p USING (permit_id) JOIN job j USING (job_id) JOIN complaint c USING (complaint_id) JOIN manhole m USING (manhole_id) WHERE pc.permit_id=p_id LIMIT 1;
    WHEN 'gear_issue' THEN SELECT m.ulb_id INTO v_ulb FROM gear_issue gi JOIN entry_permit p USING (permit_id) JOIN job j USING (job_id) JOIN complaint c USING (complaint_id) JOIN manhole m USING (manhole_id) WHERE gi.issue_id=p_id;
    WHEN 'gas_reading' THEN SELECT m.ulb_id INTO v_ulb FROM gas_reading r JOIN entry_permit p USING (permit_id) JOIN job j USING (job_id) JOIN complaint c USING (complaint_id) JOIN manhole m USING (manhole_id) WHERE r.reading_id=p_id;
    WHEN 'entry_log' THEN SELECT m.ulb_id INTO v_ulb FROM entry_log e JOIN entry_permit p USING (permit_id) JOIN job j USING (job_id) JOIN complaint c USING (complaint_id) JOIN manhole m USING (manhole_id) WHERE e.entry_id=p_id;
    WHEN 'permit_safety_event' THEN SELECT m.ulb_id INTO v_ulb FROM permit_safety_event e JOIN entry_permit p USING (permit_id) JOIN job j USING (job_id) JOIN complaint c USING (complaint_id) JOIN manhole m USING (manhole_id) WHERE e.event_id=p_id;
    WHEN 'permit_authorization_decision' THEN SELECT m.ulb_id INTO v_ulb FROM permit_authorization_decision d JOIN entry_permit p USING (permit_id) JOIN job j USING (job_id) JOIN complaint c USING (complaint_id) JOIN manhole m USING (manhole_id) WHERE d.decision_id=p_id;
    WHEN 'permit_decision_receipt' THEN SELECT m.ulb_id INTO v_ulb FROM permit_decision_receipt r JOIN entry_permit p USING (permit_id) JOIN job j USING (job_id) JOIN complaint c USING (complaint_id) JOIN manhole m USING (manhole_id) WHERE r.receipt_id=p_id;
    WHEN 'permit_readiness' THEN SELECT m.ulb_id INTO v_ulb FROM permit_readiness r JOIN entry_permit p USING (permit_id) JOIN job j USING (job_id) JOIN complaint c USING (complaint_id) JOIN manhole m USING (manhole_id) WHERE r.readiness_id=p_id;
    WHEN 'gear_asset' THEN SELECT ulb_id INTO v_ulb FROM gear_asset WHERE gear_asset_id=p_id;
    WHEN 'permit_site_gear' THEN SELECT m.ulb_id INTO v_ulb FROM permit_site_gear g JOIN entry_permit p USING (permit_id) JOIN job j USING (job_id) JOIN complaint c USING (complaint_id) JOIN manhole m USING (manhole_id) WHERE g.site_gear_id=p_id;
    WHEN 'permit_resource_reservation' THEN SELECT m.ulb_id INTO v_ulb FROM permit_resource_reservation r JOIN entry_permit p USING (permit_id) JOIN job j USING (job_id) JOIN complaint c USING (complaint_id) JOIN manhole m USING (manhole_id) WHERE r.reservation_id=p_id;
    WHEN 'completion_claim' THEN SELECT source_ulb_id INTO v_ulb FROM completion_claim WHERE claim_id=p_id;
    WHEN 'completion_projection' THEN SELECT m.ulb_id INTO v_ulb FROM completion_projection x JOIN job j USING (job_id) JOIN complaint c USING (complaint_id) JOIN manhole m USING (manhole_id) WHERE x.job_id=p_id;
    WHEN 'shadow_entry_alert' THEN SELECT m.ulb_id INTO v_ulb FROM shadow_entry_alert a JOIN complaint c USING (complaint_id) JOIN manhole m USING (manhole_id) WHERE a.alert_id=p_id;
    WHEN 'shadow_entry_alert_event' THEN SELECT m.ulb_id INTO v_ulb FROM shadow_entry_alert_event e JOIN shadow_entry_alert a USING (alert_id) JOIN complaint c USING (complaint_id) JOIN manhole m USING (manhole_id) WHERE e.event_id=p_id;
    WHEN 'incident' THEN SELECT m.ulb_id INTO v_ulb FROM incident i JOIN manhole m USING (manhole_id) WHERE i.incident_id=p_id;
    WHEN 'compensation_case' THEN SELECT m.ulb_id INTO v_ulb FROM compensation_case cc JOIN incident i USING (incident_id) JOIN manhole m USING (manhole_id) WHERE cc.case_id=p_id;
    WHEN 'invoice' THEN SELECT m.ulb_id INTO v_ulb FROM invoice i JOIN job j USING (job_id) JOIN complaint c USING (complaint_id) JOIN manhole m USING (manhole_id) WHERE i.invoice_id=p_id;
    WHEN 'invoice_hold' THEN
      SELECT COALESCE(r.ulb_id,m.ulb_id,mj.ulb_id) INTO v_ulb FROM invoice_hold h
      LEFT JOIN incident_report r USING (report_id)
      LEFT JOIN incident i ON i.incident_id=h.incident_id
      LEFT JOIN manhole m ON m.manhole_id=i.manhole_id
      LEFT JOIN invoice inv ON inv.invoice_id=h.invoice_id
      LEFT JOIN job j ON j.job_id=inv.job_id
      LEFT JOIN complaint cj ON cj.complaint_id=j.complaint_id
      LEFT JOIN manhole mj ON mj.manhole_id=cj.manhole_id
      WHERE h.hold_id=p_id;
    WHEN 'worker' THEN
      SELECT m.ulb_id INTO v_ulb FROM worker w JOIN job j ON j.contractor_id=w.contractor_id
       JOIN complaint c USING (complaint_id) JOIN manhole m USING (manhole_id)
       WHERE w.worker_id=p_id AND m.ulb_id=app_ulb_id() LIMIT 1;
    WHEN 'contractor' THEN
      SELECT s.ulb_id INTO v_ulb FROM ulb_contractor_scope s
       WHERE s.contractor_id=p_id AND s.ulb_id=app_ulb_id()
      UNION ALL
      SELECT m.ulb_id FROM contractor x JOIN job j USING (contractor_id)
       JOIN complaint c USING (complaint_id) JOIN manhole m USING (manhole_id)
       WHERE x.contractor_id=p_id AND m.ulb_id=app_ulb_id() LIMIT 1;
    -- Gas detectors are a global instrument catalogue in the legacy schema (they have no ULB owner).
    -- Their calibration metadata is catalogued, while actual readings remain permit/ULB scoped.
    WHEN 'gas_detector' THEN
      SELECT ulb_id INTO v_ulb FROM ulb_detector_scope WHERE detector_id=p_id AND ulb_id=app_ulb_id();
    ELSE RETURN false;
  END CASE;
  RETURN v_ulb = app_ulb_id();
END $$;
REVOKE ALL ON FUNCTION staff_scope_row(text,bigint) FROM PUBLIC, ze_app;
GRANT EXECUTE ON FUNCTION staff_scope_row(text,bigint) TO ze_app;

CREATE FUNCTION assign_ulb_contractor(p_ulb_id bigint,p_contractor_id bigint,p_reason text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE v_row ulb_contractor_scope%ROWTYPE;
BEGIN
  IF app_user_id() IS NULL OR app_role() NOT IN ('ADMIN','ENGINEER') THEN
    RAISE EXCEPTION 'Only an ADMIN or ENGINEER may assign a contractor to a ULB' USING ERRCODE='ZE006';
  END IF;
  IF app_role()='ENGINEER' AND (app_ulb_id() IS NULL OR app_ulb_id()<>p_ulb_id) THEN
    RAISE EXCEPTION 'An ENGINEER may assign contractors only to the ULB stored on their account' USING ERRCODE='ZE006';
  END IF;
  IF length(btrim(COALESCE(p_reason,''))) NOT BETWEEN 20 AND 500 THEN
    RAISE EXCEPTION 'A scoped contractor assignment needs a reason of 20 to 500 characters' USING ERRCODE='ZE002';
  END IF;
  IF NOT EXISTS(SELECT 1 FROM ulb WHERE ulb_id=p_ulb_id) OR NOT EXISTS(SELECT 1 FROM contractor WHERE contractor_id=p_contractor_id) THEN
    RAISE EXCEPTION 'The ULB or contractor does not exist' USING ERRCODE='ZE004';
  END IF;
  INSERT INTO ulb_contractor_scope(ulb_id,contractor_id,assigned_by,assignment_reason)
    VALUES(p_ulb_id,p_contractor_id,app_user_id(),btrim(p_reason)) ON CONFLICT DO NOTHING;
  SELECT * INTO STRICT v_row FROM ulb_contractor_scope WHERE ulb_id=p_ulb_id AND contractor_id=p_contractor_id;
  RETURN jsonb_build_object('ulb_id',v_row.ulb_id,'contractor_id',v_row.contractor_id,
    'assigned_by',v_row.assigned_by,'assigned_at',v_row.assigned_at,'assignment_reason',v_row.assignment_reason);
END $$;
REVOKE ALL ON FUNCTION assign_ulb_contractor(bigint,bigint,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION assign_ulb_contractor(bigint,bigint,text) TO ze_app;

CREATE FUNCTION assign_ulb_detector(p_ulb_id bigint,p_detector_id bigint,p_reason text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE v_row ulb_detector_scope%ROWTYPE;
BEGIN
  IF app_user_id() IS NULL OR app_role()<>'ADMIN' THEN
    RAISE EXCEPTION 'Only an ADMIN may allocate a detector catalogue item to a ULB' USING ERRCODE='ZE006';
  END IF;
  IF length(btrim(COALESCE(p_reason,''))) NOT BETWEEN 20 AND 500 THEN
    RAISE EXCEPTION 'A scoped detector assignment needs a reason of 20 to 500 characters' USING ERRCODE='ZE002';
  END IF;
  IF NOT EXISTS(SELECT 1 FROM ulb WHERE ulb_id=p_ulb_id) OR NOT EXISTS(SELECT 1 FROM gas_detector WHERE detector_id=p_detector_id) THEN
    RAISE EXCEPTION 'The ULB or detector does not exist' USING ERRCODE='ZE004';
  END IF;
  INSERT INTO ulb_detector_scope(ulb_id,detector_id,assigned_by,assignment_reason)
    VALUES(p_ulb_id,p_detector_id,app_user_id(),btrim(p_reason)) ON CONFLICT DO NOTHING;
  SELECT * INTO STRICT v_row FROM ulb_detector_scope WHERE ulb_id=p_ulb_id AND detector_id=p_detector_id;
  RETURN jsonb_build_object('ulb_id',v_row.ulb_id,'detector_id',v_row.detector_id,
    'assigned_by',v_row.assigned_by,'assigned_at',v_row.assigned_at,'assignment_reason',v_row.assignment_reason);
END $$;
REVOKE ALL ON FUNCTION assign_ulb_detector(bigint,bigint,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION assign_ulb_detector(bigint,bigint,text) TO ze_app;

CREATE TABLE command_dedup (
  dedup_id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  actor_user_id    bigint NOT NULL REFERENCES app_user ON DELETE RESTRICT,
  operation        text NOT NULL CHECK (length(btrim(operation)) BETWEEN 1 AND 120),
  idempotency_key  uuid NOT NULL,
  body_sha256      text NOT NULL CHECK (body_sha256 ~ '^[0-9a-f]{64}$'),
  response_status  smallint NOT NULL CHECK (response_status BETWEEN 100 AND 599),
  response_json    jsonb NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (actor_user_id, operation, idempotency_key)
);

CREATE TABLE outbox_scope_counter (
  ulb_id   bigint PRIMARY KEY REFERENCES ulb ON DELETE RESTRICT,
  last_seq bigint NOT NULL DEFAULT 0 CHECK (last_seq >= 0)
);

CREATE TABLE outbox_event (
  event_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ulb_id     bigint NOT NULL REFERENCES ulb ON DELETE RESTRICT,
  event_seq  bigint NOT NULL CHECK (event_seq > 0),
  event_type text NOT NULL CHECK (event_type IN
    ('PERMIT_DECISION', 'PERMIT_READINESS', 'PERMIT_SAFETY', 'COMPLETION_RECONCILED', 'COMPLETION_CLAIM', 'INCIDENT_RECORDED')),
  entity_type text NOT NULL CHECK (entity_type IN ('permit', 'job', 'incident_report', 'completion_claim')),
  entity_id   bigint,
  payload     jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(payload) = 'object'),
  occurred_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (ulb_id, event_seq)
);
CREATE INDEX ix_outbox_event_scope_sequence ON outbox_event (ulb_id, event_seq);

CREATE TABLE incident_report (
  report_id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ulb_id                 bigint NOT NULL REFERENCES ulb ON DELETE RESTRICT,
  job_id                 bigint REFERENCES job ON DELETE RESTRICT,
  permit_id              bigint REFERENCES entry_permit ON DELETE RESTRICT,
  contractor_id          bigint REFERENCES contractor ON DELETE RESTRICT,
  occurred_at            timestamptz NOT NULL,
  site_label             text NOT NULL CHECK (length(btrim(site_label)) BETWEEN 1 AND 300),
  hazard_type            text NOT NULL CHECK (length(btrim(hazard_type)) BETWEEN 1 AND 100),
  description            text NOT NULL CHECK (length(btrim(description)) BETWEEN 1 AND 2000),
  reported_sections      text CHECK (reported_sections IS NULL OR length(reported_sections) <= 500),
  reported_by            bigint NOT NULL REFERENCES app_user ON DELETE RESTRICT,
  classification_status text NOT NULL DEFAULT 'REVIEW_REQUIRED'
    CHECK (classification_status IN ('REVIEW_REQUIRED', 'UNDER_REVIEW', 'REFERRED')),
  source_mode            text NOT NULL DEFAULT 'MANUAL' CHECK (source_mode IN ('MANUAL', 'IMPORTED')),
  created_at             timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_incident_report_scope_time ON incident_report (ulb_id, occurred_at DESC, report_id DESC);
CREATE INDEX ix_incident_report_job ON incident_report (job_id) WHERE job_id IS NOT NULL;

CREATE TABLE incident_report_victim (
  victim_id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  report_id    bigint NOT NULL REFERENCES incident_report ON DELETE RESTRICT,
  victim_key   text NOT NULL CHECK (length(btrim(victim_key)) BETWEEN 1 AND 100),
  worker_id    bigint REFERENCES worker ON DELETE RESTRICT,
  display_alias text NOT NULL CHECK (length(btrim(display_alias)) BETWEEN 1 AND 200),
  outcome      text NOT NULL CHECK (outcome IN ('FATAL', 'INJURY', 'OTHER')),
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (report_id, victim_key)
);
CREATE INDEX ix_incident_report_victim_worker ON incident_report_victim (worker_id) WHERE worker_id IS NOT NULL;

CREATE TABLE incident_assessment_case (
  assessment_case_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  victim_id          bigint NOT NULL UNIQUE REFERENCES incident_report_victim ON DELETE RESTRICT,
  status             text NOT NULL DEFAULT 'PENDING_REVIEW'
    CHECK (status IN ('PENDING_REVIEW', 'ASSESSED', 'EXTERNAL_AWARD_RECORDED', 'EXTERNAL_PAYMENT_RECORDED')),
  reference_amount   numeric(12,2) CHECK (reference_amount IS NULL OR reference_amount >= 0),
  claimed_amount     numeric(12,2) CHECK (claimed_amount IS NULL OR claimed_amount >= 0),
  awarded_amount     numeric(12,2) CHECK (awarded_amount IS NULL OR awarded_amount >= 0),
  paid_amount        numeric(12,2) NOT NULL DEFAULT 0 CHECK (paid_amount >= 0),
  review_due_at      timestamptz,
  notes              text,
  created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_incident_assessment_status ON incident_assessment_case (status, review_due_at);

-- Extend invoice-hold provenance while preserving the older alert and incident sources.
ALTER TABLE invoice_hold ADD COLUMN report_id bigint REFERENCES incident_report ON DELETE RESTRICT;
ALTER TABLE invoice_hold DROP CONSTRAINT ck_hold_has_exactly_one_source;
ALTER TABLE invoice_hold ADD CONSTRAINT ck_hold_has_exactly_one_source CHECK (
       (reason = 'SHADOW_ENTRY' AND alert_id IS NOT NULL AND incident_id IS NULL AND report_id IS NULL)
    OR (reason = 'INCIDENT' AND num_nonnulls(incident_id, report_id) = 1 AND alert_id IS NULL));
CREATE UNIQUE INDEX uq_hold_invoice_report ON invoice_hold (invoice_id, report_id) WHERE report_id IS NOT NULL;

-- Claim identifiers are scoped by source municipality; the same source key can exist in another ULB.
ALTER TABLE completion_claim DROP CONSTRAINT completion_claim_source_external_id_key;
ALTER TABLE completion_claim ADD CONSTRAINT uq_completion_claim_scope_source_external
  UNIQUE (source_ulb_id,source,external_id);

-- Per-scope row locking makes event_seq follow commit order. The increment rolls back with the event.
CREATE FUNCTION append_outbox_event(p_ulb_id bigint, p_event_type text, p_entity_type text, p_entity_id bigint)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  v_seq bigint;
BEGIN
  IF p_event_type NOT IN ('PERMIT_DECISION', 'PERMIT_READINESS', 'PERMIT_SAFETY', 'COMPLETION_RECONCILED', 'COMPLETION_CLAIM', 'INCIDENT_RECORDED')
     OR p_entity_type NOT IN ('permit', 'job', 'incident_report', 'completion_claim') THEN
    RAISE EXCEPTION 'Unsupported outbox event type or entity' USING ERRCODE = 'ZE003';
  END IF;
  INSERT INTO outbox_scope_counter (ulb_id, last_seq) VALUES (p_ulb_id, 0) ON CONFLICT (ulb_id) DO NOTHING;
  UPDATE outbox_scope_counter SET last_seq = last_seq + 1 WHERE ulb_id = p_ulb_id RETURNING last_seq INTO v_seq;
  INSERT INTO outbox_event (ulb_id, event_seq, event_type, entity_type, entity_id, payload)
  VALUES (p_ulb_id, v_seq, p_event_type, p_entity_type, p_entity_id,
          jsonb_build_object('ulb_id', p_ulb_id, 'event_seq', v_seq, 'event_type', p_event_type,
                             'entity_type', p_entity_type, 'entity_id', p_entity_id));
  RETURN v_seq;
END $$;
REVOKE ALL ON FUNCTION append_outbox_event(bigint, text, text, bigint) FROM PUBLIC, ze_app;

-- A fact trigger looks up scope from its owning permit/job and publishes only identifiers, never private fields.
CREATE FUNCTION outbox_for_evidence_fact() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  v_ulb bigint;
  v_permit bigint;
  v_job bigint;
  v_type text;
  v_entity_type text := 'permit';
  v_entity_id bigint;
BEGIN
  IF TG_TABLE_NAME = 'completion_projection' THEN
    v_job := NEW.job_id;
    v_type := 'COMPLETION_RECONCILED';
    v_entity_type := 'job';
    v_entity_id := v_job;
  ELSE
    v_permit := NEW.permit_id;
    v_entity_id := v_permit;
    v_type := CASE TG_TABLE_NAME
      WHEN 'permit_decision_receipt' THEN 'PERMIT_DECISION'
      WHEN 'permit_readiness' THEN 'PERMIT_READINESS'
      ELSE 'PERMIT_SAFETY' END;
    SELECT p.job_id INTO v_job FROM entry_permit p WHERE p.permit_id = v_permit;
  END IF;
  SELECT m.ulb_id INTO v_ulb
    FROM job j JOIN complaint c ON c.complaint_id = j.complaint_id JOIN manhole m ON m.manhole_id = c.manhole_id
   WHERE j.job_id = v_job;
  IF v_ulb IS NOT NULL THEN
    PERFORM append_outbox_event(v_ulb, v_type, v_entity_type, v_entity_id);
  END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION outbox_for_evidence_fact() FROM PUBLIC, ze_app;

CREATE FUNCTION outbox_for_incident_report() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  PERFORM append_outbox_event(NEW.ulb_id, 'INCIDENT_RECORDED', 'incident_report', NEW.report_id);
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION outbox_for_incident_report() FROM PUBLIC, ze_app;

CREATE FUNCTION outbox_for_completion_claim() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  PERFORM append_outbox_event(NEW.source_ulb_id, 'COMPLETION_CLAIM', 'completion_claim', NEW.claim_id);
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION outbox_for_completion_claim() FROM PUBLIC, ze_app;

-- Match the original invoice/incident serialization order: complaint row first, invoice row second.
CREATE FUNCTION incident_report_complaint_lock() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE v_complaint_id bigint;
BEGIN
  IF NEW.job_id IS NOT NULL THEN
    SELECT complaint_id INTO v_complaint_id FROM job WHERE job_id=NEW.job_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Job % does not exist', NEW.job_id USING ERRCODE='ZE004'; END IF;
    PERFORM 1 FROM complaint WHERE complaint_id=v_complaint_id FOR UPDATE;
  END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION incident_report_complaint_lock() FROM PUBLIC, ze_app;

CREATE FUNCTION hold_new_invoice_for_prior_reports() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  INSERT INTO invoice_hold (invoice_id,reason,report_id)
    SELECT NEW.invoice_id,'INCIDENT',r.report_id FROM incident_report r
     WHERE r.job_id=NEW.job_id
    ON CONFLICT (invoice_id,report_id) WHERE report_id IS NOT NULL DO NOTHING;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION hold_new_invoice_for_prior_reports() FROM PUBLIC, ze_app;

CREATE FUNCTION require_read_committed_incident_report() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  IF current_setting('transaction_isolation') <> 'read committed' THEN
    RAISE EXCEPTION 'Incident report and invoice serialization requires READ COMMITTED isolation; retry with READ COMMITTED'
      USING ERRCODE='40001';
  END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION require_read_committed_incident_report() FROM PUBLIC, ze_app;

CREATE FUNCTION record_completion_claim(p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  v_ulb bigint;
  v_claim bigint;
  v_row completion_claim%ROWTYPE;
BEGIN
  IF app_user_id() IS NULL OR app_role() NOT IN ('ADMIN','ENGINEER') THEN
    RAISE EXCEPTION 'This role may not submit completion claims' USING ERRCODE='ZE006';
  END IF;
  IF jsonb_typeof(p_payload) IS DISTINCT FROM 'object'
     OR jsonb_typeof(COALESCE(p_payload->'payload','{}'::jsonb)) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'A claim and its payload must be JSON objects' USING ERRCODE='ZE002';
  END IF;
  v_ulb := NULLIF(p_payload->>'ulb_id','')::bigint;
  IF v_ulb IS NULL OR (app_role()<>'ADMIN' AND (app_ulb_id() IS NULL OR app_ulb_id()<>v_ulb)) THEN
    RAISE EXCEPTION 'The claim ULB does not match the signed-in account scope' USING ERRCODE='ZE004';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM ulb WHERE ulb_id=v_ulb)
     OR length(btrim(COALESCE(p_payload->>'source',''))) NOT BETWEEN 1 AND 100
     OR length(btrim(COALESCE(p_payload->>'external_id',''))) NOT BETWEEN 1 AND 200
     OR length(btrim(COALESCE(p_payload->>'external_job_ref',''))) NOT BETWEEN 1 AND 200
     OR length(btrim(COALESCE(p_payload->>'claimed_status',''))) NOT BETWEEN 1 AND 40
     OR (p_payload->>'claimed_at') IS NULL
     OR (p_payload->>'claimed_at')::timestamptz > clock_timestamp() THEN
    RAISE EXCEPTION 'The claim is outside accepted bounds or references an unknown ULB' USING ERRCODE='ZE002';
  END IF;
  INSERT INTO completion_claim(source_ulb_id,source,external_id,external_job_ref,claimed_status,claimed_at,payload,match_status)
  VALUES (v_ulb,btrim(p_payload->>'source'),btrim(p_payload->>'external_id'),
          btrim(p_payload->>'external_job_ref'),btrim(p_payload->>'claimed_status'),
          (p_payload->>'claimed_at')::timestamptz,COALESCE(p_payload->'payload','{}'::jsonb),'UNMATCHED')
  RETURNING * INTO v_row;
  INSERT INTO audit_log(actor_user_id,action,table_name,row_pk,new_data)
  VALUES (app_user_id(),'INSERT','completion_claim',v_row.claim_id::text,
    jsonb_build_object('source_ulb_id',v_ulb,'source',v_row.source,'external_id',v_row.external_id,
      'match_status','UNMATCHED','claimed_status',v_row.claimed_status));
  RETURN jsonb_build_object('claim_id',v_row.claim_id,'source_ulb_id',v_row.source_ulb_id,
    'source',v_row.source,'external_id',v_row.external_id,'external_job_ref',v_row.external_job_ref,
    'matched_job_id',v_row.matched_job_id,'claimed_status',v_row.claimed_status,'claimed_at',v_row.claimed_at,
    'received_at',v_row.received_at,'payload',v_row.payload,'match_status',v_row.match_status);
END $$;
REVOKE ALL ON FUNCTION record_completion_claim(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION record_completion_claim(jsonb) TO ze_app;

CREATE FUNCTION review_completion_claim(p_claim_id bigint,p_job_id bigint,p_decision text,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  v_claim completion_claim%ROWTYPE;
  v_job_ulb bigint;
  v_match_status text;
BEGIN
  IF app_user_id() IS NULL OR app_role() NOT IN ('ADMIN','ENGINEER') THEN
    RAISE EXCEPTION 'This role may not reconcile completion claims' USING ERRCODE='ZE006';
  END IF;
  IF p_decision NOT IN ('MATCHED','AMBIGUOUS')
     OR length(btrim(COALESCE(p_reason,''))) NOT BETWEEN 20 AND 1000
     OR ((p_decision='MATCHED') IS DISTINCT FROM (p_job_id IS NOT NULL)) THEN
    RAISE EXCEPTION 'A matched review needs a job; an ambiguous review must not include one, and a reason is required' USING ERRCODE='ZE002';
  END IF;
  SELECT * INTO v_claim FROM completion_claim WHERE claim_id=p_claim_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Completion claim % does not exist',p_claim_id USING ERRCODE='ZE004'; END IF;
  IF app_role()<>'ADMIN' AND (app_ulb_id() IS NULL OR app_ulb_id()<>v_claim.source_ulb_id) THEN
    RAISE EXCEPTION 'The claim is outside the signed-in account scope' USING ERRCODE='ZE004';
  END IF;
  IF p_decision='MATCHED' THEN
    SELECT m.ulb_id INTO v_job_ulb FROM job j JOIN complaint c USING(complaint_id)
      JOIN manhole m USING(manhole_id) WHERE j.job_id=p_job_id;
    IF v_job_ulb IS NULL OR v_job_ulb<>v_claim.source_ulb_id THEN
      RAISE EXCEPTION 'The selected job is unknown or outside the claim ULB' USING ERRCODE='ZE003';
    END IF;
    v_match_status:='MATCHED';
  ELSE
    v_match_status:='AMBIGUOUS';
  END IF;
  UPDATE completion_claim SET matched_job_id=CASE WHEN p_decision='MATCHED' THEN p_job_id ELSE NULL END,
    match_status=v_match_status WHERE claim_id=p_claim_id;
  INSERT INTO audit_log(actor_user_id,action,table_name,row_pk,old_data,new_data)
  VALUES (app_user_id(),'UPDATE','completion_claim_review',p_claim_id::text,
    jsonb_build_object('matched_job_id',v_claim.matched_job_id,'match_status',v_claim.match_status),
    jsonb_build_object('matched_job_id',CASE WHEN p_decision='MATCHED' THEN p_job_id ELSE NULL END,
      'match_status',v_match_status,'reason',btrim(p_reason)));
  RETURN jsonb_build_object('claim_id',p_claim_id,'decision',p_decision,
    'matched_job_id',CASE WHEN p_decision='MATCHED' THEN p_job_id ELSE NULL END,
    'match_status',v_match_status,'reason',btrim(p_reason));
END $$;
REVOKE ALL ON FUNCTION review_completion_claim(bigint,bigint,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION review_completion_claim(bigint,bigint,text,text) TO ze_app;

DROP VIEW v_completion_claim_gaps;
CREATE VIEW v_completion_claim_gaps WITH(security_invoker=true) AS
SELECT * FROM v_completion_claim_reference;

-- The intake routine validates every optional registry link before creating any row. Business denial is a
-- SQLSTATE ZE003/ZE006 and therefore rolls back; the API commits expected completed reports and stores their
-- response in command_dedup in the same transaction.
CREATE FUNCTION record_incident_report(p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  v_ulb bigint := (p_payload->>'ulb_id')::bigint;
  v_job bigint := NULLIF(p_payload->>'job_id', '')::bigint;
  v_permit bigint := NULLIF(p_payload->>'permit_id', '')::bigint;
  v_contractor bigint := NULLIF(p_payload->>'contractor_id', '')::bigint;
  v_job_ulb bigint;
  v_job_contractor bigint;
  v_permit_job bigint;
  v_report bigint;
  v_victim bigint;
  v_case bigint;
  v_case_ids bigint[] := ARRAY[]::bigint[];
  v_invoice_effects integer := 0;
  v_permit_effect text := 'NONE';
  v_now timestamptz := clock_timestamp();
  v_victim_row record;
  v_reference numeric(12,2);
BEGIN
  IF app_user_id() IS NULL OR app_role() NOT IN ('ADMIN', 'ENGINEER', 'SUPERVISOR') THEN
    RAISE EXCEPTION 'This role may not record an incident report' USING ERRCODE = 'ZE006';
  END IF;
  IF app_role() <> 'ADMIN' AND (app_ulb_id() IS NULL OR app_ulb_id() <> v_ulb) THEN
    RAISE EXCEPTION 'The report ULB is outside the signed-in account scope' USING ERRCODE = 'ZE004';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM ulb WHERE ulb_id = v_ulb) THEN
    RAISE EXCEPTION 'Unknown ULB' USING ERRCODE = 'ZE004';
  END IF;
  IF jsonb_typeof(p_payload) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'Report body must be a JSON object' USING ERRCODE = 'ZE002';
  END IF;
  IF jsonb_typeof(p_payload->'victims') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'Between one and 100 victims are required' USING ERRCODE = 'ZE002';
  END IF;
  IF jsonb_array_length(p_payload->'victims') NOT BETWEEN 1 AND 100 THEN
    RAISE EXCEPTION 'Between one and 100 victims are required' USING ERRCODE = 'ZE002';
  END IF;
  IF EXISTS (SELECT 1 FROM jsonb_array_elements(p_payload->'victims') AS v(value)
      WHERE jsonb_typeof(v.value) IS DISTINCT FROM 'object') THEN
    RAISE EXCEPTION 'Each victim must be a JSON object' USING ERRCODE = 'ZE002';
  END IF;
  IF (p_payload->>'occurred_at') IS NULL OR (p_payload->>'occurred_at')::timestamptz > clock_timestamp()
     OR length(btrim(COALESCE(p_payload->>'site_label',''))) NOT BETWEEN 1 AND 300
     OR length(btrim(COALESCE(p_payload->>'hazard_type',''))) NOT BETWEEN 1 AND 100
     OR length(btrim(COALESCE(p_payload->>'description',''))) NOT BETWEEN 1 AND 2000
     OR length(COALESCE(p_payload->>'reported_sections','')) > 500 THEN
    RAISE EXCEPTION 'The report timestamp or report fields are outside accepted bounds' USING ERRCODE = 'ZE002';
  END IF;
  IF EXISTS (SELECT 1 FROM jsonb_to_recordset(p_payload->'victims') AS x(victim_key text, display_alias text, outcome text)
     WHERE length(btrim(COALESCE(x.victim_key,''))) NOT BETWEEN 1 AND 100
        OR length(btrim(COALESCE(x.display_alias,''))) NOT BETWEEN 1 AND 200
        OR x.outcome IS NULL OR x.outcome NOT IN ('FATAL','INJURY','OTHER')) THEN
    RAISE EXCEPTION 'A victim key, alias or outcome is invalid' USING ERRCODE = 'ZE002';
  END IF;
  IF EXISTS (SELECT victim_key FROM jsonb_to_recordset(p_payload->'victims') AS x(victim_key text)
      GROUP BY victim_key HAVING count(*) > 1) THEN
    RAISE EXCEPTION 'Victim keys must be unique within a report' USING ERRCODE = 'ZE002';
  END IF;

  IF v_permit IS NOT NULL THEN
    SELECT p.job_id INTO v_permit_job
      FROM entry_permit p JOIN job j ON j.job_id = p.job_id
      JOIN complaint c ON c.complaint_id = j.complaint_id JOIN manhole m ON m.manhole_id = c.manhole_id
     WHERE p.permit_id = v_permit AND m.ulb_id = v_ulb;
    IF v_permit_job IS NULL OR (v_job IS NOT NULL AND v_job <> v_permit_job) THEN
      RAISE EXCEPTION 'The optional permit does not match the selected ULB/job' USING ERRCODE = 'ZE003';
    END IF;
    v_job := v_permit_job;
  END IF;
  IF v_job IS NOT NULL THEN
    SELECT m.ulb_id, j.contractor_id INTO v_job_ulb, v_job_contractor
      FROM job j JOIN complaint c ON c.complaint_id = j.complaint_id JOIN manhole m ON m.manhole_id = c.manhole_id
     WHERE j.job_id = v_job;
    IF v_job_ulb IS NULL OR v_job_ulb <> v_ulb THEN
      RAISE EXCEPTION 'The optional job is outside the selected ULB' USING ERRCODE = 'ZE003';
    END IF;
  END IF;
  IF v_contractor IS NOT NULL AND (v_job IS NULL OR v_job_contractor IS DISTINCT FROM v_contractor) THEN
    RAISE EXCEPTION 'A contractor link must match a scoped job' USING ERRCODE = 'ZE003';
  END IF;
  IF v_contractor IS NULL AND v_job IS NOT NULL THEN
    v_contractor := v_job_contractor;
  END IF;
  IF v_job IS NULL AND EXISTS (
    SELECT 1 FROM jsonb_to_recordset(p_payload->'victims') AS x(worker_id bigint) WHERE x.worker_id IS NOT NULL
  ) THEN
    RAISE EXCEPTION 'A registered victim link requires a scoped job or permit; otherwise leave worker_id empty' USING ERRCODE = 'ZE003';
  END IF;
  IF v_job IS NOT NULL AND EXISTS (
    SELECT 1 FROM jsonb_to_recordset(p_payload->'victims') AS x(worker_id bigint)
    LEFT JOIN worker w ON w.worker_id = x.worker_id
    WHERE x.worker_id IS NOT NULL AND (w.worker_id IS NULL OR w.contractor_id IS DISTINCT FROM v_job_contractor)
  ) THEN
    RAISE EXCEPTION 'A registered victim is unknown or does not match the scoped job contractor' USING ERRCODE = 'ZE003';
  END IF;

  INSERT INTO incident_report
    (ulb_id, job_id, permit_id, contractor_id, occurred_at, site_label, hazard_type, description,
     reported_sections, reported_by)
  VALUES (v_ulb, v_job, v_permit, v_contractor, (p_payload->>'occurred_at')::timestamptz,
          btrim(p_payload->>'site_label'), btrim(p_payload->>'hazard_type'), btrim(p_payload->>'description'),
          NULLIF(btrim(p_payload->>'reported_sections'), ''), app_user_id())
  RETURNING report_id INTO v_report;

  FOR v_victim_row IN
    SELECT * FROM jsonb_to_recordset(p_payload->'victims')
      AS x(victim_key text, worker_id bigint, display_alias text, outcome text)
  LOOP
    INSERT INTO incident_report_victim (report_id, victim_key, worker_id, display_alias, outcome)
    VALUES (v_report, btrim(v_victim_row.victim_key), v_victim_row.worker_id,
            btrim(v_victim_row.display_alias), v_victim_row.outcome)
    RETURNING victim_id INTO v_victim;
    v_reference := CASE v_victim_row.outcome
      WHEN 'FATAL' THEN (SELECT value FROM rule_parameter WHERE param_key = 'compensation_fatality_inr')
      WHEN 'INJURY' THEN (SELECT value FROM rule_parameter WHERE param_key = 'compensation_disability_inr')
      ELSE NULL END;
    INSERT INTO incident_assessment_case (victim_id, reference_amount, claimed_amount, paid_amount, notes)
      VALUES (v_victim, v_reference, NULL, 0,
              'Pending internal assessment only; no award, entitlement decision, legal deadline, or payment recorded.')
      RETURNING assessment_case_id INTO v_case;
    v_case_ids := array_append(v_case_ids, v_case);
  END LOOP;

  IF v_job IS NOT NULL THEN
    INSERT INTO invoice_hold (invoice_id, reason, report_id)
      SELECT i.invoice_id, 'INCIDENT', v_report FROM invoice i WHERE i.job_id = v_job
      ON CONFLICT (invoice_id, report_id) WHERE report_id IS NOT NULL DO NOTHING;
    GET DIAGNOSTICS v_invoice_effects = ROW_COUNT;
  END IF;
  IF v_permit IS NOT NULL THEN
    UPDATE entry_permit SET status = CASE WHEN status = 'DRAFT' THEN 'CANCELLED' ELSE 'ABORTED' END,
      ended_at = v_now, end_reason = 'Incident report ' || v_report || ' recorded; review required.'
     WHERE permit_id = v_permit AND status IN ('DRAFT', 'AUTHORISED');
    IF FOUND THEN v_permit_effect := 'STOPPED_FOR_REVIEW'; END IF;
  END IF;

  INSERT INTO audit_log (actor_user_id, action, table_name, row_pk, new_data)
    VALUES (app_user_id(), 'INSERT', 'incident_report', v_report::text,
      jsonb_build_object('ulb_id', v_ulb, 'victim_count', jsonb_array_length(p_payload->'victims'),
        'job_id', v_job, 'permit_id', v_permit, 'classification_status', 'REVIEW_REQUIRED'));
  RETURN jsonb_build_object('report_id', v_report, 'case_ids', to_jsonb(v_case_ids), 'outcome', 'RECORDED',
    'payment_status', 'NOT_PAID', 'permit_effect', v_permit_effect,
    'invoice_effects', v_invoice_effects,
    'contractor_effect', CASE WHEN v_contractor IS NULL THEN 'NONE' ELSE 'REVIEW_REQUIRED' END,
    'classification_status', 'REVIEW_REQUIRED');
END $$;
REVOKE ALL ON FUNCTION record_incident_report(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION record_incident_report(jsonb) TO ze_app;

-- Durable outbox event creation for committed evidence transitions.
CREATE TRIGGER trg_outbox_incident_report AFTER INSERT ON incident_report
  FOR EACH ROW EXECUTE FUNCTION outbox_for_incident_report();
CREATE TRIGGER trg_outbox_completion_claim AFTER INSERT OR UPDATE ON completion_claim
  FOR EACH ROW EXECUTE FUNCTION outbox_for_completion_claim();
CREATE TRIGGER trg_00_incident_report_read_committed BEFORE INSERT ON incident_report
  FOR EACH ROW EXECUTE FUNCTION require_read_committed_incident_report();
CREATE TRIGGER trg_incident_report_complaint_lock BEFORE INSERT ON incident_report
  FOR EACH ROW EXECUTE FUNCTION incident_report_complaint_lock();
CREATE TRIGGER trg_invoice_hold_for_prior_reports AFTER INSERT ON invoice
  FOR EACH ROW EXECUTE FUNCTION hold_new_invoice_for_prior_reports();

-- Outbox evidence triggers are added after migration 0015 has created these source relations.
CREATE TRIGGER trg_outbox_permit_safety AFTER INSERT ON permit_safety_event
  FOR EACH ROW EXECUTE FUNCTION outbox_for_evidence_fact();
CREATE TRIGGER trg_outbox_permit_receipt AFTER INSERT ON permit_decision_receipt
  FOR EACH ROW EXECUTE FUNCTION outbox_for_evidence_fact();
CREATE TRIGGER trg_outbox_permit_readiness AFTER INSERT ON permit_readiness
  FOR EACH ROW EXECUTE FUNCTION outbox_for_evidence_fact();
CREATE TRIGGER trg_outbox_completion_projection AFTER INSERT OR UPDATE ON completion_projection
  FOR EACH ROW EXECUTE FUNCTION outbox_for_evidence_fact();

-- Runtime reads are scoped; all writes except dedup are through the narrow definer functions/triggers.
ALTER TABLE command_dedup ENABLE ROW LEVEL SECURITY;
CREATE POLICY rls_select_actor ON command_dedup FOR SELECT USING (actor_user_id = app_user_id());
CREATE POLICY rls_insert_actor ON command_dedup FOR INSERT WITH CHECK (actor_user_id = app_user_id());
REVOKE UPDATE, DELETE ON command_dedup FROM ze_app;
GRANT SELECT, INSERT ON command_dedup TO ze_app;
GRANT USAGE, SELECT ON SEQUENCE command_dedup_dedup_id_seq TO ze_app;

ALTER TABLE outbox_scope_counter ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON outbox_scope_counter FROM ze_app;
ALTER TABLE outbox_event ENABLE ROW LEVEL SECURITY;
CREATE POLICY rls_select_outbox_scope ON outbox_event FOR SELECT USING (
  app_role() IN ('ADMIN','AUDITOR')
  OR (app_role() IN ('ENGINEER', 'SUPERVISOR') AND app_ulb_id() IS NOT NULL AND ulb_id = app_ulb_id())
);
GRANT SELECT ON outbox_event TO ze_app;
REVOKE INSERT, UPDATE, DELETE ON outbox_event FROM ze_app;

ALTER TABLE incident_report ENABLE ROW LEVEL SECURITY;
CREATE POLICY rls_select_incident_scope ON incident_report FOR SELECT USING (
  app_role() IN ('ADMIN','AUDITOR') OR
  (app_role() IN ('ENGINEER', 'SUPERVISOR', 'AUDITOR') AND ulb_id = app_ulb_id())
);
ALTER TABLE incident_report_victim ENABLE ROW LEVEL SECURITY;
CREATE POLICY rls_select_report_victim ON incident_report_victim FOR SELECT USING (
  EXISTS (SELECT 1 FROM incident_report r WHERE r.report_id = incident_report_victim.report_id)
);
ALTER TABLE incident_assessment_case ENABLE ROW LEVEL SECURITY;
CREATE POLICY rls_select_report_case ON incident_assessment_case FOR SELECT USING (
  EXISTS (SELECT 1 FROM incident_report_victim v WHERE v.victim_id = incident_assessment_case.victim_id)
);
GRANT SELECT ON incident_report, incident_report_victim, incident_assessment_case TO ze_app;
REVOKE INSERT, UPDATE, DELETE ON incident_report, incident_report_victim, incident_assessment_case FROM ze_app;

-- Tighten legacy broad staff policies without replacing each table's existing role-specific permissions.
DO $$
DECLARE x record;
BEGIN
  FOR x IN SELECT * FROM (VALUES
    ('manhole','staff_scope_ulb(ulb_id)','staff_scope_ulb(ulb_id)'),
    ('complaint','staff_scope_row(''manhole'',manhole_id)','staff_scope_row(''manhole'',manhole_id)'),
    ('contractor','staff_scope_row(''contractor'',contractor_id)','app_ulb_id() IS NOT NULL OR app_role() NOT IN (''ENGINEER'',''SUPERVISOR'')'),
    ('worker','staff_scope_row(''contractor'',contractor_id)','app_ulb_id() IS NOT NULL OR app_role() NOT IN (''ENGINEER'',''SUPERVISOR'')'),
    ('job','staff_scope_row(''complaint'',complaint_id)','staff_scope_row(''complaint'',complaint_id)'),
    ('machine','staff_scope_ulb(ulb_id)','staff_scope_ulb(ulb_id)'),
    ('machine_deployment','staff_scope_row(''job'',job_id)','staff_scope_row(''job'',job_id)'),
    ('mechanisation_waiver','staff_scope_row(''job'',job_id)','staff_scope_row(''job'',job_id)'),
    ('entry_permit','staff_scope_row(''job'',job_id)','staff_scope_row(''job'',job_id)'),
    ('permit_crew','staff_scope_row(''entry_permit'',permit_id)','staff_scope_row(''entry_permit'',permit_id)'),
    ('gear_issue','staff_scope_row(''entry_permit'',permit_id)','staff_scope_row(''entry_permit'',permit_id)'),
    ('gas_detector','staff_scope_row(''gas_detector'',detector_id)','app_role() NOT IN (''ENGINEER'',''SUPERVISOR'')'),
    ('gas_reading','staff_scope_row(''entry_permit'',permit_id)','staff_scope_row(''entry_permit'',permit_id)'),
    ('entry_log','staff_scope_row(''entry_permit'',permit_id)','staff_scope_row(''entry_permit'',permit_id)'),
    ('incident','staff_scope_row(''manhole'',manhole_id)','staff_scope_row(''manhole'',manhole_id)'),
    ('compensation_case','staff_scope_row(''incident'',incident_id)','staff_scope_row(''incident'',incident_id)'),
    ('invoice','staff_scope_row(''job'',job_id)','staff_scope_row(''job'',job_id)'),
    ('invoice_hold','staff_scope_row(''invoice_hold'',hold_id)','staff_scope_row(''invoice'',invoice_id)'),
    ('shadow_entry_alert','staff_scope_row(''complaint'',complaint_id)','staff_scope_row(''complaint'',complaint_id)'),
    ('shadow_entry_alert_event','staff_scope_row(''shadow_entry_alert'',alert_id)','staff_scope_row(''shadow_entry_alert'',alert_id)'),
    ('permit_safety_event','staff_scope_row(''entry_permit'',permit_id)','staff_scope_row(''entry_permit'',permit_id)'),
    ('permit_authorization_decision','staff_scope_row(''entry_permit'',permit_id)','staff_scope_row(''entry_permit'',permit_id)'),
    ('gear_asset','staff_scope_ulb(ulb_id)','staff_scope_ulb(ulb_id)'),
    ('permit_site_gear','staff_scope_row(''entry_permit'',permit_id)','staff_scope_row(''entry_permit'',permit_id)'),
    ('permit_readiness','staff_scope_row(''entry_permit'',permit_id)','staff_scope_row(''entry_permit'',permit_id)'),
    ('permit_resource_reservation','staff_scope_row(''entry_permit'',permit_id)','staff_scope_row(''entry_permit'',permit_id)'),
    ('permit_decision_receipt','staff_scope_row(''entry_permit'',permit_id)','staff_scope_row(''entry_permit'',permit_id)'),
    ('completion_claim','staff_scope_ulb(source_ulb_id)','staff_scope_ulb(source_ulb_id)'),
    ('completion_projection','staff_scope_row(''job'',job_id)','staff_scope_row(''job'',job_id)')
  ) AS t(tbl,using_expr,check_expr)
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', x.tbl);
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename=x.tbl AND policyname='rls_staff_ulb_scope') THEN
      EXECUTE format('CREATE POLICY rls_staff_ulb_scope ON %I AS RESTRICTIVE FOR ALL TO ze_app '
        'USING (%s) WITH CHECK (%s)', x.tbl, x.using_expr, x.check_expr);
    END IF;
  END LOOP;
END $$;

-- These legacy master tables were not covered by the original RLS matrix. The restrictive ULB
-- policy above is now meaningful only alongside intentional permissive policies for their routes.
CREATE POLICY rls_select_manhole_scope ON manhole FOR SELECT TO ze_app USING (
  app_is_staff() OR EXISTS (
    SELECT 1 FROM complaint c JOIN job j USING(complaint_id)
     WHERE c.manhole_id=manhole.manhole_id
       AND (j.contractor_id=app_contractor_id() OR worker_on_job(j.job_id))
  )
);
CREATE POLICY rls_insert_manhole_officer ON manhole FOR INSERT TO ze_app
  WITH CHECK (app_role() IN ('ADMIN','ENGINEER') AND staff_scope_ulb(ulb_id));
CREATE POLICY rls_update_manhole_officer ON manhole FOR UPDATE TO ze_app
  USING (app_role() IN ('ADMIN','ENGINEER') AND staff_scope_ulb(ulb_id))
  WITH CHECK (app_role() IN ('ADMIN','ENGINEER') AND staff_scope_ulb(ulb_id));
CREATE POLICY rls_delete_manhole_admin ON manhole FOR DELETE TO ze_app USING (app_role()='ADMIN');
CREATE POLICY rls_select_machine_staff ON machine FOR SELECT TO ze_app USING (app_is_staff());
CREATE POLICY rls_insert_machine_officer ON machine FOR INSERT TO ze_app
  WITH CHECK (app_role() IN ('ADMIN','ENGINEER') AND staff_scope_ulb(ulb_id));
CREATE POLICY rls_update_machine_officer ON machine FOR UPDATE TO ze_app
  USING (app_role() IN ('ADMIN','ENGINEER') AND staff_scope_ulb(ulb_id))
  WITH CHECK (app_role() IN ('ADMIN','ENGINEER') AND staff_scope_ulb(ulb_id));

-- Previously the ULB directory had no RLS. Its names are shared metadata, but only ADMIN may change it.
ALTER TABLE ulb ENABLE ROW LEVEL SECURITY;
CREATE POLICY rls_ulb_authenticated_read ON ulb FOR SELECT TO ze_app USING (app_role() IS NOT NULL);
CREATE POLICY rls_ulb_admin_insert ON ulb FOR INSERT TO ze_app WITH CHECK (app_role()='ADMIN');
CREATE POLICY rls_ulb_admin_update ON ulb FOR UPDATE TO ze_app USING (app_role()='ADMIN') WITH CHECK (app_role()='ADMIN');
CREATE POLICY rls_ulb_admin_delete ON ulb FOR DELETE TO ze_app USING (app_role()='ADMIN');

-- New relations expose only the reads/actions required by their authenticated API paths.
CREATE POLICY rls_select_asset_staff ON gear_asset FOR SELECT TO ze_app
  USING (app_role() IN ('ADMIN','ENGINEER','SUPERVISOR','AUDITOR'));
CREATE POLICY rls_insert_asset_officer ON gear_asset FOR INSERT TO ze_app
  WITH CHECK (app_role() IN ('ADMIN','ENGINEER') AND staff_scope_ulb(ulb_id));
CREATE POLICY rls_update_asset_officer ON gear_asset FOR UPDATE TO ze_app
  USING (app_role() IN ('ADMIN','ENGINEER') AND staff_scope_ulb(ulb_id))
  WITH CHECK (app_role() IN ('ADMIN','ENGINEER') AND staff_scope_ulb(ulb_id));
CREATE POLICY rls_select_projection_staff ON completion_projection FOR SELECT TO ze_app
  USING (app_role() IN ('ADMIN','ENGINEER','SUPERVISOR','AUDITOR'));
CREATE POLICY rls_select_claim_staff ON completion_claim FOR SELECT TO ze_app
  USING (app_role() IN ('ADMIN','ENGINEER','SUPERVISOR','AUDITOR'));
CREATE POLICY rls_insert_claim_staff ON completion_claim FOR INSERT TO ze_app
  WITH CHECK (app_role() IN ('ADMIN','ENGINEER') AND staff_scope_row('ulb',source_ulb_id));
CREATE POLICY rls_select_readiness_staff ON permit_readiness FOR SELECT TO ze_app
  USING (app_role() IN ('ADMIN','ENGINEER','SUPERVISOR','AUDITOR'));
CREATE POLICY rls_insert_readiness_supervisor ON permit_readiness FOR INSERT TO ze_app
  WITH CHECK (app_role()='SUPERVISOR' AND permit_writer(permit_id));
CREATE POLICY rls_select_site_gear_staff ON permit_site_gear FOR SELECT TO ze_app
  USING (app_role() IN ('ADMIN','ENGINEER','SUPERVISOR','AUDITOR'));
CREATE POLICY rls_insert_site_gear_supervisor ON permit_site_gear FOR INSERT TO ze_app
  WITH CHECK (app_role()='SUPERVISOR' AND permit_writer(permit_id));
CREATE POLICY rls_select_receipt_staff ON permit_decision_receipt FOR SELECT TO ze_app
  USING (app_role() IN ('ADMIN','ENGINEER','SUPERVISOR','AUDITOR'));
CREATE POLICY rls_select_reservation_staff ON permit_resource_reservation FOR SELECT TO ze_app
  USING (app_role() IN ('ADMIN','ENGINEER','SUPERVISOR','AUDITOR'));
GRANT SELECT ON gear_asset, completion_projection, completion_claim, permit_readiness, permit_site_gear,
  permit_decision_receipt, permit_resource_reservation TO ze_app;
GRANT SELECT ON v_completion_claim_gaps TO ze_app;
-- Existing 0015 permissive policies invoke this narrowly scoped helper during RLS evaluation.
GRANT EXECUTE ON FUNCTION contractor_owns_job(bigint) TO ze_app;
GRANT INSERT ON permit_readiness, permit_site_gear TO ze_app;
REVOKE INSERT, UPDATE, DELETE ON completion_claim FROM ze_app;
REVOKE ALL ON SEQUENCE completion_claim_claim_id_seq FROM ze_app;

-- The reporting function is the sole write path for the standalone report hierarchy.
COMMENT ON TABLE command_dedup IS 'Transactional idempotency response cache keyed by trusted actor, operation and client UUID; business effects commit atomically with the saved response.';
COMMENT ON TABLE outbox_event IS 'Durable, privacy-minimised events ordered per ULB by a transactional counter row; event_id identity is not a replay cursor.';
COMMENT ON TABLE incident_report IS 'Standalone review intake; linked assets are optional and classification remains review-required until external review.';
COMMENT ON TABLE incident_report_victim IS 'Victim-specific report detail; worker registry linkage is optional and aliases can preserve unregistered people.';
COMMENT ON TABLE incident_assessment_case IS 'Pending internal assessment and reference values; not a legal award, blacklist or payment record.';
