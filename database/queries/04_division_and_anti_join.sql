-- 04_division_and_anti_join.sql: THE two operations ZeroEntry is built on. Read-only.
--
--   RELATIONAL DIVISION  "for EVERY required safeguard there EXISTS a matching record"  = NOT EXISTS ... NOT EXISTS
--   ANTI-JOIN            "an event with NO matching record"                               = NOT EXISTS
--
-- The first four are the proposal's signature queries in their plain form (so a reader can see the idea);
-- the production versions that add timeliness, grace windows and explanations are permit_clause_check() and
-- v_suspected_shadow_entry, shown at the end.

-- (a) DIVISION over gear. Which entrants are missing AT LEAST ONE statutory item?
--     Read it as: an entrant for whom there EXISTS a statutory item for which there does NOT EXIST an issue record.
SELECT pc.permit_id, w.namaste_id AS entrant_missing_gear
FROM permit_crew pc
JOIN worker w ON w.worker_id = pc.worker_id
WHERE pc.crew_role = 'ENTRANT'
  AND EXISTS (SELECT 1 FROM gear_item g
              WHERE g.statutory
                AND NOT EXISTS (SELECT 1 FROM gear_issue gi
                                WHERE gi.permit_id = pc.permit_id AND gi.worker_id = pc.worker_id AND gi.gear_code = g.gear_code))
ORDER BY pc.permit_id, w.namaste_id;

-- (b) DIVISION over the three depth levels. For each DRAFT permit, which levels have NO fresh, in-limit reading
--     from a detector that was calibrated on the day? (limits are literals here; the real function reads rule_parameter)
SELECT p.permit_id, lv.level AS level_without_valid_reading
FROM entry_permit p
CROSS JOIN (VALUES ('TOP'), ('MID'), ('BOTTOM')) AS lv(level)
WHERE p.status = 'DRAFT'
  AND NOT EXISTS (SELECT 1 FROM gas_reading r JOIN gas_detector d ON d.detector_id = r.detector_id
                  WHERE r.permit_id = p.permit_id AND r.depth_level = lv.level
                    AND r.taken_at > now() - interval '15 minutes'
                    AND d.calibration_valid_until >= local_date(r.taken_at)
                    AND r.o2_pct BETWEEN 19.5 AND 21.0 AND r.h2s_ppm < 10 AND r.lel_pct < 10)
ORDER BY p.permit_id, lv.level;

-- (c) ANTI-JOIN. Resolved "cleared" complaints with NO machine clearance and NO closed permit on any of their jobs.
--     (Anchored on complaint, not job, so a complaint with no job at all is still found.)
SELECT c.complaint_id, c.resolved_at, m.code AS manhole
FROM complaint c
JOIN manhole m          ON m.manhole_id = c.manhole_id
JOIN resolution_type rt ON rt.code = c.resolution_code AND rt.requires_evidence
WHERE c.status = 'RESOLVED'
  AND NOT EXISTS (SELECT 1 FROM job j JOIN machine_deployment d ON d.job_id = j.job_id
                  WHERE j.complaint_id = c.complaint_id AND d.outcome = 'CLEARED')
  AND NOT EXISTS (SELECT 1 FROM job j JOIN entry_permit p ON p.job_id = j.job_id
                  WHERE j.complaint_id = c.complaint_id AND p.status = 'CLOSED')
ORDER BY c.complaint_id;

--     NOTE: (c) and (d) are the PLAIN idea and ignore timing. They list a complaint resolved 3 hours ago (still inside its grace
--     window: records may yet arrive) and miss one whose only machine log was recorded days late. The production view below fixes both:
--     evidence counts only if RECORDED within the grace window, and late evidence is sent to a person.

-- (d) The SAME question as set algebra: expected population MINUS evidenced population = the absences.
SELECT c.complaint_id
FROM complaint c JOIN resolution_type rt ON rt.code = c.resolution_code AND rt.requires_evidence
WHERE c.status = 'RESOLVED'
EXCEPT
SELECT j.complaint_id FROM job j JOIN machine_deployment d ON d.job_id = j.job_id WHERE d.outcome = 'CLEARED'
EXCEPT
SELECT j.complaint_id FROM job j JOIN entry_permit p ON p.job_id = j.job_id WHERE p.status = 'CLOSED'
ORDER BY 1;

-- (e) ANTI-JOIN at permit level (rule SE2): entrants of closed permits with no entry-log row at all.
SELECT p.permit_id, w.namaste_id AS entrant_never_logged
FROM entry_permit p
JOIN permit_crew pc ON pc.permit_id = p.permit_id AND pc.crew_role = 'ENTRANT'
JOIN worker w       ON w.worker_id = pc.worker_id
WHERE p.status = 'CLOSED'
  AND NOT EXISTS (SELECT 1 FROM entry_log e WHERE e.permit_id = p.permit_id AND e.worker_id = pc.worker_id);

-- PRODUCTION VERSIONS ---------------------------------------------------------------------------------------------
-- The full gate for one permit: 11 clauses, each with PASS/FAIL and the reason, as the permit screen shows them.
SELECT l.sort_order, c.clause_code, c.passed, c.detail
FROM permit_clause_check((SELECT max(permit_id) FROM entry_permit WHERE status = 'DRAFT')) c
JOIN legal_clause l ON l.clause_code = c.clause_code
ORDER BY l.sort_order;

-- Every DRAFT permit and what it is missing right now.
SELECT * FROM v_permit_compliance ORDER BY permit_id;

-- What the detector suspects, including items still inside the grace window (past_grace = false means "pending").
SELECT rule_code, complaint_id, past_grace, late_evidence_exists, alert_status, left(reason, 80) AS why
FROM v_suspected_shadow_entry ORDER BY evidence_deadline;
