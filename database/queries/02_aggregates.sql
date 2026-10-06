-- 02_aggregates.sql: COUNT, SUM, AVG, MIN, MAX, GROUP BY, HAVING and FILTER. Read-only.

-- 1. How fast are complaints resolved? (COUNT, AVG, MIN, MAX over an interval)
SELECT count(*)                                                                   AS complaints,
       count(*) FILTER (WHERE status = 'RESOLVED')                                AS resolved,
       round(avg(extract(epoch FROM resolved_at - raised_at) / 3600), 1)          AS avg_hours_to_resolve,
       round(min(extract(epoch FROM resolved_at - raised_at) / 3600), 1)          AS fastest_hours,
       round(max(extract(epoch FROM resolved_at - raised_at) / 3600), 1)          AS slowest_hours
FROM complaint;

-- 2. Complaints per zone, only zones with more than one (GROUP BY + HAVING).
SELECT u.name AS zone, count(*) AS complaints, count(*) FILTER (WHERE c.status <> 'RESOLVED') AS still_open
FROM complaint c JOIN manhole m ON m.manhole_id = c.manhole_id JOIN ulb u ON u.ulb_id = m.ulb_id
GROUP BY u.name HAVING count(*) > 1 ORDER BY complaints DESC;

-- 3. Money owed and paid for deaths and disabilities (SUM, AVG, MIN, MAX).
SELECT count(*) AS cases, sum(amount_due) AS total_due, sum(amount_paid) AS total_paid, round(avg(amount_due), 2) AS avg_case,
       min(due_by) AS earliest_deadline, max(due_by) AS latest_deadline
FROM compensation_case;

-- 4. Atmosphere statistics per depth level over all readings ever signed off.
SELECT depth_level, count(*) AS readings, min(o2_pct) AS min_o2, max(o2_pct) AS max_o2, round(avg(o2_pct), 2) AS avg_o2, max(h2s_ppm) AS worst_h2s
FROM gas_reading GROUP BY depth_level ORDER BY CASE depth_level WHEN 'TOP' THEN 1 WHEN 'MID' THEN 2 ELSE 3 END;

-- 5. Invoice book by status, and how much of it is currently frozen by a hold.
SELECT i.status, count(*) AS invoices, sum(i.amount_inr) AS value,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM invoice_hold h WHERE h.invoice_id = i.invoice_id AND h.released_at IS NULL)) AS on_hold
FROM invoice i GROUP BY i.status ORDER BY i.status;

-- 6. Zero-entry rate and deaths per zone per year (the report views, built from the same aggregates).
SELECT * FROM v_ulb_year_kpi ORDER BY year DESC, ulb_name;
SELECT * FROM v_ulb_year_incidents ORDER BY year DESC, ulb_name;

-- 7. Contractor risk ranking: 10 x deaths + 5 x disabilities + 3 x confirmed alerts + open alerts + 2 x overdue cases.
SELECT name, status, fatalities, disabilities, confirmed_alerts, open_alerts, overdue_cases, risk_score
FROM v_contractor_risk ORDER BY risk_score DESC, name;

-- 8. Shadow-entry alerts by rule and status, with the oldest still waiting.
SELECT rule_code, status, count(*) AS alerts, min(detected_at) AS oldest
FROM shadow_entry_alert GROUP BY rule_code, status ORDER BY rule_code, status;
