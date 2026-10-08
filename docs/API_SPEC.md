# API specification

**Authoritative for:** HTTP conventions (auth, errors, paging) and the list of endpoints with the roles allowed to call them.
The endpoint table at the bottom is **generated** from the code (`python scripts/gen_docs.py`); a test fails when it is stale.
Interactive documentation with request/response schemas: run the app and open `/docs` (disabled when `APP_ENV=production`).

## Conventions

* **Base path** `/api/v1`. JSON in and out. Timestamps are ISO 8601 with offset; the server stores `timestamptz`.
* **The database decides.** The API authenticates, checks the role, and calls SQL. Business rules (entry gate, 90-minute limit,
  state machine, holds) are enforced by PostgreSQL; their refusals come back with the database's own message.
* **One transaction per request**, committed *before* the response is sent. A response of 2xx means the change is durable.
  Runtime authorization and financial writes require PostgreSQL `READ COMMITTED` (the API default). Authorization,
  invoice creation/status, alert/incident creation and hold creation reject other snapshot isolation with SQLSTATE `40001`; direct SQL callers must retry the
  whole transaction using `READ COMMITTED`. A stale repeatable-read snapshot cannot safely recheck newly committed holds.

## Authentication

```http
POST /api/v1/auth/login
{"email": "supervisor@zeroentry.example", "password": "..."}

200 {"user": {...,"role": "SUPERVISOR"}, "csrf_token": "...", "session_token": "...", "expires_at": "..."}
Set-Cookie: ze_session=...; HttpOnly; SameSite=Strict; Path=/
```

| Client | Send | CSRF |
|---|---|---|
| Browser (the bundled UI) | the `ze_session` cookie (automatic) | every `POST/PATCH/PUT/DELETE` must carry `X-CSRF-Token: <csrf_token>` **and** come from the same origin |
| Script / curl / another service | `Authorization: Bearer <session_token>` | not needed (no ambient credential) |

Sessions are opaque random tokens; only their SHA-256 hash is stored. They expire after `SESSION_TTL_MINUTES` (default 60) and
are revoked by `POST /auth/logout` or a password change (other sessions). Five failed logins lock the account for 15 minutes;
more than 20 attempts per minute from one IP get `429`. Every failure says the same thing, so e-mail addresses cannot be enumerated.

```bash
TOKEN=$(curl -s localhost:8000/api/v1/auth/login -H 'content-type: application/json' \
  -d '{"email":"engineer@zeroentry.example","password":"<from .pgdata/dev_secrets.json>"}' | python -c "import sys,json;print(json.load(sys.stdin)['session_token'])")
curl -s localhost:8000/api/v1/detections/alerts -H "Authorization: Bearer $TOKEN"
```

## Authorisation

* The role comes from the session row in the database, never from the request. Every endpoint declares its roles with
  `require(...)`; a test probes **every endpoint as every role** (`tests/api/test_rbac.py`) and another proves that only
  `/health` and `/auth/login` are public.
* **Row scoping:** a `CONTRACTOR` sees only its own jobs, workers, permits, invoices and incidents; a `WORKER` only permits it is
  crewed on. Another party's row answers `404`, not `403`, so ids cannot be probed. PostgreSQL row-level security enforces the
  same scoping a second time (see [SECURITY.md](../SECURITY.md)).
* A `SUPERVISOR` may operate only permits they drafted; an `ENGINEER` may operate any.

## Lists, filters, search

List endpoints take `limit` (1-200, default 50) and `offset` (default 0) and answer
`{"items": [...], "total": 123, "limit": 50, "offset": 0}`. `q` is a case-insensitive **prefix** search on the listed
columns (wildcards in `q` are escaped). Other query parameters are exact-match filters (`status`, `ulb_id`, ...); an invalid value
is a `422`, never a database error.

## Errors

Every error has the same envelope:

```json
{"error": {"code": "legal_clause_failed", "message": "Entry denied: ...", "details": null}}
```

| HTTP | `code` | When |
|---|---|---|
| 401 | `unauthorized` | not signed in, session expired or revoked, wrong password |
| 403 | `forbidden`, `csrf`, `not_permitted` | role not allowed; missing/invalid CSRF token or foreign origin; database refused the actor (`ZE006`) |
| 404 | `not_found` | no such row, or a row outside your scope |
| 409 | `invalid_state`, `duplicate`, `reference_conflict`, `overlap` | state machine / frozen record (`ZE003`); unique key; row still referenced; overlapping entries (exclusion constraint) |
| 422 | `validation_error`, `legal_clause_failed`, `rule_violation`, `check_failed`, `bad_value`, `missing_value` | bad input; a legal clause (`ZE001`) or rule (`ZE002`: calibration, 90 minutes, daylight) refused it; a CHECK constraint |
| 429 | `rate_limited` | login throttle |
| 500 | `internal_error`, `misconfigured` | unexpected; details only in the server log. `misconfigured` = a rule parameter is missing (`ZE005`) |

**Asking for authorisation is not an error.** `POST /permits/{id}/authorise` answers `200` either way:

```json
{"authorised": false, "permit_status": "DRAFT", "failed": ["GEAR_ALL", "GAS_BOTTOM"],
 "clauses": [{"clause_code": "GEAR_ALL", "title": "...", "legal_ref": "...", "passed": false, "detail": "worker 12 lacks HARNESS"}, ...]}
```

## Endpoints

<!-- BEGIN GENERATED ENDPOINTS -->

123 operations. Generated by `python scripts/gen_docs.py`; do not edit by hand.

### accountability

| Method | Path | Who may call it | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/completion-claims` | ADMIN, ENGINEER | Create completion claim |
| `POST` | `/api/v1/completion-claims/{claim_id}/match` | ADMIN, ENGINEER | Review completion claim |
| `GET` | `/api/v1/completion-reconciliation` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR | Completion reconciliation |

### administration

| Method | Path | Who may call it | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/admin/users` | ADMIN | List users |
| `POST` | `/api/v1/admin/users` | ADMIN | Create user |
| `PATCH` | `/api/v1/admin/users/{user_id}` | ADMIN | Update user |
| `GET` | `/api/v1/audit-log` | ADMIN, AUDITOR | Audit log |
| `POST` | `/api/v1/maintenance/sweep` | ADMIN, ENGINEER | Run the current-time safety sweep now; automatic ticks call the same database function. |
| `GET` | `/api/v1/policy-sources` | any signed-in user | Classified citations and applicability limits for configured law/guidance/product policy. |
| `GET` | `/api/v1/rules` | any signed-in user | The numbers the law is encoded as, with their legal references; assumptions are flagged. |
| `PATCH` | `/api/v1/rules/{param_key}` | ADMIN | Set rule |
| `GET` | `/api/v1/rules/{param_key}/history` | any signed-in user | Rule history |

### auth

| Method | Path | Who may call it | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/auth/change-password` | any signed-in user | Change password |
| `POST` | `/api/v1/auth/login` | public | Login |
| `POST` | `/api/v1/auth/logout` | any signed-in user | Logout |
| `GET` | `/api/v1/auth/me` | any signed-in user | Me |

### complaints and jobs

| Method | Path | Who may call it | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/complaints` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR | List complaints |
| `POST` | `/api/v1/complaints` | ADMIN, ENGINEER | Create complaint |
| `GET` | `/api/v1/complaints/{complaint_id}` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR | Complaint detail |
| `PATCH` | `/api/v1/complaints/{complaint_id}` | ADMIN, ENGINEER | Edit complaint |
| `POST` | `/api/v1/complaints/{complaint_id}/resolve` | ADMIN, ENGINEER | Record the resolution. |
| `POST` | `/api/v1/deployments/{deploy_id}/finish` | ADMIN, ENGINEER | Finish deployment |
| `GET` | `/api/v1/jobs` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR, CONTRACTOR | List jobs |
| `POST` | `/api/v1/jobs` | ADMIN, ENGINEER | Create job |
| `GET` | `/api/v1/jobs/{job_id}` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR, CONTRACTOR | Job detail |
| `PATCH` | `/api/v1/jobs/{job_id}` | ADMIN, ENGINEER | Update job |
| `POST` | `/api/v1/jobs/{job_id}/deployments` | ADMIN, ENGINEER | Deploy machine |
| `POST` | `/api/v1/jobs/{job_id}/waiver` | ENGINEER | Only the Responsible Sanitation Authority (ENGINEER) may record why a machine cannot do the job (BR-01). |

### contractor

| Method | Path | Who may call it | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/contractors` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR, CONTRACTOR | List / filter / search (paged) |
| `POST` | `/api/v1/contractors` | ADMIN, ENGINEER | Create |
| `DELETE` | `/api/v1/contractors/{item_id}` | ADMIN | Delete (refused while dependants exist) |
| `GET` | `/api/v1/contractors/{item_id}` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR, CONTRACTOR | One row by id |
| `PATCH` | `/api/v1/contractors/{item_id}` | ADMIN, ENGINEER | Partial update |

### detection by absence

| Method | Path | Who may call it | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/detections/alerts` | ADMIN, ENGINEER, AUDITOR | List alerts |
| `GET` | `/api/v1/detections/alerts/{alert_id}` | ADMIN, ENGINEER, AUDITOR | Alert detail |
| `POST` | `/api/v1/detections/alerts/{alert_id}/review` | ADMIN, ENGINEER | Review alert |
| `GET` | `/api/v1/detections/candidates` | ADMIN, ENGINEER, AUDITOR | Every complaint/permit currently missing its expected evidence, including those still inside the grace window. |
| `GET` | `/api/v1/detections/rules` | ADMIN, ENGINEER, AUDITOR | List rules |
| `PATCH` | `/api/v1/detections/rules/{rule_code}` | ADMIN | Toggle rule |
| `POST` | `/api/v1/detections/scan` | ADMIN, ENGINEER | Idempotent: opens alerts whose evidence window has closed, sends changed ones to review, never closes anything. |

### events

| Method | Path | Who may call it | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/events` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR | Poll events |

### gas detector

| Method | Path | Who may call it | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/detectors` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR | List / filter / search (paged) |
| `POST` | `/api/v1/detectors` | ADMIN | Create |
| `DELETE` | `/api/v1/detectors/{item_id}` | ADMIN | Delete (refused while dependants exist) |
| `GET` | `/api/v1/detectors/{item_id}` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR | One row by id |
| `PATCH` | `/api/v1/detectors/{item_id}` | ADMIN | Partial update |

### gear item

| Method | Path | Who may call it | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/gear-items` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR | List / filter / search (paged) |
| `POST` | `/api/v1/gear-items` | ADMIN | Create |
| `DELETE` | `/api/v1/gear-items/{item_id}` | ADMIN | Delete (refused while dependants exist) |
| `GET` | `/api/v1/gear-items/{item_id}` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR | One row by id |
| `PATCH` | `/api/v1/gear-items/{item_id}` | ADMIN | Partial update |

### incident reports

| Method | Path | Who may call it | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/incident-reports` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR | List incident reports |
| `POST` | `/api/v1/incident-reports` | ADMIN, ENGINEER, SUPERVISOR | Create incident report |
| `GET` | `/api/v1/incident-reports/{report_id}` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR | Get incident report |

### incidents, compensation, invoices

| Method | Path | Who may call it | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/compensation-cases` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR, CONTRACTOR | List cases |
| `POST` | `/api/v1/compensation-cases/{case_id}/payments` | ADMIN, ENGINEER | Pay compensation |
| `GET` | `/api/v1/incidents` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR, CONTRACTOR | List incidents |
| `POST` | `/api/v1/incidents` | ADMIN, ENGINEER, SUPERVISOR | ONE call, ONE transaction: incident + compensation case + contractor sanction + stop-work + invoice holds. |
| `GET` | `/api/v1/incidents/{incident_id}` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR, CONTRACTOR | Get incident |
| `GET` | `/api/v1/invoice-holds` | ADMIN, ENGINEER, AUDITOR | List holds |
| `POST` | `/api/v1/invoice-holds/{hold_id}/release` | ADMIN, ENGINEER | Release hold |
| `GET` | `/api/v1/invoices` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR, CONTRACTOR | List invoices |
| `POST` | `/api/v1/invoices` | ADMIN, ENGINEER, CONTRACTOR | Submit invoice |
| `POST` | `/api/v1/invoices/{invoice_id}/approve` | ADMIN, ENGINEER | Approve invoice |
| `POST` | `/api/v1/invoices/{invoice_id}/pay` | ADMIN, ENGINEER | Pay invoice |
| `POST` | `/api/v1/invoices/{invoice_id}/reject` | ADMIN, ENGINEER | Reject invoice |

### machine

| Method | Path | Who may call it | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/machines` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR | List / filter / search (paged) |
| `POST` | `/api/v1/machines` | ADMIN, ENGINEER | Create |
| `DELETE` | `/api/v1/machines/{item_id}` | ADMIN | Delete (refused while dependants exist) |
| `GET` | `/api/v1/machines/{item_id}` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR | One row by id |
| `PATCH` | `/api/v1/machines/{item_id}` | ADMIN, ENGINEER | Partial update |

### manhole

| Method | Path | Who may call it | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/manholes` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR | List / filter / search (paged) |
| `POST` | `/api/v1/manholes` | ADMIN, ENGINEER | Create |
| `DELETE` | `/api/v1/manholes/{item_id}` | ADMIN | Delete (refused while dependants exist) |
| `GET` | `/api/v1/manholes/{item_id}` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR | One row by id |
| `PATCH` | `/api/v1/manholes/{item_id}` | ADMIN, ENGINEER | Partial update |

### permits

| Method | Path | Who may call it | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/permits` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR, CONTRACTOR, WORKER | List permits |
| `POST` | `/api/v1/permits` | SUPERVISOR | Create permit |
| `GET` | `/api/v1/permits/{permit_id}` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR, CONTRACTOR, WORKER | Everything about one permit in one answer: permit ⋈ job ⋈ complaint ⋈ manhole ⋈ crew ⋈ worker ⋈ gear ⋈ readings ⋈ detector. |
| `POST` | `/api/v1/permits/{permit_id}/abort` | SUPERVISOR, ENGINEER | Abort permit |
| `POST` | `/api/v1/permits/{permit_id}/acknowledge` | WORKER | A worker acknowledges only their own stored crew assignment. |
| `POST` | `/api/v1/permits/{permit_id}/authorise` | SUPERVISOR, ENGINEER | Ask the database to authorise entry. |
| `POST` | `/api/v1/permits/{permit_id}/cancel` | SUPERVISOR, ENGINEER | Cancel permit |
| `GET` | `/api/v1/permits/{permit_id}/clauses` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR, CONTRACTOR, WORKER | The red/green checklist as of right now (read-only; nothing is authorised by looking). |
| `POST` | `/api/v1/permits/{permit_id}/close` | SUPERVISOR, ENGINEER | Close permit |
| `POST` | `/api/v1/permits/{permit_id}/crew` | SUPERVISOR | Add crew |
| `DELETE` | `/api/v1/permits/{permit_id}/crew/{worker_id}` | SUPERVISOR | Remove crew |
| `GET` | `/api/v1/permits/{permit_id}/decision` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR, CONTRACTOR, WORKER | Original successful gate explanation. |
| `POST` | `/api/v1/permits/{permit_id}/entries` | SUPERVISOR | Log entry |
| `POST` | `/api/v1/permits/{permit_id}/entries/{entry_id}/exit` | SUPERVISOR | Log exit |
| `POST` | `/api/v1/permits/{permit_id}/gear` | SUPERVISOR | Issue gear |
| `DELETE` | `/api/v1/permits/{permit_id}/gear/{issue_id}` | SUPERVISOR | Withdraw gear |
| `POST` | `/api/v1/permits/{permit_id}/readiness` | SUPERVISOR | Record readiness |
| `POST` | `/api/v1/permits/{permit_id}/readings` | SUPERVISOR, ENGINEER | Supervisor's digital sign-off: the reading is bound to a detector serial, the recorder and the server clock. |
| `GET` | `/api/v1/permits/{permit_id}/receipts` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR, CONTRACTOR, WORKER | Permit receipts |
| `GET` | `/api/v1/permits/{permit_id}/safety-events` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR, CONTRACTOR, WORKER | Scoped immutable stop and violation history; records survive a permit ending. |
| `POST` | `/api/v1/permits/{permit_id}/site-gear` | SUPERVISOR | Issue site gear |
| `POST` | `/api/v1/permits/{permit_id}/stop-work` | WORKER, SUPERVISOR, ENGINEER | A crew member's right to refuse. |

### reports

| Method | Path | Who may call it | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/reports/compensation-overdue` | ADMIN, ENGINEER, AUDITOR | Compensation overdue |
| `GET` | `/api/v1/reports/contractor-risk` | ADMIN, ENGINEER, AUDITOR | Contractor risk |
| `GET` | `/api/v1/reports/dashboard` | any signed-in user | Role-shaped counters. |
| `GET` | `/api/v1/reports/permit-readiness` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR | Permit readiness |
| `GET` | `/api/v1/reports/shadow-summary` | ADMIN, ENGINEER, AUDITOR | Alerts by rule and status, with the oldest still unresolved (GROUP BY + COUNT + MIN). |
| `GET` | `/api/v1/reports/summary` | ADMIN, ENGINEER, AUDITOR | Aggregate demonstration: COUNT, SUM, AVG, MIN, MAX over complaints, gas readings and compensation. |
| `GET` | `/api/v1/reports/ulb-kpis` | ADMIN, ENGINEER, AUDITOR | Ulb kpis |

### system

| Method | Path | Who may call it | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/judge/evidence` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR | Evidence inventory is live DB data; generated experiment results are never inferred or copied stale. |
| `GET` | `/api/v1/reference/gear-assets` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR | Serialised site assets and current availability; staff visibility never widens a scoped account. |
| `POST` | `/api/v1/reference/gear-assets` | ADMIN, ENGINEER | Register gear asset |
| `GET` | `/api/v1/ulbs/{ulb_id}/contractor-scopes` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR | List contractor scopes |
| `POST` | `/api/v1/ulbs/{ulb_id}/contractors/{contractor_id}/scope` | ADMIN, ENGINEER | Assign contractor scope |
| `GET` | `/api/v1/ulbs/{ulb_id}/detector-scopes` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR | List detector scopes |
| `POST` | `/api/v1/ulbs/{ulb_id}/detectors/{detector_id}/scope` | ADMIN | Assign detector scope |
| `GET` | `/health` | public | Liveness plus a real database round-trip. |

### ulb

| Method | Path | Who may call it | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/ulbs` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR | List / filter / search (paged) |
| `POST` | `/api/v1/ulbs` | ADMIN | Create |
| `DELETE` | `/api/v1/ulbs/{item_id}` | ADMIN | Delete (refused while dependants exist) |
| `GET` | `/api/v1/ulbs/{item_id}` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR | One row by id |
| `PATCH` | `/api/v1/ulbs/{item_id}` | ADMIN | Partial update |

### worker

| Method | Path | Who may call it | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/workers` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR, CONTRACTOR, WORKER | List / filter / search (paged) |
| `POST` | `/api/v1/workers` | ADMIN, ENGINEER | Create |
| `DELETE` | `/api/v1/workers/{item_id}` | ADMIN | Delete (refused while dependants exist) |
| `GET` | `/api/v1/workers/{item_id}` | ADMIN, ENGINEER, SUPERVISOR, AUDITOR, CONTRACTOR, WORKER | One row by id |
| `PATCH` | `/api/v1/workers/{item_id}` | ADMIN, ENGINEER | Partial update |

<!-- END GENERATED ENDPOINTS -->
