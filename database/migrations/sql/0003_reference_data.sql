-- 0003_reference_data.sql
-- Data the system cannot run without. Demo data lives in database/seeds/, not here.
-- Legal references are quoted as the proposal states them; rule numbers of the 2013 Rules are deliberately
-- NOT cited (the proposal says they must be checked against the Gazette). Rows marked is_assumption = true
-- are engineering placeholders listed in PROJECT_SPEC.md section 6.

INSERT INTO role (name, description) VALUES
  ('ADMIN',      'Manages users, rule parameters, gear catalogue and detectors'),
  ('ENGINEER',   'Municipal engineer / Responsible Sanitation Authority: complaints, jobs, waivers, alert review, invoices'),
  ('SUPERVISOR', 'Site supervisor: permits, crew, gear, gas readings, authorisation, entry logs'),
  ('WORKER',     'Sanitation worker: sees own permits, can stop work'),
  ('CONTRACTOR', 'Contractor office: sees own jobs, workers, permits and invoices only'),
  ('AUDITOR',    'Read-only reviewer of alerts, compensation, reports and the audit trail');

-- A resolution that claims "cleared" must have left evidence; the others are intentionally absent (BR-33).
INSERT INTO resolution_type (code, description, requires_evidence) VALUES
  ('CLEARED',             'Blockage cleared, by machine or by an authorised manual entry', true),
  ('NO_BLOCKAGE_FOUND',   'Inspection found no blockage',                                  false),
  ('DUPLICATE_COMPLAINT', 'Duplicate of another complaint',                                false),
  ('REFERRED_OUT',        'Not a municipal sewer; referred to another agency',             false),
  ('WITHDRAWN',           'Complainant withdrew the complaint',                            false);

INSERT INTO detection_rule (rule_code, title, description) VALUES
  ('SE1_NO_CLEARANCE_EVIDENCE',
   'Resolved without clearance evidence',
   'Complaint closed as cleared, but no machine deployment with outcome CLEARED and no authorised, closed permit with a logged entry was recorded in time.'),
  ('SE2_ENTRANT_NOT_LOGGED',
   'Closed permit with an unlogged entrant',
   'A permit was closed, but an entrant on its crew has no entry-log row recorded in time: someone may have gone down unrecorded.');

-- Entry-gate clauses, in the order the checklist shows them.
INSERT INTO legal_clause (clause_code, title, legal_ref, sort_order) VALUES
  ('MECH_WAIVER',     'Mechanised cleaning ruled out in writing by the Responsible Sanitation Authority', 'CPHEEO/MoHUA SOP 2018: manual entry only after reasons are recorded in writing', 10),
  ('CONTRACTOR_OK',   'Contractor is ACTIVE with a valid licence',                                       'Balram Singh v. Union of India (SC, 2023): contract cancellation / blacklisting', 20),
  ('CREW_ENTRANT',    'At least one entrant',                                                            '2013 Rules / MoHUA ERSU book: crew composition',                                30),
  ('CREW_SUPERVISOR', 'A supervisor is part of the crew',                                                '2013 Rules / MoHUA ERSU book: crew composition',                                40),
  ('CREW_STANDBY',    'A standby (top man) who does not enter',                                          '2013 Rules / MoHUA ERSU book: crew composition',                                50),
  ('CREW_SIZE',       'Crew has the minimum number of persons',                                          '2013 Rules / MoHUA ERSU book: at least three persons',                          60),
  ('CREW_FIT',        'Every crew member is medically fit and trained on the day',                       'Proposal section 6.2 (NAMASTE fitness and training dates); legal basis to be verified', 70),
  ('GEAR_ALL',        'Every entrant holds every statutory protective-gear item',                        '2013 Act s.2(1)(d) "hazardous cleaning"; 2013 Rules protective-gear schedule',  80),
  ('GAS_TOP',         'TOP atmosphere tested recently, by a calibrated detector, within limits',         '2013 Rules; CPHEEO SOP 2018; MoHUA ERSU advisory 2019',                         90),
  ('GAS_MID',         'MID atmosphere tested recently, by a calibrated detector, within limits',         '2013 Rules; CPHEEO SOP 2018; MoHUA ERSU advisory 2019',                        100),
  ('GAS_BOTTOM',      'BOTTOM atmosphere tested recently, by a calibrated detector, within limits',      '2013 Rules; CPHEEO SOP 2018; MoHUA ERSU advisory 2019',                        110);

-- Law as data: thresholds are rows, changing one is audited, none is hard-coded in a function.
INSERT INTO rule_parameter (param_key, value, unit, description, legal_ref, is_assumption) VALUES
  ('gas_o2_min',               19.5,    '% O2',      'Minimum oxygen',                                        '2013 Rules; CPHEEO SOP 2018', false),
  ('gas_o2_max',               21.0,    '% O2',      'Maximum oxygen',                                        '2013 Rules; CPHEEO SOP 2018', false),
  ('gas_h2s_max_ppm',          10,      'ppm',       'Hydrogen sulphide must be BELOW this value',            'MoHUA ERSU advisory 2019',    false),
  ('gas_lel_max_pct',          10,      '% LEL',     'Combustibles must be BELOW this value',                 'MoHUA ERSU advisory 2019',    false),
  ('gas_co_max_ppm',           35,      'ppm',       'Carbon monoxide must be BELOW this value',              'ASSUMPTION A-01 (NIOSH REL placeholder; not in the proposal)', true),
  ('gas_max_age_min',          15,      'minutes',   'A reading must be at most this old at authorisation',   'Proposal section 4 (2013 Rules; CPHEEO SOP 2018)', false),
  ('min_crew_size',            3,       'persons',   'Minimum crew including supervisor and standby',         '2013 Rules / MoHUA ERSU book', false),
  ('max_continuous_minutes',   90,      'minutes',   'Longest single entry',                                  '2013 Rules / MoHUA ERSU book', false),
  ('daylight_start_hour',      6,       'hour IST',  'Entries may not start before this hour',                'ASSUMPTION A-03 ("daylight only" has no fixed hours)', true),
  ('daylight_end_hour',        18,      'hour IST',  'Entries must end by this hour',                         'ASSUMPTION A-03', true),
  ('permit_valid_minutes',     240,     'minutes',   'How long an authorised permit stays valid',             'ASSUMPTION A-02', true),
  ('compensation_fatality_inr',3000000, 'INR',       'Compensation for a death',                              'Balram Singh v. Union of India (SC, 20 Oct 2023)', false),
  ('compensation_disability_inr',2000000,'INR',      'Compensation for a disability',                         'Balram Singh (range INR 10-20 lakh; upper end assumed) A-05', true),
  ('compensation_due_days',    30,      'days',      'Days after the incident by which compensation is due',  'ASSUMPTION A-05', true),
  ('shadow_grace_hours',       24,      'hours',     'Evidence recorded within this window after resolution counts as timely', 'ASSUMPTION A-06', true);

-- Statutory catalogue baseline per the proposal's examples; the real schedule must be verified (A-09).
INSERT INTO gear_item (gear_code, name, statutory, legal_ref) VALUES
  ('BREATHING_APPARATUS', 'Breathing apparatus (SCBA / air-line)', true,  '2013 Rules, protective-gear schedule (verify)'),
  ('GAS_MONITOR_4',       'Personal 4-gas monitor',                true,  '2013 Rules, protective-gear schedule (verify)'),
  ('SAFETY_HARNESS',      'Safety harness with lifeline',          true,  '2013 Rules, protective-gear schedule (verify)'),
  ('HELMET_LAMP',         'Helmet with head lamp',                 true,  '2013 Rules, protective-gear schedule (verify)'),
  ('WADER_SUIT',          'Wader / protective suit',               true,  '2013 Rules, protective-gear schedule (verify)'),
  ('GUMBOOTS',            'Gumboots',                              false, NULL),
  ('RUBBER_GLOVES',       'Rubber gloves',                         false, NULL),
  ('FIRST_AID_KIT',       'First-aid kit',                         false, NULL);
