-- 01_joins.sql: multi-table JOINs over the relationships in ER_DIAGRAM.md. Read-only; run against the demo data:
--   python scripts/run_sql.py database/queries/01_joins.sql      (or psql -f, against any ZeroEntry database)

-- 1. Permit dossier: permit -> job -> complaint -> manhole -> zone, and the contractor on the job (6 tables).
SELECT p.permit_id, p.status, m.code AS manhole, u.name AS zone, ct.name AS contractor, left(c.description, 50) AS complaint
FROM entry_permit p
JOIN job j        ON j.job_id = p.job_id
JOIN complaint c  ON c.complaint_id = j.complaint_id
JOIN manhole m    ON m.manhole_id = c.manhole_id
JOIN ulb u        ON u.ulb_id = m.ulb_id
JOIN contractor ct ON ct.contractor_id = j.contractor_id
ORDER BY p.permit_id;

-- 2. Crew of every permit, with each person's fitness dates (many-to-many: permit <-> worker through permit_crew).
SELECT pc.permit_id, pc.crew_role, w.full_name, w.namaste_id, w.medical_fit_until, w.trained_until, ct.name AS employer
FROM permit_crew pc
JOIN worker w      ON w.worker_id = pc.worker_id
JOIN contractor ct ON ct.contractor_id = w.contractor_id
ORDER BY pc.permit_id, pc.crew_role, w.full_name;

-- 3. Gear matrix of the newest DRAFT permit: every entrant x every statutory item, MISSING where no issue row exists.
--    (CROSS JOIN builds the required pairs; LEFT JOIN finds the matching records. The gaps are the denial reasons.)
SELECT w.namaste_id, g.name AS statutory_item, COALESCE(gi.serial_no, '** MISSING **') AS serial_no
FROM permit_crew pc
JOIN worker w ON w.worker_id = pc.worker_id
CROSS JOIN gear_item g
LEFT JOIN gear_issue gi ON gi.permit_id = pc.permit_id AND gi.worker_id = pc.worker_id AND gi.gear_code = g.gear_code
WHERE pc.permit_id = (SELECT max(permit_id) FROM entry_permit WHERE status = 'DRAFT')
  AND pc.crew_role = 'ENTRANT' AND g.statutory
ORDER BY w.namaste_id, g.name;

-- 4. Gas readings with the detector's calibration and the supervisor who signed each off.
SELECT r.permit_id, r.depth_level, r.taken_at, r.o2_pct, r.h2s_ppm, r.lel_pct, r.co_ppm, d.serial_no AS detector,
       d.calibration_valid_until, a.full_name AS signed_off_by
FROM gas_reading r
JOIN gas_detector d ON d.detector_id = r.detector_id
JOIN app_user a     ON a.user_id = r.recorded_by
ORDER BY r.permit_id, r.taken_at;

-- 5. The evidence picture of every resolved complaint (LEFT JOINs keep complaints with NO jobs or NO evidence visible).
SELECT c.complaint_id, m.code AS manhole, c.resolution_code,
       count(DISTINCT j.job_id)                                       AS jobs,
       count(d.deploy_id) FILTER (WHERE d.outcome = 'CLEARED')        AS machine_cleared,
       count(d.deploy_id) FILTER (WHERE d.outcome = 'FAILED')         AS machine_failed,
       count(DISTINCT p.permit_id) FILTER (WHERE p.status = 'CLOSED') AS closed_permits
FROM complaint c
JOIN manhole m              ON m.manhole_id = c.manhole_id
LEFT JOIN job j             ON j.complaint_id = c.complaint_id
LEFT JOIN machine_deployment d ON d.job_id = j.job_id
LEFT JOIN entry_permit p    ON p.job_id = j.job_id
WHERE c.status = 'RESOLVED'
GROUP BY c.complaint_id, m.code, c.resolution_code
ORDER BY c.complaint_id;

-- 6. Consequences of an incident: incident -> compensation case -> contractor -> zone (1:1 and N:1 relationships).
SELECT i.incident_id, i.incident_type, i.occurred_at, w.namaste_id, ct.name AS employer, ct.status AS employer_status,
       cc.amount_due, cc.amount_paid, cc.due_by, cc.status AS case_status, u.name AS zone
FROM incident i
JOIN worker w      ON w.worker_id = i.worker_id
JOIN contractor ct ON ct.contractor_id = i.contractor_id
JOIN manhole m     ON m.manhole_id = i.manhole_id
JOIN ulb u         ON u.ulb_id = m.ulb_id
LEFT JOIN compensation_case cc ON cc.incident_id = i.incident_id
ORDER BY i.occurred_at;

-- 7. Invoices with their active holds and where each hold came from (alert or incident).
SELECT inv.invoice_no, inv.amount_inr, inv.status, h.reason, COALESCE('alert #' || h.alert_id, 'incident #' || h.incident_id) AS source, h.placed_at
FROM invoice inv
JOIN invoice_hold h ON h.invoice_id = inv.invoice_id AND h.released_at IS NULL
ORDER BY inv.invoice_no;
