-- 01_base.sql: deterministic SYNTHETIC base data for demos and tests. No real people, licences or locations.
-- Idempotent: every insert is keyed by a natural key and uses ON CONFLICT DO NOTHING.
-- Demo users are created by src/zeroentry/seed.py (they need a bcrypt hash, so not in SQL).

INSERT INTO ulb (name, district, state) VALUES
  ('GCC Zone 4 - Tondiarpet', 'Chennai', 'Tamil Nadu'),
  ('GCC Zone 9 - Teynampet',  'Chennai', 'Tamil Nadu'),
  ('GCC Zone 13 - Adyar',     'Chennai', 'Tamil Nadu')
ON CONFLICT (name) DO NOTHING;

-- 60 manholes, 20 per zone. Every 5th is a septic tank; depths 2.0-6.5 m; coordinates scatter around Chennai.
INSERT INTO manhole (ulb_id, code, kind, depth_m, lat, lng, address)
SELECT u.ulb_id,
       format('CHN-%s-%s', z.abbr, lpad(g::text, 3, '0')),
       CASE WHEN g % 5 = 0 THEN 'SEPTIC' ELSE 'SEWER' END,
       round((2.0 + ((g * 37) % 46) / 10.0)::numeric, 2),
       round((13.0000 + z.lat_off + ((g * 13) % 100) / 2000.0)::numeric, 6),
       round((80.2000 + z.lng_off + ((g * 29) % 100) / 2000.0)::numeric, 6),
       format('Street %s, %s', g, z.label)
FROM (VALUES
        ('GCC Zone 4 - Tondiarpet', 'TON',  0.1000, 0.0700, 'Tondiarpet'),
        ('GCC Zone 9 - Teynampet',  'TEY',  0.0300, 0.0600, 'Teynampet'),
        ('GCC Zone 13 - Adyar',     'ADY', -0.0200, 0.0500, 'Adyar')
     ) AS z(ulb_name, abbr, lat_off, lng_off, label)
JOIN ulb u ON u.name = z.ulb_name
CROSS JOIN generate_series(1, 20) AS g
ON CONFLICT (code) DO NOTHING;

INSERT INTO contractor (name, licence_no, licence_valid_until) VALUES
  ('Marina Sanitation Services', 'TN-SAN-2026-001', '2027-03-31'),
  ('Cauvery Drainage Works',     'TN-SAN-2026-002', '2027-06-30'),
  ('Palar Infra Cleaners',       'TN-SAN-2026-003', '2027-01-31'),
  ('Adyar Hydro Services',       'TN-SAN-2026-004', '2027-09-30'),
  ('Coromandel Civic Works',     'TN-SAN-2026-005', '2026-12-31')
ON CONFLICT (licence_no) DO NOTHING;

-- 40 workers, 8 per contractor. Given name + neutral initial only (synthetic).
-- Deliberate gaps for the demo: workers 7 and 23 have lapsed medical fitness, worker 15 lapsed training.
INSERT INTO worker (contractor_id, full_name, namaste_id, medical_fit_until, trained_until)
SELECT c.contractor_id,
       (ARRAY['Murugan','Selvam','Karthik','Anbu','Ravi','Senthil','Kumar','Arun','Vijay','Mani',
              'Rajesh','Dinesh','Suresh','Gopal','Ramesh','Prakash','Saravanan','Velu','Balu','Sekar'])[1 + ((n - 1) * 7) % 20]
         || ' ' || (ARRAY['A.','K.','M.','P.','R.','S.','V.'])[1 + ((n - 1) * 3) % 7],
       format('NAM-TN-%s', 100000 + n),
       CASE WHEN n IN (7, 23) THEN DATE '2026-08-30' ELSE DATE '2027-06-30' END,
       CASE WHEN n = 15       THEN DATE '2026-07-31' ELSE DATE '2027-06-30' END
FROM generate_series(1, 40) AS n
JOIN contractor c ON c.licence_no = format('TN-SAN-2026-%s', lpad(((n - 1) / 8 + 1)::text, 3, '0'))
ON CONFLICT (namaste_id) DO NOTHING;

INSERT INTO machine (ulb_id, code, kind)
SELECT u.ulb_id, m.code, m.kind
FROM (VALUES ('GCC Zone 4 - Tondiarpet', 'JET-TON-01', 'JETTING'),
             ('GCC Zone 9 - Teynampet',  'JET-TEY-01', 'JETTING'),
             ('GCC Zone 13 - Adyar',     'SUC-ADY-01', 'SUCTION'),
             ('GCC Zone 13 - Adyar',     'ROB-ADY-01', 'ROBOT')) AS m(ulb_name, code, kind)
JOIN ulb u ON u.name = m.ulb_name
ON CONFLICT (code) DO NOTHING;

-- Two detectors; the second one's calibration has lapsed (the demo shows its readings being refused).
INSERT INTO gas_detector (serial_no, model, calibration_valid_until) VALUES
  ('GD-4G-0001', 'Demo 4-gas monitor', '2027-03-31'),
  ('GD-4G-0002', 'Demo 4-gas monitor', '2026-08-31')
ON CONFLICT (serial_no) DO NOTHING;
