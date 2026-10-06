# Development log

Newest entry first. Resume from the latest entry; do not reconstruct the plan from chat history.

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
