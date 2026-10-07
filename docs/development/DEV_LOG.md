# Development log

Newest entry first. Resume from the latest entry; do not reconstruct the plan from chat history.

---

## 2026-10-08 (later) · Condition showcase, copy-paste commands, conditions deck

### Done
* **`scripts/showcase.py`** (`python run.py showcase`) starts its own throwaway PostgreSQL. It builds one template from the
  migrations plus the demo seed (widening daylight to all day in that copy, through policy history with a reason), clones one
  database per condition and runs **19 conditions concurrently**. Each one prints the situation, the action, the database's
  reaction and the state before and after. It exits 1 on any unexpected reaction. The conditions:
  * A, the gate: denied, raw-UPDATE bypass, authorised with snapshot, expired detector, frozen crew;
  * B, the work: overlap (`23P01`), standby entering, unsafe O2 aborting the permit while the exit is still recorded;
  * C, detection: idempotent scan, late evidence leading to `EVIDENCE_RECEIVED`, dismissal releasing only its own hold,
    supervisor refused (`ZE006`);
  * D, money: held invoice, atomic fatality with the blacklisted contractor refused a new job, forced failure rolled back
    (`23514`);
  * E, concurrency: crew race during authorisation, double payment;
  * F, security: RLS row counts per user, three `ze_app` statements refused with `42501`.
* **`tests/db/test_showcase.py`** runs it as a subprocess and requires 19 of 19.
* **`docs/guide/DEMO_COMMANDS.md`:** terminal-by-terminal commands to copy and paste.
* **`docs/guide/ZeroEntry_Conditions.pptx`:** 14 slides with speaker notes, built with pptxgenjs from the real showcase
  output. It validates, and every slide was checked visually through PowerPoint's own export. The generator script is not
  kept in the repository; it needs Node and pptxgenjs.

### Tests run
* `python run.py showcase`: 19 of 19 as expected, about 1.5 s wall time for the conditions.
* `tests/db/test_showcase.py`: 1 passed (39 s).
* Full suite `python -m pytest -n 6` on Windows, Python 3.11: **575 passed in 190 s** (574 plus the showcase test).

---

## 2026-10-08 · Frontend merged into main; one-command run; judge's guide

### Done
* **Merge:** `main` fast-forwarded to `origin/feat/frontend-safety-operations-ui` (`04c7d8d`, the safety-operations console
  redesign), which sits on `origin/main` (`a3db1b4`, PR #1 squashed). No conflicts. The earlier entry's four merge points were
  already handled by PR #1: migrations renumbered `0012`-`0014`, the materialised CTE kept (now in `0013`),
  `evaluate_temporal.py` separate. **Local only; not pushed.**
* **`run.py` (repository root):** the one command. It creates `.venv` with Python 3.11/3.12 on first run, installs (it
  reinstalls only when `pyproject.toml` changes), then delegates: no flags → `scripts/dev.py`, `sql [file|"SQL"]` →
  `run_sql.py` (no file runs all seven showcase files), `psql [--app]` → the bundled psql as the owner or `ze_app`,
  `test` → pytest, `<name>` → `scripts/<name>.py`. `--data-dir` passes through.
* **`scripts/run_sql.py`:** `--data-dir` (it was hard-wired to `.pgdata`, so DEMO_SCRIPT's `.pgdata/presentation-final`
  runs attached to the wrong cluster) and inline SQL. DEMO_SCRIPT now passes the matching `--data-dir`.
* **`scripts/dev.py`:** the startup banner lists `run.py psql`, `psql --app` and `sql`, with the `--data-dir` in use.
* **`docs/guide/`:** README (run and try it, evening daylight caveat), PROJECT_EXPLAINED (from zero), TECH_STACK_AND_GUARANTEES
  (stack; ACID, isolation choice, races and their tests; security; audit; performance; limits), JUDGE_QA (48 questions with
  answers, plus live-demo challenges). Linked from README.

### Tests run
* `python -m pytest -n 6` on the merged code before any change, Windows, Python 3.11: **574 passed in 144 s**.
* After the `run_sql.py` change and the guides: **574 passed in 166 s** (same machine). After the final doc edits:
  `tests/unit/test_docs.py` and `tests/db/test_demo_queries.py`, **17 passed**.
* Manual walk in the in-app browser on an isolated `.pgdata/judge-demo` (started by
  `python run.py --data-dir .pgdata/judge-demo --port 8010`), at about 00:06 IST:
  * as supervisor: dashboard, then the DRAFT permit on CHN-ADY-010 denied with the five expected clauses; added a standby,
    "Issue all missing" gear, logged TOP/MID/BOTTOM with GD-4G-0001, then **AUTHORISED** (authorisation works at night;
    only starting an entry is limited to daylight); Original authorisation shows "Saved decision digest verified";
  * as engineer: five alerts listed; dismissing alert #5 (CHN-ADY-006) released exactly hold #4, with holds 1-3 still active
    (checked with `run.py sql`); the UI scan reported 0 opened, nothing re-opened;
  * as admin: users and policy-and-sources pages loaded;
  * every API call returned 2xx, except a deliberate logout without a CSRF token (403, as designed).
* `python run.py sql --data-dir .pgdata/judge-demo` (all seven showcase files, exit 0) and an inline statement both worked.
  Restarting through `run.py` printed the new banner.

### Known issues
* `python run.py psql [--app]` was not executed in this session (the agent's tool permissions blocked running psql). Try it
  by hand once.
* After a forced kill (not Ctrl+C), the next start can fail with a `pg_ctl` 10-second timeout while PostgreSQL recovers on
  Windows; running it again works. Noted in `docs/guide/README.md`.
* Child output is block-buffered when `run.py` runs under a pipe (an IDE preview); in a terminal it prints live.
* `docs/guide/JUDGE_QA.md` Q5 defers the exact SDG targets and TRL to SUBMISSION.md; check that they match before presenting.

### Next step
Ask the user before pushing `main` (origin is at `a3db1b4`) and before committing these changes. Then M6-05 and the backlog
(automated browser tests first).

---

## 2026-10-07 · Audit hardening, preserved decisions and presentation evidence

**State:** original foundation extended on `feat/audit-hardening-and-evaluation`, with three new forward migrations,
35 tables, new scoped read endpoints and presentation screens. Original migrations 0001–0011 remain unchanged.
Initial audit version, before the concurrent M6 integration: **568 passed in 30.21 seconds**, macOS, Python 3.12.11,
embedded PostgreSQL 16.2. All six CI jobs passed on `28b8bee`, including PostgreSQL service and all five OS/Python jobs.
Final integrated local validation: **574 passed in 29.67 seconds**, including upstream late-evidence invoice measurement.
Branch CI is configured for the original five OS/Python jobs and a separate PostgreSQL 16 service; see Actions for its
current result. The release is for review, not an automatic merge or a production safety certification.

### Implemented and verified

* Immutable crew/gear parents; live revalidation; time-based maintenance; rest interval; truthful exits after stop and
  durable violation history (`0012`). Private locking/event helpers have runtime execution revoked.
* Final-outcome receipt semantics and audited legacy backfill; common complaint/invoice serialization for alert and
  incident holds versus payment, approval and invoice creation (`0013`). Financial writers require `READ COMMITTED`;
  repeatable-read snapshots fail with retryable `40001` rather than accept stale decisions.
* Classified primary sources, reasoned policy revisions and immutable successful authorization snapshots with
  PostgreSQL SHA-256 (`0014`). Runtime actors/receipts are DB-owned; authorization samples a fresh clock after locks.
* Automatic safety/detection tasks commit separately with bounded waits and advisory locks. Failure injection confirms
  that a failed scan cannot roll back an already committed stop.
* Built and separately installed wheel passes shell/JS/CSS smoke checks. No new application dependency added.
* Synthetic SE1 evaluation at 1k/10k/100k complaints, seven query samples per scale, raw plans/counts/confusion matrices
  and source hashes. The saved 100k run measured 140.88 ms p50 and 142.18 ms p95 for SE1 and 2460.04 ms for first scan.
  Six synthetic labels classify as expected; this is not field accuracy or an equal-task speedup claim.
* Fresh isolated local demo: expected five initial alerts; UI denial with five reasons; completed crew/gear through API;
  simulator-authorized safe readings; an open entry; low-oxygen stop; browser-recorded exit after stop; three retained
  safety events. A subsequent policy revision left the original decision bytes/digest unchanged.
* Original-decision, safety-history and policy-history screens were manually walked through in the in-app browser.
  Automated browser coverage remains unimplemented.

### Concurrent upstream integration

Upstream `fc4261e` added M6 while the audit release was underway. It is merged, including its original migration `0011`.
The audit migrations are now 0012–0014, and their SE1 view preserves the upstream materialized parameter CTE.
The main `scripts/evaluate.py` is retained and adapted to truthful historical receipt imports and a current rest-admission
probe; `scripts/evaluate_temporal.py` is the supplementary SE1 finalization experiment. The unmaterialized comparison
retains final temporal semantics. Runtime draft authorization now also requires READ COMMITTED to prevent stale worker
credentials in repeatable-read snapshots, with regressions for function and raw UPDATE. Source provenance includes the
official 20 January 2026 compensation clarification. Latest upstream `72dc6d1` is also integrated, including its explicit held-invoice measurement for late paperwork.
The final M6 run on committed `7893c09` measured a 1.7 ms median decision and a 254.9 ms median persisted scan at
100,001 complaints; 20/20 late-evidence invoices remained held and E2 refused 18/18 probes. The supplementary run on
`6c55b37` uses a different, evenly interleaved temporal workload; all 15 source fingerprints match the final SQL/runner.
The final isolated demo `.pgdata/presentation-final` retained an exit after the unsafe stop, three safety events and
unchanged original decision bytes after a policy revision. Only this synthetic rehearsal widens the daylight proxy to
24:00 for the evening presentation. The default migration remains 06:00–18:00 IST. UI wording now refers to configured
checks over recorded evidence. Final branch CI is linked from PR #1; no automatic merge is authorized.

### Handoff

[AUDIT_RELEASE.md](AUDIT_RELEASE.md) maps findings to changes and the earlier schema.
[PRESENTATION_BRIEF.md](PRESENTATION_BRIEF.md), [DEMO_SCRIPT.md](DEMO_SCRIPT.md),
[POLICY_AND_PRIOR_ART.md](../POLICY_AND_PRIOR_ART.md) and [evaluation/RESULTS.md](../evaluation/RESULTS.md) support the
presentation. Remaining pilot/production work is tracked in ROADMAP; local decision hashes have no external anchor,
physical instruments are not authenticated, equipment applicability remains illustrative, and history starts at cutover.

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
* **Historical integration instructions, resolved by this audit release.** PR #1 was written
  in parallel with this entry. Whoever merges it must:
  1. **Renumber its migrations** `0011_safety_lifecycle`, `0012_temporal_evidence_invoice_serialization`,
     `0013_policy_provenance` to `0012`-`0014` (files and `revision`/`down_revision` in `database/migrations/versions/`):
     `main` already has `0011_detection_parameters_once`, and applied migrations are never renumbered.
  2. **Keep `WITH g AS MATERIALIZED`** in its re-creation of `v_shadow_se1` (its `0012`): the PR copies 0007's inlined CTE,
     which would silently undo `0011`'s fix. `test_detection_reads_the_grace_parameter_once_per_statement_not_once_per_row`
     fails if it is lost.
  3. **Two `scripts/evaluate.py`** (add/add conflict): the PR's measures SE1 as `ze_app` and writes `docs/evaluation/`; this
     one runs E1-E3 including enforcement and writes `docs/EVALUATION_RESULTS.md`. Suggested: rename the PR's to
     `scripts/evaluate_se1.py`, link its results from `docs/EVALUATION.md`, and rerun both after the merge.
  4. Union the overlapping docs (README, ROADMAP, DEV_LOG, ARCHITECTURE, DATABASE_DESIGN, TESTING, ACCEPTANCE_CHECKLIST,
     DEMO_SCRIPT), regenerate `docs/SCHEMA_REFERENCE.md`, and run the whole suite: `tests/db/test_evaluation.py` builds rows with
     `tests/factories.py`, which the PR changes, and its stricter rules may change which SQLSTATE a probe gets (the test only
     requires class `ZE`).
* Timings come from one Windows laptop; counts are machine-independent. Rerun `python scripts/evaluate.py` (about 10 minutes)
  before quoting numbers from a different commit.
* E4 (concurrency) is cited from the earlier session and `tests/db/test_concurrency.py`, not re-run without `0010`.
* Still open (a person, not a test): verify the statistics and the 2013 Rules' numbering and gear schedule (ROADMAP M6-05).
* The user's local `.pgdata` database has not been migrated by this session; `python scripts/dev.py` applies `0011` on its next start.

### Next step
The audit release resolves the four integration points above. Review PR #1, then M6-05 and the
backlog (automated browser tests first). For slides or a report, start from `docs/SUBMISSION.md` and quote numbers only from
`docs/EVALUATION_RESULTS.md`.

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
