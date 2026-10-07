-- 0011_detection_parameters_once.sql
-- Performance fix for detection by absence (BR-30, BR-31, BR-32), found by scripts/evaluate.py (docs/EVALUATION.md).
--
-- Before: the one-row CTE `g` (the grace window, read with rule_num()) was referenced once, so PostgreSQL 12+ INLINED it
-- and evaluated rule_num('shadow_grace_hours') (a lookup in rule_parameter) once per joined row inside the anti-join
-- filters. At 100,000 resolved complaints that was about 100,000 extra buffer reads per evaluation of the view.
-- Now: `WITH g AS MATERIALIZED` computes the parameter once per statement. rule_num() is STABLE, so the value was already
-- fixed for the statement: the candidates are identical; only the work changes. Before/after numbers: the "before 0011"
-- columns of docs/EVALUATION_RESULTS.md (scripts/evaluate.py re-creates the old views in a rolled-back transaction).
-- The definitions below are 0007's, unchanged except for the word MATERIALIZED (same columns, so dependants stay valid).

CREATE OR REPLACE VIEW v_shadow_se1 WITH (security_invoker = true) AS
WITH g AS MATERIALIZED (SELECT rule_num('shadow_grace_hours')::int AS hours,
                               make_interval(hours => rule_num('shadow_grace_hours')::int) AS grace)
SELECT c.complaint_id,
       'SE1_NO_CLEARANCE_EVIDENCE'::text            AS rule_code,
       c.manhole_id, m.ulb_id,
       lj.contractor_id, lj.job_id,
       c.resolved_at                                AS anchor_at,
       c.resolved_at + g.grace                      AS evidence_deadline,
       (st.cleared > 0 OR st.logged_permits > 0)    AS late_evidence_exists,
       format('Resolved %s as %s, but no clearance evidence was recorded within %s h. Jobs: %s. Machine deployments: '
              '%s cleared, %s failed, %s unfinished. Closed permits with a logged entry: %s.',
              to_char(local_ts(c.resolved_at), 'YYYY-MM-DD HH24:MI'), c.resolution_code, g.hours,
              st.jobs, st.cleared, st.failed, st.unfinished, st.logged_permits) AS reason
FROM complaint c
CROSS JOIN g
JOIN manhole m          ON m.manhole_id = c.manhole_id
JOIN resolution_type rt ON rt.code = c.resolution_code AND rt.requires_evidence          -- BR-33: exempt types never appear
LEFT JOIN LATERAL (SELECT j.job_id, j.contractor_id FROM job j WHERE j.complaint_id = c.complaint_id
                   ORDER BY j.created_at DESC, j.job_id DESC LIMIT 1) lj ON true
CROSS JOIN LATERAL (
  SELECT (SELECT count(*) FROM job j WHERE j.complaint_id = c.complaint_id) AS jobs,
         (SELECT count(*) FROM job j JOIN machine_deployment d ON d.job_id = j.job_id
           WHERE j.complaint_id = c.complaint_id AND d.outcome = 'CLEARED') AS cleared,
         (SELECT count(*) FROM job j JOIN machine_deployment d ON d.job_id = j.job_id
           WHERE j.complaint_id = c.complaint_id AND d.outcome = 'FAILED')  AS failed,
         (SELECT count(*) FROM job j JOIN machine_deployment d ON d.job_id = j.job_id
           WHERE j.complaint_id = c.complaint_id AND d.outcome IS NULL)     AS unfinished,
         (SELECT count(*) FROM job j JOIN entry_permit p ON p.job_id = j.job_id
           WHERE j.complaint_id = c.complaint_id AND p.status = 'CLOSED' AND p.authorised_at IS NOT NULL
             AND EXISTS (SELECT 1 FROM entry_log e WHERE e.permit_id = p.permit_id)) AS logged_permits) st
WHERE c.status = 'RESOLVED'
  AND NOT EXISTS (                                  -- ANTI-JOIN 1: no TIMELY machine clearance on any job
        SELECT 1 FROM job j JOIN machine_deployment d ON d.job_id = j.job_id
         WHERE j.complaint_id = c.complaint_id AND d.outcome = 'CLEARED'
           AND d.recorded_at <= c.resolved_at + g.grace)
  AND NOT EXISTS (                                  -- ANTI-JOIN 2: no TIMELY authorised, closed permit with a logged entry
        SELECT 1 FROM job j JOIN entry_permit p ON p.job_id = j.job_id
         WHERE j.complaint_id = c.complaint_id AND p.status = 'CLOSED' AND p.authorised_at IS NOT NULL
           AND p.ended_at <= c.resolved_at + g.grace
           AND EXISTS (SELECT 1 FROM entry_log e
                        WHERE e.permit_id = p.permit_id AND e.recorded_at <= c.resolved_at + g.grace));

CREATE OR REPLACE VIEW v_shadow_se2 WITH (security_invoker = true) AS
WITH g AS MATERIALIZED (SELECT rule_num('shadow_grace_hours')::int AS hours,
                               make_interval(hours => rule_num('shadow_grace_hours')::int) AS grace)
SELECT j.complaint_id,
       'SE2_ENTRANT_NOT_LOGGED'::text                                              AS rule_code,
       c.manhole_id, m.ulb_id,
       (array_agg(j.contractor_id ORDER BY p.ended_at DESC, p.permit_id DESC))[1]  AS contractor_id,
       (array_agg(j.job_id        ORDER BY p.ended_at DESC, p.permit_id DESC))[1]  AS job_id,
       max(p.ended_at)                                                             AS anchor_at,
       max(p.ended_at + g.grace)                                                   AS evidence_deadline,
       bool_or(EXISTS (SELECT 1 FROM entry_log e WHERE e.permit_id = p.permit_id AND e.worker_id = pc.worker_id))
                                                                                   AS late_evidence_exists,
       format('Permit(s) %s closed with no entry log recorded within %s h for entrant(s): %s.',
              string_agg(DISTINCT p.permit_id::text, ', '), g.hours, string_agg(DISTINCT w.namaste_id, ', ')) AS reason
FROM entry_permit p
JOIN job j       ON j.job_id = p.job_id
JOIN complaint c ON c.complaint_id = j.complaint_id
JOIN manhole m   ON m.manhole_id = c.manhole_id
JOIN permit_crew pc ON pc.permit_id = p.permit_id AND pc.crew_role = 'ENTRANT'
JOIN worker w    ON w.worker_id = pc.worker_id
CROSS JOIN g
WHERE p.status = 'CLOSED' AND p.authorised_at IS NOT NULL
  AND NOT EXISTS (                                  -- ANTI-JOIN: this entrant has no TIMELY entry log on this permit
        SELECT 1 FROM entry_log e
         WHERE e.permit_id = p.permit_id AND e.worker_id = pc.worker_id AND e.recorded_at <= p.ended_at + g.grace)
GROUP BY j.complaint_id, c.manhole_id, m.ulb_id, g.hours, g.grace;
