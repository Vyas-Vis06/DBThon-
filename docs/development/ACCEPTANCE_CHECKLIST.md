# Acceptance checklist

Each requirement of the project brief, the evidence for it, and how it was verified. `[x]` = verified by a command or test that
was run; `[~]` = done with a stated limit. Last full pass: 2026-10-07 (see [DEV_LOG.md](DEV_LOG.md) for the test run).

## Database

| | Requirement | Evidence |
|---|---|---|
| [x] | ≥ 8 related tables | 30 tables ([SCHEMA_REFERENCE.md](../SCHEMA_REFERENCE.md)); `tests/db/test_schema.py::test_thirty_application_tables_exist` |
| [x] | ≥ 4 entities, ≥ 3 relationships, including M:N | 53 foreign keys; entry_permit M:N worker through `permit_crew` ([ER_DIAGRAM.md](../ER_DIAGRAM.md), drift-tested) |
| [x] | Normalised to 3NF, exceptions justified | [DATABASE_DESIGN.md §4](../DATABASE_DESIGN.md#4-normalisation-3nf-and-the-deliberate-exceptions) |
| [x] | Keys and constraints (PK, FK, UNIQUE, CHECK, NOT NULL) | every table has a PK (`test_every_table_has_a_primary_key`); CHECKs reject bad rows (`test_declarative_checks_reject_bad_rows`) |
| [x] | CRUD | reference-table routers (`crud.py`), complaints, jobs, permits, invoices; `tests/api/test_admin_and_validation.py`, `test_workflow.py` |
| [x] | Multi-table JOINs | `database/queries/01_joins.sql`; the permit list joins six tables (`routers/permits.py`) |
| [x] | Aggregates (COUNT, SUM, AVG, MIN, MAX, GROUP BY, HAVING) | `database/queries/02_aggregates.sql`; `/reports/summary`, `/reports/shadow-summary` |
| [x] | Search and filtering | `database/queries/03_search_and_filter.sql`; `q` prefix search and filters on list endpoints |
| [x] | Views | 10 views, all `security_invoker` ([DATABASE_DESIGN.md §7](../DATABASE_DESIGN.md#7-programmable-objects)) |
| [x] | Transactions (commit, rollback, atomic failure) | `database/queries/06_transactions.sql`; `record_incident` rollback test; one transaction per API request |
| [x] | Triggers | gate, freeze, gas, entry, waiver, job, invoice, alert, audit, append-only (`tests/db/test_entry_rules.py`, `test_entry_gate.py`) |
| [x] | Stored procedure and functions | `record_incident` (procedure), `authorise_entry`, `permit_clause_check`, `scan_shadow_entries`, ... |
| [x] | Indexes with a reason | [DATABASE_DESIGN.md §9](../DATABASE_DESIGN.md#9-indexes) |
| [x] | Concurrency safety of the core rule | `tests/db/test_concurrency.py` (three races, fixed by migration `0010`) |

## Detection by absence

| | Requirement | Evidence |
|---|---|---|
| [x] | Normal, missing, late, duplicate/conflicting, exempt, detected-then-resolved | mapped test by test in [TESTING.md](../TESTING.md#the-six-detection-scenarios-the-briefs-checklist) |
| [x] | Idempotent, explainable, reviewable alerts | `test_rescanning_is_idempotent_...`; alert `reason`; history table; review with a written note |

## Application

| | Requirement | Evidence |
|---|---|---|
| [x] | Authentication | sessions, bcrypt, lockout, throttle, CSRF ([SECURITY.md](../../SECURITY.md)); `tests/api/test_auth.py` |
| [x] | ≥ 2 roles with RBAC | 6 roles; every endpoint × every role probed (`tests/api/test_rbac.py`, 176 cases); RLS (`tests/db/test_rls.py`) |
| [~] | Usable UI | every screen built; demo flow walked through in a browser on 2026-10-07 ([DEMO_SCRIPT.md](DEMO_SCRIPT.md)); **no automated browser tests** |
| [x] | Input validation and readable errors | one error envelope ([API_SPEC.md](../API_SPEC.md#errors)); `test_validation_errors_share_one_shape_and_name_the_field` |

## Engineering

| | Requirement | Evidence |
|---|---|---|
| [x] | Runs from a fresh clone | fresh clone + fresh venv + install + full suite, 2026-10-07; CI on Linux and Windows |
| [x] | Tests at several levels | unit, database, API ([TESTING.md](../TESTING.md)) |
| [x] | Migrations and seed data | `database/migrations/` (10, forward-only); `database/seeds/` (deterministic, idempotent; `tests/db/test_seed.py`) |
| [x] | No secrets in the repository | `.env.example` placeholders only; dev secrets generated into git-ignored `.pgdata/` |
| [x] | Documentation set | README, PROJECT_SPEC, ROADMAP, AGENTS, CLAUDE, CONTRIBUTING, SECURITY, docs/ (ARCHITECTURE, DATABASE_DESIGN, ER_DIAGRAM, SCHEMA_REFERENCE, API_SPEC, SETUP, TESTING, decisions, development); links checked by `tests/unit/test_docs.py` |
| [~] | Real PostgreSQL server | `scripts/db.py bootstrap`/`reset` tested against PostgreSQL 16 (embedded); the Docker command in SETUP was not run here |

## Open items (not claimed)

* Legal references (2013 Rules numbering, gear schedule) must be checked against the Gazette before a presentation.
* Automated browser tests; ULB-scoped visibility; rest-interval rule (A-04); simulated sensor feed. See [ROADMAP.md](../../ROADMAP.md).
