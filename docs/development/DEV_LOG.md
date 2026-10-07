# Development log

Newest entry first. Resume from the latest entry; do not reconstruct the plan from chat history.

---

## 2026-10-07 (evening) · M6: answering the DBThon 2026 brief (evaluation, submission guide, migration 0011)

**Trigger:** the organisers' brief, now in the repository at `docs/proposal/DBTHON2026_Challenge.pdf`. It asks for eight
demonstrated components, novelty stated in five steps, and a 30-mark rubric that includes *SDG alignment* (2), *validation and
measurable improvement* (3) and *TRL* (2). The repository had evidence for the rest but no measured comparison, no SDG mapping
and no TRL statement.

### Done
* **`scripts/evaluate.py`** (own throwaway embedded PostgreSQL; never touches `.pgdata`) runs E1 detection accuracy vs the
  proposal's naive anti-join, E2 enforcement (one invalid write per write-enforced rule) vs the same schema with its rule
  triggers disabled, and E3 decision and scan latency at 1k, 10k and 100k complaints, with and without indexes and before
  `0011`. Baselines and the history generator are in `database/evaluation/` (never migrations). It writes
  `docs/EVALUATION_RESULTS.md` (generated; do not edit).
* **Results (2026-10-07):** E1 precision and recall 100 %/100 % vs 40 %/50 %; late paperwork 20/20 kept for review with their
  invoices held vs 20/20 silently dropped; E2 18/18 refused vs 1/18; E3 decision about 2 ms median and about 50 buffers, flat
  from 1k to 100k; full scan under a second at 100k. Exact figures only in `docs/EVALUATION_RESULTS.md`; hand-written docs
  round them so a rerun does not make them wrong.
* **Migration `0011`** (found by the first evaluation run): the detection views' one-row parameter CTE was inlined by PostgreSQL,
  so `rule_num()` ran once per joined row. `WITH g AS MATERIALIZED` makes the candidate query about 4x faster with 2.7x fewer
  buffers (stable across runs) and the scan 4x to 6x faster across sizes, with identical results. ADR-013; `test_detection_reads_the_grace_parameter_once_per_statement_not_once_per_row`.
* **Benchmark pitfall found and fixed:** with one warm-up, whichever variant ran first looked slower (PL/pgSQL re-plans for the
  first five calls of a session). `_timed()` now warms up six times; the first full run's E3b numbers were discarded. The
  results were then regenerated on the committed code, so the commit they name contains `evaluate.py`.
* **Docs:** `docs/EVALUATION.md` (method, baselines, headline table, limits), `docs/SUBMISSION.md` (the brief's eight components,
  five-step novelty for the three innovations, rubric map, SDG 8.8 / 3.9 / 6.2 / 16.6 with wording checked on sdgs.un.org, TRL 4
  and the path to 5-6, proposal vs as-built). README, AGENTS (where things live, read-first item 5), ROADMAP (M6), ARCHITECTURE,
  DATABASE_DESIGN §6, TESTING, DEMO_SCRIPT (evidence step), ACCEPTANCE_CHECKLIST, regenerated SCHEMA_REFERENCE.
* **`tests/db/test_evaluation.py`** runs E1-E3 at a tiny scale on every CI run and asserts counts only (never timings).

### Tests run
`python -m pytest -n 6` on Windows, Python 3.11: **513 passed** (509 before plus 4 in `tests/db/test_evaluation.py`).
`python scripts/evaluate.py` (full run, default sizes): completed, results in `docs/EVALUATION_RESULTS.md`.

### Known issues
* Timings come from one Windows laptop; counts are machine-independent. Rerun `python scripts/evaluate.py` (about 10 minutes)
  before quoting numbers from a different commit.
* E4 (concurrency) is cited from the earlier session and `tests/db/test_concurrency.py`, not re-run without `0010`.
* Still open (a person, not a test): verify the statistics and the 2013 Rules' numbering and gear schedule (ROADMAP M6-05).
* The user's local `.pgdata` database has not been migrated by this session; `python scripts/dev.py` applies `0011` on its next start.

### Next step
M6-05, then the backlog (automated browser tests first). For slides or a report, start from `docs/SUBMISSION.md` and quote
numbers only from `docs/EVALUATION_RESULTS.md`.

---

## 2026-10-07 · Documentation, a concurrency fix, cross-platform support, published to GitHub

**State:** M0-M5 complete; only the UI rows stay `[-]` (manual browser verification, no automated browser tests). Repository at
<https://github.com/Vyas-Vis06/DBThon->, CI green on Linux and Windows × Python 3.11 and 3.12, and macOS × 3.12. Final local run: see the end of
this entry.

### Done
* **Docs:** ARCHITECTURE, DATABASE_DESIGN (3NF / FD analysis, gate, detection, locking, indexes), ER_DIAGRAM (four Mermaid
  diagrams), API_SPEC (endpoint table **generated** from the role guards), SETUP, TESTING, SECURITY, CONTRIBUTING, ADRs
  (`docs/decisions/`), DEMO_SCRIPT, ACCEPTANCE_CHECKLIST, README rewritten for teammates and their agents; AGENTS/CLAUDE made
  machine-neutral. `scripts/gen_docs.py` replaces `gen_schema_doc.py`.
* **Drift tests:** endpoint table vs routes and OpenAPI; every API route guarded; every table drawn and described; every drawn
  relationship is a real FK and every non-actor FK is drawn; Markdown links resolve; every `BR-nn`/`A-nn` cited in code exists
  (found `A-10`, cited by `v_contractor_risk` but never defined: added to PROJECT_SPEC).
* **Concurrency bug (real):** guards read the permit status without a lock. Four races committed before the fix (standby
  removed / un-geared entrant added during `authorise_entry`, raw `UPDATE` racing an uncommitted crew change, entry started
  while the permit closed). Migration `0010` (`lock_permit()`, `FOR SHARE`) fixes them; `tests/db/test_concurrency.py` fails on
  all four without `0010` and passes with it. A comment in `database/queries/06_transactions.sql` claimed this was already safe;
  corrected.
* **Cross-platform:** CI showed `KeyError: 'port'` on Linux (pgserver uses a Unix socket there). `zeroentry.db.url_for()` and
  `make_conninfo()` fix the harness, `dev.py`, `gen_docs.py`, `run_sql.py`. pgserver has wheels for Python 3.9-3.12 only: the dev
  extra is now conditional and the tests / `dev.py` stop with an instruction on 3.13+ (verified with 3.13 locally).
* **`scripts/db.py`** `bootstrap`, `reset`, `new` now tested (`tests/db/test_db_script.py`).
* **Fresh-clone check:** clone → new venv → `pip install -e ".[dev]"` → full suite green (Windows, Python 3.11). The demo flow was
  re-checked on fresh data from a clone (`dev.py`), partly by clicking (denial, authorise button, incidents) and partly through
  the endpoints the forms call: five-clause denial, calibration refusal, authorisation, daylight refusal, audited rule change,
  95-minute / standby / overlap / close-while-inside refusals, alert dismissal releasing only its hold, idempotent rescan.

### Known issues
* The first CI run had one Windows/3.12 failure whose log needs a GitHub sign-in; later runs on the same OS/Python were green.
  If it recurs, read the "pytest (last 60 lines)" annotation the workflow now writes.
* After a forced kill, the embedded PostgreSQL's crash recovery can outlast pgserver's 10-second start timeout; running
  `dev.py` again works (SETUP troubleshooting).
* `database/queries/07_trigger_refusals.sql` needs a DRAFT permit for two of its nine refusals (run it before authorising the
  demo permit, as DEMO_SCRIPT says).
* Legal references still to be verified against the Gazette.

### Final local run
`python -m pytest -n 6` on Windows, Python 3.11: **509 passed in 104 s** (2026-10-07).

### Next step
Automated browser test of the demo flow; CI job against a real PostgreSQL service container; backlog in ROADMAP.

---

## 2026-10-06 · End of the first build session (usage limit reached)

**State:** M0-M4 complete and tested; M5 (UI) built and manually verified. **492 tests passed in 105 s**
(`python -m pytest -n 6`). Nothing is committed; `git init` was run in this folder only.

### Built and verified
* **Database** (`database/migrations/sql/0001-0009`): 30 tables; keys/CHECK/UNIQUE/FK; `ex_entry_no_overlap` exclusion constraint;
  audit trigger on 20 tables, append-only evidence tables; `permit_clause_check()` (relational division over gear and the three depth
  levels), `authorise_entry()`, the gate trigger (no path reaches `AUTHORISED` without the proof), crew/gear freeze, gas/entry/waiver/job
  guards; `record_incident()` procedure (atomic consequences); invoice holds with provenance; SE1/SE2 candidate views,
  `scan_shadow_entries()` (idempotent), alert lifecycle + history; least-privilege grants (0008); row-level security + definer
  helpers + `stop_work()` (0009).
* **API** (`src/zeroentry/`): sessions (opaque token, hash stored), bcrypt, lockout, per-IP throttle, CSRF header + origin check,
  RBAC via `require()`, request-scoped transaction committed *before* the response (`scope="function"`), one error vocabulary
  (SQLSTATE class `ZE`), 100 operations.
* **UI** (`src/zeroentry/web/`): one HTML shell + one ES module per screen; text nodes only (a test bans `innerHTML`-style APIs).
* **Data/queries/docs**: `database/seeds/01_base.sql`, `02_scenarios.sql` (S0-S10); `database/queries/01-07`; generated
  `docs/SCHEMA_REFERENCE.md` with a sync test.
* **Manually verified in the in-app browser** (not automated): login, dashboard, shadow-entry list/detail/dismiss, complaints and
  detail, permit wizard (denied with 5 reasons → fixed through the forms → AUTHORISED), 95-minute entry blocked, overlap blocked,
  audited rule change, incidents, invoices/holds, registry, reports, admin rules/audit.

### Real defects found by the tests and fixed (worth remembering)
1. Terminal permits accepted `status=ABORTED` again and **overwrote the stop-work reason** → whole row now frozen outside DRAFT.
2. RLS insert policy for a new permit looked the (nonexistent) row up → every supervisor insert refused → check the row itself.
3. Inner joins to RLS-protected lookup tables silently drop rows (worker's permit list empty) → outer joins for display names.
4. A NUL byte in a search string produced a 500 → driver `DataError` now maps to 422.
5. FastAPI default-scope dependency teardown runs *after* the response: a failed commit would return 200 → `scope="function"`.
6. UI: `datetime-local` rounds to the minute, so "now" could precede the authorisation instant → seconds precision + safe default.
7. Windows PowerShell `Set-Content -Encoding UTF8` writes a BOM that breaks SQL files → use Python/`Edit`, never that cmdlet.

### Not done (in priority order; ROADMAP has the checklist)
1. **Docs not yet written:** ARCHITECTURE, DATABASE_DESIGN (narrative + 3NF/functional-dependency analysis), ER_DIAGRAM (Mermaid, split in 3-4
   diagrams), API_SPEC (conventions + endpoint/role table), SETUP, TESTING, SECURITY, CONTRIBUTING, `docs/decisions/` ADRs, `DEMO_SCRIPT.md`,
   `ACCEPTANCE_CHECKLIST.md`. AGENTS.md points at some of these; they are listed as unwritten in ROADMAP. Add drift tests as each lands
   (every table named in DATABASE_DESIGN and ER_DIAGRAM; every OpenAPI operation named in API_SPEC; roles in the doc = `require()` roles).
   Idea for the API doc: walk `app.routes` (`_IncludedRouter.original_router`, 102 routes) and read each guard's roles by setting `guard.roles = roles` in `deps.require`.
2. `docker-compose.yml`, `.github/workflows/ci.yml` (CI must be marked not-executed unless run), `scripts/demo.py` (scripted 3-minute demo; `database/queries/06-07` already demonstrate rollback and refusals).
3. `scripts/db.py` (`bootstrap`, `new`, `reset`) has no automated test; `scripts/dev.py` was verified by running it.
4. Verify README steps in a **fresh venv**; run the final advisor review; commit only when the user asks.
5. Product gaps (backlog in ROADMAP): ULB-scoped visibility, rest-interval rule (assumption A-04), simulated sensor feed, UI automated tests.

### Decisions (to become ADRs)
Schema as numbered raw `.sql` run by Alembic (no `create_all`); opaque DB sessions not JWT; detection anchored on complaint with
timely-evidence + grace and **late evidence never auto-closes**; holds as a table with provenance; `int8range` exclusion and fixed
+05:30 time because the embedded PostgreSQL lacks `btree_gist` and tz data; RLS second to RBAC, claimed only because tested.

---

## 2026-10-06 · Earlier milestones

M0 foundation → M1 schema + seed (30 tables) → M2 entry gate + consequences → M3 detection → M4 API/auth/RBAC/RLS → M5 UI.
Each was verified before the next began; details are in the entry above and in ROADMAP.
