# Testing

**Authoritative for:** how to run the tests, how the harness works, and what each layer proves.

## Run them

```bash
python -m pytest -n auto                      # everything, in parallel (about 2 minutes on a laptop)
python -m pytest tests/db/test_entry_gate.py  # one file
python -m pytest -k "late_evidence"           # by name
python -m pytest -x --lf                      # stop at the first failure; rerun the last failures
```

Needs the dev install (`pip install -e ".[dev]"`) on **Python 3.11 or 3.12** (the embedded PostgreSQL wheel does not exist
for 3.13+; the tests say so and stop). No Docker, no PostgreSQL install, no `.env`: the harness starts its own server.
CI runs the same command on Linux and Windows, Python 3.11 and 3.12 (`.github/workflows/ci.yml`).

## How the harness isolates tests

`tests/conftest.py`:

1. **One embedded PostgreSQL 16 cluster per test session** (per `pytest-xdist` worker), in a temporary directory deleted at
   the end.
2. **One template database** migrated once through the real Alembic path (`database/migrations/`), exactly as a teammate
   would migrate.
3. **A fresh `CREATE DATABASE ... TEMPLATE` clone for every test** (`db` / `conn` fixtures). Nothing is wrapped in an outer
   transaction, so commit, rollback, locks and triggers behave as in production, and no test can see another's rows.
4. Read-only modules may share one clone (`module_db`); the role × endpoint matrix uses this (`tests/api/conftest.py`).

Rows are built by `tests/factories.py` through the real constraints and triggers (nothing is bypassed): if a factory can build a
row, the row is legal. `Factory.gate_scenario(at)` builds a permit that passes every clause, so a test breaks exactly one thing.
`tests/helpers.py` has `expect(...)` (assert a statement fails with a given SQLSTATE and message) and `act_as(...)` (set the
RLS context on a `ze_app` connection).

## What each layer proves

| Layer | Files | Proves |
|---|---|---|
| Unit (no database) | `tests/unit/` | password and token rules, throttle, configuration validation, error mapping, URL building, docs links and rule IDs |
| Database behaviour | `tests/db/` | constraints reject bad rows; **every gate clause has a pass and a fail case**; the gate cannot be bypassed (raw `UPDATE`, raw `INSERT`, concurrent sessions); entry rules (90 minutes, daylight, overlap, window, role); waivers; `record_incident` is atomic (forced failure leaves nothing); detection scenarios; holds; privileges of `ze_app`; row-level security per role; the seed and every demonstration query run; docs match the database |
| API | `tests/api/` | sessions, lockout, throttle, CSRF, cookie flags; **every endpoint probed as every role** (`test_rbac.py`, 176 cases); end-to-end workflows; scoping for contractors and workers; validation errors; UI files served with a strict CSP and no markup built from data; the endpoint table matches the code |

## The six detection scenarios (the brief's checklist)

| Scenario | Test (`tests/db/test_detection.py` unless noted) |
|---|---|
| Normal: evidence present | `test_a_machine_cleared_complaint_with_timely_evidence_is_never_flagged`, `test_a_lawful_manual_clearance_is_evidence_too` |
| Missing evidence | `test_resolved_with_no_evidence_is_pending_inside_the_grace_window_then_an_alert`, `test_a_complaint_resolved_with_no_job_at_all_is_caught`, `test_se2_flags_an_entrant_with_no_entry_log_and_names_them` |
| Late evidence | `test_late_evidence_never_closes_an_alert_it_sends_it_to_a_human`, `test_evidence_that_arrives_after_the_deadline_but_before_any_scan_is_still_late`, `test_se2_late_log_goes_to_review_not_to_silence` |
| Duplicate or conflicting | `test_rescanning_is_idempotent_no_duplicate_alerts_or_holds`, `test_duplicate_evidence_rows_do_not_duplicate_detection_results`, `test_a_machine_that_reported_failure_contradicts_a_cleared_resolution`, `test_two_rules_can_flag_the_same_complaint_once_each` |
| Exempt (intentionally absent) | `test_resolutions_that_need_no_evidence_are_never_flagged`, `test_open_and_in_progress_complaints_are_not_in_the_expected_population`, `test_a_disabled_rule_is_skipped_and_picked_up_when_enabled` |
| Detected, then resolved | `test_confirming_keeps_the_hold_and_counts_against_the_contractor`, `test_dismissing_an_alert_releases_only_its_own_hold_never_a_fatalitys`, `test_a_dismissed_alert_is_final_and_never_reopened_by_the_scan` |

## Tests that guard the documentation

| Test | Fails when |
|---|---|
| `tests/db/test_docs_in_sync.py` | `docs/SCHEMA_REFERENCE.md` differs from the migrated catalogue; an ER diagram misses a table or draws a relationship that is not a foreign key; `DATABASE_DESIGN.md` omits a table |
| `tests/api/test_api_doc_in_sync.py` | the endpoint table in `docs/API_SPEC.md` is stale or disagrees with the OpenAPI schema; an endpoint has no role guard |
| `tests/unit/test_docs.py` | a relative Markdown link is broken; code cites a `BR-nn`/`A-nn` that `PROJECT_SPEC.md` does not define |

Fix the first two with `python scripts/gen_docs.py` (plus a hand edit for the diagrams and design text).

## Proving that a test has teeth

When adding a rule, make the test fail first. Examples that were done while building this repository:

* dropping the gate trigger or the exclusion constraint makes the bypass tests fail;
* `tests/db/test_concurrency.py` failed on all three races before migration `0010` added the permit lock, and passes after.

## What is not tested automatically

* **The browser UI's behaviour.** Every screen was walked through by hand in a browser (list in
  [DEV_LOG.md](development/DEV_LOG.md)); `tests/api/test_web.py` checks that screens are served, the CSP is strict and no screen
  builds markup from data. There is no headless-browser suite.
* **A real (non-embedded) PostgreSQL server.** The schema needs nothing beyond PostgreSQL 15+, but CI runs only the embedded
  server. `scripts/db.py bootstrap` against a real server is documented in [SETUP.md](SETUP.md) and was not run in CI.
