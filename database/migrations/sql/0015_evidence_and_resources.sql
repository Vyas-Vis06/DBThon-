-- 0015_evidence_and_resources.sql: additive evidence, policy and resource controls.
ALTER TABLE ulb ADD COLUMN policy_mode text NOT NULL DEFAULT 'REVIEW_REQUIRED'
  CHECK (policy_mode IN ('EDUCATIONAL','DENIED','REVIEW_REQUIRED'));
COMMENT ON COLUMN ulb.policy_mode IS 'New/real scopes default to review. Only explicitly educational fixtures can pass the manual-entry policy gate.';
ALTER TABLE entry_permit ADD COLUMN evidence_revision bigint NOT NULL DEFAULT 0 CHECK (evidence_revision >= 0);
ALTER TABLE permit_crew ADD COLUMN acknowledged_at timestamptz;
ALTER TABLE permit_crew ADD COLUMN acknowledged_by bigint REFERENCES app_user;
ALTER TABLE permit_crew ADD CONSTRAINT ck_crew_ack_pair CHECK ((acknowledged_at IS NULL) = (acknowledged_by IS NULL));
CREATE FUNCTION permit_crew_ack_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
BEGIN
  IF TG_OP='INSERT' THEN
    IF session_user='ze_app' AND (NEW.acknowledged_at IS NOT NULL OR NEW.acknowledged_by IS NOT NULL) THEN
      RAISE EXCEPTION 'A supervisor cannot insert a worker acknowledgement' USING ERRCODE='ZE006';
    END IF;
    RETURN NEW;
  END IF;
  IF (NEW.acknowledged_at,NEW.acknowledged_by) IS DISTINCT FROM (OLD.acknowledged_at,OLD.acknowledged_by)
     AND session_user='ze_app' THEN
    IF app_role()<>'WORKER' OR app_worker_id() IS DISTINCT FROM OLD.worker_id
       OR app_user_id() IS NULL OR NEW.acknowledged_by IS DISTINCT FROM app_user_id()
       OR OLD.acknowledged_at IS NOT NULL OR NEW.acknowledged_at IS NULL THEN
      RAISE EXCEPTION 'Only the assigned worker can provide their own first acknowledgement' USING ERRCODE='ZE006';
    END IF;
    NEW.acknowledged_at:=clock_timestamp();
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_crew_ack_guard BEFORE INSERT OR UPDATE OF acknowledged_at,acknowledged_by ON permit_crew
  FOR EACH ROW EXECUTE FUNCTION permit_crew_ack_guard();
REVOKE ALL ON FUNCTION permit_crew_ack_guard() FROM PUBLIC,ze_app;
ALTER TABLE gear_item ADD COLUMN requirement_scope text NOT NULL DEFAULT 'ENTRANT' CHECK (requirement_scope IN ('ENTRANT','SITE'));
UPDATE gear_item SET requirement_scope='SITE' WHERE gear_code='FIRST_AID_KIT';
ALTER TABLE gas_reading ALTER COLUMN o2_pct DROP NOT NULL;
ALTER TABLE gas_reading ALTER COLUMN h2s_ppm DROP NOT NULL;
ALTER TABLE gas_reading ALTER COLUMN lel_pct DROP NOT NULL;
ALTER TABLE gas_reading ALTER COLUMN co_ppm DROP NOT NULL;
ALTER TABLE gas_reading ADD COLUMN source_mode text NOT NULL DEFAULT 'TYPED' CHECK (source_mode IN ('SIMULATED','TYPED','HARDWARE_RAW'));

-- Keep every signed observation, including future-dated or incomplete samples. Latest evidence is
-- evaluated by the gate; ingestion never erases an adverse observation or silently repairs it.
CREATE OR REPLACE FUNCTION gas_reading_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE v_status text; v_valid date; v_serial text; v_role text;
BEGIN
  SELECT status INTO v_status FROM entry_permit WHERE permit_id=NEW.permit_id FOR UPDATE;
  IF v_status IS DISTINCT FROM 'DRAFT' AND v_status IS DISTINCT FROM 'AUTHORISED' THEN
    RAISE EXCEPTION 'Readings cannot be added to a % permit',v_status USING ERRCODE='ZE003';
  END IF;
  SELECT calibration_valid_until,serial_no INTO v_valid,v_serial FROM gas_detector WHERE detector_id=NEW.detector_id;
  IF v_valid<local_date(NEW.taken_at) THEN
    RAISE EXCEPTION 'Detector % calibration expired on % for observation date %',v_serial,v_valid,local_date(NEW.taken_at) USING ERRCODE='ZE002';
  END IF;
  SELECT r.name INTO v_role FROM app_user u JOIN role r USING(role_id) WHERE u.user_id=NEW.recorded_by AND u.is_active;
  IF v_role IS NULL OR v_role NOT IN('SUPERVISOR','ENGINEER') THEN
    RAISE EXCEPTION 'Only an active SUPERVISOR or ENGINEER may sign off a gas reading' USING ERRCODE='ZE006';
  END IF;
  NEW.recorded_at:=clock_timestamp();
  RETURN NEW;
END $$;

CREATE TABLE gear_asset (
  gear_asset_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ulb_id bigint NOT NULL REFERENCES ulb,
  gear_code text NOT NULL REFERENCES gear_item,
  serial_no text NOT NULL UNIQUE CHECK (length(btrim(serial_no))>0),
  status text NOT NULL DEFAULT 'USABLE' CHECK (status IN ('USABLE','OUT_OF_SERVICE','RETIRED')),
  inspection_valid_until date,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE gear_issue ADD COLUMN gear_asset_id bigint REFERENCES gear_asset;
CREATE INDEX ix_gear_issue_asset ON gear_issue(gear_asset_id);
CREATE UNIQUE INDEX uq_gear_issue_permit_asset ON gear_issue(permit_id,gear_asset_id) WHERE gear_asset_id IS NOT NULL;
CREATE TABLE permit_site_gear (
  site_gear_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  permit_id bigint NOT NULL REFERENCES entry_permit,
  gear_asset_id bigint NOT NULL REFERENCES gear_asset,
  issued_by bigint REFERENCES app_user,
  issued_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  returned_at timestamptz,
  UNIQUE(permit_id,gear_asset_id), CHECK (returned_at IS NULL OR returned_at>=issued_at)
);
CREATE TABLE permit_readiness (
  readiness_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  permit_id bigint NOT NULL REFERENCES entry_permit,
  kind text NOT NULL CHECK (kind IN ('STRUCTURE','ISOLATION','VENTILATION','RESCUE','COMMUNICATION','TRAFFIC','MEDICAL')),
  passed boolean NOT NULL,
  recorded_by bigint NOT NULL REFERENCES app_user,
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  expires_at timestamptz NOT NULL,
  details jsonb NOT NULL DEFAULT '{}'::jsonb,
  source_mode text NOT NULL DEFAULT 'TYPED' CHECK (source_mode IN ('SIMULATED','TYPED','HARDWARE_RAW')),
  CHECK(expires_at>recorded_at)
);
CREATE INDEX ix_permit_readiness_latest ON permit_readiness(permit_id,kind,recorded_at DESC,readiness_id DESC);
CREATE FUNCTION permit_readiness_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE v_status text; v_role text; v_mode text;
BEGIN
  SELECT status INTO v_status FROM entry_permit WHERE permit_id=NEW.permit_id FOR UPDATE;
  IF v_status NOT IN('DRAFT','AUTHORISED') THEN
    RAISE EXCEPTION 'Readiness cannot be added to a % permit',v_status USING ERRCODE='ZE003';
  END IF;
  SELECT r.name INTO v_role FROM app_user u JOIN role r USING(role_id) WHERE u.user_id=NEW.recorded_by AND u.is_active;
  IF v_role IS NULL OR v_role NOT IN('SUPERVISOR','ENGINEER') THEN
    RAISE EXCEPTION 'Only an active SUPERVISOR or ENGINEER may sign off readiness' USING ERRCODE='ZE006';
  END IF;
  SELECT u.policy_mode INTO v_mode FROM entry_permit p JOIN job j USING(job_id) JOIN complaint c USING(complaint_id)
    JOIN manhole m USING(manhole_id) JOIN ulb u USING(ulb_id) WHERE p.permit_id=NEW.permit_id;
  IF session_user='ze_app' THEN NEW.recorded_at:=clock_timestamp(); END IF;
  IF NEW.source_mode='SIMULATED' AND v_mode<>'EDUCATIONAL' THEN
    RAISE EXCEPTION 'Simulated readiness is allowed only in an explicit educational scope' USING ERRCODE='ZE002';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_permit_readiness_guard BEFORE INSERT ON permit_readiness FOR EACH ROW EXECUTE FUNCTION permit_readiness_guard();
REVOKE ALL ON FUNCTION permit_readiness_guard() FROM PUBLIC,ze_app;
CREATE TABLE permit_resource_reservation (
  reservation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  permit_id bigint NOT NULL REFERENCES entry_permit,
  worker_id bigint REFERENCES worker,
  gear_asset_id bigint REFERENCES gear_asset,
  acquired_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  released_at timestamptz,
  release_reason text,
  CHECK(num_nonnulls(worker_id,gear_asset_id)=1),
  CHECK((released_at IS NULL)=(release_reason IS NULL)),
  CHECK(released_at IS NULL OR released_at>=acquired_at)
);
CREATE UNIQUE INDEX uq_resource_worker_occupied ON permit_resource_reservation(worker_id) WHERE worker_id IS NOT NULL AND released_at IS NULL;
CREATE UNIQUE INDEX uq_resource_asset_occupied ON permit_resource_reservation(gear_asset_id) WHERE gear_asset_id IS NOT NULL AND released_at IS NULL;
CREATE INDEX ix_resource_permit_open ON permit_resource_reservation(permit_id) WHERE released_at IS NULL;
CREATE TABLE permit_decision_receipt (
  receipt_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  permit_id bigint NOT NULL REFERENCES entry_permit,
  evidence_revision bigint NOT NULL CHECK(evidence_revision>=0),
  decision text NOT NULL CHECK(decision IN ('AUTHORISED','DENIED')),
  evaluated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  expires_at timestamptz,
  failures jsonb NOT NULL DEFAULT '[]'::jsonb,
  snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  snapshot_sha256 text NOT NULL CHECK(snapshot_sha256 ~ '^[0-9a-f]{64}$'),
  CHECK((decision='AUTHORISED')=(expires_at IS NOT NULL)),
  CHECK(expires_at IS NULL OR expires_at>evaluated_at)
);
CREATE INDEX ix_decision_receipt_current ON permit_decision_receipt(permit_id,evidence_revision DESC,evaluated_at DESC,receipt_id DESC);
ALTER TABLE entry_log ADD COLUMN receipt_id bigint REFERENCES permit_decision_receipt;
CREATE TABLE completion_claim (
  claim_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source_ulb_id bigint NOT NULL REFERENCES ulb,
  source text NOT NULL CHECK(length(btrim(source))>0),
  external_id text NOT NULL CHECK(length(btrim(external_id))>0),
  external_job_ref text NOT NULL CHECK(length(btrim(external_job_ref))>0),
  matched_job_id bigint REFERENCES job,
  claimed_status text NOT NULL,
  claimed_at timestamptz NOT NULL,
  received_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  match_status text NOT NULL DEFAULT 'UNMATCHED' CHECK(match_status IN ('MATCHED','UNMATCHED','AMBIGUOUS')),
  UNIQUE(source,external_id), CHECK((matched_job_id IS NULL)=(match_status<>'MATCHED'))
);
CREATE INDEX ix_completion_claim_job ON completion_claim(matched_job_id,claimed_status) WHERE matched_job_id IS NOT NULL;
CREATE TABLE completion_projection (
  job_id bigint PRIMARY KEY REFERENCES job,
  evidence_revision bigint NOT NULL DEFAULT 0 CHECK(evidence_revision>=0),
  gap_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
  has_gap boolean NOT NULL DEFAULT false,
  disposition text NOT NULL DEFAULT 'REVIEW_REQUIRED' CHECK(disposition IN ('REVIEW_REQUIRED','RESOLVED','EXCEPTION_RECORDED')),
  computed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  reviewed_by bigint REFERENCES app_user,
  review_reason text,
  CHECK((reviewed_by IS NULL)=(review_reason IS NULL))
);
INSERT INTO legal_clause(clause_code,title,legal_ref,sort_order) VALUES
 ('POLICY_ELIGIBILITY','Scope policy explicitly permits educational entry','Real or unknown scope is denied or requires review',5),
 ('CREW_ACK','Every assigned crew member acknowledged participation','Assigned crew is not proof of actual participation',75),
 ('SITE_GEAR','Required shared site equipment is present','Shared site assets are distinct from personal gear',85),
 ('READINESS','Latest required readiness attestations are current and passed','Unknown or adverse readiness fails closed',88),
 ('RESOURCE_AVAILABLE','Every worker and serial asset is available','One active occupancy per worker or asset',89),
 ('GEAR_ASSET','Every required personal item is an inspected physical serial asset','Inventory and inspection state are checked on the asset itself',86),
 ('GAS_COMPLETE_SOURCE','Latest complete atmospheric observations are current and source-labelled','Incomplete, future, or raw observations fail closed',87),
 ('AUTHORIZATION_BOUNDARY','Evidence remained valid through the final serialized decision','A boundary race requires fresh evidence and a new admission attempt',120)
ON CONFLICT(clause_code) DO NOTHING;

INSERT INTO policy_source(source_code,source_type,title,source_url,source_version,citation_clause,applicability) VALUES
 ('POLICY_EDUCATIONAL_ONLY','PRODUCT_POLICY','ZeroEntry educational-only policy scope',NULL,'ZE-2 integration baseline',
  'This project policy is not a legal permission','Only a visibly synthetic educational scope can demonstrate authorization; real or unknown scope defaults to review/deny.'),
 ('POLICY_ACTUAL_PARTICIPATION','PRODUCT_POLICY','ZeroEntry actual-participant acknowledgement',NULL,'ZE-2 integration baseline',
  'Assigned crew does not establish participation','Each assigned crew member must acknowledge their own participation; the system cannot independently verify physical presence.'),
 ('POLICY_READINESS_REFERENCES','PRODUCT_POLICY','ZeroEntry typed readiness reference completeness',NULL,'ZE-2 integration baseline',
  'Product evidence references, not legal certification','Required references make the latest attestation reviewable but do not prove that a physical inspection, test or contact occurred.'),
 ('POLICY_RESOURCE_EXCLUSIVITY','PRODUCT_POLICY','ZeroEntry exclusive crew and serial-resource allocation',NULL,'ZE-2 integration baseline',
  'One current reservation per worker/serial asset','Database-level occupancy prevents overlapping software allocations; it cannot prove that field resources are physically present.'),
 ('POLICY_VERSIONED_RECEIPT','PRODUCT_POLICY','ZeroEntry revision-bound admission receipt',NULL,'ZE-2 integration baseline',
  'Decision freshness and evidence revision','A current receipt binds the database decision to a revision and expiry; it is not an external signature or safety certification.')
ON CONFLICT(source_code) DO NOTHING;
INSERT INTO legal_clause_source(clause_code,source_code,sort_order) VALUES
 ('POLICY_ELIGIBILITY','POLICY_EDUCATIONAL_ONLY',1),
 ('CREW_ACK','POLICY_ACTUAL_PARTICIPATION',1),
 ('SITE_GEAR','LAW_PROTECTIVE_GEAR',1),
 ('SITE_GEAR','POLICY_RESOURCE_EXCLUSIVITY',2),
 ('READINESS','POLICY_READINESS_REFERENCES',1),
 ('GEAR_ASSET','LAW_PROTECTIVE_GEAR',1),
 ('GAS_COMPLETE_SOURCE','POLICY_GAS_COMPOSITE',1),
 ('RESOURCE_AVAILABLE','POLICY_RESOURCE_EXCLUSIVITY',1),
 ('AUTHORIZATION_BOUNDARY','POLICY_VERSIONED_RECEIPT',1)
ON CONFLICT(clause_code,source_code) DO NOTHING;

-- Preserve the original gate as an auditable implementation layer; the public gate appends the new
-- requirements. Existing authorisation and lifecycle routines are rebound below to this wrapper.
ALTER FUNCTION permit_clause_check(bigint,timestamptz) RENAME TO permit_clause_check_legacy;
CREATE FUNCTION readiness_details_complete(p_kind text,p_details jsonb,p_at timestamptz) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE v_opened_at timestamptz;
BEGIN
  IF jsonb_typeof(p_details)<>'object' THEN RETURN false; END IF;
  CASE p_kind
    WHEN 'STRUCTURE' THEN RETURN NULLIF(btrim(p_details->>'inspection_ref'),'') IS NOT NULL
                            AND NULLIF(btrim(p_details->>'qualified_person_ref'),'') IS NOT NULL;
    WHEN 'ISOLATION' THEN RETURN NULLIF(btrim(p_details->>'isolation_ref'),'') IS NOT NULL;
    WHEN 'VENTILATION' THEN
      IF NULLIF(btrim(p_details->>'method_ref'),'') IS NULL OR NULLIF(btrim(p_details->>'opened_at'),'') IS NULL THEN RETURN false; END IF;
      BEGIN v_opened_at:=(p_details->>'opened_at')::timestamptz;
      EXCEPTION WHEN OTHERS THEN RETURN false; END;
      RETURN v_opened_at<=p_at;
    WHEN 'RESCUE' THEN RETURN NULLIF(btrim(p_details->>'plan_ref'),'') IS NOT NULL
                         AND NULLIF(btrim(p_details->>'retrieval_asset_ref'),'') IS NOT NULL;
    WHEN 'COMMUNICATION' THEN RETURN NULLIF(btrim(p_details->>'method_ref'),'') IS NOT NULL
                                  AND NULLIF(btrim(p_details->>'test_ref'),'') IS NOT NULL;
    WHEN 'TRAFFIC' THEN RETURN NULLIF(btrim(p_details->>'barrier_ref'),'') IS NOT NULL;
    WHEN 'MEDICAL' THEN RETURN NULLIF(btrim(p_details->>'contact_ref'),'') IS NOT NULL
                            AND NULLIF(btrim(p_details->>'first_aid_ref'),'') IS NOT NULL;
    ELSE RETURN false;
  END CASE;
END $$;
REVOKE ALL ON FUNCTION readiness_details_complete(text,jsonb,timestamptz) FROM PUBLIC,ze_app;
GRANT EXECUTE ON FUNCTION readiness_details_complete(text,jsonb,timestamptz) TO ze_app;
CREATE FUNCTION permit_clause_check(p_permit_id bigint,p_at timestamptz DEFAULT now())
RETURNS TABLE(clause_code text,passed boolean,detail text)
LANGUAGE plpgsql STABLE AS $$
DECLARE v_ulb bigint; v_mode text; v_count int;
BEGIN
  RETURN QUERY SELECT legacy.clause_code,legacy.passed,legacy.detail
    FROM permit_clause_check_legacy(p_permit_id,p_at) legacy WHERE legacy.clause_code<>'GEAR_ALL';
  SELECT count(*) INTO v_count FROM gear_item WHERE statutory AND requirement_scope='ENTRANT';
  RETURN QUERY SELECT 'GEAR_ALL'::text,v_count>0 AND NOT EXISTS(
      SELECT 1 FROM permit_crew pc JOIN gear_item g ON g.statutory AND g.requirement_scope='ENTRANT'
      WHERE pc.permit_id=p_permit_id AND pc.crew_role='ENTRANT'
        AND NOT EXISTS(SELECT 1 FROM gear_issue gi WHERE gi.permit_id=pc.permit_id AND gi.worker_id=pc.worker_id AND gi.gear_code=g.gear_code)),
    CASE WHEN v_count=0 THEN 'No entrant-scoped statutory gear item is defined, so entry cannot be authorised'
      WHEN EXISTS(SELECT 1 FROM permit_crew pc JOIN gear_item g ON g.statutory AND g.requirement_scope='ENTRANT'
        WHERE pc.permit_id=p_permit_id AND pc.crew_role='ENTRANT'
          AND NOT EXISTS(SELECT 1 FROM gear_issue gi WHERE gi.permit_id=pc.permit_id AND gi.worker_id=pc.worker_id AND gi.gear_code=g.gear_code))
      THEN (SELECT string_agg(format('%s missing: %s',w.namaste_id,g.name),'; ' ORDER BY w.namaste_id,g.name)
        FROM permit_crew pc JOIN worker w USING(worker_id) JOIN gear_item g ON g.statutory AND g.requirement_scope='ENTRANT'
        WHERE pc.permit_id=p_permit_id AND pc.crew_role='ENTRANT'
          AND NOT EXISTS(SELECT 1 FROM gear_issue gi WHERE gi.permit_id=pc.permit_id AND gi.worker_id=pc.worker_id AND gi.gear_code=g.gear_code))
      ELSE format('Every entrant holds all %s entrant-scoped statutory items',v_count) END;
  SELECT m.ulb_id,u.policy_mode INTO v_ulb,v_mode FROM entry_permit p JOIN job j USING(job_id)
    JOIN complaint c USING(complaint_id) JOIN manhole m USING(manhole_id) JOIN ulb u USING(ulb_id)
    WHERE p.permit_id=p_permit_id;
  RETURN QUERY SELECT 'POLICY_ELIGIBILITY'::text,v_mode='EDUCATIONAL',
    CASE WHEN v_mode='EDUCATIONAL' THEN 'Explicit educational-only policy is active'
         WHEN v_mode='DENIED' THEN 'Scope policy explicitly denies manual entry'
         ELSE 'Scope policy requires review; evidence cannot create permission' END;
  RETURN QUERY SELECT 'CREW_ACK'::text,count(*)>0 AND count(*) FILTER(WHERE acknowledged_at IS NULL)=0,
    CASE WHEN count(*)=0 THEN 'No crew is assigned'
         WHEN count(*) FILTER(WHERE acknowledged_at IS NULL)>0 THEN format('%s crew member(s) have not acknowledged',count(*) FILTER(WHERE acknowledged_at IS NULL))
         ELSE 'Every assigned crew member acknowledged participation' END
    FROM permit_crew WHERE permit_id=p_permit_id;
  SELECT count(*) INTO v_count FROM gear_item WHERE requirement_scope='SITE';
  RETURN QUERY SELECT 'SITE_GEAR'::text,v_count>0 AND NOT EXISTS(
      SELECT 1 FROM gear_item g WHERE g.requirement_scope='SITE' AND NOT EXISTS(
        SELECT 1 FROM permit_site_gear sg JOIN gear_asset ga USING(gear_asset_id)
        WHERE sg.permit_id=p_permit_id AND ga.gear_code=g.gear_code AND sg.returned_at IS NULL
          AND ga.status='USABLE' AND ga.inspection_valid_until>=local_date(p_at))),
    CASE WHEN v_count=0 THEN 'No shared-site gear is configured; gate fails closed'
         WHEN EXISTS(SELECT 1 FROM gear_item g WHERE g.requirement_scope='SITE' AND NOT EXISTS(
           SELECT 1 FROM permit_site_gear sg JOIN gear_asset ga USING(gear_asset_id)
           WHERE sg.permit_id=p_permit_id AND ga.gear_code=g.gear_code AND sg.returned_at IS NULL
             AND ga.status='USABLE' AND ga.inspection_valid_until>=local_date(p_at))) THEN 'A required shared site asset is missing, expired or out of service'
         ELSE format('%s required shared-site equipment type(s) are present',v_count) END;
  RETURN QUERY SELECT 'READINESS'::text,NOT EXISTS(SELECT 1 FROM (VALUES
      ('STRUCTURE'),('ISOLATION'),('VENTILATION'),('RESCUE'),('COMMUNICATION'),('TRAFFIC'),('MEDICAL')) req(kind)
      LEFT JOIN LATERAL(SELECT r.passed,r.expires_at,r.recorded_at,r.source_mode,r.details FROM permit_readiness r WHERE r.permit_id=p_permit_id AND r.kind=req.kind
        ORDER BY r.recorded_at DESC,r.readiness_id DESC LIMIT 1) latest ON true
      WHERE latest.passed IS DISTINCT FROM true OR latest.expires_at<=p_at OR latest.recorded_at>p_at
        OR latest.source_mode='HARDWARE_RAW' OR (latest.source_mode='SIMULATED' AND v_mode<>'EDUCATIONAL')
        OR NOT readiness_details_complete(req.kind,latest.details,p_at)),
    CASE WHEN EXISTS(SELECT 1 FROM (VALUES ('STRUCTURE'),('ISOLATION'),('VENTILATION'),('RESCUE'),('COMMUNICATION'),('TRAFFIC'),('MEDICAL')) req(kind)
      LEFT JOIN LATERAL(SELECT r.passed,r.expires_at,r.recorded_at,r.source_mode,r.details FROM permit_readiness r WHERE r.permit_id=p_permit_id AND r.kind=req.kind
        ORDER BY r.recorded_at DESC,r.readiness_id DESC LIMIT 1) latest ON true
      WHERE latest.passed IS DISTINCT FROM true OR latest.expires_at<=p_at OR latest.recorded_at>p_at
        OR latest.source_mode='HARDWARE_RAW' OR (latest.source_mode='SIMULATED' AND v_mode<>'EDUCATIONAL')
        OR NOT readiness_details_complete(req.kind,latest.details,p_at))
      THEN 'One or more latest required readiness attestations are missing, adverse, expired or lack required evidence references'
      ELSE 'All seven latest readiness attestations pass and remain current' END;
  RETURN QUERY SELECT 'GEAR_ASSET'::text,NOT EXISTS(
      SELECT 1 FROM gear_issue gi JOIN gear_item g USING(gear_code) LEFT JOIN gear_asset ga USING(gear_asset_id)
      WHERE gi.permit_id=p_permit_id AND g.statutory AND g.requirement_scope='ENTRANT'
        AND (ga.gear_asset_id IS NULL OR ga.status<>'USABLE' OR ga.inspection_valid_until IS NULL OR ga.inspection_valid_until<local_date(p_at))),
    'Required personal issues must resolve to inspected, usable physical serial assets';
  RETURN QUERY SELECT 'GAS_COMPLETE_SOURCE'::text,NOT EXISTS(
      SELECT 1 FROM (VALUES('TOP'),('MID'),('BOTTOM')) depths(level)
      LEFT JOIN LATERAL(SELECT gr.* FROM gas_reading gr WHERE gr.permit_id=p_permit_id AND gr.depth_level=depths.level
        ORDER BY taken_at DESC,reading_id DESC LIMIT 1) latest ON true
      WHERE latest.reading_id IS NULL OR latest.taken_at>p_at OR latest.source_mode='HARDWARE_RAW'
        OR latest.o2_pct IS NULL OR latest.h2s_ppm IS NULL OR latest.lel_pct IS NULL OR latest.co_ppm IS NULL),
    'Latest observation at every depth must be current, complete and not raw hardware data';
  RETURN QUERY SELECT 'RESOURCE_AVAILABLE'::text,NOT EXISTS(
      SELECT 1 FROM permit_crew pc JOIN permit_resource_reservation rr USING(worker_id)
       WHERE pc.permit_id=p_permit_id AND rr.released_at IS NULL AND rr.permit_id<>p_permit_id)
      AND NOT EXISTS(SELECT 1 FROM permit_resource_reservation rr WHERE rr.released_at IS NULL AND rr.permit_id<>p_permit_id
       AND rr.gear_asset_id IN(SELECT gear_asset_id FROM gear_issue WHERE permit_id=p_permit_id
                              UNION SELECT gear_asset_id FROM permit_site_gear WHERE permit_id=p_permit_id AND returned_at IS NULL)),
    'Workers including standby/supervisor and all serial assets must be free across active permits';
END $$;

-- The existing dashboard view was bound to the renamed legacy function OID; recreate it so readiness
-- always reflects the full additive gate after this migration.
CREATE OR REPLACE VIEW v_permit_compliance WITH (security_invoker=true) AS
SELECT p.permit_id,p.job_id,p.supervisor_id,count(*) AS clauses_total,
       count(*) FILTER(WHERE NOT c.passed) AS clauses_failed,bool_and(c.passed) AS ready_to_authorise,
       string_agg(c.clause_code,', ' ORDER BY c.clause_code) FILTER(WHERE NOT c.passed) AS failing_clauses
FROM entry_permit p CROSS JOIN LATERAL permit_clause_check(p.permit_id,now()) c
WHERE p.status='DRAFT' GROUP BY p.permit_id;

-- Preserve the original lifecycle state machine while allowing SECURITY DEFINER evidence triggers
-- to advance only the evidence revision of a live authorization. ze_app cannot forge that column.
CREATE OR REPLACE FUNCTION permit_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_denied text; v_role text;
BEGIN
  IF NEW.job_id<>OLD.job_id THEN RAISE EXCEPTION 'A permit cannot be moved to another job' USING ERRCODE='ZE003'; END IF;
  IF NEW.status=OLD.status THEN
    IF OLD.status<>'DRAFT' AND NEW IS DISTINCT FROM OLD THEN
      IF OLD.status='AUTHORISED' AND NEW.evidence_revision<>OLD.evidence_revision
         AND (to_jsonb(NEW)-'evidence_revision')=(to_jsonb(OLD)-'evidence_revision')
         AND (current_user<>session_user OR session_user<>'ze_app') THEN RETURN NEW; END IF;
      RAISE EXCEPTION 'A % permit cannot be altered',OLD.status USING ERRCODE='ZE003';
    END IF;
    RETURN NEW;
  END IF;
  IF NOT ((OLD.status='DRAFT' AND NEW.status IN('AUTHORISED','CANCELLED'))
       OR (OLD.status='AUTHORISED' AND NEW.status IN('CLOSED','ABORTED'))) THEN
    RAISE EXCEPTION 'A permit cannot change from % to %',OLD.status,NEW.status USING ERRCODE='ZE003';
  END IF;
  IF NEW.status='AUTHORISED' THEN
    NEW.authorised_at:=COALESCE(NEW.authorised_at,now());
    NEW.authorised_by:=COALESCE(NEW.authorised_by,app_user_id());
    NEW.valid_until:=NEW.authorised_at+make_interval(mins=>rule_num('permit_valid_minutes')::int);
    SELECT r.name INTO v_role FROM app_user u JOIN role r USING(role_id) WHERE u.user_id=NEW.authorised_by AND u.is_active;
    IF v_role IS NULL OR v_role NOT IN('SUPERVISOR','ENGINEER') THEN
      RAISE EXCEPTION 'Only an active SUPERVISOR or ENGINEER may authorise an entry' USING ERRCODE='ZE006'; END IF;
    SELECT string_agg(format('- %s: %s',l.title,c.detail),E'\n' ORDER BY l.sort_order) INTO v_denied
      FROM permit_clause_check(NEW.permit_id,NEW.authorised_at) c JOIN legal_clause l USING(clause_code) WHERE NOT c.passed;
    IF v_denied IS NOT NULL THEN RAISE EXCEPTION E'Entry denied. Unmet legal clauses:\n%',v_denied USING ERRCODE='ZE001'; END IF;
  ELSIF NEW.status='CLOSED' THEN
    IF EXISTS(SELECT 1 FROM entry_log WHERE permit_id=NEW.permit_id AND upper_inf(period)) THEN
      RAISE EXCEPTION 'The permit cannot be closed while a worker is still inside' USING ERRCODE='ZE003'; END IF;
    NEW.ended_at:=COALESCE(NEW.ended_at,now());
  ELSE NEW.ended_at:=COALESCE(NEW.ended_at,now());
  END IF;
  RETURN NEW;
END $$;

-- An explicit status update is also guarded. This supplements the pre-existing complete clause gate and
-- protects its raw-SQL route with the additive requirements.
CREATE FUNCTION permit_additive_gate_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE v_failed text; v_at timestamptz; v_permit_ulb bigint; v_stored_actor_ulb bigint; v_scope_ulb bigint;
BEGIN
  IF NEW.status='AUTHORISED' AND OLD.status IS DISTINCT FROM 'AUTHORISED' THEN
    IF session_user='ze_app' THEN
      IF current_setting('transaction_isolation')<>'read committed' THEN
        RAISE EXCEPTION 'Runtime authorization requires READ COMMITTED' USING ERRCODE='40001';
      END IF;
      SELECT m.ulb_id,au.ulb_id INTO v_permit_ulb,v_stored_actor_ulb
        FROM entry_permit p JOIN job j USING(job_id) JOIN complaint c USING(complaint_id)
        JOIN manhole m USING(manhole_id) JOIN app_user au ON au.user_id=app_user_id() AND au.is_active
       WHERE p.permit_id=NEW.permit_id;
      v_scope_ulb:=NULLIF(current_setting('app.ulb_id',true),'')::bigint;
      IF NEW.authorised_by IS DISTINCT FROM app_user_id() OR app_role() NOT IN('ENGINEER','SUPERVISOR')
         OR NOT permit_writer(NEW.permit_id) OR v_permit_ulb IS NULL OR v_stored_actor_ulb IS NULL
         OR v_scope_ulb IS NULL OR v_scope_ulb<>v_permit_ulb OR v_stored_actor_ulb<>v_permit_ulb THEN
        RAISE EXCEPTION 'The current actor cannot authorize this permit' USING ERRCODE='ZE006';
      END IF;
      PERFORM param_key FROM rule_parameter ORDER BY param_key FOR SHARE;
      v_at:=clock_timestamp();
      NEW.authorised_at:=v_at;
      NEW.valid_until:=v_at+make_interval(mins=>rule_num('permit_valid_minutes')::int);
    ELSE
      v_at:=COALESCE(NEW.authorised_at,clock_timestamp());
    END IF;
    SELECT string_agg(clause_code,', ' ORDER BY clause_code) INTO v_failed
      FROM permit_clause_check(NEW.permit_id,v_at) WHERE NOT passed;
    IF v_failed IS NOT NULL THEN RAISE EXCEPTION 'Entry denied by current evidence gates: %',v_failed USING ERRCODE='ZE001'; END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_00_permit_additive_gate BEFORE UPDATE OF status ON entry_permit
  FOR EACH ROW EXECUTE FUNCTION permit_additive_gate_guard();
REVOKE ALL ON FUNCTION permit_additive_gate_guard() FROM PUBLIC,ze_app;

-- Save an immutable success receipt for every permitted admission, including raw SQL that passes the gate.
CREATE FUNCTION permit_receipt_expiry(p_permit_id bigint,p_evaluated_at timestamptz) RETURNS timestamptz
LANGUAGE sql STABLE SET search_path=public,pg_temp AS $$
WITH p AS (
  SELECT ep.valid_until,ep.permit_id,j.contractor_id FROM entry_permit ep JOIN job j USING(job_id) WHERE ep.permit_id=p_permit_id
)
SELECT least(p.valid_until,
  (SELECT min(g.taken_at+make_interval(mins=>rule_num('gas_max_age_min')::int)+interval '1 microsecond')
     FROM (SELECT DISTINCT ON(depth_level) taken_at FROM gas_reading WHERE permit_id=p_permit_id
           ORDER BY depth_level,taken_at DESC,reading_id DESC) g),
  (SELECT min(r.expires_at) FROM (SELECT DISTINCT ON(kind) kind,expires_at FROM permit_readiness WHERE permit_id=p_permit_id
           ORDER BY kind,recorded_at DESC,readiness_id DESC) r),
  (SELECT min(from_local((ga.inspection_valid_until+1)::timestamp)) FROM gear_asset ga JOIN gear_issue gi USING(gear_asset_id)
     JOIN gear_item g ON g.gear_code=gi.gear_code WHERE gi.permit_id=p_permit_id AND g.statutory AND g.requirement_scope='ENTRANT'),
  (SELECT min(from_local((ga.inspection_valid_until+1)::timestamp)) FROM gear_asset ga JOIN permit_site_gear sg USING(gear_asset_id)
     WHERE sg.permit_id=p_permit_id AND sg.returned_at IS NULL),
  (SELECT min(from_local((w.medical_fit_until+1)::timestamp)) FROM permit_crew pc JOIN worker w USING(worker_id) WHERE pc.permit_id=p_permit_id),
  (SELECT min(from_local((w.trained_until+1)::timestamp)) FROM permit_crew pc JOIN worker w USING(worker_id) WHERE pc.permit_id=p_permit_id),
  (SELECT from_local((c.licence_valid_until+1)::timestamp) FROM p JOIN contractor c USING(contractor_id)),
  (SELECT min(from_local((d.calibration_valid_until+1)::timestamp)) FROM (SELECT DISTINCT ON(depth_level) detector_id FROM gas_reading
     WHERE permit_id=p_permit_id ORDER BY depth_level,taken_at DESC,reading_id DESC) g JOIN gas_detector d USING(detector_id)),
  from_local((local_date(p_evaluated_at)+CASE WHEN local_ts(p_evaluated_at)::time>=make_time(rule_num('daylight_end_hour')::int,0,0)
    THEN 1 ELSE 0 END)::timestamp+make_interval(hours=>rule_num('daylight_end_hour')::int)))
FROM p
$$;
REVOKE ALL ON FUNCTION permit_receipt_expiry(bigint,timestamptz) FROM PUBLIC,ze_app;

CREATE FUNCTION record_permit_receipt() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE v_now timestamptz:=clock_timestamp(); v_expiry timestamptz; v_snapshot jsonb; v_text text;
BEGIN
  IF NEW.status='AUTHORISED' AND OLD.status IS DISTINCT FROM 'AUTHORISED' THEN
    -- Preserve the serialized authorization decision time for owner-run historic fixtures.
    v_now:=COALESCE(NEW.authorised_at,clock_timestamp());
    v_expiry:=permit_receipt_expiry(NEW.permit_id,v_now);
    v_snapshot:=jsonb_build_object('permit_id',NEW.permit_id,'evidence_revision',NEW.evidence_revision,'evaluated_at',v_now,
      'clauses',(SELECT jsonb_agg(jsonb_build_object('clause_code',clause_code,'passed',passed,'detail',detail)
        ORDER BY clause_code) FROM permit_clause_check(NEW.permit_id,v_now)));
    v_text:=v_snapshot::text;
    INSERT INTO permit_decision_receipt(permit_id,evidence_revision,decision,evaluated_at,expires_at,failures,snapshot,snapshot_sha256)
    VALUES(NEW.permit_id,NEW.evidence_revision,'AUTHORISED',v_now,v_expiry,'[]'::jsonb,v_snapshot,encode(sha256(convert_to(v_text,'UTF8')),'hex'));
  END IF;
  RETURN NULL;
END $$;
CREATE TRIGGER trg_permit_receipt AFTER UPDATE OF status ON entry_permit
  FOR EACH ROW EXECUTE FUNCTION record_permit_receipt();
REVOKE ALL ON FUNCTION record_permit_receipt() FROM PUBLIC,ze_app;

-- Commit a negative decision as evidence instead of throwing away its explanation.
CREATE OR REPLACE FUNCTION authorise_entry(p_permit_id bigint,p_actor_id bigint,p_at timestamptz DEFAULT now())
RETURNS TABLE(clause_code text,title text,legal_ref text,passed boolean,detail text,permit_status text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
#variable_conflict use_column
DECLARE v_status text; v_rows jsonb; v_ok boolean; v_snapshot jsonb; v_text text; v_at timestamptz;
  v_permit_ulb bigint; v_actor_ulb bigint; v_stored_actor_ulb bigint;
BEGIN
  SELECT status INTO v_status FROM entry_permit WHERE permit_id=p_permit_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Permit % does not exist',p_permit_id USING ERRCODE='ZE004'; END IF;
  IF v_status<>'DRAFT' THEN RAISE EXCEPTION 'Permit % is % and cannot be authorised',p_permit_id,v_status USING ERRCODE='ZE003'; END IF;
  IF session_user='ze_app' THEN
    IF current_setting('transaction_isolation')<>'read committed' THEN RAISE EXCEPTION 'Runtime authorization requires READ COMMITTED' USING ERRCODE='40001'; END IF;
    SELECT m.ulb_id INTO v_permit_ulb
      FROM entry_permit p JOIN job j USING(job_id) JOIN complaint c USING(complaint_id)
      JOIN manhole m USING(manhole_id) WHERE p.permit_id=p_permit_id;
    v_actor_ulb:=NULLIF(current_setting('app.ulb_id',true),'')::bigint;
    SELECT ulb_id INTO v_stored_actor_ulb FROM app_user WHERE user_id=p_actor_id AND is_active;
    IF p_actor_id IS DISTINCT FROM app_user_id() OR NOT permit_writer(p_permit_id)
       OR app_role() NOT IN ('ENGINEER','SUPERVISOR') OR v_actor_ulb IS NULL OR v_stored_actor_ulb IS NULL
       OR v_actor_ulb<>v_permit_ulb OR v_stored_actor_ulb<>v_permit_ulb THEN
      RAISE EXCEPTION 'The current actor cannot authorize this permit' USING ERRCODE='ZE006'; END IF;
    PERFORM param_key FROM rule_parameter ORDER BY param_key FOR SHARE;
    v_at:=clock_timestamp();
  ELSE v_at:=p_at; END IF;
  SELECT jsonb_agg(jsonb_build_object('clause_code',clause_code,'passed',passed,'detail',detail)),bool_and(passed)
    INTO v_rows,v_ok FROM permit_clause_check(p_permit_id,v_at);
  IF v_ok THEN
    BEGIN
      UPDATE entry_permit SET status='AUTHORISED',authorised_at=v_at,authorised_by=p_actor_id WHERE permit_id=p_permit_id;
      v_status:='AUTHORISED';
    EXCEPTION WHEN SQLSTATE 'ZE001' THEN
      v_at:=clock_timestamp();
      SELECT jsonb_agg(jsonb_build_object('clause_code',c.clause_code,'passed',c.passed,'detail',c.detail)),bool_and(c.passed)
        INTO v_rows,v_ok FROM permit_clause_check(p_permit_id,v_at) c;
      IF v_ok THEN
        v_rows:=v_rows||jsonb_build_array(jsonb_build_object('clause_code','AUTHORIZATION_BOUNDARY','passed',false,
          'detail','Evidence changed at the final serialized check; refresh and retry authorization'));
      END IF;
      v_ok:=false; v_status:='DRAFT';
    END;
  END IF;
  IF NOT v_ok THEN
    v_snapshot:=jsonb_build_object('permit_id',p_permit_id,'evidence_revision',(SELECT evidence_revision FROM entry_permit WHERE permit_id=p_permit_id),
      'evaluated_at',v_at,'clauses',v_rows); v_text:=v_snapshot::text;
    INSERT INTO permit_decision_receipt(permit_id,evidence_revision,decision,evaluated_at,expires_at,failures,snapshot,snapshot_sha256)
      SELECT p_permit_id,evidence_revision,'DENIED',v_at,NULL,v_rows,v_snapshot,encode(sha256(convert_to(v_text,'UTF8')),'hex')
      FROM entry_permit WHERE permit_id=p_permit_id;
  END IF;
  RETURN QUERY SELECT x.clause_code,COALESCE(l.title,x.clause_code),COALESCE(l.legal_ref,'Product authorization boundary'),x.passed,x.detail,v_status
    FROM jsonb_to_recordset(v_rows) x(clause_code text,passed boolean,detail text)
    LEFT JOIN legal_clause l ON l.clause_code=x.clause_code ORDER BY COALESCE(l.sort_order,32000),x.clause_code;
END $$;
REVOKE ALL ON FUNCTION authorise_entry(bigint,bigint,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION authorise_entry(bigint,bigint,timestamptz) TO ze_app;

-- Admission must use a positive, unexpired receipt for exactly this revision. A safe evidence change
-- can mint a new receipt; an adverse observation stops the permit via the existing safety lifecycle.
CREATE FUNCTION require_current_permit_receipt() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE p entry_permit%ROWTYPE; r permit_decision_receipt%ROWTYPE; v_now timestamptz; v_failed boolean;
BEGIN
  IF TG_OP<>'INSERT' THEN RETURN NEW; END IF;
  -- A bounded interval is a completed historical report, not a new admission. Preserve it even
  -- when policy/evidence has since aged out; a supplied receipt is checked as historical evidence.
  IF NOT upper_inf(NEW.period) THEN
    IF NEW.receipt_id IS NOT NULL AND NOT EXISTS(
      SELECT 1 FROM permit_decision_receipt receipt_record WHERE receipt_record.receipt_id=NEW.receipt_id AND receipt_record.permit_id=NEW.permit_id
        AND receipt_record.decision='AUTHORISED' AND receipt_record.evaluated_at<=lower(NEW.period)
        AND receipt_record.snapshot_sha256=encode(sha256(convert_to(receipt_record.snapshot::text,'UTF8')),'hex')) THEN
      RAISE EXCEPTION 'Historical receipt must be an authentic authorization for this permit before entry' USING ERRCODE='ZE001';
    END IF;
    RETURN NEW;
  END IF;
  SELECT * INTO p FROM entry_permit WHERE permit_id=NEW.permit_id FOR UPDATE;
  IF p.status IS DISTINCT FROM 'AUTHORISED' THEN
    RAISE EXCEPTION 'Entry cannot start while permit % is %',NEW.permit_id,p.status USING ERRCODE='ZE003';
  END IF;
  v_now:=clock_timestamp();
  SELECT EXISTS(SELECT 1 FROM permit_clause_check(p.permit_id,v_now) WHERE NOT passed) INTO v_failed;
  IF v_failed AND p.status='AUTHORISED' THEN
    PERFORM revalidate_authorised_permit(p.permit_id,'entry_receipt_guard');
    RETURN NULL;
  END IF;
  SELECT * INTO r FROM permit_decision_receipt WHERE permit_id=p.permit_id AND decision='AUTHORISED'
    ORDER BY evidence_revision DESC,evaluated_at DESC,receipt_id DESC LIMIT 1;
  IF r.receipt_id IS NULL OR (NEW.receipt_id IS NOT NULL AND NEW.receipt_id<>r.receipt_id)
     OR r.evidence_revision<>p.evidence_revision OR r.expires_at<=v_now
     OR r.snapshot_sha256<>encode(sha256(convert_to(r.snapshot::text,'UTF8')),'hex') THEN
    RAISE EXCEPTION 'No usable current decision receipt exists for this evidence revision' USING ERRCODE='ZE001';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_00_entry_receipt BEFORE INSERT ON entry_log FOR EACH ROW EXECUTE FUNCTION require_current_permit_receipt();
REVOKE ALL ON FUNCTION require_current_permit_receipt() FROM PUBLIC,ze_app;

-- Every assigned person and every personal/shared serial asset is reserved in deterministic order.
CREATE FUNCTION reserve_permit_resources() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE v_id bigint; v_ulb bigint;
BEGIN
  IF NEW.status='AUTHORISED' AND OLD.status IS DISTINCT FROM 'AUTHORISED' THEN
    FOR v_id IN SELECT worker_id FROM permit_crew WHERE permit_id=NEW.permit_id ORDER BY worker_id LOOP
      PERFORM pg_advisory_xact_lock(1,(v_id%2147483647)::int);
      INSERT INTO permit_resource_reservation(permit_id,worker_id) VALUES(NEW.permit_id,v_id);
    END LOOP;
    FOR v_id IN SELECT gear_asset_id FROM gear_issue WHERE permit_id=NEW.permit_id AND gear_asset_id IS NOT NULL
      UNION SELECT gear_asset_id FROM permit_site_gear WHERE permit_id=NEW.permit_id AND returned_at IS NULL ORDER BY 1 LOOP
      PERFORM pg_advisory_xact_lock(2,(v_id%2147483647)::int);
      INSERT INTO permit_resource_reservation(permit_id,gear_asset_id) VALUES(NEW.permit_id,v_id);
    END LOOP;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_01_reserve_permit_resources BEFORE UPDATE OF status ON entry_permit
  FOR EACH ROW EXECUTE FUNCTION reserve_permit_resources();
REVOKE ALL ON FUNCTION reserve_permit_resources() FROM PUBLIC,ze_app;

CREATE FUNCTION release_permit_resources(p_permit_id bigint,p_reason text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
BEGIN
  IF EXISTS(SELECT 1 FROM entry_log WHERE permit_id=p_permit_id AND upper_inf(period)) THEN RETURN; END IF;
  UPDATE permit_resource_reservation SET released_at=clock_timestamp(),release_reason=p_reason
   WHERE permit_id=p_permit_id AND released_at IS NULL;
END $$;
REVOKE ALL ON FUNCTION release_permit_resources(bigint,text) FROM PUBLIC,ze_app;
CREATE FUNCTION release_when_clear() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE v_permit bigint;
BEGIN
  IF TG_TABLE_NAME='entry_permit' THEN
    IF NEW.status IN('CLOSED','ABORTED','CANCELLED') THEN PERFORM release_permit_resources(NEW.permit_id,NEW.status); END IF;
  ELSE
    v_permit:=NEW.permit_id;
    IF NOT upper_inf(NEW.period) AND EXISTS(SELECT 1 FROM entry_permit WHERE permit_id=v_permit AND status IN('ABORTED','CLOSED','CANCELLED'))
      THEN PERFORM release_permit_resources(v_permit,'LAST_ENTRY_EXITED'); END IF;
  END IF;
  RETURN NULL;
END $$;
CREATE TRIGGER trg_resource_release_permit AFTER UPDATE OF status ON entry_permit FOR EACH ROW EXECUTE FUNCTION release_when_clear();
CREATE TRIGGER trg_resource_release_exit AFTER UPDATE OF period ON entry_log FOR EACH ROW EXECUTE FUNCTION release_when_clear();
REVOKE ALL ON FUNCTION release_when_clear() FROM PUBLIC,ze_app;

-- Row locks serialize changes with the existing gate. A real adverse record is retained and stops an
-- authorized permit; it is never rejected just because it makes the gate fail.
CREATE FUNCTION bump_permit_evidence() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE v_id bigint;
BEGIN
  IF TG_OP='DELETE' THEN v_id:=OLD.permit_id; ELSE v_id:=NEW.permit_id; END IF;
  PERFORM 1 FROM entry_permit WHERE permit_id=v_id FOR UPDATE;
  UPDATE entry_permit SET evidence_revision=evidence_revision+1 WHERE permit_id=v_id;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_crew_revision AFTER INSERT OR UPDATE OR DELETE ON permit_crew FOR EACH ROW EXECUTE FUNCTION bump_permit_evidence();
CREATE TRIGGER trg_gear_revision AFTER INSERT OR UPDATE OR DELETE ON gear_issue FOR EACH ROW EXECUTE FUNCTION bump_permit_evidence();
CREATE TRIGGER trg_site_revision AFTER INSERT OR UPDATE OR DELETE ON permit_site_gear FOR EACH ROW EXECUTE FUNCTION bump_permit_evidence();
-- PostgreSQL orders same-kind triggers by name. Revision must advance before the legacy safety-stop
-- trigger runs, otherwise the successful terminal ABORTED transition would be followed by a forbidden
-- revision-only UPDATE that rolls the adverse observation and stop back together.
CREATE TRIGGER trg_00_gas_revision AFTER INSERT ON gas_reading FOR EACH ROW EXECUTE FUNCTION bump_permit_evidence();
CREATE TRIGGER trg_00_readiness_revision AFTER INSERT ON permit_readiness FOR EACH ROW EXECUTE FUNCTION bump_permit_evidence();
REVOKE ALL ON FUNCTION bump_permit_evidence() FROM PUBLIC,ze_app;

CREATE FUNCTION readiness_effects() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
BEGIN PERFORM revalidate_authorised_permit(NEW.permit_id,'permit_readiness'); RETURN NULL; END $$;
CREATE TRIGGER trg_readiness_effects AFTER INSERT ON permit_readiness FOR EACH ROW EXECUTE FUNCTION readiness_effects();
REVOKE ALL ON FUNCTION readiness_effects() FROM PUBLIC,ze_app;

CREATE FUNCTION record_current_permit_receipt(p_permit_id bigint) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE v_now timestamptz:=clock_timestamp(); v_rev bigint; v_status text; v_fail jsonb; v_snap jsonb; v_text text; v_exp timestamptz;
BEGIN
  SELECT status,evidence_revision INTO v_status,v_rev FROM entry_permit WHERE permit_id=p_permit_id FOR UPDATE;
  IF v_status IS DISTINCT FROM 'AUTHORISED' THEN RETURN; END IF;
  SELECT COALESCE(jsonb_agg(jsonb_build_object('clause_code',clause_code,'passed',passed,'detail',detail) ORDER BY clause_code),'[]'::jsonb)
    INTO v_fail FROM permit_clause_check(p_permit_id,v_now) WHERE NOT passed;
  IF jsonb_array_length(v_fail)>0 THEN
    PERFORM revalidate_authorised_permit(p_permit_id,'evidence_revision');
    RETURN;
  END IF;
  v_exp:=permit_receipt_expiry(p_permit_id,v_now);
  v_snap:=jsonb_build_object('permit_id',p_permit_id,'evidence_revision',v_rev,'evaluated_at',v_now,
    'clauses',(SELECT jsonb_agg(jsonb_build_object('clause_code',clause_code,'passed',passed,'detail',detail) ORDER BY clause_code)
      FROM permit_clause_check(p_permit_id,v_now)));
  v_text:=v_snap::text;
  INSERT INTO permit_decision_receipt(permit_id,evidence_revision,decision,evaluated_at,expires_at,failures,snapshot,snapshot_sha256)
    VALUES(p_permit_id,v_rev,'AUTHORISED',v_now,v_exp,'[]'::jsonb,v_snap,encode(sha256(convert_to(v_text,'UTF8')),'hex'));
END $$;
REVOKE ALL ON FUNCTION record_current_permit_receipt(bigint) FROM PUBLIC,ze_app;

-- Physical asset state is evidence too. Keep identity immutable, lock every affected permit in a
-- stable order, revise its evidence, and run the ordinary safety recheck. An adverse change commits
-- with ABORTED; open entries remain open until a truthful exit is recorded.
CREATE FUNCTION gear_asset_change_effects() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE v_permit bigint; v_changed boolean;
BEGIN
  IF (NEW.ulb_id,NEW.gear_code,NEW.serial_no) IS DISTINCT FROM (OLD.ulb_id,OLD.gear_code,OLD.serial_no) THEN
    RAISE EXCEPTION 'A physical asset identity cannot be changed in place' USING ERRCODE='ZE003';
  END IF;
  v_changed:=(NEW.status,NEW.inspection_valid_until) IS DISTINCT FROM (OLD.status,OLD.inspection_valid_until);
  IF NOT v_changed THEN RETURN NEW; END IF;
  FOR v_permit IN
    SELECT DISTINCT x.permit_id FROM (
      SELECT permit_id FROM gear_issue WHERE gear_asset_id=NEW.gear_asset_id
      UNION ALL SELECT permit_id FROM permit_site_gear WHERE gear_asset_id=NEW.gear_asset_id
    ) x JOIN entry_permit p USING(permit_id) WHERE p.status IN('DRAFT','AUTHORISED') ORDER BY x.permit_id
  LOOP
    PERFORM 1 FROM entry_permit WHERE permit_id=v_permit FOR UPDATE;
    UPDATE entry_permit SET evidence_revision=evidence_revision+1 WHERE permit_id=v_permit;
    PERFORM record_current_permit_receipt(v_permit);
  END LOOP;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_gear_asset_change_effects AFTER UPDATE OF status,inspection_valid_until,ulb_id,gear_code,serial_no
  ON gear_asset FOR EACH ROW EXECUTE FUNCTION gear_asset_change_effects();
REVOKE ALL ON FUNCTION gear_asset_change_effects() FROM PUBLIC,ze_app;

CREATE FUNCTION gear_issue_asset_bind() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE v_code text; v_serial text; v_ulb bigint;
BEGIN
  SELECT m.ulb_id INTO v_ulb FROM entry_permit p JOIN job j USING(job_id) JOIN complaint c USING(complaint_id)
    JOIN manhole m USING(manhole_id) WHERE p.permit_id=NEW.permit_id;
  IF NEW.gear_asset_id IS NULL THEN
    INSERT INTO gear_asset(ulb_id,gear_code,serial_no,status,inspection_valid_until)
      VALUES(v_ulb,NEW.gear_code,NEW.serial_no,'USABLE',NULL)
      ON CONFLICT(serial_no) DO UPDATE SET serial_no=EXCLUDED.serial_no
        WHERE gear_asset.gear_code=EXCLUDED.gear_code AND gear_asset.ulb_id=EXCLUDED.ulb_id
      RETURNING gear_asset_id INTO NEW.gear_asset_id;
  END IF;
  SELECT gear_code,serial_no INTO v_code,v_serial FROM gear_asset WHERE gear_asset_id=NEW.gear_asset_id AND ulb_id=v_ulb;
  IF v_code IS DISTINCT FROM NEW.gear_code OR v_serial IS DISTINCT FROM NEW.serial_no THEN
    RAISE EXCEPTION 'Gear item and serial must match an asset in the permit ULB' USING ERRCODE='ZE002';
  END IF;
  IF EXISTS(SELECT 1 FROM permit_site_gear WHERE permit_id=NEW.permit_id AND gear_asset_id=NEW.gear_asset_id) THEN
    RAISE EXCEPTION 'A shared site asset cannot also be assigned as personal gear' USING ERRCODE='ZE002';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_gear_issue_asset_bind BEFORE INSERT OR UPDATE OF gear_code,serial_no,gear_asset_id ON gear_issue
  FOR EACH ROW EXECUTE FUNCTION gear_issue_asset_bind();
REVOKE ALL ON FUNCTION gear_issue_asset_bind() FROM PUBLIC,ze_app;

CREATE FUNCTION site_gear_scope_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE v_ulb bigint; v_status text;
BEGIN
  PERFORM 1 FROM entry_permit WHERE permit_id=NEW.permit_id FOR UPDATE;
  SELECT m.ulb_id,p.status INTO v_ulb,v_status FROM entry_permit p JOIN job j USING(job_id)
    JOIN complaint c USING(complaint_id) JOIN manhole m USING(manhole_id) WHERE p.permit_id=NEW.permit_id;
  IF v_status NOT IN('DRAFT','AUTHORISED') THEN RAISE EXCEPTION 'Site gear cannot change while permit is %',v_status USING ERRCODE='ZE003'; END IF;
  IF NOT EXISTS(SELECT 1 FROM gear_asset WHERE gear_asset_id=NEW.gear_asset_id AND ulb_id=v_ulb) THEN
    RAISE EXCEPTION 'Site gear asset must belong to the permit ULB' USING ERRCODE='ZE002';
  END IF;
  IF EXISTS(SELECT 1 FROM gear_issue WHERE permit_id=NEW.permit_id AND gear_asset_id=NEW.gear_asset_id) THEN
    RAISE EXCEPTION 'A personal asset cannot also be assigned as shared site gear' USING ERRCODE='ZE002';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_site_gear_scope BEFORE INSERT OR UPDATE ON permit_site_gear FOR EACH ROW EXECUTE FUNCTION site_gear_scope_guard();
REVOKE ALL ON FUNCTION site_gear_scope_guard() FROM PUBLIC,ze_app;

CREATE FUNCTION refresh_current_receipt() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE v_id bigint;
BEGIN
  IF TG_OP='DELETE' THEN v_id:=OLD.permit_id; ELSE v_id:=NEW.permit_id; END IF;
  PERFORM record_current_permit_receipt(v_id);
  RETURN NULL;
END $$;
CREATE TRIGGER trg_gas_receipt_refresh AFTER INSERT ON gas_reading FOR EACH ROW EXECUTE FUNCTION refresh_current_receipt();
CREATE TRIGGER trg_readiness_receipt_refresh AFTER INSERT ON permit_readiness FOR EACH ROW EXECUTE FUNCTION refresh_current_receipt();
REVOKE ALL ON FUNCTION refresh_current_receipt() FROM PUBLIC,ze_app;

ALTER TABLE gear_asset ENABLE ROW LEVEL SECURITY;
ALTER TABLE permit_site_gear ENABLE ROW LEVEL SECURITY;
ALTER TABLE permit_readiness ENABLE ROW LEVEL SECURITY;
ALTER TABLE permit_resource_reservation ENABLE ROW LEVEL SECURITY;
ALTER TABLE permit_decision_receipt ENABLE ROW LEVEL SECURITY;
ALTER TABLE completion_claim ENABLE ROW LEVEL SECURITY;
ALTER TABLE completion_projection ENABLE ROW LEVEL SECURITY;
CREATE FUNCTION contractor_owns_job(p_job_id bigint) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=public,pg_temp AS $$ SELECT EXISTS(SELECT 1 FROM job WHERE job_id=p_job_id AND contractor_id=app_contractor_id()) $$;
REVOKE ALL ON FUNCTION contractor_owns_job(bigint) FROM PUBLIC,ze_app;
GRANT EXECUTE ON FUNCTION contractor_owns_job(bigint) TO ze_app;
CREATE POLICY rls_select ON gear_asset FOR SELECT USING(app_is_staff());
CREATE POLICY rls_select ON permit_site_gear FOR SELECT USING(app_is_staff() OR worker_on_permit(permit_id) OR contractor_owns_permit(permit_id));
CREATE POLICY rls_select ON permit_readiness FOR SELECT USING(app_is_staff() OR worker_on_permit(permit_id) OR contractor_owns_permit(permit_id));
CREATE POLICY rls_insert ON permit_readiness FOR INSERT WITH CHECK(permit_writer(permit_id) AND recorded_by=app_user_id());
CREATE POLICY rls_select ON permit_resource_reservation FOR SELECT USING(app_is_staff() OR worker_on_permit(permit_id) OR contractor_owns_permit(permit_id));
CREATE POLICY rls_select ON permit_decision_receipt FOR SELECT USING(app_is_staff() OR worker_on_permit(permit_id) OR contractor_owns_permit(permit_id));
CREATE POLICY rls_select ON completion_claim FOR SELECT USING(app_is_staff() OR (matched_job_id IS NOT NULL AND contractor_owns_job(matched_job_id)));
CREATE POLICY rls_insert ON completion_claim FOR INSERT WITH CHECK(app_has_role('ADMIN','ENGINEER'));
CREATE POLICY rls_select ON completion_projection FOR SELECT USING(app_is_staff() OR contractor_owns_job(job_id));
CREATE POLICY rls_insert_site_gear ON permit_site_gear FOR INSERT WITH CHECK(permit_writer(permit_id));
CREATE POLICY rls_update_site_gear ON permit_site_gear FOR UPDATE USING(permit_writer(permit_id)) WITH CHECK(permit_writer(permit_id));
CREATE POLICY rls_worker_ack_update ON permit_crew FOR UPDATE
  USING(app_role()='WORKER' AND worker_id=app_worker_id())
  WITH CHECK(app_role()='WORKER' AND worker_id=app_worker_id());
GRANT SELECT ON gear_asset,permit_site_gear,permit_readiness,permit_resource_reservation,permit_decision_receipt,completion_claim,completion_projection TO ze_app;
GRANT INSERT ON permit_readiness,completion_claim TO ze_app;
GRANT INSERT,UPDATE ON permit_site_gear TO ze_app;
GRANT UPDATE (acknowledged_at,acknowledged_by) ON permit_crew TO ze_app;
GRANT INSERT,UPDATE ON gear_asset TO ze_app;
GRANT USAGE,SELECT ON SEQUENCE permit_readiness_readiness_id_seq,completion_claim_claim_id_seq,gear_asset_gear_asset_id_seq,permit_site_gear_site_gear_id_seq TO ze_app;
REVOKE INSERT,UPDATE,DELETE ON permit_resource_reservation,permit_decision_receipt,completion_projection FROM ze_app;
REVOKE ALL ON SEQUENCE permit_resource_reservation_reservation_id_seq,permit_decision_receipt_receipt_id_seq FROM ze_app;

CREATE FUNCTION completion_claim_scope_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE v_ulb bigint;
BEGIN
  IF NEW.matched_job_id IS NOT NULL THEN
    SELECT m.ulb_id INTO v_ulb FROM job j JOIN complaint c USING(complaint_id) JOIN manhole m USING(manhole_id)
      WHERE j.job_id=NEW.matched_job_id;
    IF v_ulb IS DISTINCT FROM NEW.source_ulb_id THEN
      RAISE EXCEPTION 'Matched completion claim and source municipality must agree' USING ERRCODE='ZE002';
    END IF;
    NEW.match_status:='MATCHED';
  ELSIF NEW.match_status='MATCHED' THEN RAISE EXCEPTION 'A matched claim requires a job reference' USING ERRCODE='ZE002';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_completion_claim_scope BEFORE INSERT OR UPDATE OF matched_job_id,source_ulb_id ON completion_claim
  FOR EACH ROW EXECUTE FUNCTION completion_claim_scope_guard();
REVOKE ALL ON FUNCTION completion_claim_scope_guard() FROM PUBLIC,ze_app;

CREATE OR REPLACE VIEW v_completion_claim_reference WITH(security_invoker=true) AS
WITH grace AS MATERIALIZED(SELECT make_interval(hours=>rule_num('shadow_grace_hours')::int) AS duration)
SELECT cc.claim_id,cc.source_ulb_id,cc.source,cc.external_id,cc.external_job_ref,cc.matched_job_id,
       cc.claimed_status,cc.claimed_at,cc.match_status,j.complaint_id,c.status AS complaint_status,
       c.resolution_code,c.resolved_at,c.resolved_at+grace.duration AS evidence_deadline,
       EXISTS(SELECT 1 FROM machine_deployment d WHERE d.job_id=cc.matched_job_id AND d.outcome='CLEARED'
         AND d.outcome_recorded_at IS NOT NULL AND d.outcome_recorded_at<=c.resolved_at+grace.duration) AS timely_machine_evidence,
       EXISTS(SELECT 1 FROM entry_permit p WHERE p.job_id=cc.matched_job_id AND p.status='CLOSED'
         AND p.authorised_at IS NOT NULL AND p.ended_at<=c.resolved_at+grace.duration
         AND EXISTS(SELECT 1 FROM permit_crew pc WHERE pc.permit_id=p.permit_id AND pc.crew_role='ENTRANT')
         AND NOT EXISTS(SELECT 1 FROM permit_crew pc WHERE pc.permit_id=p.permit_id AND pc.crew_role='ENTRANT'
           AND NOT EXISTS(SELECT 1 FROM entry_log e WHERE e.permit_id=p.permit_id AND e.worker_id=pc.worker_id
             AND NOT lower_inf(e.period) AND NOT upper_inf(e.period) AND e.recorded_at<=c.resolved_at+grace.duration
             AND e.exit_recorded_at IS NOT NULL AND e.exit_recorded_at<=c.resolved_at+grace.duration))) AS timely_permit_evidence,
       (EXISTS(SELECT 1 FROM machine_deployment d WHERE d.job_id=cc.matched_job_id AND d.outcome='CLEARED'
          AND d.outcome_recorded_at>c.resolved_at+grace.duration)
        OR EXISTS(SELECT 1 FROM entry_permit p WHERE p.job_id=cc.matched_job_id AND p.status='CLOSED'
          AND p.authorised_at IS NOT NULL AND EXISTS(SELECT 1 FROM permit_crew pc WHERE pc.permit_id=p.permit_id AND pc.crew_role='ENTRANT')
          AND EXISTS(SELECT 1 FROM permit_crew pc WHERE pc.permit_id=p.permit_id AND pc.crew_role='ENTRANT'
            AND EXISTS(SELECT 1 FROM entry_log e WHERE e.permit_id=p.permit_id AND e.worker_id=pc.worker_id
              AND NOT upper_inf(e.period) AND (e.recorded_at>c.resolved_at+grace.duration
                OR e.exit_recorded_at>c.resolved_at+grace.duration))))) AS late_evidence_exists,
       COALESCE(holds.refs,'[]'::jsonb) AS invoice_hold_refs,
       CASE WHEN cc.match_status='AMBIGUOUS' THEN 'AMBIGUOUS_CLAIM'
            WHEN cc.matched_job_id IS NULL THEN 'UNMATCHED_CLAIM'
            WHEN cc.claimed_status<>'COMPLETED' THEN 'CLAIM_NOT_COMPLETED'
            WHEN c.status IS DISTINCT FROM 'RESOLVED' OR COALESCE(rt.requires_evidence,false)=false THEN NULL
            WHEN EXISTS(SELECT 1 FROM machine_deployment d WHERE d.job_id=cc.matched_job_id AND d.outcome='CLEARED'
              AND d.outcome_recorded_at IS NOT NULL AND d.outcome_recorded_at<=c.resolved_at+grace.duration)
              OR EXISTS(SELECT 1 FROM entry_permit p WHERE p.job_id=cc.matched_job_id AND p.status='CLOSED'
                AND p.authorised_at IS NOT NULL AND p.ended_at<=c.resolved_at+grace.duration
                AND EXISTS(SELECT 1 FROM permit_crew pc WHERE pc.permit_id=p.permit_id AND pc.crew_role='ENTRANT')
                AND NOT EXISTS(SELECT 1 FROM permit_crew pc WHERE pc.permit_id=p.permit_id AND pc.crew_role='ENTRANT'
                  AND NOT EXISTS(SELECT 1 FROM entry_log e WHERE e.permit_id=p.permit_id AND e.worker_id=pc.worker_id
                    AND NOT lower_inf(e.period) AND NOT upper_inf(e.period) AND e.recorded_at<=c.resolved_at+grace.duration
                    AND e.exit_recorded_at IS NOT NULL AND e.exit_recorded_at<=c.resolved_at+grace.duration))) THEN NULL
            WHEN clock_timestamp()<=c.resolved_at+grace.duration THEN 'WITHIN_GRACE'
            WHEN (EXISTS(SELECT 1 FROM machine_deployment d WHERE d.job_id=cc.matched_job_id AND d.outcome='CLEARED'
                  AND d.outcome_recorded_at>c.resolved_at+grace.duration)
               OR EXISTS(SELECT 1 FROM entry_permit p WHERE p.job_id=cc.matched_job_id AND p.status='CLOSED'
                  AND p.authorised_at IS NOT NULL AND EXISTS(SELECT 1 FROM permit_crew pc WHERE pc.permit_id=p.permit_id AND pc.crew_role='ENTRANT')
                  AND EXISTS(SELECT 1 FROM permit_crew pc WHERE pc.permit_id=p.permit_id AND pc.crew_role='ENTRANT'
                    AND EXISTS(SELECT 1 FROM entry_log e WHERE e.permit_id=p.permit_id AND e.worker_id=pc.worker_id
                      AND NOT upper_inf(e.period) AND (e.recorded_at>c.resolved_at+grace.duration
                        OR e.exit_recorded_at>c.resolved_at+grace.duration))))) THEN 'LATE_EVIDENCE_HUMAN_REVIEW'
            ELSE 'COMPLETION_EVIDENCE_MISSING' END AS gap_code
FROM completion_claim cc
LEFT JOIN job j ON j.job_id=cc.matched_job_id
LEFT JOIN complaint c ON c.complaint_id=j.complaint_id
LEFT JOIN resolution_type rt ON rt.code=c.resolution_code
CROSS JOIN grace
LEFT JOIN LATERAL(SELECT jsonb_agg(jsonb_build_object('hold_id',h.hold_id,'reason',h.reason,
    'incident_id',h.incident_id,'alert_id',h.alert_id,'invoice_id',h.invoice_id) ORDER BY h.hold_id) AS refs
  FROM invoice i JOIN invoice_hold h USING(invoice_id) WHERE i.job_id=cc.matched_job_id) holds ON true;

-- Per-job incremental projection of the exact complaint-anchored reference anti-join above. The
-- projection retains one object per discrepant imported claim; source complaint/hold provenance stays
-- available in the reference view. A changed gap never silently clears human review disposition.
CREATE FUNCTION refresh_completion_projection(p_job_id bigint) RETURNS completion_projection
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE v_codes jsonb; v_result completion_projection%ROWTYPE;
BEGIN
  IF NOT EXISTS(SELECT 1 FROM job WHERE job_id=p_job_id) THEN
    RAISE EXCEPTION 'Job % does not exist',p_job_id USING ERRCODE='ZE004';
  END IF;
  SELECT COALESCE(jsonb_agg(jsonb_build_object('claim_id',claim_id,'gap_code',gap_code) ORDER BY claim_id),'[]'::jsonb)
    INTO v_codes FROM v_completion_claim_reference
   WHERE matched_job_id=p_job_id AND gap_code IS NOT NULL;
  INSERT INTO completion_projection(job_id,evidence_revision,gap_codes,has_gap,disposition,computed_at)
  VALUES(p_job_id,1,v_codes,jsonb_array_length(v_codes)>0,
         CASE WHEN jsonb_array_length(v_codes)=0 THEN 'RESOLVED' ELSE 'REVIEW_REQUIRED' END,clock_timestamp())
  ON CONFLICT(job_id) DO UPDATE SET
    evidence_revision=completion_projection.evidence_revision+1,
    gap_codes=EXCLUDED.gap_codes,
    has_gap=EXCLUDED.has_gap,
    computed_at=EXCLUDED.computed_at,
    disposition=CASE WHEN completion_projection.gap_codes IS DISTINCT FROM EXCLUDED.gap_codes
                     THEN 'REVIEW_REQUIRED' ELSE completion_projection.disposition END,
    reviewed_by=CASE WHEN completion_projection.gap_codes IS DISTINCT FROM EXCLUDED.gap_codes
                     THEN NULL ELSE completion_projection.reviewed_by END,
    review_reason=CASE WHEN completion_projection.gap_codes IS DISTINCT FROM EXCLUDED.gap_codes
                       THEN NULL ELSE completion_projection.review_reason END
  RETURNING * INTO v_result;
  RETURN v_result;
END $$;
REVOKE ALL ON FUNCTION refresh_completion_projection(bigint) FROM PUBLIC,ze_app;

-- Time alone can move a claim from WITHIN_GRACE to MISSING without any row mutation. Maintenance walks
-- matched jobs in bounded keyset batches and calls this same refresh function; callers restart at zero
-- after has_more=false so no job is starved by a fixed first-page sweep.
CREATE FUNCTION sweep_completion_projections(p_after_job_id bigint DEFAULT 0,p_limit integer DEFAULT 500)
RETURNS TABLE(processed_count integer,next_after_job_id bigint,has_more boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE v_ids bigint[]; v_count integer; v_more boolean; v_next bigint; v_job bigint;
BEGIN
  IF p_after_job_id<0 OR p_limit<1 OR p_limit>5000 THEN
    RAISE EXCEPTION 'Invalid completion projection sweep cursor or limit' USING ERRCODE='ZE002';
  END IF;
  SELECT array_agg(job_id ORDER BY job_id) INTO v_ids FROM (
    SELECT DISTINCT matched_job_id AS job_id FROM completion_claim
     WHERE matched_job_id IS NOT NULL AND matched_job_id>p_after_job_id
     ORDER BY matched_job_id LIMIT p_limit+1
  ) page;
  v_count:=LEAST(COALESCE(cardinality(v_ids),0),p_limit);
  v_more:=COALESCE(cardinality(v_ids),0)>p_limit;
  IF v_count>0 THEN
    FOR v_job IN SELECT unnest(v_ids[1:v_count]) LOOP
      PERFORM refresh_completion_projection(v_job);
    END LOOP;
    v_next:=v_ids[v_count];
  ELSE v_next:=0; END IF;
  RETURN QUERY SELECT v_count,v_next,v_more;
END $$;
REVOKE ALL ON FUNCTION sweep_completion_projections(bigint,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sweep_completion_projections(bigint,integer) TO ze_app;

CREATE FUNCTION completion_projection_source_changed() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE v_job bigint; v_old_job bigint;
BEGIN
  IF TG_TABLE_NAME='completion_claim' THEN
    IF TG_OP<>'INSERT' THEN v_old_job:=OLD.matched_job_id; IF v_old_job IS NOT NULL THEN PERFORM refresh_completion_projection(v_old_job); END IF; END IF;
    IF TG_OP<>'DELETE' THEN v_job:=NEW.matched_job_id; IF v_job IS NOT NULL AND v_job IS DISTINCT FROM v_old_job THEN PERFORM refresh_completion_projection(v_job); END IF; END IF;
  ELSIF TG_TABLE_NAME IN('machine_deployment','invoice') THEN
    IF TG_OP<>'INSERT' THEN v_old_job:=OLD.job_id; PERFORM refresh_completion_projection(v_old_job); END IF;
    IF TG_OP<>'DELETE' AND NEW.job_id IS DISTINCT FROM v_old_job THEN PERFORM refresh_completion_projection(NEW.job_id); END IF;
  ELSIF TG_TABLE_NAME IN('entry_permit','entry_log') THEN
    IF TG_OP<>'INSERT' THEN SELECT job_id INTO v_old_job FROM entry_permit WHERE permit_id=OLD.permit_id; END IF;
    IF v_old_job IS NOT NULL THEN PERFORM refresh_completion_projection(v_old_job); END IF;
    IF TG_OP<>'DELETE' THEN SELECT job_id INTO v_job FROM entry_permit WHERE permit_id=NEW.permit_id;
      IF v_job IS NOT NULL AND v_job IS DISTINCT FROM v_old_job THEN PERFORM refresh_completion_projection(v_job); END IF; END IF;
  ELSIF TG_TABLE_NAME='complaint' THEN
    FOR v_job IN SELECT job_id FROM job WHERE complaint_id=COALESCE(NEW.complaint_id,OLD.complaint_id) LOOP
      PERFORM refresh_completion_projection(v_job);
    END LOOP;
  ELSIF TG_TABLE_NAME='invoice_hold' THEN
    IF TG_OP<>'INSERT' THEN SELECT job_id INTO v_old_job FROM invoice WHERE invoice_id=OLD.invoice_id; END IF;
    IF v_old_job IS NOT NULL THEN PERFORM refresh_completion_projection(v_old_job); END IF;
    IF TG_OP<>'DELETE' THEN SELECT job_id INTO v_job FROM invoice WHERE invoice_id=NEW.invoice_id;
      IF v_job IS NOT NULL AND v_job IS DISTINCT FROM v_old_job THEN PERFORM refresh_completion_projection(v_job); END IF; END IF;
  END IF;
  RETURN NULL;
END $$;
CREATE TRIGGER trg_completion_projection_claim AFTER INSERT OR UPDATE OR DELETE ON completion_claim
  FOR EACH ROW EXECUTE FUNCTION completion_projection_source_changed();
CREATE TRIGGER trg_completion_projection_machine AFTER INSERT OR UPDATE OR DELETE ON machine_deployment
  FOR EACH ROW EXECUTE FUNCTION completion_projection_source_changed();
CREATE TRIGGER trg_completion_projection_permit AFTER INSERT OR UPDATE OF status,ended_at ON entry_permit
  FOR EACH ROW EXECUTE FUNCTION completion_projection_source_changed();
CREATE TRIGGER trg_completion_projection_entry AFTER INSERT OR UPDATE OR DELETE ON entry_log
  FOR EACH ROW EXECUTE FUNCTION completion_projection_source_changed();
CREATE TRIGGER trg_completion_projection_complaint AFTER INSERT OR UPDATE OF status,resolved_at,resolution_code ON complaint
  FOR EACH ROW EXECUTE FUNCTION completion_projection_source_changed();
CREATE TRIGGER trg_completion_projection_invoice AFTER INSERT OR UPDATE OR DELETE ON invoice
  FOR EACH ROW EXECUTE FUNCTION completion_projection_source_changed();
CREATE TRIGGER trg_completion_projection_hold AFTER INSERT OR UPDATE OR DELETE ON invoice_hold
  FOR EACH ROW EXECUTE FUNCTION completion_projection_source_changed();
REVOKE ALL ON FUNCTION completion_projection_source_changed() FROM PUBLIC,ze_app;

CREATE OR REPLACE VIEW v_completion_claim_gaps WITH(security_invoker=true) AS
SELECT claim_id,source_ulb_id,source,external_id,external_job_ref,matched_job_id,claimed_status,claimed_at,match_status,gap_code
FROM v_completion_claim_reference;
COMMENT ON VIEW v_completion_claim_gaps IS 'Imported completion claims are compared with the time-aware per-job reference anti-join. Missing evidence means review, not proof of misconduct.';
