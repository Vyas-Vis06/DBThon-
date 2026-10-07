# Security

**Authoritative for:** the threat model, the controls, and the tests that prove them. A control is listed here only if a test
exercises it; known gaps are listed as gaps.

## Reporting a problem

This is a student project, not a deployed service. If you find a vulnerability, open a GitHub issue that describes the
*class* of problem without a working exploit, or contact the maintainers privately through GitHub. Never put real
credentials, personal data or production URLs in an issue.

## What is being protected, from whom

| Asset | Threat | Main controls |
|---|---|---|
| The entry decision | A client (UI, script, `psql`) marks a permit `AUTHORISED` without the proof | the gate trigger refuses every path, including a raw `UPDATE`/`INSERT` and concurrent sessions ([DATABASE_DESIGN §5, §8](docs/DATABASE_DESIGN.md)) |
| Continuing admission | New unsafe readings, expired credentials, stale checks after waiting for locks | revalidation on evidence changes and each admission, fresh server clocks after locking, periodic safety sweep |
| Evidence (readings, entries, alerts, audit) | Rewriting or deleting the record after the fact | append-only triggers, revoked privileges, audit trigger as owner |
| Contractor and worker data | One tenant reading or changing another's rows | role guards in the API **and** row-level security in PostgreSQL |
| Accounts | Password guessing, session theft, CSRF | bcrypt, lockout, throttle, opaque sessions, HttpOnly SameSite=Strict cookie, CSRF token plus origin check |
| The database | SQL injection, over-privileged runtime | parameterised queries / ORM only; runtime role `ze_app` owns nothing |

## Controls and their tests

| Control | Where | Proved by |
|---|---|---|
| Passwords: bcrypt (cost 12), ≥ 12 characters with mixed case and a digit, ≤ 72 bytes (refused, never truncated) | `security.py` | `tests/unit/test_security.py` |
| Same answer and same cost for "unknown e-mail" and "wrong password" (no enumeration, no timing oracle) | `routers/auth.py` | `test_wrong_password_and_unknown_email_are_refused_identically` |
| Per-account lockout (5 failures → 15 min), per-IP throttle (20/min → 429) | `routers/auth.py`, `security.py` | `test_repeated_failures_lock_the_account_...`, `test_login_is_throttled_per_address` |
| Opaque 256-bit session tokens; only the SHA-256 is stored; server-side logout, expiry, revocation on password change or deactivation | `deps.py`, `user_session` | `tests/api/test_auth.py` |
| Cookie `HttpOnly; SameSite=Strict; Path=/`, `Secure` when `COOKIE_SECURE=true` (required in production) | `routers/auth.py`, `config.py` | `test_login_sets_an_httponly_strict_cookie...`, `test_the_session_cookie_is_marked_secure_when_configured` |
| CSRF: cookie-authenticated writes need the per-session `X-CSRF-Token` **and** a same-origin `Origin`; Bearer clients are exempt | `deps.py` | `test_bearer_tokens_need_no_csrf_but_cookie_writes_do` |
| Identity only from the session row; role or user id sent by the client is ignored | `deps.py` | `test_a_client_cannot_claim_a_role_or_identity` |
| Every endpoint has a role guard; only `/health` and `/auth/login` are public; every role × endpoint is probed | `deps.require` | `tests/api/test_rbac.py`, `tests/api/test_api_doc_in_sync.py` |
| Row-level security: no context = no rows; contractors and workers see only their own rows; auditors read-only | migration `0009` | `tests/db/test_rls.py` |
| The request's identity is transaction-local and cannot leak to the next request on a pooled connection | `deps.py` (`set_config(..., true)`) | `test_the_request_context_never_leaks_...` |
| Least privilege: `ze_app` cannot rewrite or delete evidence (readings, entries, waivers, incidents, alert history, holds), rewrite a rule's legal reference, add roles, clauses or rules, run DDL, or write `audit_log` at all | migrations `0008`, `0009` | `tests/db/test_privileges.py` (31 refused statements), `test_the_application_role_cannot_forge_an_audit_row` |
| Search text and filters are bound parameters, type-checked before reaching SQL | `crud.py`, routers | `test_filters_are_type_checked_and_search_text_is_never_executed_as_sql` |
| Errors never leak internals: unknown database errors become a generic 500 (details only in the log); driver-refused input is a 422 | `errors.py` | `test_unknown_sqlstate_is_not_mapped`, `test_a_value_the_driver_refuses_client_side_is_a_422_not_a_500` |
| Audit log never contains password hashes | `audit_row()` | `test_the_audit_log_is_filterable_and_never_contains_password_hashes` |
| Browser: strict CSP (`default-src 'self'`, no inline script or style, no third-party origin), `X-Frame-Options: DENY`, `nosniff`, `no-store`; the UI builds the DOM from text nodes only | `main.py`, `web/` | `tests/api/test_web.py` |
| Production hardening: refuses to start with `COOKIE_SECURE=false` or a `CHANGE_ME` URL; `/docs` and `/openapi.json` are off | `config.py`, `main.py` | `test_security_headers_are_set_and_docs_are_hidden_in_production`, unit tests |
| Secrets: nothing secret in the repository; `.env` is ignored; dev passwords are generated per machine into `.pgdata/` | `.gitignore`, `scripts/dev.py` | review; `.env.example` holds placeholders only |
| Crew and gear cannot be moved from a frozen permit to a draft; private lock helpers cannot be called directly by runtime users | migration `0012` | `tests/db/test_safety_lifecycle.py` |
| Open entries remain closable after stop; future exit assertions and excessive durations create refusals or immutable violation evidence | migration `0012`, `routers/permits.py` | `tests/db/test_safety_lifecycle.py`, `tests/db/test_integration_adversarial.py`, `tests/api/test_workflow.py` |
| Evidence receipt times are assigned by the server; a late finalization cannot masquerade as timely clearance | migrations `0012`, `0013` | `tests/db/test_temporal_evidence_and_invoice_races.py`, `tests/api/test_temporal_evidence.py` |
| Payment/approval, source holds and new invoices share serialization locks; unsupported stale snapshot isolation is refused | migration `0013` | `tests/db/test_temporal_evidence_and_invoice_races.py`, `tests/db/test_integration_adversarial.py` |
| Runtime policy writes update only the value; revision, actor and receipt time are trigger-owned; reason required | migration `0014`, `routers/admin.py` | `tests/db/test_policy_provenance.py`, `tests/db/test_integration_adversarial.py` |
| Authorization saves immutable evidence, source classifications and policy revisions with a SHA-256 digest; tenant scope applies to decision and safety history | migration `0014`, permit endpoints | `tests/db/test_policy_provenance.py`, `tests/api/test_decision_history_api.py` |
| Runtime authorization requires READ COMMITTED; stale snapshots of draft-worker credentials are refused through both function and raw UPDATE | migration `0014` | `tests/db/test_integration_adversarial.py` |
| A failed detection scan cannot roll back a committed safety stop; automatic work uses bounded waits and transaction advisory locks | `maintenance.py` | `tests/db/test_maintenance.py` |

## Known limitations (not hidden, not fixed)

* **Row-level security is a second line, not the first.** Anyone who can run arbitrary SQL as `ze_app` can set the
  `app.*` settings themselves. It protects against API bugs and tenant mix-ups; parameterised queries and least privilege are
  the controls against injection and stolen database credentials.
* **The per-IP throttle lives in process memory.** Behind several workers each keeps its own window; the per-account lockout in
  the database is the authoritative brake.
* **No TLS in the application.** Run it behind a reverse proxy that terminates HTTPS and set `COOKIE_SECURE=true`.
* **Engineers and supervisors see every ULB.** ULB-scoped visibility is in the ROADMAP backlog.
* **The database enforces state, not physics.** A typed gas value may be false; it is bound to a detector serial, a calibration
  date and a signed-in recorder, and kept append-only (PROJECT_SPEC §7).
* **Append-only is an application trust boundary.** A database owner or superuser can disable triggers or alter the schema.
  Snapshot hashes are local integrity checks, without an external signature or anchor. They do not establish sensor truth.
* **Time-based stops are periodic.** Automatic sweeps default to 30 seconds while the application runs; admission always
  rechecks current conditions. Physical evacuation and external notifications still require people and equipment.
  The SQL maintenance function is available for an external scheduler when automatic ticks are disabled.
* **Historical import is privileged.** Demo seeds and synthetic evaluation fixtures use narrowly scoped owner-only receipt
  backfills. Runtime callers cannot set these receipts; the imported examples are not genuine field evidence.
* **Demo credentials** printed by `scripts/dev.py` are for a local machine only; never expose the development server.
