# ZeroEntry: four-person implementation and integration runbook

Contract release: ZE-1.0. This is an implementation plan, not an already runnable application. Commands below become executable when the named scaffold milestone has been delivered. Never report them as passed merely because they appear here.

## 1. Who does what now

| Human/session | Primary responsibility | First action | First deliverable |
|---|---|---|---|
| L: release lead | Architecture, source decisions, shared files, review, release; absorbs friend's M2 domain lane | Read README, MASTER_PLAN, REVIEW_AND_EVIDENCE, then prompts/LEAD_COORDINATOR.md | Repository baseline, contract snapshot, starting commit SHA and assignments |
| A: database worker | Friend's M1 plus database evidence | Paste prompts/WORKER_A_DATABASE.md; supply all frozen contracts and relevant syllabus | Migration A1: complete schema, deterministic reference seed and constraint tests |
| B: backend worker | Friend's M3 plus integration tests and measurements | Paste prompts/WORKER_B_BACKEND.md with same baseline | Mock-compatible API skeleton, auth boundary and routine adapters |
| C: frontend worker | Friend's M4 implementation/pitch responsibilities | Paste prompts/WORKER_C_FRONTEND.md with same baseline | Four mock-backed views using frozen JSON, never fake live-success claims |

Two ChatGPT+ and one Claude Pro account are available according to the team. Assign the three coding lanes to those available sessions; L can operate manually or use an available planning session. Do not assume a fourth subscription, API credits, unattended cross-account communication or infinite quotas. Each human remains responsible for running and understanding their changes. For repetitive extraction/checking delegated from this package, use GPT-6 Luna when available, not Astra. Do not change another account's model without its owner's agreement.

Separate accounts coordinate through versioned files and human handoffs. They do not need to read each other's chats. One stable repository commit plus one bounded packet is the shared state. Use separate local clones/databases on the four laptops. Do not have multiple workers editing the same directory on one machine.

## 2. Scaffold and ownership

L creates a new repository or uses the team's explicitly selected existing one. Inspect existing files first; never overwrite a friend's implementation. The supplied Friend_progress folder contained research/prompts, not verified application code.

```text
zeroentry/
  README.md                         L: startup, limitations, actual results
  .env.example                      L: variable names only, no real secrets
  .gitignore                        L
  compose.yaml                      L; B may propose a patch for L to apply
  pyproject.toml / dependency lock  L; B proposes Python dependencies
  CLAUDE.md / AGENTS.md              L: equivalent short contract pointers
  scripts/dev.ps1                   L: portable bootstrap/reset/check wrappers
  scripts/demo.ps1                  B: deterministic demo actions
  db/alembic/versions/               A ONLY: numbered migration history
  db/sql/                           A: routines, policies, views and LAB examples
  db/seed/                          A: source catalogue + relative-time fixtures
  backend/app/                      B: FastAPI, schemas, auth, command adapters
  backend/tests/                    B: endpoint, scope and integration tests
  backend/devices/                  B: signed simulator and optional ESP32 adapter
  frontend/                         C: sole package.json and JS lockfile owner
  tests/db/                         A: SQL correctness and permissions
  tests/concurrency/                B: barrier-coordinated transactions, with A review
  benchmarks/                       B: isolated B0/B1/ZE harness + raw results
  docs/plan/                        L: copy of this package, frozen ZE-1.0
  docs/evidence/db/                 A: query plans, normalisation, SQL transcripts
  docs/evidence/api/                B: run manifests, test and benchmark output
  docs/evidence/ui/                 C: screenshots, recordings, slide source
  docs/coordination/                L: task board, decisions, handoff snapshots
```

Ownership is an integration rule, not a security system. A worker needing another lane's change writes a precise request; the owner implements it. L alone edits cross-lane contracts and root dependencies. Neither an API-generated ORM migration nor `create_all()` may compete with A's Alembic history. Tests may describe missing capabilities without silently adding a second implementation.

Freeze these before dispatch: PostgreSQL 16; Python 3.12; Node 22; FastAPI + SQLAlchemy 2 + Alembic; React + Vite + TypeScript; schema `ze`; UTC timestamps; INR decimals as strings at the API; field/state/error names in the three contract documents. Resolve compatible package patch versions once during bootstrap and commit lockfiles. These are selected target versions, not a claim that a tested dependency lock exists today.

### Baseline creation: L only

In the selected project directory, inspect `git status` first. For a genuinely new repository only:

```powershell
git init -b main
git add .gitignore README.md docs/plan
git diff --cached --check
git commit -m "docs: freeze ZeroEntry ZE-1.0 planning contracts"
git remote add origin <TEAM_REPOSITORY_URL>
git push -u origin main
git rev-parse HEAD
```

Angle-bracket values are placeholders requiring a real authorized team repository. Create the remote through the team's normal account; this plan has not created or published one. L shares the exact resulting SHA, not just “latest main.” Add root scaffold in one further reviewed baseline commit before A/B/C depend on it. Keep branches short-lived and make the remote main branch the accepted integration state.

### Migration and fixture contract

1. A owns revision `001_core`: extensions, 37 base relations, PK/FK/UQ/CHECK/exclusion constraints and indexes. Add receipt circular FK after both tables exist.
2. A owns `002_engine`: fixed policy vocabulary, all named routines, trigger ordering, views, outbox logic. Install function definitions transactionally; signatures cannot silently drift.
3. A owns `003_runtime_permissions`: owner/engine/runtime roles, narrowly scoped EXECUTE/SELECT, revocations, RLS/view paths and smoke tests. Runtime login must never own the schema or inherit an owner role.
4. After a migration is merged and used by another lane, do not edit its history. Add a new revision owned by A. Check exactly one Alembic head.
5. Reference CSV loading is idempotent, code-to-UUID mapped and validated. Demo seed is a separate explicit command, not a time-dependent migration. Source metadata retains verification status.
6. Seed two scopes, Chennai real-policy DENY/REVIEW and EDU_LAB educational-only. Seed one mechanical success, one intentionally failing educational permit, one completed-claim evidence gap, one legitimate second job for the same complaint, and a standalone synthetic incident.
7. IDs follow API_CONTRACT namespaces. Set time-sensitive fixture evidence relative to reset time. Deterministic content plus relative timestamps is reproducible; hard-coded yesterday's samples are not.
8. Reset only an unmistakably labelled demo database. The wrapper checks database name/environment, asks for explicit confirmation and refuses unknown targets. Do not put broad `down -v` or destructive cleanup into ordinary startup.

### Startup commands the scaffold must provide

```powershell
Copy-Item .env.example .env
# Fill local-only development values; never commit .env.
docker compose up -d db
docker compose run --rm api alembic upgrade head
docker compose run --rm api python -m app.seed --profile demo
docker compose up -d api web
Invoke-RestMethod http://localhost:8000/health
```

Service names and ports above are the root scaffold contract; B implements `/health` outside `/api/v1` for process/database readiness, with no secrets. L's `scripts/dev.ps1 up` wraps these steps; `check` runs migration, server and UI checks; `reset-demo` performs the guarded demo-only reset. The seed module delegates SQL fixture loading to A's files rather than inventing ORM inserts that bypass the engine. A separate privileged seed login is available only to the reset tool, never the running API.

Internet-free demonstration means no hosted runtime dependency; building initially may download dependencies/images. L prepares images and lockfile installs in advance and tests after disconnecting the network. If Docker is unavailable on the presentation laptop, use a pre-tested local PostgreSQL 16 instance with the same migrations and environment; do not switch databases to SQLite.

## 3. Milestones and dependency-ordered merges

| Packet | Owner | Budget | Dependency | Deliverable and merge gate |
|---|---|---:|---|---|
| L0 | L | 60–90m | None | Frozen contracts, repo/scaffold and common SHA; all three can start |
| A1 | A | 2–3h | L0 | Clean migration + reference/demo seed + schema constraints; fresh DB passes |
| B1 | B | 2h | L0 | Typed endpoint skeleton, auth, mocked adapter, `/health`; JSON contract tests |
| C1 | C | 2–3h | L0 | Four views + explicit MOCK banner; typecheck/build and denial UI |
| A2 | A | 3–4h | A1 | G0–G8, receipts/recheck, scope lock, exclusions; boundary/NULL/direct-write tests |
| B2 | B | 2–3h | A2,B1 | Real commands, transaction context, ingestion and SSE/poll fallback; pool isolation tests |
| C2 | C | 1–2h | B2,C1 | Live adapter golden path; stale receipt and incident states displayed correctly |
| A3 | A | 2–3h | A2 | Reconciliation, incident procedure, cursor, grant/recovery evidence; rollback tests |
| B3 | B | 2–3h | A3,B2 | Full adversarial/race suite and fair benchmark raw results |
| C3 | C | 2h | C2,B3 | Evidence view, truthful slides, offline recording and timed rehearsal |
| L1 | L with all | 2–3h reserved | Integrated features | Clean-clone run, no-network demo, rubric audit, release tag |

These estimates overlap across lanes and are not promises. Merge A1 then compatible B1/C1; B/C may work on mocks before A1. Integrate A2/B2/C2 before spending hours polishing A3 extras. A3 core reconciliation/incident functionality remains mandatory for the selected end-to-end contribution; reduce UI breadth and benchmark dataset size before dropping it. Do not wait for a worker's whole lane to be complete before reviewing an independent milestone.

## 4. What happens when a worker finishes and wants to push

“Task complete” means a small reviewable change, not permission to merge into main. Worker:

```powershell
git status --short
git switch -c worker-a/schema-core
# Implement only the assigned files, run the milestone's checks.
git diff --check
git diff
git add <EXPLICIT_OWNED_PATHS>
git diff --cached
git commit -m "db: add core schema and reference seed"
git fetch origin
git merge origin/main
# Re-run tests after this integration; resolve only understood conflicts.
git push -u origin worker-a/schema-core
```

Create the branch before editing; if it already exists, switch to it without recreating it. Substitute B/C and milestone names. No `git add .` until reviewed for secrets/unrelated files, no force push, no main push by workers, no hard reset. If a conflict crosses ownership, stop that merge step, send the conflicting paths and intended semantics to L; do not accept “ours/theirs” blindly. Preserve work with a normal commit or documented patch.

Open a pull request in the repository UI and send its URL plus the handoff below to L. If the account cannot access Git, the human operator applies changes, runs checks and does the push; a chat saying “tests should pass” is not execution evidence.

```text
WORKER / MILESTONE:
STARTING MAIN SHA:
BRANCH / HEAD SHA / PR URL:
CONTRACT VERSION: ZE-1.0
IMPLEMENTED:
NOT IMPLEMENTED:
OWNED FILES CHANGED:
CONTRACT OR ROOT FILE CHANGES: none, or approved change ID
MIGRATION / SEED IMPACT:
COMMANDS ACTUALLY RUN AND RESULTS:
ACCEPTANCE TEST IDs / EVIDENCE PATHS:
DEMO STATE BEFORE -> AFTER:
KNOWN LIMITATIONS / BLOCKERS:
NEXT READY TASK:
```

L reviews the diff, exact tests and prerequisites, not just a confident summary. L checks no secret, duplicate schema authority, mock success presented as real, invented legal/benchmark claim or cross-lane rewrite. Review verdict: ACCEPT / CHANGES REQUIRED / PROVISIONAL (insufficient evidence). A/B cross-review engine/transaction changes; C checks JSON/UI impact. L merges only after current main plus this branch is tested, preferably with a merge commit so a whole milestone can be reverted. Record merged SHA and tell all workers to fetch/merge it before their next push. Attach any PR created by a Codex session to that session using the app's artifact feature.

After merging, worker does not continue indefinitely on the old packet. L assigns the next ready milestone with a new starting SHA and updates the board. Finished early? Review a named test/log or prepare docs in owned paths; do not rewrite another worker's lane.

### Contract change protocol

Submit: current contract, failing concrete scenario, proposed change, affected schema/API/UI/tests, migration/backfill impact, estimate, urgency. L consults affected owners, assigns `CCR-###`, changes the canonical contract first, bumps ZE version if incompatible, and supplies all affected workers a delta packet. A implements schema/routine change, B adapter/tests, C UI/fixtures. No silent renaming of `AUTHORISED`, `ulb`, `permit_crew`, error codes or UUID namespaces.

### Broken main and recovery

Stop new merges; identify first bad milestone with a reproducible failure. Prefer a small owner fix; if release-critical and uncertain, L reverts the known merge with a normal reviewed `git revert -m 1 <MERGE_SHA>` on a repair branch. Never erase history or guess the merge SHA. A reviews migration compatibility before a revert: reverting code does not undo a migrated database. Restore a disposable demo DB from the previous tested backup or use an explicit forward repair migration. Preserve raw failure evidence.

Every handoff updates `docs/coordination/STATE.md`: current main SHA, contract version, last green test run, merged packets, blockers/owners, pending source decisions, demo reset state, next three tasks. This is the context snapshot for a restarted account.

## 5. Time plan and checkpoints

The friend's notes give 7 Oct 2026 14:00 to 8 Oct 14:00 IST; the official challenge PDF does not verify that schedule. Confirm locally. At the 7 Oct 17:03 IST planning checkpoint, approximately 20h57 remained on that assumption. Use actual remaining time when starting; do not pretend the original 24 hours still remain.

| Original elapsed hours | Work / checkpoint |
|---|---|
| 0–1 | L contracts; A/B/C inventory/setup |
| 1–2 | Dispatch, schema migration start, API schemas, UI wireframes |
| 2–3 | A1 tables/seed; B1 auth; C1 mock views |
| 3–4 | First small PRs, clean migration on second laptop |
| 4–5 | A G0/G1/receipt; B engine adapter; C denial dossier |
| 5–6 | Latest gas/configuration failures; incident skeleton |
| 6–7 | Scope mutex, exclusions, first race test |
| 7–8 | Recheck, stop latch, authentic role/worker acknowledgement |
| 8–9 | First live denial -> correction -> receipt -> stale denial |
| 9–10 | Mechanical completion, import gap and legitimate comparison |
| 10–11 | Incident transaction, duplicate/rollback evidence |
| 11–12 | Main integrated, no mock on golden path |
| 12–13 | LAB SQL examples and cursor transaction |
| 13–14 | RLS/pool/grants tests, restore test |
| 14–15 | Controlled baseline race and correctness comparison |
| 15–16 | Indexed query measurement; repeated run manifests |
| 16–17 | Full acceptance sweep, fix critical defects |
| 17–18 | Slide evidence, source/TRL review |
| 18–19 | Timed rehearsal on demo laptop |
| 19–20 | Offline run, backup recording, second operator rehearsal |
| 20–21 | Feature freeze and candidate tag |
| 21–22 | Clean-clone startup/reset verification |
| 22–23 | Only regression fixes; evidence package export |
| 23–24 | Final short rehearsal, submission buffer |

If starting around 17:00 IST, compress L0 to 30–45m using this package. Target A1/B1/C1 by20:00, first live integrated path by00:00, reconciliation/incident by03:00, verification/measurements by07:00, pitch and offline rehearsal by10:00, feature freeze by11:00, release verification by12:30. Reserve the final90m for submission and presentation. If any checkpoint slips, cut lower-priority features immediately. Arrange staggered rest; do not depend on all four humans being alert for an entire night. Ensure A and B overlap for the first transaction integration and all four overlap for the final rehearsal.

## 6. Cut order and contingency

Cut in this order: animations/maps -> custom admin screens -> live hardware/MQ streaming -> optional B0 baseline -> large synthetic scale -> extra analytics -> polished SSE (retain durable outbox and polling). Keep B1 or an explicitly labelled fair concurrency baseline, all six LAB examples, current-evidence decision/recheck, resource race, mechanical closure, anti-join gap, atomic incident, source limits and honest measured results.

If React integration fails, demonstrate the same real API through its documented interface plus SQL evidence; label the UI unfinished. If network fails, use local stack. If hardware fails, use signed deterministic simulated readings with SIMULATED visible; do not pretend they came from sensors. If API fails, the emergency fallback is a clearly labelled DB-only demonstration of genuine routines, not a completed end-to-end claim. If source applicability remains unresolved, keep real-city denial and the non-deployable educational fixture. If a benchmark gives no speedup, present correctness results and explain the measured trade-off.

Release checklist: fresh migration; guarded reset; correct actor logins; live non-mock path; default-deny; no stale permit start; race outcome; incident rollback and idempotency; legitimate job not flagged; six LAB transcripts; raw measurement files; offline images/dependencies; backup recording; presentation metadata contains no “world first”, “safe entry certified”, “paid compensation” or fabricated TRL claim. Tag the actual tested SHA `demo-v1` only when checks pass.
