# ZE-1.0 routines, gates and transaction protocol

All signatures below use schema `ze`. Context actor is derived by the authenticated API and set transaction-locally; clients never provide an effective role. Public writes run through engine-owned routines. Runtime role gets SELECT on permitted read models and narrowly granted EXECUTE, not direct DML on operational tables. No safety evaluator is duplicated in Python or JavaScript.

## Frozen gates and policy profile

G0 is an added eligibility gate; preserve the friend's G1-G8 identifiers.

| Gate | Exact ZE-1.0 meaning | Example failure codes |
|---|---|---|
| G0 | Active policy exists, activity/scope matches, and profile permits only this educational fixture | POLICY_MISSING, ACTIVITY_PROHIBITED, LEGAL_REVIEW_REQUIRED, EDUCATIONAL_SCOPE_MISMATCH |
| G1 | Every required personal item for every acknowledged entrant; separately every required site item; quantities use distinct usable serial assets | REQUIREMENTS_EMPTY, GEAR_MISSING, GEAR_EXPIRED, GEAR_CONFLICT |
| G2 | TOP/MID/BOTTOM each has a latest coherent four-field sample; no newer incomplete/invalid sample is hidden; fresh and within profile bounds | GAS_DEPTH_MISSING, GAS_INCOMPLETE, GAS_STALE, GAS_UNSAFE, GAS_CLOCK_INVALID |
| G3 | Detector enabled and calibration covers collection and current evaluation; educational source cannot masquerade as certified hardware | CALIBRATION_EXPIRED, DETECTOR_DISABLED, SOURCE_NOT_ACCEPTED |
| G4 | At least3 distinct acknowledged workers: entrant(s), exactly1 supervisor, at least1 distinct standby; no withdrawn participant; job supervisor matches | CREW_EMPTY, CREW_INCOMPLETE, ACK_REQUIRED, STANDBY_CONFLICT |
| G5 | Appropriate documented mechanical outcome and unexpired RSA-approved educational exception | MECHANISATION_RECORD_MISSING, WAIVER_MISSING, WAIVER_ACTOR_INVALID |
| G6 | Finite planned stretch <=90min; actual-entry rest >=30min across all permits; profile operating-hours condition | WINDOW_INVALID, DURATION_LIMIT, REST_REQUIRED, OUTSIDE_PROFILE_HOURS |
| G7 | Contractor eligibility/licence, worker fitness/training/insurance and selected site-readiness evidence | CONTRACTOR_INELIGIBLE, TRAINING_EXPIRED, FITNESS_EXPIRED, READINESS_MISSING |
| G8 | No unresolved adverse observation/refusal/stop; recheck at action start and on new evidence, plus expiry watchdog | STOP_LATCHED, RECEIPT_STALE, RECEIPT_EXPIRED, PERMIT_NOT_USABLE |

Real Chennai routine manual-cleaning policy: G0 DENY even with perfect evidence. EDU_LAB policy: isolated is_educational scope, operational mode EDUCATIONAL_ONLY. No deployed ALLOW policy is shipped. Education is a test environment, not an exception to law.

### Seed profile values and provenance

Reference values supported by2013 Rules: O2 19.5..21 inclusive,3 depths,3 onsite people,90min stretch,30min rest, gear checks every6 calendar months and training every2 years. Exact locators are in REVIEW_AND_EVIDENCE. Current applicability still needs jurisdiction review.

EDU numerical demonstration assumptions: freshness900s, max future skew120s, H2S<10ppm, LEL<10%, CO<25ppm, current detector calibration, inspection/fitness ranges supplied in seed. The toxic-gas bounds and freshness are labelled OPERATIONAL_DEMO; CO is not claimed as an Indian statutory threshold. A profile missing any configured required gas cannot pass.

EDU live operating window is00:00-24:00 so overnight implementation can be demonstrated; label this explicitly as an educational deviation. Demonstrate the source daylight rule separately with a controlled private time-evaluator test, never claim the full-day profile implements daylight. Production routines have no client-settable clock. A fixed06:00-18:00 example is only a controlled simplification, not astronomical daylight.

EDU personal gear: GEAR_R4_02 breathing apparatus,19 full-body suit,21 gloves,23 helmet,37 harness,39 gumboots. EDU site catalogue:15 first-aid box,17 gas monitor,43 tripod. These are an explicit demonstration subset, not exhaustive legal applicability. Required readiness codes: STRUCTURE, ISOLATION, VENTILATION, RESCUE, COMMUNICATION, TRAFFIC, MEDICAL. Details identify the attesting actor/reference and expiry; they do not certify physical conditions.

## Shared command protocol

### Required execution roles

ZE-1.0 design: `ze_owner` NOLOGIN owns tables; `ze_engine` NOLOGIN owns public mutating functions/procedures declared **SECURITY DEFINER**, with only needed table privileges. Neither role is granted to the runtime login; runtime cannot SET ROLE to either. Mutators are VOLATILE functions where applicable. Set a fixed safe search_path (`pg_catalog, ze, pg_temp`), schema-qualify referenced objects, revoke PUBLIC EXECUTE when creating routines, and grant only specific signatures to runtime/service roles. Install privilege changes atomically. Runtime gets no CREATE on trusted schemas. These choices follow PostgreSQL's [function security guidance](https://www.postgresql.org/docs/16/sql-createfunction.html); the defaults alone do not implement this design.

Read design: a separate `ze_reader` NOLOGIN, not table owner and without BYPASSRLS, owns read-only security-barrier views; runtime receives SELECT on those views only. Underlying RLS policies apply to that reader role and trusted transaction-local actor context, with fail-closed missing context. The reader has only needed underlying SELECT; views omit credentials/private fields. RLS must scope rows AND count queries, including contractor ownership, assigned supervisor and own worker relationships. Do not accidentally use owner views that bypass the intended policies. PostgreSQL documents view privilege/RLS behaviour in [CREATE VIEW](https://www.postgresql.org/docs/16/sql-createview.html).

Engine commands independently validate the stored actor/scope before mutation; engine RLS policies must permit the documented command's necessary linked updates without granting runtime DML. Helpers that read identity to evaluate policies must avoid recursive RLS and expose no passwords. The narrow authentication lookup is a separately reviewed backend-only interface, never a general public account view. The expiry service has only its dedicated command privilege and service identity. SECURITY DEFINER changes current_user; authorization therefore checks the validated application actor, not current_user as a human identity. Test the actual runtime/view/engine roles, not only an owner session. Shared service-credential compromise and owner/superuser tampering remain disclosed trust limits.

1. Authenticate before beginning business work; derive scope from resource and stored identity.
2. Start a short READ COMMITTED transaction; SET LOCAL context through parameterised `set_config`.
3. Call a public routine. It locks the appropriate existing ulb row FIRST. A multi-scope administrative action is not supported in this release.
4. Recheck actor permission and scope; load current facts after the lock. If a routine needs resource locks, acquire IDs in sorted order.
5. Consult request_dedup under the lock. Same actor/operation/key and identical canonical body returns the stored response without new effects; same key/different body returns409 IDEMPOTENCY_MISMATCH.
6. Capture one `clock_timestamp()` after locks. Internal diagnostic helpers receive that same time for consistent boundaries.
7. Apply changes, update affected revisions, assert structural invariants, refresh affected-job projection, persist audit/outbox and dedup response.
8. Commit before returning a successful HTTP response or publishing UI state. Expected business denials are return values that can be committed with their diagnostic record. Structural/database exceptions roll back the transaction; log request failure outside the failed DB transaction if needed.

On40001/40P01 retry the WHOLE transaction at most3 times with short jitter. A23P01 occupied-resource conflict is normally a409, not a retry loop. Deadlock logging must retain test context. All direct operational writers are denied by grants; maintenance scripts use the same protocol or run offline with no concurrent app sessions.

## Public routine contract

Every mutating function has final `p_key uuid` and returns jsonb unless stated otherwise. JSON input is validated by a strict fixed schema, not dynamically executed SQL. Actor and municipality are inferred and rechecked. B owns transaction commit/rollback; routines never issue COMMIT.

| Signature | State/evidence effect |
|---|---|
| `evaluate_permit(p_permit uuid)` | Read-only advisory diagnostic, `preview=true`; no receipt and no promise of future authorization |
| `authorise_entry(p_permit uuid,p_key uuid)` | Lock/re-evaluate; persist immutable AUTHORISED/DENIED certificate and evidence links; reserve available crew/assets on pass; set permit state; return receipt |
| `begin_entry(p_permit uuid,p_worker uuid,p_certificate uuid,p_key uuid)` | Recheck every gate, exact current revision/rule and receipt expiry; hold all crew/site resources through open operation; insert actual entry; state ACTIVE |
| `record_exit(p_entry uuid,p_observed_exit timestamptz,p_key uuid)` | Record true exit and lateness; suspicious/future timestamps are flagged/reviewed, not silently rewritten; only impossible ordering is rejected; release only through controlled close |
| `ingest_reading(p_payload jsonb,p_key uuid)` | Device identity verified by API; locked DB bind/scope/dedup; append observation; update revision; latch adverse/quality conditions, suspend and outbox in same transaction |
| `stop_work(p_permit uuid,p_reason text,p_key uuid)` | Preserve worker_refusal for own worker actor or supervisor stop event; SUSPENDED, latch reason/time; retain open entries/resources |
| `resolve_stop(p_permit uuid,p_reason text,p_key uuid)` | RSA; no open entries; new complete acceptable samples after latch; required evidence rechecked; clear latch and return DRAFT, never auto-AUTHORISED |
| `set_crew(p_permit uuid,p_assignments jsonb,p_key uuid)` | DRAFT/DENIED only; preserve withdrawn assignment history in audit; touch revision; rejects worker from another scope |
| `acknowledge_crew(p_permit uuid,p_key uuid)` | Current user's worker identity acknowledges own assignment; touch revision |
| `issue_gear(p_permit uuid,p_worker uuid,p_asset uuid,p_key uuid)` | p_worker nullable for site; validate scope, asset and crew; unique active custody; touch revision |
| `record_readiness(p_permit uuid,p_evidence jsonb,p_key uuid)` | Append typed attestation; latest adverse input may suspend; touch revision |
| `record_waiver(p_job uuid,p_evidence jsonb,p_key uuid)` | RSA only; append versioned exception; G0 remains controlling |
| `record_deployment(p_job uuid,p_machine uuid,p_evidence jsonb,p_key uuid)` | Validate machine scope and outcome proof; update job workflow, reconcile job |
| `complete_job(p_job uuid,p_completion jsonb,p_key uuid)` | Mechanical success or fully exited educational permit and required evidence; guard valid closure; close permit/release resources when appropriate; reconcile |
| `import_completion_claim(p_claim jsonb,p_key uuid)` | Preserve source IDs and raw claim; conservative match; no automatic job COMPLETED transition; reconcile matched job |
| `reconcile_completion(p_job uuid,p_key uuid)` | Recompute affected-job projection and invoice hold; idempotent result |
| `review_reconciliation(p_job uuid,p_disposition text,p_reason text,p_key uuid)` | RSA recorded review; release only if current evidence consistent or explicit justified administrative exception; never modifies historical evidence |
| `write_reference(p_entity text,p_id uuid,p_changes jsonb,p_key uuid)` | Static whitelist of draft/reference CRUD; all affected permit revisions handled; immutable evidence/policies excluded; request-scoped authorisation mandatory |
| `expire_permissions(p_ulb uuid,p_limit int default100)` | Worker process engine role; lock scope; suspend expired decisions, emit events; keep open entry/resource state; no user-callable timer override |
| `open_case_report(p_ulb uuid,p_cursor refcursor)` returns refcursor | Read-only bounded ordered pending-case report; validate auditor/RSA scope, SQL cursor consumed within same transaction |
| `CALL record_incident(p_payload jsonb,p_key uuid,INOUT p_result jsonb)` | One incident, many victims/cases, relevant internal holds, permit abort and audit/outbox/dedup in caller transaction |

`write_reference` permits explicit static branches for user/master setup, complaint/job/invoice drafts and archive/delete of unreferenced drafts. B uses ORM queries plus SQL function invocation; no `Base.metadata.create_all` or direct ORM safety writes. For existing credential/asset changes it invalidates all affected current permits under the same ulb lock.

## Receipts and evidence selection

`evidence_revision` changes on every relevant crew/acknowledgment/gear/readiness/sample/credential/policy change. Authorization records the revision after selecting immutable facts and obtaining reservations. Begin-entry's occupancy transition is not new evidence and does not invalidate the same certificate for the remaining approved crew. It still rechecks present resource ownership and gate conditions. New evidence always forces a new receipt before another entry.

Select the most recent row for each required depth by `(collected_at DESC,device_sequence DESC,id DESC)` from bound detector events. Do not filter to safe/complete rows before selection. Duplicate exact events return the original acknowledgment. Newer incomplete/future/clock-invalid evidence blocks a new authorization. Late unsafe data latches a review/suspension regardless of whether it becomes the latest chronological sample; late safe data cannot clear a latch. A changed accepted boot ID is an administrative/device-reset event and invalidates outstanding receipts.

An old receipt remains historical evidence. Its current usability requires matching active rule, revision, permitted state, no latch and `evaluation_time < expires_at`. Receipt expiry is the minimum of sample freshness expiry, credential/inspection/waiver/readiness expiry and planned permit deadline. Empty required sets/zero entrants deny independently of division semantics.

Use `snapshot_text` as the canonical persisted UTF8 serialization and SHA256 those bytes. Verification recomputes the digest and can compare with an export captured earlier. A digest stored beside mutable data cannot defeat a malicious privileged rewrite. Snapshots supplement FK-backed certificate_evidence; they do not replace source relations.

## Trigger catalogue and commit-time checking

| Object | Timing and responsibility |
|---|---|
| `trg_reading_effects` | AFTER INSERT: under already-held scope lock, revise permit; adverse/invalid data sets SUSPENDED and stop latch; persist event |
| `trg_readiness_effects` | AFTER INSERT: revise and suspend where needed; never reject an honest failing observation |
| `trg_transition_guard` | BEFORE UPDATE permit/job state: validate allowed transition and engine-only mutation path |
| `trg_evidence_immutable` | Reject unauthorized UPDATE/DELETE of readings, certificates, refusals and evidence links |
| `trg_reconcile_job` | AFTER changed claim/completion or invoice input fields (job_id,amount): recompute affected job; exclude derived invoice status/hold fields and the projection itself to prevent recursion |
| `ct_permit_final_state` | DEFERRABLE INITIALLY DEFERRED AFTER ROW guard: AUTHORISED/ACTIVE structure requires crew/receipt; ABORTED/SUSPENDED may retain truthful adverse events/open entry |
| `ct_incident_victims` | Deferred check incident contains at least one victim after assembly |
| `trg_audit` | Append redacted mutation summary with actor/request context; excludes recursive audit/outbox triggering |

In PostgreSQL constraint triggers are row-level AFTER triggers; transition tables cannot be combined with a constraint trigger. Keep final-state checks compact and indexed, optionally deduplicate affected IDs in the application routine. Never assert clock freshness for every ACTIVE row at commit: time passes without writes. Entry checks and watchdog address time, while state history records what happened.

## Incremental reconciliation

Historical completion is evaluated against evidence valid at the relevant entry/completion event, not whether that gas reading remains fresh today. Current ageing alone must never turn a legitimate past completion into a gap. Later retraction, discovered mismatch or explicit contradictory evidence can reopen review; preserve the previous decision history. This is acceptance test T26.

`v_completion_gaps_reference` is the truth query. At the JOB level, compare linked COMPLETED claims with current validated completion, mode-specific evidence, actual participation and open entry status. Successful machinery and CANCELLED jobs have explicit treatment; an unrelated failed job under the same complaint must not contaminate another job's result. Unmatched claims appear in a separate read view, not a fabricated job.

`refresh_job_ledger(job_id)` recomputes that one job from indexed relations and upserts shadow_ledger; it does not increment/decrement guessed counters. Trigger it on every contributing insert/correction/retraction/link/review. Cost depends on related evidence for changed jobs and indexes, not a universal O(1) claim. Bulk imports collect distinct affected job IDs and refresh each once while holding scope lock.

Use the reference query to rebuild or verify the entire projection in a disposable benchmark. Automatic discrepancy holds are policy. Releasing a hold requires review with reason; `EXCEPTION_RECORDED` is visible and does not make evidence complete. Never call a flagged row proven fraud or illegal entry.

## Durable events and time

Each ulb lock protects a per-ulb `event_seq`; allocation and outbox insertion occur in the same transaction. Stream one ulb at a time. This avoids treating a global identity/sequence allocated before commit as a universally safe replay cursor. SSE ID is `ulb_uuid:event_seq`.

NOTIFY sends only a scope/event wake-up after commit. Dedicated listener establishes LISTEN and commits it before reading the current durable event position; then catches up. On reconnect, read durable events after Last-Event-ID, scope-check each fetch, and refresh the current dossier. If retention removed the requested history, send RESET_REQUIRED and a full snapshot. Do not broadcast private rows to every connected user. Heartbeat and a low-frequency refetch recover dropped UI notifications.

Watchdog every5s handles receipt expiry and excessive active duration; API detail also reports derived expired status immediately from current time. Therefore new entry is denied at the decision boundary even if the watchdog is down, but stop-work display latency depends on watchdog/connectivity. This is not a real-time physical interlock.

## Procedure, cursor and relational derivations

Incident command order: scope lock -> dedup -> incident -> victims -> pending cases -> internal contractor hold if identified -> applicable permit ABORTED -> relevant invoices HELD -> audit/outbox -> dedup -> caller COMMIT. Failure at any step leaves none of those effects. No-permit/no-contractor incidents retain review states; no dummy IDs. The injected-failure path belongs in a test-only wrapper/database, never a public production request field.

Cursor demonstration, after seed IDs are loaded into psql variables:

```sql
BEGIN;
SELECT ze.open_case_report(:'ulb_id'::uuid, 'case_dossier');
FETCH FORWARD 5 FROM case_dossier;
FETCH FORWARD 5 FROM case_dossier;
CLOSE case_dossier;
COMMIT;
```

Cursor traversal supports paged audit consumption; set-based SQL calculates totals. For G1 let E be entrants, R applicable required gear and I valid issues. Missing pairs are `(E x R) - project(worker,item)(I)`; authorize only when E and R are nonempty and Missing is empty. Correlated NOT EXISTS implements the universal condition; also return Missing as explanatory rows. Tuple-calculus form: for each e in E and r in R, there exists i in I with matching worker, permit and item. Personal and site scopes are separate divisors. Use EXCEPT/count variants only as equality/performance comparisons with duplicates handled.

For reconciliation let C be linked completed claims and V validated completions. Candidate gaps are `C anti-join V`, refined by correct job/mode and explicit cancellation/review rules. This describes missing evidence, not the physical cause of the gap.
