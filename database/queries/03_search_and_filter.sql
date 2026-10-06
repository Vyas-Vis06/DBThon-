-- 03_search_and_filter.sql: the searches behind the screens. Read-only. Each uses an index (see ix_* in 0002_core_schema.sql).

-- 1. Worker search by NAMASTE id prefix (ix_worker_namaste_prefix, text_pattern_ops) or by name prefix (ix_worker_name_prefix).
SELECT worker_id, full_name, namaste_id FROM worker WHERE namaste_id LIKE 'NAM-TN-1000%' ORDER BY namaste_id LIMIT 10;
SELECT worker_id, full_name, namaste_id FROM worker WHERE lower(full_name) LIKE 'a%' ORDER BY full_name;

-- 2. Permits filtered by status, zone, date range and contractor (all four filters on the permits screen).
SELECT p.permit_id, p.status, p.created_at, u.name AS zone, ct.name AS contractor
FROM entry_permit p
JOIN job j ON j.job_id = p.job_id JOIN complaint c ON c.complaint_id = j.complaint_id
JOIN manhole m ON m.manhole_id = c.manhole_id JOIN ulb u ON u.ulb_id = m.ulb_id JOIN contractor ct ON ct.contractor_id = j.contractor_id
WHERE p.status IN ('CLOSED', 'DRAFT')
  AND u.name LIKE 'GCC Zone%'
  AND p.created_at >= now() - interval '30 days'
  AND ct.licence_no LIKE 'TN-SAN-2026-00%'
ORDER BY p.created_at DESC;

-- 3. Complaint text search (manhole-code prefix OR a word in the description), newest first.
SELECT c.complaint_id, m.code, c.status, left(c.description, 60) AS description
FROM complaint c JOIN manhole m ON m.manhole_id = c.manhole_id
WHERE m.code ILIKE 'CHN-ADY-00%' OR c.description ILIKE '%overflow%'
ORDER BY c.raised_at DESC;

-- 4. Shadow-entry alerts that still need a person: open or with late evidence, by zone.
SELECT a.alert_id, a.status, a.rule_code, m.code AS manhole, u.name AS zone, a.detected_at
FROM shadow_entry_alert a
JOIN complaint c ON c.complaint_id = a.complaint_id JOIN manhole m ON m.manhole_id = c.manhole_id JOIN ulb u ON u.ulb_id = m.ulb_id
WHERE a.status IN ('OPEN', 'EVIDENCE_RECEIVED') AND u.name LIKE 'GCC Zone 13%'
ORDER BY a.detected_at;

-- 5. Workers whose fitness or training will have lapsed on a given date: who could NOT be crewed then.
SELECT w.namaste_id, w.full_name, w.medical_fit_until, w.trained_until
FROM worker w WHERE w.is_active AND (w.medical_fit_until < DATE '2027-01-01' OR w.trained_until < DATE '2027-01-01')
ORDER BY least(w.medical_fit_until, w.trained_until);

-- 6. Audit trail for one record: every change to a given permit, newest first (ix_audit_row).
SELECT occurred_at, actor_user_id, action, new_data ->> 'status' AS status
FROM audit_log WHERE table_name = 'entry_permit' AND row_pk = (SELECT max(permit_id)::text FROM entry_permit)
ORDER BY log_id DESC;
