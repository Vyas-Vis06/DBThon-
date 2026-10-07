# Architecture decision records

Short records of the choices that shape the code, so nobody has to rediscover why. Newest last. To change one, add a new record
that supersedes it; do not rewrite history.

Format: **context** → **decision** → **consequences** (including what it costs).

---

### ADR-001 · Interpret the problem as sanitation-worker safety

* **Context.** "Zero-Entry / Shadow-Entry Detection by Absence" names no domain. The workspace held a complete DBThon proposal
  using exactly these terms (sewer entry), and an unrelated second proposal.
* **Decision.** Zero-entry = default-deny manual sewer entry; shadow-entry = an unrecorded entry inferred from missing evidence.
  Rejected readings and why: [PROJECT_SPEC.md §1](../../PROJECT_SPEC.md).
* **Consequences.** Legal references must be checked against the Gazette before presenting (rules are cited by name).

### ADR-002 · PostgreSQL is the authority for business rules

* **Context.** The core claim is that *no* client can authorise an unsafe entry.
* **Decision.** Rules live in constraints, triggers and functions; the API is thin. The gate function is called both by
  `authorise_entry()` and by a `BEFORE UPDATE` trigger.
* **Consequences.** The rules hold for `psql`, scripts and any future client. PL/pgSQL is harder to unit-test in isolation, so
  each rule has a pass and a fail test against a real database.

### ADR-003 · Numbered raw SQL migrations, run by Alembic

* **Context.** The schema is mostly behaviour (triggers, policies) that ORM autogeneration cannot express.
* **Decision.** `database/migrations/sql/NNNN_name.sql`, each wrapped by a one-line Alembic revision; forward-only; no
  `create_all()`. ORM models map onto the SQL tables, and a test checks they match.
* **Consequences.** Reviewers read plain SQL. An applied migration is never edited; fixes are new migrations (see ADR-012).

### ADR-004 · Embedded PostgreSQL for development and tests

* **Context.** Contributors may have no Docker and no admin rights.
* **Decision.** Use the `pgserver` wheel (PostgreSQL 16 inside pip) for `scripts/dev.py` and the test harness.
* **Consequences.** One-command setup on Windows, macOS and Linux, but only on Python 3.9-3.12 (no newer wheels). The build has
  no `btree_gist` and no time-zone database, so the overlap rule uses a single-point `int8range` instead of a btree-gist
  equality, and local time is a fixed +05:30 (`local_ts()`, `local_date()`, `from_local()`; assumption A-07). On Linux and macOS
  it listens on a Unix socket, so URLs carry host and port as query parameters (`zeroentry.db.url_for`).

### ADR-005 · Opaque server-side sessions, not JWT

* **Context.** Logout, lockout and deactivation must take effect immediately.
* **Decision.** 256-bit random tokens; only the SHA-256 is stored in `user_session`; cookie for the browser (with CSRF token and
  origin check), Bearer for scripts.
* **Consequences.** One indexed lookup per request; real revocation; no signing keys to manage.

### ADR-006 · Detection is anchored on the complaint and on *recorded* time

* **Context.** A shadow entry leaves no row; the alert must not race the scan schedule or be silenced by paperwork created later.
* **Decision.** SE1 starts from every complaint resolved as "cleared" (so a complaint with no job at all is caught); evidence
  counts only if `recorded_at` falls inside the grace window. Late evidence moves an alert to `EVIDENCE_RECEIVED`; a human decides.
* **Consequences.** Candidates are a pure function of the data. Some honest late paperwork creates review work; that is the
  intended trade-off (A-06).

### ADR-007 · Invoice holds are rows with provenance

* **Context.** A dismissed alert must not release a hold placed by a fatality on the same invoice.
* **Decision.** `invoice_hold` rows with exactly one source (alert or incident); an invoice is on hold while any hold is unreleased.
* **Consequences.** Release logic is per source and auditable; "is it on hold" is an `EXISTS` (partial index).

### ADR-008 · Row-level security as a second line behind role guards

* **Context.** API bugs and tenant mix-ups are likelier than a stolen database login.
* **Decision.** Every endpoint has a role guard; PostgreSQL RLS scopes contractor and worker rows again, from transaction-local
  settings. Claimed only because `tests/db/test_rls.py` proves it.
* **Consequences.** Inner joins to RLS-protected lookups can silently drop rows; display joins are outer joins. RLS does not
  protect against arbitrary SQL as `ze_app` ([SECURITY.md](../../SECURITY.md)).

### ADR-009 · A no-build browser UI

* **Context.** A database course project; the UI must be easy to read and must not pull third-party code.
* **Decision.** One HTML shell and one ES module per screen; no framework, bundler or CDN; strict CSP; DOM built from text nodes.
* **Consequences.** Nothing to install for the UI; more verbose than a framework; no automated browser tests yet.

### ADR-010 · A fresh database per test

* **Context.** Rules involve commits, rollbacks, locks and triggers; a shared transaction would hide them.
* **Decision.** Migrate a template once per session; `CREATE DATABASE ... TEMPLATE` for every test.
* **Consequences.** Real transaction behaviour, full isolation, about 2 minutes for 500+ tests in parallel.

### ADR-011 · Generated documentation with drift tests

* **Context.** Hand-written schema and endpoint lists go stale.
* **Decision.** `docs/SCHEMA_REFERENCE.md` and the endpoint table in `docs/API_SPEC.md` are generated (`scripts/gen_docs.py`);
  tests fail when they are stale, when the ER diagrams miss a table or invent a relationship, or when a link breaks.
* **Consequences.** Changing a migration or router means regenerating and committing the docs in the same change.

### ADR-012 · Serialise evidence changes with permit decisions (migration 0010)

* **Context.** Guards read the permit's status without a lock; under READ COMMITTED a concurrent crew change or entry could
  commit alongside an authorisation or a close (reproduced by `tests/db/test_concurrency.py`).
* **Decision.** Every guard on crew, gear, readings and entries first takes `FOR SHARE` on the permit row through an owner-rights
  `lock_permit()` (so RLS cannot hide the row). Chosen over `SERIALIZABLE` isolation, which would need retry logic in every caller.
* **Consequences.** Concurrent edits to one permit wait for each other (permits are edited by one supervisor at a time, so the
  wait is negligible); the proof behind an `AUTHORISED` permit cannot change underneath it.

### ADR-013 · Measure against a stated baseline; read rule parameters once per statement (migration 0011)

* **Context.** The DBThon brief asks for measured improvement over a conventional approach. `scripts/evaluate.py` compares
  ZeroEntry with the proposal's naive anti-join (detection) and with the same schema minus its rule triggers (enforcement), and
  times both core operations as history grows. Its first run showed the detection views calling `rule_num()` once per joined row,
  because PostgreSQL 12+ inlines a CTE that is referenced once.
* **Decision.** Baselines live in `database/evaluation/` and run only in a throwaway database, never as migrations. Migration
  `0011` re-creates `v_shadow_se1` and `v_shadow_se2` with `WITH g AS MATERIALIZED`; `rule_num()` is `STABLE`, so results are
  unchanged. A test checks the plan keeps the CTE (`tests/db/test_evaluation.py`).
* **Consequences.** The initial M6 measurement on commit `fc4261e` recorded a 12x scan improvement at 100,000 complaints.
  Current measurements are regenerated for the hardened release in [EVALUATION.md](../EVALUATION.md). The evaluation is a
  repeatable command, and its counts (not its timings) are asserted in CI. Any future view that reads a parameter should
  materialise it the same way.
