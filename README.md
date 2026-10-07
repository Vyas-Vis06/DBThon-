# ZeroEntry

[![tests](https://github.com/Vyas-Vis06/DBThon-/actions/workflows/ci.yml/badge.svg)](https://github.com/Vyas-Vis06/DBThon-/actions/workflows/ci.yml)

**A default-deny database for sewer-entry safety, with shadow-entry detection by absence.** DBThon 2026 · VIT SCOPE · BCSE302P.

India's law defines the offence as *missing safeguards*. ZeroEntry turns that into database integrity:

* **Zero-entry (preventive).** A permit to enter a sewer becomes `AUTHORISED` only when relational division proves every
  statutory safeguard has a matching record: gear for every entrant, fresh in-limit gas readings at all three depths from a
  calibrated detector, a full crew with distinct roles, a written reason why no machine can do the job. Any unmet clause refuses
  the entry **for every client, including a raw SQL `UPDATE` and concurrent sessions**, and names the clause that failed.
* **Shadow-entry (detective).** An entry nobody recorded cannot be seen, so anti-joins look for the records a lawful clearance
  would have left. Alerts are persisted, idempotent, reviewable, never closed by late paperwork, and hold the contractor's invoices.
* **Consequences are one transaction.** A fatality opens a ₹30-lakh compensation case with a deadline, blacklists the contractor,
  stops the job's permits and holds its invoices, all or nothing.

**Measured against conventional approaches** ([EVALUATION.md](docs/EVALUATION.md), reproducible with `python scripts/evaluate.py`):
shadow-entry detection with 100 % precision and recall on labelled cases, against 40 % and 50 % for a naive anti-join; 18 of 18
rule-breaking writes refused, against 1 of 18 when the same rules live in application code; an entry decision in about 2 ms whether
the history holds 1,000 or 100,000 complaints. How this answers the DBThon brief: [SUBMISSION.md](docs/SUBMISSION.md).

![The entry gate denying a permit, clause by clause](docs/img/entry-gate-denied.jpg)

## Quick start

You need **Python 3.11 or 3.12** and nothing else: no Docker, no PostgreSQL install (an embedded PostgreSQL 16 comes from pip).
On Python 3.13+ see [SETUP.md](docs/SETUP.md#requirements) first.

```bash
git clone https://github.com/Vyas-Vis06/DBThon-.git zeroentry && cd zeroentry
python -m venv .venv
source .venv/bin/activate              # Windows PowerShell:  .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python scripts/dev.py                  # migrate, load demo data, serve http://127.0.0.1:8000/
```

Sign in as `supervisor@zeroentry.example` with the password `dev.py` prints, open the **DRAFT** permit and press
*Ask the database to authorise entry*: denied, with five reasons. The full three-minute story is in
[docs/development/DEMO_SCRIPT.md](docs/development/DEMO_SCRIPT.md); other logins, flags and troubleshooting in
[docs/SETUP.md](docs/SETUP.md).

```bash
python -m pytest -n auto               # about 500 tests in about 2 minutes; each test gets its own fresh database
```

## What is in the box

| Area | What | Verified by |
|---|---|---|
| Schema | 30 tables, 53 foreign keys, CHECK/UNIQUE/exclusion constraints, indexes, 11 forward-only migrations | `tests/db/test_schema.py`, generated [SCHEMA_REFERENCE](docs/SCHEMA_REFERENCE.md) |
| Entry gate | relational division over gear and gas depths, state machine, freeze, 90-minute / daylight / overlap rules, race-free under concurrency | `tests/db/test_entry_gate.py`, `test_entry_rules.py`, `test_concurrency.py` |
| Detection by absence | SE1 / SE2 anti-joins, grace window, idempotent scan, review with history, invoice holds with provenance | `tests/db/test_detection.py` (the six scenarios) |
| Consequences | `record_incident()` procedure, compensation payments, holds | `tests/db/test_consequences.py` |
| API | FastAPI, 100 operations, sessions, CSRF, lockout, six roles, row-level security | `tests/api/` (every endpoint × every role), `tests/db/test_rls.py` |
| UI | no-build browser UI, strict CSP | walked through by hand; `tests/api/test_web.py` (no headless-browser tests) |
| SQL showcase | joins, aggregates, search, division, anti-join, views, transactions, trigger refusals | `database/queries/`, each file run by `tests/db/test_demo_queries.py` |
| Evaluation | accuracy, enforcement and latency against stated baselines, at up to 100,000 complaints | `python scripts/evaluate.py` ([EVALUATION.md](docs/EVALUATION.md)); counts asserted by `tests/db/test_evaluation.py` |

CI runs the whole suite on Linux and Windows (Python 3.11 and 3.12) and macOS (Python 3.12).

## Repository map

| Path | Contents |
|---|---|
| `database/migrations/sql/` | the schema and every rule (PL/pgSQL), numbered and forward-only |
| `database/seeds/` · `database/queries/` | deterministic demo data · annotated demonstration queries |
| `src/zeroentry/` | the API (`routers/`, `deps.py`, `errors.py`, ...) and the browser UI (`web/`) |
| `tests/` | `unit/`, `db/` (SQL behaviour), `api/` (HTTP and roles) |
| `database/evaluation/` | the baselines and synthetic history used only by `scripts/evaluate.py` |
| `scripts/` | `dev.py` run everything · `db.py` migrate/bootstrap/new/reset · `seed.py` · `run_sql.py` · `gen_docs.py` · `evaluate.py` |
| `docs/` | design, API, setup, testing, decisions, development log |

## Documentation

| Read | For |
|---|---|
| [docs/SUBMISSION.md](docs/SUBMISSION.md) | **for the judges:** the DBThon brief's eight components, five-step novelty, 30-mark rubric, SDG and TRL, each mapped to evidence |
| [docs/EVALUATION.md](docs/EVALUATION.md) · [docs/EVALUATION_RESULTS.md](docs/EVALUATION_RESULTS.md) | how ZeroEntry is measured against conventional approaches · the generated numbers |
| [PROJECT_SPEC.md](PROJECT_SPEC.md) | the problem, roles, business rules (`BR-nn`) and assumptions (`A-nn`) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | components and the life of a request |
| [docs/DATABASE_DESIGN.md](docs/DATABASE_DESIGN.md) · [docs/ER_DIAGRAM.md](docs/ER_DIAGRAM.md) | why the schema looks like this (3NF analysis, gate, detection, locking) · four ER diagrams |
| [docs/API_SPEC.md](docs/API_SPEC.md) | conventions, errors, and every endpoint with the roles allowed to call it |
| [docs/SETUP.md](docs/SETUP.md) · [docs/TESTING.md](docs/TESTING.md) | running it (embedded or a real PostgreSQL) · the test harness and what it proves |
| [SECURITY.md](SECURITY.md) | threat model, controls and the tests behind them, known limits |
| [docs/decisions/](docs/decisions/README.md) | architecture decision records |
| [ROADMAP.md](ROADMAP.md) · [docs/development/DEV_LOG.md](docs/development/DEV_LOG.md) | what is done and next · the latest state |

## Working on it (friends and their coding agents)

* **People:** [CONTRIBUTING.md](CONTRIBUTING.md) (workflow, PR checklist) and [AGENTS.md](AGENTS.md) (the rules).
* **Coding agents** (Claude Code, Codex, Cursor, Copilot): point them at [AGENTS.md](AGENTS.md); Claude Code also reads
  [CLAUDE.md](CLAUDE.md). A good first prompt: *"Read AGENTS.md, PROJECT_SPEC.md, ROADMAP.md and the latest entry of
  docs/development/DEV_LOG.md, then <task>. Run the whole test suite and report the real result."*
* The database is the authority: rules go in a new migration with a pass **and** a fail test, never only in Python.

## Before presenting

* The 2013 Rules' numbering and gear schedule are cited by name and must be verified against the Gazette; the statistics quoted
  in PROJECT_SPEC §2 must be re-checked against their sources. Ten engineering assumptions are flagged in
  [PROJECT_SPEC.md §6](PROJECT_SPEC.md#6-assumptions-explicit-configurable-to-be-confirmed).
* All demo data is synthetic; no real person, contractor or licence is represented.
