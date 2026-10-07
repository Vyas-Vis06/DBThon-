-- 0014_policy_provenance.sql
-- Add source classification and append-only policy/authorization snapshots.
-- This is provenance for the configured product gate, not a compiler or certification of law.

-- ---------------------------------------------------------------------------------------------
-- Citation records. A source's classification is explicit; a clause may point to more than one
-- source because statutory text, operational guidance and a stricter product choice can coexist.
-- Citations are migration-managed and append-only for the runtime role.
-- ---------------------------------------------------------------------------------------------
CREATE TABLE policy_source (
  source_code       text PRIMARY KEY CHECK (source_code ~ '^[A-Z0-9_]+$'),
  source_type       text NOT NULL CHECK (source_type IN ('LAW', 'COURT_DIRECTION', 'GUIDANCE', 'PRODUCT_POLICY')),
  title             text NOT NULL,
  source_url        text,
  source_version    text NOT NULL,
  citation_clause   text NOT NULL,
  applicability     text NOT NULL
);

CREATE TABLE legal_clause_source (
  clause_code text NOT NULL REFERENCES legal_clause,
  source_code text NOT NULL REFERENCES policy_source,
  sort_order  smallint NOT NULL CHECK (sort_order > 0),
  PRIMARY KEY (clause_code, source_code),
  UNIQUE (clause_code, sort_order)
);

INSERT INTO policy_source (source_code, source_type, title, source_url, source_version, citation_clause, applicability) VALUES
  ('LAW_RULES_2013', 'LAW',
   'Prohibition of Employment as Manual Scavengers and their Rehabilitation Rules, 2013 (G.S.R. 776(E))',
   'https://socialjustice.gov.in/public/ckeditor/upload/86751727950899.pdf', 'G.S.R. 776(E), 12 Dec 2013',
   'Rules 3(1), 4, 6(3)(a), (b), (k), (p)',
   'Official Gazette text. Applicability depends on the particular clause; see each link and applicability note.'),
  ('COURT_BALRAM_2023', 'COURT_DIRECTION',
   'Balram Singh v. Union of India, Supreme Court of India, 20 October 2023',
   'https://api.sci.gov.in/supremecourt/2020/4072/4072_2020_8_1502_47917_Judgement_20-Oct-2023.pdf', '2023 judgment, directions ¶96(4)-(7)',
   'Paragraph 96(4)-(7)',
   'Court directions concerning sewer-death compensation and government/contract accountability; they do not supply every product threshold or make every sanction automatic.'),
  ('GUIDANCE_CPHEEO_2018', 'GUIDANCE',
   'CPHEEO, Standard Operating Procedure for Cleaning of Sewers and Septic Tanks',
   'https://cpheeo.gov.in/upload/5c0a062b23e94SOPforcleaningofSewersSepticTanks.pdf', '2018 SOP',
   'Sewer cleaning Step 4(ii), (xiv)',
   'CPHEEO 2018 government operational guidance. Includes three-depth oxygen testing, an explicit 19.5%-21% oxygen band, a 90-minute stretch and mandatory 30-minute interval.'),
  ('GUIDANCE_ERSU_2019', 'GUIDANCE',
   'MoHUA Emergency Response Sanitation Unit handbook',
   'https://static.pib.gov.in/WriteReadData/userfiles/SBM%20ERSU%20Book_Final.pdf', '2019 handbook',
   'Authorized Entrant / Attendant (Top Man) role descriptions; Annexure 2 gas table',
   'Government guidance, not statutory text. Annexure 2 presents gas-testing thresholds; it does not establish the app 15-minute freshness value.'),
  ('POLICY_MACHINE_FIRST_WAIVER', 'PRODUCT_POLICY',
   'ZeroEntry machine-first waiver control',
   'https://socialjustice.gov.in/public/ckeditor/upload/86751727950899.pdf', 'ZeroEntry policy baseline',
   'Rules 3(1)(a)-(e), read with Rule 3(1)(e)',
   'The app requires an engineer-approved written waiver before every permit. Rule 3(1)(e) specifically concerns the residual absolutely-necessary case; the app gate is a stricter product workflow and is not a verbatim Rule 3 implementation.'),
  ('POLICY_CONTRACTOR_GATE', 'PRODUCT_POLICY',
   'ZeroEntry contractor-status and licence gate',
   'https://api.sci.gov.in/supremecourt/2020/4072/4072_2020_8_1502_47917_Judgement_20-Oct-2023.pdf', 'ZeroEntry policy baseline',
   'Balram Singh directions ¶96(6)-(7)',
   'The app requires ACTIVE status and an unexpired licence. The cited directions address accountability/cancellation and a model contract with possible blacklisting; this exact status/licence check is product policy.'),
  ('POLICY_DISTINCT_CREW_ROLES', 'PRODUCT_POLICY',
   'ZeroEntry distinct entrant, supervisor and standby roles',
   'https://static.pib.gov.in/WriteReadData/userfiles/SBM%20ERSU%20Book_Final.pdf', 'ZeroEntry policy baseline',
   'ERSU handbook: Authorized Entrant and Attendant/Top Man descriptions',
   'The three distinct database roles are product policy informed by guidance. Rule 6(3)(a) requires three employees including a supervisor; it does not name three distinct statutory roles.'),
  ('POLICY_CREW_FIT', 'PRODUCT_POLICY',
   'ZeroEntry worker active, medical-fitness and training-date checks',
   'https://socialjustice.gov.in/public/ckeditor/upload/86751727950899.pdf', 'ZeroEntry policy baseline',
   'No exact expiring-date check is asserted from the cited Rules',
   'The app requires the configured active/medical/training fields to be current on the decision date. This is a product gate pending confirmation against applicable law and programme records.'),
  ('POLICY_GEAR_DIVISION', 'PRODUCT_POLICY',
   'ZeroEntry configured gear division',
   'https://socialjustice.gov.in/public/ckeditor/upload/86751727950899.pdf', 'ZeroEntry illustrative catalogue',
   'Rules 4 and 6(3)',
   'The app requires every gear_item marked statutory for every entrant. Rule 4 and its schedule mix personal protection and site equipment; the seeded global per-entrant set is illustrative and does not establish item-specific applicability.'),
  ('POLICY_GAS_FRESHNESS_15M', 'PRODUCT_POLICY',
   'ZeroEntry 15-minute gas-reading freshness threshold',
   'https://cpheeo.gov.in/upload/5c0a062b23e94SOPforcleaningofSewersSepticTanks.pdf', 'ZeroEntry policy baseline',
   'No 15-minute age limit identified in the cited SOP or Rules; Rule 6(3)(b), (p) concern gas testing and oxygen sampling',
   'A 15-minute cutoff is a configurable product policy. The linked document is relevant context, not authority for that numeric age.'),
  ('GUIDANCE_GAS_THRESHOLDS', 'GUIDANCE',
   'MoHUA ERSU handbook, Annexure 2 gas-testing table (CPHEEO manual extract)',
   'https://static.pib.gov.in/WriteReadData/userfiles/SBM%20ERSU%20Book_Final.pdf', '2019 handbook',
   'Annexure 2',
   'The cited O2/H2S/combustible thresholds are guidance values. Rule 6(3)(b) names hazards and Rule 6(3)(p) sets the statutory oxygen band; numeric H2S/LEL values are not attributed to that statutory clause.'),
  ('POLICY_CO_SAMPLE_35PPM', 'PRODUCT_POLICY',
   'ZeroEntry CO sample threshold',
   'https://www.cdc.gov/niosh/npg/npgd0105.html', 'ZeroEntry A-01; NIOSH Pocket Guide reference',
   'NIOSH REL TWA 35 ppm; ceiling 200 ppm',
   'The app compares a single reading with 35 ppm. NIOSH describes 35 ppm as an occupational time-weighted average and 200 ppm as a ceiling; using the TWA value as a spot-reading cutoff is a product assumption, does not calculate a time-weighted exposure, and is not an Indian legal limit.'),
  ('POLICY_FIXED_DAYLIGHT', 'PRODUCT_POLICY',
   'ZeroEntry fixed 06:00-18:00 daylight proxy',
   'https://socialjustice.gov.in/public/ckeditor/upload/86751727950899.pdf', 'ZeroEntry assumption A-03',
   'Rule 6(3)(k) says work is in daylight; it does not set fixed clock hours',
   'The configured fixed-hour window is a proxy for daylight and does not calculate local sunrise/sunset.'),
  ('POLICY_PERMIT_VALIDITY', 'PRODUCT_POLICY',
   'ZeroEntry permit validity duration', NULL, 'ZeroEntry assumption A-02',
   'No 240-minute statutory permit duration is asserted',
   'The 240-minute duration is an application assumption used to bound the authorization window.'),
  ('POLICY_COMPENSATION_DUE_30D', 'PRODUCT_POLICY',
   'ZeroEntry compensation due-date policy',
   'https://api.sci.gov.in/supremecourt/2020/4072/4072_2020_8_1502_47917_Judgement_20-Oct-2023.pdf', 'ZeroEntry assumption A-05',
   'Balram Singh direction ¶96(4); no general 30-day due period identified there',
   'The 30-day due period is a product assumption; it is not attributed to the judgment.'),
  ('POLICY_DISABILITY_AMOUNT', 'PRODUCT_POLICY',
   'ZeroEntry flat disability amount selection',
   'https://api.sci.gov.in/supremecourt/2020/4072/4072_2020_8_1502_47917_Judgement_20-Oct-2023.pdf', 'ZeroEntry assumption A-05',
   'Balram Singh direction ¶96(5)',
   'The configured ₹20 lakh value is a product choice. The direction sets a minimum of ₹10 lakh and a minimum of ₹20 lakh for a stated permanent-disability/economic-helplessness condition; it does not set one universal amount or a ceiling.'),
  ('POLICY_BLACKLIST', 'PRODUCT_POLICY',
   'ZeroEntry automatic contractor blacklist response',
   'https://api.sci.gov.in/supremecourt/2020/4072/4072_2020_8_1502_47917_Judgement_20-Oct-2023.pdf', 'ZeroEntry policy baseline',
   'Balram Singh directions ¶96(6)-(7)',
   'The prototype automatically blacklists after fatality. The judgment directs accountability/cancellation and describes blacklisting as a possible model-contract consequence; automatic blacklisting is team policy.'),
  ('POLICY_SHADOW_GRACE_24H', 'PRODUCT_POLICY',
   'ZeroEntry 24-hour evidence grace window', NULL, 'ZeroEntry assumption A-06',
   'No source-specific 24-hour statutory or guidance period is asserted',
   'The 24-hour grace period is a product choice for late field-record synchronization.'),
  ('POLICY_FATALITY_AMOUNT', 'COURT_DIRECTION',
   'ZeroEntry fatality compensation amount grounded in Balram Singh',
   'https://api.sci.gov.in/supremecourt/2020/4072/4072_2020_8_1502_47917_Judgement_20-Oct-2023.pdf', '2023 judgment',
   'Direction ¶96(4)',
   'The judgment directs ₹30 lakh for sewer deaths. The app amount is a configured value and does not decide legal entitlement or a case-specific deadline.'),
  ('LAW_CREW_SIZE', 'LAW',
   '2013 Rules minimum crew count',
   'https://socialjustice.gov.in/public/ckeditor/upload/86751727950899.pdf', 'G.S.R. 776(E), 12 Dec 2013',
   'Rule 6(3)(a)',
   'At least three employees are to be present at all times, including at least one supervisor.'),
  ('LAW_ENTRY_DURATION', 'LAW',
   '2013 Rules daylight and work-stretch limit',
   'https://socialjustice.gov.in/public/ckeditor/upload/86751727950899.pdf', 'G.S.R. 776(E), 12 Dec 2013',
   'Rule 6(3)(k)(i)-(ii)',
   'The rule states daylight, no more than 90 minutes at a stretch, and a 30-minute interval between stretches. This citation record is not itself enforcement; inspect the active database guard and tests for the exact implementation.' ),
  ('LAW_REST_INTERVAL', 'LAW',
   '2013 Rules mandatory interval between work stretches',
   'https://socialjustice.gov.in/public/ckeditor/upload/86751727950899.pdf', 'G.S.R. 776(E), 12 Dec 2013',
   'Rule 6(3)(k)(ii)',
   'Requires a mandatory 30-minute interval between stretches after a duration not exceeding 90 minutes. In this release, entry_log_guard enforces the configured rest per worker after a recorded stretch lasting at least the configured 90-minute maximum, measured from the later of reported exit and server receipt; the source citation does not itself enforce behavior.'),
  ('LAW_OXYGEN_BOUNDS', 'LAW',
   '2013 Rules oxygen limits and three-level measurement',
   'https://socialjustice.gov.in/public/ckeditor/upload/86751727950899.pdf', 'G.S.R. 776(E), 12 Dec 2013',
   'Rule 6(3)(b), (p)',
   'Rule 6(3)(p) names bottom, middle and top measurement and a 19.5% minimum. Its published English wording about the 21% boundary is conjunctively phrased and ambiguous; the maximum configured here is separately attributed to CPHEEO guidance. Rule 6(3)(b) requires testing for named toxic/combustible hazards.'),
  ('POLICY_GAS_COMPOSITE', 'PRODUCT_POLICY',
   'ZeroEntry composite gas-check policy',
   'https://socialjustice.gov.in/public/ckeditor/upload/86751727950899.pdf', 'ZeroEntry policy baseline',
   'Rules 6(3)(b), (p); see separately linked CPHEEO/ERSU guidance and 15-minute policy',
   'GAS_TOP/MID/BOTTOM combine statutory oxygen requirements with guidance thresholds, a CO product threshold and a 15-minute freshness rule. The composite clause is not an executable representation of law.'),
  ('LAW_PROTECTIVE_GEAR', 'LAW',
   '2013 Rules protective-gear duties and schedule',
   'https://socialjustice.gov.in/public/ckeditor/upload/86751727950899.pdf', 'G.S.R. 776(E), 12 Dec 2013',
   'Rule 4 and Schedule; Rule 6(3)',
   'The schedule contains both personal and site equipment, and Rule 6 gives conditional applicability. Do not read the current global per-entrant catalogue flag as a complete statutory mapping.');

-- Link each checklist clause to the exact source record(s) and their stated applicability.
INSERT INTO legal_clause_source (clause_code, source_code, sort_order) VALUES
  ('MECH_WAIVER', 'POLICY_MACHINE_FIRST_WAIVER', 1),
  ('CONTRACTOR_OK', 'POLICY_CONTRACTOR_GATE', 1),
  ('CREW_ENTRANT', 'POLICY_DISTINCT_CREW_ROLES', 1),
  ('CREW_SUPERVISOR', 'LAW_CREW_SIZE', 1),
  ('CREW_STANDBY', 'POLICY_DISTINCT_CREW_ROLES', 1),
  ('CREW_SIZE', 'LAW_CREW_SIZE', 1),
  ('CREW_FIT', 'POLICY_CREW_FIT', 1),
  ('GEAR_ALL', 'LAW_PROTECTIVE_GEAR', 1),
  ('GEAR_ALL', 'POLICY_GEAR_DIVISION', 2),
  ('GAS_TOP', 'LAW_OXYGEN_BOUNDS', 1),
  ('GAS_TOP', 'GUIDANCE_CPHEEO_2018', 2),
  ('GAS_TOP', 'GUIDANCE_GAS_THRESHOLDS', 3),
  ('GAS_TOP', 'POLICY_GAS_FRESHNESS_15M', 4),
  ('GAS_TOP', 'POLICY_CO_SAMPLE_35PPM', 5),
  ('GAS_TOP', 'POLICY_GAS_COMPOSITE', 6),
  ('GAS_MID', 'LAW_OXYGEN_BOUNDS', 1),
  ('GAS_MID', 'GUIDANCE_CPHEEO_2018', 2),
  ('GAS_MID', 'GUIDANCE_GAS_THRESHOLDS', 3),
  ('GAS_MID', 'POLICY_GAS_FRESHNESS_15M', 4),
  ('GAS_MID', 'POLICY_CO_SAMPLE_35PPM', 5),
  ('GAS_MID', 'POLICY_GAS_COMPOSITE', 6),
  ('GAS_BOTTOM', 'LAW_OXYGEN_BOUNDS', 1),
  ('GAS_BOTTOM', 'GUIDANCE_CPHEEO_2018', 2),
  ('GAS_BOTTOM', 'GUIDANCE_GAS_THRESHOLDS', 3),
  ('GAS_BOTTOM', 'POLICY_GAS_FRESHNESS_15M', 4),
  ('GAS_BOTTOM', 'POLICY_CO_SAMPLE_35PPM', 5),
  ('GAS_BOTTOM', 'POLICY_GAS_COMPOSITE', 6);

-- Keep the human-readable legacy reference truthful for clients that still display legal_ref.
UPDATE legal_clause SET legal_ref = CASE clause_code
  WHEN 'MECH_WAIVER' THEN 'PRODUCT_POLICY: Rules 2013 r.3(1) exception structure; app requires written engineer waiver for every permit (stricter than r.3(1)(e))'
  WHEN 'CONTRACTOR_OK' THEN 'PRODUCT_POLICY: Balram Singh directions ¶96(6)-(7) concern accountability / possible model-contract blacklisting; this exact status/licence test is product policy'
  WHEN 'CREW_ENTRANT' THEN 'PRODUCT_POLICY informed by ERSU guidance: distinct entrant role'
  WHEN 'CREW_SUPERVISOR' THEN 'LAW: 2013 Rules r.6(3)(a), at least three present including a supervisor'
  WHEN 'CREW_STANDBY' THEN 'PRODUCT_POLICY informed by ERSU guidance: distinct outside attendant / top-man role'
  WHEN 'CREW_SIZE' THEN 'LAW: 2013 Rules r.6(3)(a), minimum three employees including one supervisor'
  WHEN 'CREW_FIT' THEN 'PRODUCT_POLICY: active/medical/training date check; exact source mapping requires domain review'
  WHEN 'GEAR_ALL' THEN 'LAW: 2013 Rules r.4/Schedule and r.6; current universal per-entrant catalogue is illustrative and overstates item-specific applicability'
  WHEN 'GAS_TOP' THEN 'MIXED: Rules oxygen minimum/depth requirement; CPHEEO 2018 oxygen band guidance; ERSU gas guidance; ZeroEntry freshness/CO product thresholds; see source links'
  WHEN 'GAS_MID' THEN 'MIXED: Rules oxygen minimum/depth requirement; CPHEEO 2018 oxygen band guidance; ERSU gas guidance; ZeroEntry freshness/CO product thresholds; see source links'
  WHEN 'GAS_BOTTOM' THEN 'MIXED: Rules oxygen minimum/depth requirement; CPHEEO 2018 oxygen band guidance; ERSU gas guidance; ZeroEntry freshness/CO product thresholds; see source links'
  ELSE legal_ref END;

-- ---------------------------------------------------------------------------------------------
-- Versioned parameter history. Current rows remain the active gate input; the append-only table is
-- a change record, not an effective-dated rule engine or a promise of historical re-evaluation.
-- ---------------------------------------------------------------------------------------------
ALTER TABLE rule_parameter ADD COLUMN revision integer NOT NULL DEFAULT 1 CHECK (revision > 0);
ALTER TABLE rule_parameter ADD COLUMN source_code text REFERENCES policy_source(source_code);

UPDATE rule_parameter SET
  source_code = CASE param_key
    WHEN 'gas_o2_min' THEN 'LAW_OXYGEN_BOUNDS'
    WHEN 'gas_o2_max' THEN 'GUIDANCE_CPHEEO_2018'
    WHEN 'gas_h2s_max_ppm' THEN 'GUIDANCE_GAS_THRESHOLDS'
    WHEN 'gas_lel_max_pct' THEN 'GUIDANCE_GAS_THRESHOLDS'
    WHEN 'gas_co_max_ppm' THEN 'POLICY_CO_SAMPLE_35PPM'
    WHEN 'gas_max_age_min' THEN 'POLICY_GAS_FRESHNESS_15M'
    WHEN 'min_crew_size' THEN 'LAW_CREW_SIZE'
    WHEN 'max_continuous_minutes' THEN 'LAW_ENTRY_DURATION'
    WHEN 'mandatory_rest_minutes' THEN 'LAW_REST_INTERVAL'
    WHEN 'daylight_start_hour' THEN 'POLICY_FIXED_DAYLIGHT'
    WHEN 'daylight_end_hour' THEN 'POLICY_FIXED_DAYLIGHT'
    WHEN 'permit_valid_minutes' THEN 'POLICY_PERMIT_VALIDITY'
    WHEN 'compensation_fatality_inr' THEN 'POLICY_FATALITY_AMOUNT'
    WHEN 'compensation_disability_inr' THEN 'POLICY_DISABILITY_AMOUNT'
    WHEN 'compensation_due_days' THEN 'POLICY_COMPENSATION_DUE_30D'
    WHEN 'shadow_grace_hours' THEN 'POLICY_SHADOW_GRACE_24H'
    ELSE NULL
  END;
ALTER TABLE rule_parameter ALTER COLUMN source_code SET NOT NULL;

-- Correct the 15-minute threshold's former non-assumption attribution. Its numeric value and gate behavior
-- remain unchanged; the source classification now makes the product-policy status explicit.
UPDATE rule_parameter SET
  is_assumption = true,
  legal_ref = 'PRODUCT_POLICY: 15-minute freshness is configurable; no matching limit identified in cited Rules/SOP'
WHERE param_key = 'gas_max_age_min';

UPDATE rule_parameter SET legal_ref = 'GUIDANCE: ERSU handbook Annexure 2 gas-testing table'
WHERE param_key IN ('gas_h2s_max_ppm', 'gas_lel_max_pct');
UPDATE rule_parameter SET legal_ref = 'GUIDANCE: CPHEEO 2018 SOP Step 4(ii), explicit 19.5%-21% oxygen band; unchanged product threshold'
WHERE param_key = 'gas_o2_max';
UPDATE rule_parameter SET legal_ref = 'PRODUCT_POLICY: 35 ppm is a NIOSH full-shift TWA reference, applied here to a spot reading as ASSUMPTION A-01'
WHERE param_key = 'gas_co_max_ppm';
UPDATE rule_parameter SET legal_ref = 'PRODUCT_POLICY: fixed 06:00-18:00 proxy for daylight; daylight is not a fixed clock interval'
WHERE param_key IN ('daylight_start_hour', 'daylight_end_hour');
UPDATE rule_parameter SET legal_ref = 'PRODUCT_POLICY: 240-minute authorization window (assumption A-02)'
WHERE param_key = 'permit_valid_minutes';
UPDATE rule_parameter SET legal_ref = 'COURT_DIRECTION: Balram Singh v. Union of India (SC, 20 Oct 2023), direction ¶96(4)'
WHERE param_key = 'compensation_fatality_inr';
UPDATE rule_parameter SET legal_ref = 'PRODUCT_POLICY: ₹20 lakh selection; Balram Singh ¶96(5) sets conditional minimums, not a universal amount or ceiling (assumption A-05)'
WHERE param_key = 'compensation_disability_inr';
UPDATE rule_parameter SET legal_ref = 'PRODUCT_POLICY: 30-day due period; no general period identified in Balram Singh ¶96(4) (assumption A-05)'
WHERE param_key = 'compensation_due_days';
UPDATE rule_parameter SET legal_ref = 'PRODUCT_POLICY: 24-hour evidence grace window (assumption A-06)'
WHERE param_key = 'shadow_grace_hours';

CREATE TABLE rule_parameter_history (
  history_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  param_key       text NOT NULL REFERENCES rule_parameter(param_key) ON DELETE RESTRICT,
  revision        integer NOT NULL CHECK (revision > 0),
  value           numeric NOT NULL,
  unit            text NOT NULL,
  description     text NOT NULL,
  legal_ref       text NOT NULL,
  is_assumption   boolean NOT NULL,
  source_code     text NOT NULL REFERENCES policy_source(source_code),
  effective_at    timestamptz NOT NULL,
  actor_user_id   bigint,
  change_reason   text NOT NULL CHECK (length(btrim(change_reason)) >= 10),
  recorded_at     timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (param_key, revision)
);

-- Existing parameter rows are the migration-time baseline. Earlier effective intervals/change reasons
-- were not present in the old schema and are not inferred here.
INSERT INTO rule_parameter_history
  (param_key, revision, value, unit, description, legal_ref, is_assumption, source_code,
   effective_at, actor_user_id, change_reason)
SELECT param_key, revision, value, unit, description, legal_ref, is_assumption, source_code,
       clock_timestamp(), NULL,
       'Initial provenance baseline at migration 0014; prior revision history was unavailable'
  FROM rule_parameter;

CREATE FUNCTION immutable_policy_record() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is migration-managed and append-only', TG_TABLE_NAME USING ERRCODE = 'ZE003';
END $$;

CREATE TRIGGER trg_policy_source_immutable BEFORE UPDATE OR DELETE ON policy_source
  FOR EACH ROW EXECUTE FUNCTION immutable_policy_record();
CREATE TRIGGER trg_legal_clause_source_immutable BEFORE UPDATE OR DELETE ON legal_clause_source
  FOR EACH ROW EXECUTE FUNCTION immutable_policy_record();
CREATE TRIGGER trg_rule_parameter_history_immutable BEFORE UPDATE OR DELETE ON rule_parameter_history
  FOR EACH ROW EXECUTE FUNCTION immutable_policy_record();

CREATE FUNCTION record_rule_parameter_revision() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  v_reason text := NULLIF(btrim(current_setting('app.rule_change_reason', true)), '');
  v_actor bigint;
BEGIN
  IF ROW(NEW.value, NEW.unit, NEW.description, NEW.legal_ref, NEW.is_assumption, NEW.source_code)
     IS NOT DISTINCT FROM ROW(OLD.value, OLD.unit, OLD.description, OLD.legal_ref, OLD.is_assumption, OLD.source_code) THEN
    RETURN NEW;
  END IF;

  -- ze_app is the only application login. Its authenticated API context must identify an ADMIN and
  -- provide a meaningful reason. Trusted migration/DBA writes may omit the request context.
  IF session_user = 'ze_app' THEN
    IF app_role() IS DISTINCT FROM 'ADMIN' OR app_user_id() IS NULL THEN
      RAISE EXCEPTION 'Only an authenticated ADMIN may change a rule parameter' USING ERRCODE = 'ZE006';
    END IF;
    IF v_reason IS NULL OR length(v_reason) < 10 THEN
      RAISE EXCEPTION 'A rule change reason of at least 10 characters is required' USING ERRCODE = 'ZE002';
    END IF;
    v_actor := app_user_id();
  ELSE
    v_actor := COALESCE(NEW.updated_by, app_user_id());
    v_reason := COALESCE(v_reason, format('Trusted database change by %s', session_user));
  END IF;

  NEW.revision := OLD.revision + 1;
  NEW.updated_by := v_actor;
  NEW.updated_at := clock_timestamp();
  INSERT INTO rule_parameter_history
    (param_key, revision, value, unit, description, legal_ref, is_assumption, source_code,
     effective_at, actor_user_id, change_reason)
  VALUES (NEW.param_key, NEW.revision, NEW.value, NEW.unit, NEW.description, NEW.legal_ref,
          NEW.is_assumption, NEW.source_code, NEW.updated_at, v_actor, v_reason);
  RETURN NEW;
END $$;

CREATE TRIGGER trg_rule_parameter_revision BEFORE UPDATE ON rule_parameter
  FOR EACH ROW EXECUTE FUNCTION record_rule_parameter_revision();

-- The permit guard re-checks the gate during the status UPDATE. Lock all active policy values first so an
-- administrator cannot change thresholds between that re-check and the immutable authorization snapshot.
CREATE FUNCTION lock_authorization_policy() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  IF OLD.status = 'DRAFT' AND NEW.status = 'AUTHORISED' THEN
    PERFORM param_key FROM rule_parameter ORDER BY param_key FOR SHARE;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_00_lock_authorization_policy BEFORE UPDATE ON entry_permit
  FOR EACH ROW EXECUTE FUNCTION lock_authorization_policy();

-- The existing permit_guard runs after this trigger alphabetically. For application sessions, discard
-- caller/transaction-start timestamps only after the permit and policy rows have been locked, so a raw
-- DRAFT -> AUTHORISED UPDATE cannot backdate around gas freshness or the permit validity window.
CREATE FUNCTION stamp_runtime_authorization_clock() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status = 'DRAFT' AND NEW.status = 'AUTHORISED' AND session_user = 'ze_app' THEN
    NEW.authorised_at := clock_timestamp();
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_01_runtime_authorization_clock BEFORE UPDATE ON entry_permit
  FOR EACH ROW EXECUTE FUNCTION stamp_runtime_authorization_clock();

-- Keep historical test/maintenance calls from trusted database sessions deterministic. The runtime
-- entry point ignores its transaction-start `now()` argument: after the permit row and active policy
-- rows are locked, it takes a fresh server time and uses that time for both its explanation and UPDATE.
CREATE OR REPLACE FUNCTION authorise_entry(p_permit_id bigint, p_actor_id bigint, p_at timestamptz DEFAULT now())
RETURNS TABLE (clause_code text, title text, legal_ref text, passed boolean, detail text, permit_status text)
LANGUAGE plpgsql AS $$
#variable_conflict use_column
DECLARE
  v_status text;
  v_rows jsonb;
  v_ok boolean;
  v_at timestamptz;
BEGIN
  SELECT p.status INTO v_status FROM entry_permit p WHERE p.permit_id = p_permit_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Permit % does not exist', p_permit_id USING ERRCODE = 'ZE004';
  END IF;
  IF v_status <> 'DRAFT' THEN
    RAISE EXCEPTION 'Permit % is % and can no longer be authorised', p_permit_id, v_status USING ERRCODE = 'ZE003';
  END IF;

  IF session_user = 'ze_app' THEN
    PERFORM rp.param_key FROM rule_parameter rp ORDER BY rp.param_key FOR SHARE;
    v_at := clock_timestamp();
  ELSE
    v_at := p_at;
  END IF;

  SELECT jsonb_agg(jsonb_build_object('clause_code', r.clause_code, 'passed', r.passed, 'detail', r.detail)),
         bool_and(r.passed)
    INTO v_rows, v_ok
    FROM permit_clause_check(p_permit_id, v_at) r;

  IF v_ok THEN
    BEGIN
      UPDATE entry_permit SET status = 'AUTHORISED', authorised_at = v_at, authorised_by = p_actor_id
       WHERE permit_id = p_permit_id; -- BEFORE triggers stamp and re-check at the final post-lock clock.
      v_status := 'AUTHORISED';
      -- Return the same timestamped clause evaluation the immutable AFTER trigger captured.
      SELECT p.authorised_at INTO v_at FROM entry_permit p WHERE p.permit_id = p_permit_id;
      SELECT jsonb_agg(jsonb_build_object('clause_code', r.clause_code, 'passed', r.passed, 'detail', r.detail)),
             bool_and(r.passed)
        INTO v_rows, v_ok
        FROM permit_clause_check(p_permit_id, v_at) r;
    EXCEPTION WHEN SQLSTATE 'ZE001' THEN
      -- A boundary may expire between the initial explanation and the BEFORE trigger's final check.
      -- Convert that race into the normal denial report; the failed UPDATE and its snapshot were rolled back.
      v_at := clock_timestamp();
      SELECT jsonb_agg(jsonb_build_object('clause_code', r.clause_code, 'passed', r.passed, 'detail', r.detail)),
             bool_and(r.passed)
        INTO v_rows, v_ok
        FROM permit_clause_check(p_permit_id, v_at) r;
      v_status := 'DRAFT';
    END;
  END IF;

  RETURN QUERY
  SELECT x.clause_code, l.title, l.legal_ref, x.passed, x.detail, v_status
    FROM jsonb_to_recordset(v_rows) AS x(clause_code text, passed boolean, detail text)
    JOIN legal_clause l ON l.clause_code = x.clause_code
   ORDER BY l.sort_order;
END $$;

-- ---------------------------------------------------------------------------------------------
-- Snapshot the successful authorization transition. The JSONB document preserves the exact gate output,
-- values/IDs used by that check, and the immutable citation records. It is an explanation snapshot, not a
-- formal proof that records are physically true or tamper-proof against the database owner.
-- ---------------------------------------------------------------------------------------------
CREATE TABLE permit_authorization_decision (
  decision_id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  permit_id           bigint NOT NULL UNIQUE REFERENCES entry_permit ON DELETE RESTRICT,
  decision_kind       text NOT NULL CHECK (decision_kind = 'AUTHORIZATION'),
  decision_at         timestamptz NOT NULL,
  actor_user_id       bigint NOT NULL,
  snapshot_format     smallint NOT NULL DEFAULT 1 CHECK (snapshot_format = 1),
  snapshot            jsonb NOT NULL,
  snapshot_sha256     text NOT NULL CHECK (snapshot_sha256 ~ '^[0-9a-f]{64}$'),
  captured_at         timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE FUNCTION permit_authorization_snapshot(p_permit_id bigint, p_at timestamptz, p_actor_id bigint)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  p entry_permit%ROWTYPE;
  v_job_id bigint;
  v_complaint_id bigint;
  v_contractor_id bigint;
  v_gate jsonb;
  v_params jsonb;
  v_sources jsonb;
  v_evidence jsonb;
BEGIN
  SELECT ep.* INTO p
    FROM entry_permit ep
   WHERE ep.permit_id = p_permit_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Permit % does not exist', p_permit_id USING ERRCODE = 'ZE004';
  END IF;
  SELECT j.job_id, j.complaint_id, j.contractor_id
    INTO v_job_id, v_complaint_id, v_contractor_id
    FROM job j WHERE j.job_id = p.job_id;

  SELECT COALESCE(jsonb_agg(jsonb_build_object(
           'clause_code', c.clause_code, 'passed', c.passed, 'detail', c.detail,
           'title', l.title, 'display_reference', l.legal_ref,
           'sources', COALESCE((
             SELECT jsonb_agg(jsonb_build_object(
                      'source_code', s.source_code, 'source_type', s.source_type, 'title', s.title,
                      'source_url', s.source_url, 'source_version', s.source_version,
                      'citation_clause', s.citation_clause, 'applicability', s.applicability)
                      ORDER BY lcs.sort_order)
               FROM legal_clause_source lcs JOIN policy_source s USING (source_code)
              WHERE lcs.clause_code = l.clause_code), '[]'::jsonb)
         ) ORDER BY l.sort_order), '[]'::jsonb)
    INTO v_gate
    FROM permit_clause_check(p_permit_id, p_at) c JOIN legal_clause l USING (clause_code);

  SELECT COALESCE(jsonb_agg(jsonb_build_object(
           'param_key', rp.param_key, 'revision', rp.revision, 'value', rp.value,
           'unit', rp.unit, 'is_assumption', rp.is_assumption,
           'source', jsonb_build_object('source_code', s.source_code, 'source_type', s.source_type,
             'title', s.title, 'source_url', s.source_url, 'source_version', s.source_version,
             'citation_clause', s.citation_clause, 'applicability', s.applicability))
           ORDER BY rp.param_key), '[]'::jsonb)
    INTO v_params
    FROM rule_parameter rp JOIN policy_source s USING (source_code);

  SELECT COALESCE(jsonb_agg(jsonb_build_object(
           'source_code', s.source_code, 'source_type', s.source_type, 'title', s.title,
           'source_url', s.source_url, 'source_version', s.source_version,
           'citation_clause', s.citation_clause, 'applicability', s.applicability)
           ORDER BY s.source_code), '[]'::jsonb)
    INTO v_sources
    FROM policy_source s;

  SELECT jsonb_build_object(
    'permit', jsonb_build_object('permit_id', p.permit_id, 'job_id', v_job_id,
      'complaint_id', v_complaint_id, 'supervisor_id', p.supervisor_id, 'status', p.status,
      'created_at', p.created_at, 'authorised_at', p.authorised_at, 'authorised_by', p.authorised_by,
      'valid_until', p.valid_until),
    'waiver', (SELECT jsonb_build_object('waiver_id', w.waiver_id, 'job_id', w.job_id,
      'reason_code', w.reason_code, 'justification', w.justification, 'approved_by', w.approved_by,
      'approved_at', w.approved_at)
      FROM mechanisation_waiver w WHERE w.job_id = v_job_id),
    'contractor', (SELECT jsonb_build_object('contractor_id', c.contractor_id,
      'status', c.status, 'licence_valid_until', c.licence_valid_until)
      FROM contractor c WHERE c.contractor_id = v_contractor_id),
    'crew', COALESCE((SELECT jsonb_agg(jsonb_build_object(
       'worker_id', w.worker_id, 'contractor_id', w.contractor_id, 'crew_role', pc.crew_role,
       'is_active', w.is_active, 'medical_fit_until', w.medical_fit_until, 'trained_until', w.trained_until,
       'gear_issues', COALESCE((SELECT jsonb_agg(jsonb_build_object(
          'issue_id', gi.issue_id, 'gear_code', gi.gear_code, 'gear_name', g.name,
          'catalogue_statutory_flag', g.statutory, 'serial_no', gi.serial_no,
          'issued_by', gi.issued_by, 'issued_at', gi.issued_at) ORDER BY gi.gear_code)
          FROM gear_issue gi JOIN gear_item g USING (gear_code)
         WHERE gi.permit_id = pc.permit_id AND gi.worker_id = pc.worker_id), '[]'::jsonb)
       ) ORDER BY pc.worker_id)
       FROM permit_crew pc JOIN worker w USING (worker_id)
       WHERE pc.permit_id = p_permit_id), '[]'::jsonb),
    'latest_gas_readings_by_depth', COALESCE((SELECT jsonb_agg(jsonb_build_object(
       'reading_id', r.reading_id, 'depth_level', r.depth_level, 'detector_id', r.detector_id,
       'serial_no', d.serial_no, 'detector_model', d.model,
       'calibration_valid_until', d.calibration_valid_until,
       'o2_pct', r.o2_pct, 'h2s_ppm', r.h2s_ppm, 'lel_pct', r.lel_pct, 'co_ppm', r.co_ppm,
       'taken_at', r.taken_at, 'recorded_by', r.recorded_by, 'recorded_at', r.recorded_at)
       ORDER BY r.depth_level)
       FROM (SELECT DISTINCT ON (gr.depth_level) gr.*
               FROM gas_reading gr WHERE gr.permit_id = p_permit_id AND gr.taken_at <= p_at
              ORDER BY gr.depth_level, gr.taken_at DESC, gr.reading_id DESC) r
       JOIN gas_detector d USING (detector_id)), '[]'::jsonb)
  ) INTO v_evidence;

  RETURN jsonb_build_object(
    'format', 'zeroentry.permit-authorization-decision.v1',
    'decision_kind', 'AUTHORIZATION',
    'permit_id', p_permit_id,
    'decision_at', p_at,
    'actor_user_id', p_actor_id,
    'gate', v_gate,
    'policy_parameters', v_params,
    'source_catalog', v_sources,
    'evidence', v_evidence
  );
END $$;

CREATE FUNCTION capture_permit_authorization_decision() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  v_snapshot jsonb;
BEGIN
  IF OLD.status = 'DRAFT' AND NEW.status = 'AUTHORISED' THEN
    v_snapshot := permit_authorization_snapshot(NEW.permit_id, NEW.authorised_at, NEW.authorised_by);
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(v_snapshot->'gate') AS checks(clause)
                WHERE (checks.clause->>'passed')::boolean IS NOT TRUE) THEN
      RAISE EXCEPTION 'The authorization snapshot does not show a passing gate' USING ERRCODE = 'ZE001';
    END IF;
    INSERT INTO permit_authorization_decision
      (permit_id, decision_kind, decision_at, actor_user_id, snapshot, snapshot_sha256)
    VALUES (NEW.permit_id, 'AUTHORIZATION', NEW.authorised_at, NEW.authorised_by, v_snapshot,
            encode(sha256(convert_to(v_snapshot::text, 'UTF8')), 'hex'));
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_permit_authorization_snapshot AFTER UPDATE ON entry_permit
  FOR EACH ROW EXECUTE FUNCTION capture_permit_authorization_decision();

CREATE TRIGGER trg_permit_authorization_decision_immutable
  BEFORE UPDATE OR DELETE ON permit_authorization_decision
  FOR EACH ROW EXECUTE FUNCTION immutable_policy_record();

-- Runtime sees citation/history/snapshot reads only. Insert is via the transition trigger; no app role can edit the
-- evidence artifact, history or citations. The DB owner/superuser remains inside the documented trust boundary.
REVOKE INSERT, UPDATE, DELETE ON policy_source, legal_clause_source, rule_parameter_history,
  permit_authorization_decision FROM ze_app;
GRANT SELECT ON policy_source, legal_clause_source, rule_parameter_history, permit_authorization_decision TO ze_app;
-- 0008 granted column-level writes to updated_by/updated_at, which a table-level REVOKE does not remove.
REVOKE UPDATE (value, updated_by, updated_at) ON rule_parameter FROM ze_app;
GRANT UPDATE (value) ON rule_parameter TO ze_app;

ALTER TABLE policy_source ENABLE ROW LEVEL SECURITY;
CREATE POLICY rls_select ON policy_source FOR SELECT USING (true);
ALTER TABLE legal_clause_source ENABLE ROW LEVEL SECURITY;
CREATE POLICY rls_select ON legal_clause_source FOR SELECT USING (true);
ALTER TABLE rule_parameter_history ENABLE ROW LEVEL SECURITY;
CREATE POLICY rls_select ON rule_parameter_history FOR SELECT USING (true);
ALTER TABLE permit_authorization_decision ENABLE ROW LEVEL SECURITY;
CREATE POLICY rls_select ON permit_authorization_decision FOR SELECT
  USING (app_is_staff() OR worker_on_permit(permit_id) OR contractor_owns_permit(permit_id));

COMMENT ON TABLE policy_source IS 'Migration-managed source metadata; source type distinguishes law, court directions, guidance and product policy.';
COMMENT ON TABLE legal_clause_source IS 'One or more classified source/applicability records for each entry checklist clause.';
COMMENT ON TABLE rule_parameter_history IS 'Append-only current-value change history with actor/reason/source; not a historical rule-replay engine.';
COMMENT ON TABLE permit_authorization_decision IS 'Immutable database-created JSONB snapshot for each successful authorization transition; not a formal proof or owner-resistant signature.';
COMMENT ON COLUMN permit_authorization_decision.snapshot_sha256 IS 'SHA-256 over UTF-8 bytes of PostgreSQL JSONB text rendering of snapshot (PG16); verify against snapshot::text.';
COMMENT ON FUNCTION permit_authorization_snapshot(bigint, timestamptz, bigint) IS 'Builds a versioned explanation snapshot of the exact successful entry gate decision and relevant evidence.';
COMMENT ON FUNCTION lock_authorization_policy() IS 'Locks active rule_parameter rows before the permit gate UPDATE re-check, keeping thresholds and decision snapshot aligned.';
REVOKE ALL ON FUNCTION permit_authorization_snapshot(bigint, timestamptz, bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION lock_authorization_policy() FROM PUBLIC;
