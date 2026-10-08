# Six LAB experiments: executable-reference blueprint

These are schema-aligned examples for A to implement as `db/sql/lab/01...06.sql` and run after migrations/fixtures exist. They are not executed results and do not replace full gate logic. Use psql with `ON_ERROR_STOP`, a selected disposable test database, the appropriate role and trusted actor setup. Base-table read examples are for the evidence/test login; the production API uses its restricted authorized views/functions. The normal runtime role must not gain write rights just to run a LAB demonstration.

Store each actual transcript with command, role, database, git SHA, timestamp and expected/observed result. The six experiments must connect to the same project facts, not six unrelated textbook applications.

## 1. DDL and DML: controlled relational lifecycle

A's real migration is the primary DDL artifact. For a reversible in-session walkthrough of create/alter/insert/update/delete, use a temporary exercise relation with project-shaped fields:

```sql
BEGIN;
CREATE TEMP TABLE lab_job_draft (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  description text NOT NULL,
  status text NOT NULL DEFAULT 'PLANNED'
    CHECK (status IN ('PLANNED','CANCELLED'))
);
ALTER TABLE lab_job_draft ADD COLUMN note text;
INSERT INTO lab_job_draft(description) VALUES ('Synthetic mechanised inspection');
UPDATE lab_job_draft SET note='Verified demonstration row' WHERE status='PLANNED';
SELECT description,status,note FROM lab_job_draft;
DELETE FROM lab_job_draft WHERE description='Synthetic mechanised inspection';
SELECT count(*) AS remaining FROM lab_job_draft; -- expected 0
ROLLBACK;
```

This temporary demonstration is not counted among37 base relations and does not pretend to be the operational write path. Follow it with the real draft-job create/update/delete API flow through `write_reference`, then show a historical/linked job cannot be deleted. This explains why teaching DML does not justify unrestricted application DML.

## 2. Constraints: fail before invalid state commits

Run independent negative cases in rollback-isolated tests so one expected SQL error does not suppress the rest:

| Project case | Required protection | Expected SQLSTATE or domain result |
|---|---|---|
| Duplicate worker_code / external claim key | UNIQUE |23505 |
| Unknown incident victim incident_id | FK |23503 |
| Missing gas detector identity | NOT NULL |23502 |
| Negative invoice amount | CHECK |23514 |
| Invalid/nonfinite planned window | CHECK or engine validator |23514 / WINDOW_INVALID |
| Two HELD overlapping reservations of same resource | Partial GiST exclusion |23P01 / RESOURCE_CONFLICT |
| Empty crew but attempted authorization | State command + deferred structural guard | G4 denial, no usable receipt |

Use actual constraint names from the migration and capture observed codes. Explain that CHECK accepts NULL/UNKNOWN unless NOT NULL or an explicit null test supplies the missing condition; ordinary FK cannot require a parent to have at least one child. The runtime direct-UPDATE denial test is separate from constraint tests under the engine/test role.

Inspect what was really installed:

```sql
SELECT c.relname AS relation,k.conname,k.contype,
       pg_get_constraintdef(k.oid) AS definition
FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='ze'
ORDER BY c.relname,k.conname;
```

## 3. Single-row functions: readable evidence, not permission

```sql
SELECT worker_code,upper(display_name) AS display_label,
       coalesce(insurance_reference,'NOT_RECORDED') AS insurance_reference
FROM ze.worker ORDER BY worker_code;

SELECT id,depth,
       to_char(collected_at AT TIME ZONE 'Asia/Kolkata',
               'YYYY-MM-DD HH24:MI:SS') AS collected_ist,
       round(extract(epoch FROM (clock_timestamp()-collected_at))::numeric,1)
         AS age_seconds,
       coalesce(o2_pct::text,'INCOMPLETE') AS oxygen_display
FROM ze.gas_reading ORDER BY collected_at DESC,id DESC LIMIT 10;
```

Expected: uppercase aliases, explicit missing field text and time/age formatted for the dossier. A missing numeric field is never COALESCE'd to a passing numeric value. Age shown here is a presentation value; the command independently applies the fixed policy after acquiring the lock.

## 4. Operators and group functions: accountability summary

```sql
SELECT status,count(*) AS cases,
       sum(coalesce(reference_amount,0)) AS reference_total_inr,
       sum(paid_amount) AS recorded_paid_total_inr,
       count(*) FILTER (WHERE review_due_at < clock_timestamp()
                        AND status='PENDING_REVIEW') AS overdue_reviews
FROM ze.compensation_case
GROUP BY status HAVING count(*) > 0 ORDER BY status;

SELECT id,depth,collected_at
FROM ze.gas_reading
WHERE depth IN ('TOP','MID','BOTTOM')
  AND (o2_pct IS NULL OR o2_pct NOT BETWEEN 19.5 AND 21)
ORDER BY collected_at DESC;
```

Expected: victim-case counts and reference-vs-paid separation; demo case paid total0. The second query illustrates operators against a selected sourced range, not complete G2 evaluation. Toxic limits, freshness, complete sampling and calibration are separate conditions.

## 5. Subquery, views and joins: the decisive business questions

Set psql variable `permit_id` to the educational fixture. This missing-personal-gear query illustrates relational division and quantity handling; A adds full profile/inspection/reservation checks in the real gate:

```sql
WITH entrants AS (
  SELECT pc.worker_id
  FROM ze.permit_crew pc
  WHERE pc.permit_id=:'permit_id'::uuid AND pc.crew_role='ENTRANT'
    AND pc.acknowledged_at IS NOT NULL AND pc.withdrawn_at IS NULL
), required AS (
  SELECT rp.id,rp.gear_item_id,rp.quantity
  FROM ze.entry_permit p
  JOIN ze.rule_parameter rp ON rp.rule_id=p.rule_id
  WHERE p.id=:'permit_id'::uuid AND rp.kind='GEAR' AND rp.scope='ENTRANT'
)
SELECT e.worker_id,r.gear_item_id,r.quantity
FROM entrants e CROSS JOIN required r
WHERE NOT EXISTS (
  SELECT 1 FROM ze.gear_issue gi
  JOIN ze.gear_asset ga ON ga.id=gi.gear_asset_id
  WHERE gi.permit_id=:'permit_id'::uuid AND gi.worker_id=e.worker_id
    AND gi.returned_at IS NULL AND ga.gear_item_id=r.gear_item_id
    AND ga.status='USABLE' AND ga.inspection_validity @> clock_timestamp()
  HAVING count(DISTINCT ga.id)>=r.quantity
)
ORDER BY e.worker_id,r.gear_item_id;
```

Expected initially: the entrant/harness missing pair; after valid issue: no missing pair. Crucially, no rows is insufficient alone: the engine independently requires nonempty entrant AND requirement sets, complete site equipment and other gates. Show empty-set test T02 so vacuous truth is not mistaken for a valid authorization.

A creates the read-only evidence view through its migration, not by letting the runtime create arbitrary views:

```sql
CREATE VIEW ze.v_lab_completion_gap AS
SELECT cc.id AS claim_id,cc.matched_job_id AS job_id,
       cc.external_id,cc.claimed_at
FROM ze.completion_claim cc
LEFT JOIN ze.job_completion jc
  ON jc.job_id=cc.matched_job_id AND jc.status='VALIDATED'
WHERE cc.claimed_status='COMPLETED'
  AND cc.matched_job_id IS NOT NULL AND jc.id IS NULL;
```

This is an illustrative missing-proof candidate view, not the full scoped reconciliation decision: refine cancellation, mode, unmatched claims and explicit review rules in the reference query. Do not broadly grant this unscoped view to runtime users. Compare its matched candidates to a correlated NOT EXISTS form; use identical results to explain join/subquery equivalence. The principal judge screenshot should use the full scoped reference result and shadow_ledger equality test, not imply this small view detects fraud.

## 6. High-level extensions: function, procedure, cursor, trigger

### Function and receipt

```sql
-- In trusted, correctly scoped test actor context:
SELECT ze.evaluate_permit(:'permit_id'::uuid); -- advisory only
SELECT ze.authorise_entry(:'permit_id'::uuid,gen_random_uuid());
```

Expected first failing fixture: returned DENIED plus persisted receipt when the transaction commits. Correct through commands, then request a new decision: AUTHORISED only for EDU_LAB with all gates valid. A supplies PL/pgSQL body with explicit variables/branching/exception policy, no dynamic legal-language interpreter. Gate computation should stay set-based where appropriate.

### Procedure and atomicity

```sql
BEGIN;
CALL ze.record_incident(:'incident_json'::jsonb,:'request_key'::uuid,NULL::jsonb);
COMMIT;
```

`incident_json` must follow API's IncidentCommand and trusted test actor. The procedure returns its INOUT result; it does not commit internally. The caller owns transaction success. The test-only failure variant rolls back all newly related incident/victim/case/hold/outbox rows; record counts before and after. A successful identical-key retry returns original IDs, not a second incident.

### Cursor lifecycle

```sql
BEGIN;
SELECT ze.open_case_report(:'ulb_id'::uuid,'case_dossier');
FETCH FORWARD 5 FROM case_dossier;
FETCH FORWARD 5 FROM case_dossier;
CLOSE case_dossier;
COMMIT;
```

Expected: bounded rows in stable order without losing the cursor to autocommit. Aggregates remain set-based; explain memory/fetch control without promising a performance win. Browser report endpoints can use bounded returned sets instead of keeping a database cursor open across unrelated HTTP requests.

### Trigger proof

Capture permit revision/state, append an adverse reading using `ingest_reading`, then inspect the committed reading, increased revision, stop latch, outbox and immutable receipt history. The reading trigger must preserve the adverse fact even when it makes the permit unusable. In a separately rolled-back transaction none of those effects persists. Record each trigger's timing and why deferred checks still need locks and cannot detect the passage of time automatically.

## Supplementary theory demonstrations

- `EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON)` on the full reference anti-join and latest-reading query, before/after a justified index on identical data. Explain actual planner choice; no forced-index screenshot.
- Separate write-skew teaching fixture from production ulb-lock protocol; test READ COMMITTED vs SERIALIZABLE and whole-transaction retry.
- Logical dump/restore on a named disposable database verifies recoverability of saved state, not a complete WAL/crash-recovery experiment.
- Functional dependencies, BCNF/4NF/5NF reasoning, EER, relational algebra/calculus and distributed/NoSQL/OLAP topics are classified in SYLLABUS_AND_RUBRIC. Explain rather than pretend to implement unrelated technologies.

Definition of LAB complete: six real scripts, six observed transcripts, relation to the application, one failure case each where meaningful, and a teammate who can explain the SQL. This document alone is not that execution evidence.
