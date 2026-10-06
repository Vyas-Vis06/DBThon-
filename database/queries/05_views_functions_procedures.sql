-- 05_views_functions_procedures.sql: how each database object is invoked. Read-only; the state-changing calls are in 06.

-- VIEWS ----------------------------------------------------------------------------------------------------------------
SELECT * FROM v_permit_compliance;          -- live readiness of every DRAFT permit (calls permit_clause_check per permit)
SELECT * FROM v_suspected_shadow_entry;     -- the anti-join detection view
SELECT * FROM v_compensation_overdue;       -- unpaid cases past their deadline
SELECT * FROM v_invoice_status;             -- invoices with their hold state and reasons
SELECT * FROM v_contractor_risk;            -- risk score per contractor
SELECT * FROM v_ulb_year_kpi;               -- zero-entry rate per zone per year
SELECT * FROM v_ulb_year_incidents;         -- incidents, deaths, compensation per zone per year

-- FUNCTIONS ------------------------------------------------------------------------------------------------------------
-- permit_clause_check(permit, as_of): side-effect-free checklist (one row per legal clause).
SELECT clause_code, passed, detail FROM permit_clause_check((SELECT max(permit_id) FROM entry_permit));

-- rule_num(key): the only way functions read a statutory number; a missing key is an error, never a default.
SELECT rule_num('min_crew_size') AS min_crew, rule_num('gas_max_age_min') AS gas_max_age_minutes, rule_num('max_continuous_minutes') AS max_entry_minutes;

-- Time helpers: statutory time rules use India Standard Time (fixed +05:30), never the session time zone.
SELECT now() AS instant, local_ts(now()) AS india_wall_clock, local_date(now()) AS india_date;

-- authorise_entry(permit, actor, as_of): ATTEMPTS to authorise and returns the full checklist. Run it for a DRAFT permit:
--   SELECT * FROM authorise_entry(<permit id>, <supervisor user id>);
-- (state-changing, so it is exercised in 06_transactions.sql inside a transaction that is rolled back)

-- scan_shadow_entries(as_of): idempotent absence scan; returns how many alerts it opened / sent to review / left pending.
--   SELECT * FROM scan_shadow_entries(now());

-- PROCEDURE ------------------------------------------------------------------------------------------------------------
-- record_incident(type, when, worker, manhole, description, recorded_by, permit, job, INOUT incident_id):
--   CALL record_incident('FATALITY', now(), <worker>, <manhole>, 'what happened', <user>, <permit or NULL>, <job or NULL>, NULL::bigint);

-- CATALOGUE: every routine and trigger the database defines, straight from the system catalogue.
SELECT p.proname AS routine, CASE p.prokind WHEN 'p' THEN 'procedure' ELSE 'function' END AS kind,
       CASE WHEN p.prosecdef THEN 'definer' ELSE 'invoker' END AS runs_as
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public' AND p.prokind IN ('f', 'p') AND p.prorettype <> 'trigger'::regtype
ORDER BY kind, routine;

SELECT c.relname AS "table", t.tgname AS trigger, pg_get_triggerdef(t.oid) AS definition
FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
WHERE NOT t.tgisinternal AND c.relnamespace = 'public'::regnamespace
ORDER BY c.relname, t.tgname;
