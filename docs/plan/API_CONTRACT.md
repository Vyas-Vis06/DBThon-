# ZE-1.0 API and client contract

Base `/api/v1`. UUIDs are strings; timestamps ISO8601 UTC; INR amounts decimal strings; durations integer seconds. B implements strict Pydantic schemas and exports OpenAPI to `docs/api-contract.yaml`. This document governs names and semantics; C uses one typed API adapter with the same mock/live responses. No frontend calculation grants permission.

Bootstrap exception: GET `/health` outside the base prefix is a local readiness alias for `/api/v1/health/ready`, used by the root startup script. It reports only readiness and non-sensitive version information.

Bearer access token; GET `/auth/me` returns stored user id, role and scope. Every ordinary mutation requires `Idempotency-Key: <uuid>`; browser generates one per user action and reuses it on retry. Server derives actor and hashes validated command fields. Same key/new body is409. User/role fields in request bodies never replace the authenticated actor. Device routes use the signed device protocol below.

## Endpoints and DB boundary

`write_reference` is a fixed whitelist, not an arbitrary table editor. List filters include only documented columns and parameterised values. The request names below are complete top-level models; nested evidence models are defined afterward.

| Method/path | Request | Response / routine / role |
|---|---|---|
| POST /auth/token | JSON login,password |200 access_token,token_type,expires_in; no refresh flow; B authentication |
| GET /auth/me | none |200 id,display_name,role,ulb_id; authenticated |
| GET /health/live | none |200 process status |
| GET /health/ready | none |200 DB/migration version ready, else503 |
| GET /jobs | page,page_size,status,search,contractor_id |200 paginated scope-limited jobs |
| POST /complaints | manhole_id,description,reported_at |201 complaint; reference routine; supervisor/admin |
| POST /jobs | complaint_id,contractor_id?,activity,scheduled_start,scheduled_end,assigned_supervisor_id |201 job; supervisor/admin |
| GET /jobs/{id} | none |200 dossier with permits,deployment,completion,invoice,reconciliation; scoped |
| PATCH /jobs/{id} | description?,scheduled_start?,scheduled_end? |200 draft update only; workflow fields rejected |
| DELETE /jobs/{id} | none |204 only unreferenced draft; otherwise409 USE_CANCEL_OR_ARCHIVE |
| POST /jobs/{id}/deployments | machine_id,outcome,started_at,ended_at?,evidence_reference? |201 record_deployment; supervisor |
| POST /jobs/{id}/waivers | reason,valid_from,valid_until,source_clause_id? |201 record_waiver; RSA |
| POST /jobs/{id}/permits | rule_id,planned_start,planned_end |201 DRAFT; routine verifies active rule/scope; supervisor |
| GET /permits/{id} | none |200 dossier,derived usability,current server time,evidence age and open entries |
| PUT /permits/{id}/crew | assignments[{worker_id,crew_role}] |200 set_crew; supervisor; DRAFT/DENIED only |
| POST /permits/{id}/acknowledgments | empty object |200 acknowledge_crew for current worker; worker |
| POST /permits/{id}/gear-issues | worker_id?,gear_asset_id |201 issue_gear; supervisor |
| POST /permits/{id}/readiness | kind,passed,expires_at,details,supersedes_id? |201 record_readiness; supervisor |
| GET /permits/{id}/evaluation | none |200 preview diagnostic; read-authorised actor |
| POST /permits/{id}/authorisations | empty object |200 committed AUTHORISED or DENIED receipt; authorise_entry; supervisor/RSA |
| POST /permits/{id}/entries | worker_id,certificate_id |201 entry; begin_entry; supervisor; worker is approved entrant |
| POST /entries/{id}/exit | observed_exit_at |200 true exit +duration_violation; record_exit; supervisor |
| POST /permits/{id}/stop-work | reason |200 suspension; stop_work; own worker/supervisor/RSA |
| POST /permits/{id}/resolve-stop | reason |200 DRAFT after successful review, else409; resolve_stop; RSA |
| POST /jobs/{id}/completion | mode,deployment_id?,permit_id?,completed_at,evidence_reference |201 validated completion; complete_job; supervisor |
| POST /completion-claims | source,external_id,external_job_ref,claimed_status,claimed_at,payload |201 claim/match state; import_completion_claim; admin/RSA |
| GET /reconciliation | page,page_size,has_gap,match_status |200 matched gaps plus explicit unmatched claim section; scoped |
| POST /jobs/{id}/reconciliation | empty object |200 recomputed result; reconcile_completion; RSA/admin |
| POST /jobs/{id}/reconciliation-review | disposition,reason |200 review/hold result; review_reconciliation; RSA |
| POST /invoices | job_id,amount |201 draft/hold evaluation; reference routine; own contractor/RSA |
| GET /cases | page,page_size,status,overdue |200 victim-specific case projection; RSA/auditor own scope |
| POST /incidents | IncidentCommand |201 incident and cases/holds; CALL record_incident; supervisor/RSA/admin |
| GET /ulbs/{id}/events | Last-Event-ID header? |authenticated SSE; only permitted scope; no business transaction held open |
| POST /device-events | DeviceEvent |202 committed observation acknowledgment; signed device principal |
| GET /reference/{entity} | page,page_size,search |200 appropriate redacted masters; entity=workers/gear-assets/detectors/machines/contractors/sites |
| POST/PATCH /reference/{entity}[/{id}] | fields from schema-contract whitelist |201/200; ADMIN/RSA; invalidates affected evidence; no rule/policy activation endpoint |

Hard-delete/archive strategy is documented in SCHEMA_CONTRACT. Provide search/filter on jobs and workers, numeric/date filters on cases, and fixed server sort `(created_at DESC,id DESC)` with page>=1, page_size1..100 (default20). List response: `{items:[],page:1,page_size:20,total:0}`; always scope both rows and count.

## Standard diagnostic and error objects

```json
{
  "contract_version": "ZE-1.0",
  "permit_id": "20000000-0000-4000-8000-000000000020",
  "preview": false,
  "outcome": "DENIED",
  "decision": {
    "id": "70000000-0000-4000-8000-000000000020",
    "rule_id": "80000000-0000-4000-8000-000000000020",
    "evidence_revision": 7,
    "evaluated_at": "2026-10-08T04:30:00Z",
    "expires_at": null,
    "educational": true
  },
  "failures": [{
    "gate": "G1", "code": "GEAR_MISSING",
    "subject_type": "worker",
    "subject_id": "30000000-0000-4000-8000-000000000021",
    "requirement_id": "90000000-0000-4000-8000-000000000021",
    "evidence_ids": [],
    "expected": {"gear_code":"GEAR_R4_37","quantity":1},
    "observed": {"quantity":0},
    "source_category":"OPERATIONAL_DEMO",
    "source_locator":"EDU profile; catalogue Rule 4(xxxvii)",
    "message":"The selected educational profile requires an assigned harness."
  }]
}
```

Successful authorisation uses the same shape: outcome AUTHORISED, failures[], real expiry, receipt ID and revision. Preview has decision=null and a diagnostic evaluated_at; it cannot be passed to begin-entry. Outcomes DENIED/AUTHORISED are200 because the decision operation succeeded. A domain conflict may be committed with audit and then returned409. Unexpected DB exceptions roll back, so do not pretend an audit row from the aborted transaction persisted.

```json
{"error":{"code":"RECEIPT_STALE","message":"Evidence changed; request a new decision.","request_id":"aaaaaaaa-0000-4000-8000-000000000001","retryable":false,"failures":[{"gate":"G8","code":"RECEIPT_STALE","expected_revision":7,"observed_revision":8}]}}
```

Map401 authentication,403 actor permission,404 unknown or inaccessible object (avoid leaking existence),409 state/resource/idempotency/revision conflicts,422 malformed input,503 unavailable database/retries exhausted. SQLSTATE23502/23503/23514 generally422;23505 maps409 when business duplicate;23P01 maps409 RESOURCE_CONFLICT;40001/40P01 bounded retry;42501 maps403; other errors500 with a correlation ID, never raw SQL/credentials. Constraint names map to stable application codes; do not parse English PostgreSQL error strings.

### IncidentCommand

Fields: ulb_id,job_id?,permit_id?,contractor_id?,occurred_at,site_label,hazard_type,description,reported_fir_sections?,victims[{victim_key,worker_id?,display_alias,outcome}]. At least one victim; victim_key unique within request. Identity fields are optional so a private/unrecorded incident can be represented. Caller must be allowed for the specified ulb; optional links must belong to it and agree. Response: `{incident_id,case_ids,permit_effect,contractor_effect,invoice_effects,outcome:"RECORDED",payment_status:"NOT_PAID"}`. No `force_failure` field is accepted in the public API.

### Readiness details

Fixed kinds and minimum fields: STRUCTURE {inspection_ref,qualified_person_ref}; ISOLATION {isolation_ref}; VENTILATION {opened_at,method_ref}; RESCUE {plan_ref,retrieval_asset_ref}; COMMUNICATION {method,test_ref}; TRAFFIC {barrier_ref}; MEDICAL {contact_ref,first_aid_ref}. Values are attributed attestations; no confidential health details or genuine emergency numbers needed in synthetic seed. False `passed` observations are stored and can trigger suspension.

## Sensor and simulator protocol

Use the existing board only after its model/power interface is confirmed. No generic wiring promise is made for unspecified MQ modules. A hardware sender can transmit raw ADC values and a button-triggered educational alarm; it cannot manufacture O2/H2S/LEL/CO measurements from an uncalibrated single sensor. Do not introduce gas/vapour into the demo area.

DeviceEvent fields: device_code,permit_id,boot_id,sequence,nonce,collected_at,depth,source_mode,measurements,raw_adc?,educational_alarm?. `measurements` has nullable o2_pct,h2s_ppm,lel_pct,co_ppm. Missing fields are admitted as INCOMPLETE evidence, not filled with safe defaults. Strict payload size16KiB and known depth codes. HARDWARE_RAW cannot pass the gas-completeness gate. Simulator signs complete SYNTHETIC samples with source_mode SIMULATED, accepted only for EDU_LAB.

Headers: X-Device-Id, X-Key-Id, X-Signature. Sign UTF8 bytes of `POST\n/api/v1/device-events\n` followed by the exact raw request body with HMAC-SHA256; hex encoding. Verify the same raw bytes with constant-time comparison, validate device binding and active boot before DB command. Reject invalid signatures401; same nonce/sequence+same hash returns prior result; same identity with changed bytes409. Event freshness and physical validity are separate from authentication. Key material stays in local environment/firmware provisioning, never CSV/repository. A fingerprint/key ID is not a secret.

Ingestion response: `{event_id,reading_id,quality,permit_status,evidence_revision,source_mode,duplicate}` only after commit. Older unsafe accepted/authenticated data raises a latch even when not selected as latest; a forged unauthenticated payload does not create observations. A disabled device cannot gain authority through a signed old message.

Simulator CLI contract, implemented by B: `python -m sensor.simulator --scenario safe|missing-bottom|unsafe|incomplete|stale|duplicate|out-of-order|alarm --permit <uuid>`. Values and collection timestamps derive from fresh reset time, not this document's illustrative dates. Normal safe simulation is O2=20.9,H2S=1,LEL=0,CO=0; unsafe scenario changes one field and labels the input synthetic. Calibration expiry is a seeded detector-state change, not a fake gas unit.

## SSE and visible state

Event types: PERMIT_DECISION, PERMIT_SUSPENDED, ENTRY_STARTED, ENTRY_EXITED, COMPLETION_RECONCILED, INCIDENT_RECORDED, RESET_REQUIRED. Payload `{ulb_id,event_seq,entity_type,entity_id,occurred_at}` tells the UI to refetch the authorised dossier; it does not carry personal data to all listeners. Native EventSource cannot set an arbitrary Authorization header; use authenticated fetch streaming with AbortController, or a reviewed same-origin cookie design. ZE-1.0 chooses fetch streaming with the in-memory bearer token.

On reconnect use Last-Event-ID, backoff1/2/5s, show connection state, and perform durable catch-up before marking live. UI safety color reflects current server usability; show EXPIRED/UNKNOWN/DISCONNECTED explicitly. A local countdown is informational and never authorizes entry.

## Stable scenario namespaces

Full UUID convention: prefix identifies kind; suffix identifies fixture. ulb=`00000000-0000-4000-8000-000000000001` Chennai, ending002 EDU. jobs prefix10000000; permits20000000; workers30000000; users40000000; detectors50000000; gear60000000; mock certificates70000000; rules80000000; parameters90000000. Use suffix010 for mechanical job,020 for educational job,030 for imported-gap job,040 for independent legitimate job under the same complaint,050 for no-permit incident scenario. A publishes `db/seed/fixture_ids.json`; C/B consume it rather than invent names.

Seed roles: admin_demo,rsa_demo,supervisor_demo,worker_demo,contractor_alpha,contractor_beta,auditor_demo. Passwords are generated locally and shared out of Git; API tokens must not appear in screenshots. Each reset regenerates fresh evidence windows; deterministic IDs stay constant. API examples show shape only and are not replay-ready dated fixtures.
