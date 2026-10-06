-- 06_transactions.sql: atomic commit / rollback, shown on the real consequence transaction. SAFE: every change below is
-- inside a transaction that ends in ROLLBACK, so the database is exactly as it was afterwards.
-- Run with autocommit on (psql, or: python scripts/run_sql.py database/queries/06_transactions.sql).
-- (PostgreSQL does not allow a subquery as a CALL argument, so ids are fetched into variables first.)

SELECT 'BEFORE' AS moment,
       (SELECT count(*) FROM incident)                                   AS incidents,
       (SELECT count(*) FROM compensation_case)                          AS cases,
       (SELECT count(*) FROM contractor WHERE status = 'BLACKLISTED')    AS blacklisted,
       (SELECT count(*) FROM invoice_hold WHERE released_at IS NULL)     AS active_holds;

BEGIN;
  -- ONE call = ONE atomic unit: incident + compensation case + blacklisting + stop-work + invoice holds.
  DO $$
  DECLARE
    v_worker   bigint := (SELECT w.worker_id FROM worker w JOIN contractor c ON c.contractor_id = w.contractor_id
                           WHERE c.status = 'ACTIVE' ORDER BY w.worker_id LIMIT 1);
    v_manhole  bigint := (SELECT manhole_id FROM manhole ORDER BY manhole_id LIMIT 1);
    v_engineer bigint := (SELECT user_id FROM app_user WHERE email = 'engineer@zeroentry.example');
    v_incident bigint;
  BEGIN
    CALL record_incident('FATALITY', now() - interval '1 hour', v_worker, v_manhole,
                         'Demonstration: recorded inside a transaction that is rolled back.', v_engineer, NULL, NULL, v_incident);
  END $$;

  -- Inside the transaction everything is visible: the case with its deadline, and the contractor now BLACKLISTED.
  SELECT 'INSIDE TRANSACTION' AS moment,
         (SELECT count(*) FROM incident)                                 AS incidents,
         (SELECT count(*) FROM compensation_case)                        AS cases,
         (SELECT count(*) FROM contractor WHERE status = 'BLACKLISTED')  AS blacklisted,
         (SELECT amount_due FROM compensation_case ORDER BY case_id DESC LIMIT 1) AS newest_case_amount,
         (SELECT due_by FROM compensation_case ORDER BY case_id DESC LIMIT 1)     AS newest_case_deadline;
ROLLBACK;                                              -- change of mind or failure: NOTHING above survives

SELECT 'AFTER ROLLBACK' AS moment,
       (SELECT count(*) FROM incident)                                   AS incidents,
       (SELECT count(*) FROM compensation_case)                          AS cases,
       (SELECT count(*) FROM contractor WHERE status = 'BLACKLISTED')    AS blacklisted,
       (SELECT count(*) FROM invoice_hold WHERE released_at IS NULL)     AS active_holds;

-- A FAILURE inside the procedure rolls back everything it did. Here the compensation amount is mis-set to 0 (the CHECK
-- amount_due > 0 fails AFTER the incident row was written); the exception block rolls the failed attempt back.
BEGIN;
  UPDATE rule_parameter SET value = 0 WHERE param_key = 'compensation_fatality_inr';
  DO $$
  DECLARE
    v_worker   bigint := (SELECT worker_id FROM worker ORDER BY worker_id LIMIT 1);
    v_manhole  bigint := (SELECT manhole_id FROM manhole ORDER BY manhole_id LIMIT 1);
    v_engineer bigint := (SELECT user_id FROM app_user WHERE email = 'engineer@zeroentry.example');
    v_incident bigint;
  BEGIN
    CALL record_incident('FATALITY', now() - interval '1 hour', v_worker, v_manhole,
                         'Demonstration of a failing consequence transaction.', v_engineer, NULL, NULL, v_incident);
  EXCEPTION WHEN check_violation THEN
    RAISE NOTICE 'record_incident failed as intended (%): the incident row and every other effect were rolled back', SQLERRM;
  END $$;
  SELECT 'AFTER FAILED CALL' AS moment, (SELECT count(*) FROM incident) AS incidents, (SELECT count(*) FROM compensation_case) AS cases;
ROLLBACK;

-- Locking: authorise_entry() takes SELECT ... FOR UPDATE on the permit row, and every guard on crew, gear, readings and entries
-- first takes FOR SHARE on the same row (lock_permit(), migration 0010). A concurrent change to the evidence therefore waits
-- until the decision commits, then re-reads the permit and is refused if it is no longer a DRAFT, so the proof can never be
-- evaluated against a crew that is changing underneath it. tests/db/test_concurrency.py proves it with two sessions.
