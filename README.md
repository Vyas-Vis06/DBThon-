# ZeroEntry

**A default-deny database for sewer-entry safety, with shadow-entry detection by absence.** DBThon 2026 · VIT SCOPE · BCSE302P.

India's law defines the offence as *missing safeguards*. ZeroEntry turns that into database integrity:

* **Zero-entry (preventive).** A permit to enter a sewer becomes `AUTHORISED` only when relational division proves every
  statutory safeguard has a matching record: gear for every entrant, fresh in-limit gas readings at all three depths from a
  calibrated detector, a full crew with distinct roles, a written reason why no machine can do the job. Any unmet clause
  refuses the entry **for every client, including a raw SQL `UPDATE`**, and names the clause that failed.
* **Shadow-entry (detective).** An entry nobody recorded cannot be seen, so anti-joins look for the records a lawful clearance
  would have left. Alerts are persisted, idempotent, reviewable, never closed by late paperwork, and hold the contractor's invoices.
* **Consequences are one transaction.** A fatality opens a ₹30-lakh compensation case with a deadline, blacklists the contractor,
  stops the job's permits and holds its invoices, all or nothing.

Problem definition, roles, business rules (`BR-nn`) and assumptions: [PROJECT_SPEC.md](PROJECT_SPEC.md).
The original proposal this implements: [docs/proposal/](docs/proposal/ZeroEntry_DBThon2026_Proposal.md).

## Status

Everything below was built and **verified by tests that were run** (`492 passed`); see [ROADMAP.md](ROADMAP.md) for the honest per-task state
and [docs/development/DEV_LOG.md](docs/development/DEV_LOG.md) for what is unfinished.

| Area | State |
|---|---|
| PostgreSQL schema: 30 tables, constraints, exclusion constraint, indexes, 9 migrations | done, tested |
| Entry gate, state machine, triggers, `record_incident`, views, row-level security, audit trail | done, tested |
| Detection by absence (SE1 / SE2), six scenarios, review, invoice holds | done, tested |
| FastAPI JSON API (100 operations), sessions, CSRF, lockout, RBAC for six roles | done, tested (role matrix) |
| Browser UI (no build, no CDN) | done; **manually verified in a browser**, no automated browser tests |
| Demo data, annotated demonstration queries | done, tested |
| Documentation: PROJECT_SPEC, ROADMAP, AGENTS, CLAUDE, DEV_LOG, generated SCHEMA_REFERENCE | done |
| ARCHITECTURE, DATABASE_DESIGN, ER_DIAGRAM, API_SPEC, SETUP, TESTING, SECURITY, CONTRIBUTING, ADRs, demo script, Docker, CI | **not written yet** (see ROADMAP) |

## Run it (no Docker, no PostgreSQL install)

Python 3.11+. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python scripts/dev.py
```

`dev.py` starts an embedded PostgreSQL 16 (from the `pgserver` wheel), migrates, loads the deterministic demo data, runs the
absence scan and serves http://127.0.0.1:8000/. It prints the demo logins (`admin@`, `engineer@`, `supervisor@`, `worker@`,
`contractor@`, `auditor@zeroentry.example`); the password is generated on first run and kept in the git-ignored
`.pgdata/dev_secrets.json`. `--reset` wipes the database. API docs are at `/docs`, health at `/health`.

**Demo path:** sign in as `supervisor@`, open the seeded draft permit, watch the checklist show five failing clauses, fix them,
press *Ask the database to authorise entry*. If you demo outside 06:00-18:00 India time, an admin widens the daylight window on the
Admin → Rules screen (itself a demonstration that the law is data, and the change is audited).

## Tests

```bash
python -m pytest -n auto      # about 2 minutes; every test gets its own database cloned from the migrated template
```

No test touches a developer database: an embedded cluster is created per test session. Layers: `tests/unit`, `tests/db` (constraints,
triggers, gate, detection, RLS, privileges, demo queries), `tests/api` (auth, RBAC matrix over every endpoint, workflows, UI guards).

## Layout

| Path | Contents |
|---|---|
| `database/migrations/sql/` | The schema and all PL/pgSQL, numbered, forward-only (run by Alembic) |
| `database/seeds/` · `database/queries/` | Demo data · annotated joins, aggregates, division, anti-join, transactions, trigger refusals |
| `src/zeroentry/` | `config`, `db`, `models`, `security`, `deps`, `errors`, `routers/`, `web/` (static UI) |
| `scripts/` | `dev.py` run everything · `db.py` migrate/bootstrap/new/reset · `seed.py` · `run_sql.py` · `gen_schema_doc.py` |
| `docs/SCHEMA_REFERENCE.md` | Every table's columns, keys, constraints, indexes, triggers and policies, **generated** (a test keeps it current) |

## Good to know

* The embedded PostgreSQL has no `btree_gist` and no time-zone database. The schema is written to not need either
  (single-point `int8range` exclusion; a fixed +05:30 offset). See [CLAUDE.md](CLAUDE.md).

Contributors and coding agents: start with [AGENTS.md](AGENTS.md). The 2013 Rules' numbering and gear schedule are cited by name
only and must be verified against the Gazette before presenting; seven engineering assumptions are flagged in
[PROJECT_SPEC.md](PROJECT_SPEC.md) section 6.
