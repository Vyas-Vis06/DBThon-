# ZE2 demonstration and rehearsal

## Prepare before presenting

Use the repository virtual environment and a dedicated synthetic directory. Do not reset a teammate's database.

```powershell
python scripts/dev.py --data-dir .pgdata/dbthon-ze2 --port 8000
```

Keep the generated local password privately. In a second terminal, while that server runs:

```powershell
python scripts/prepare_demo.py
```

Enter the same password at the hidden prompt. The helper uses the normal authenticated API as the educational engineer,
supervisor and four worker accounts. It creates one new DRAFT, synthetic inspected serial assets, seven attributed typed
readiness records and three explicitly SIMULATED gas observations. It leaves the fourth worker's acknowledgement missing.
It never changes real policy, uses owner SQL or automatically authorizes a permit. Its JSON gives the IDs to use below.
Each invocation creates a separate rehearsal, not an idempotent reset. No real inspection or field measurement occurred.

Gas expires under the configured freshness rule; prepare shortly before the demonstration and refresh all three samples
if necessary. Readiness expires after one hour. Outside the configured daylight hours, an ADMIN may widen only the
product daylight proxy for this synthetic rehearsal with an explicit audit reason. Never change a real scope from
REVIEW_REQUIRED/DENIED to EDUCATIONAL to obtain a green decision. All positive decisions are software simulations.

Open separate browser profiles/private windows for `supervisor@zeroentry.example` (real-scope denial),
`edu_supervisor@zeroentry.example` (educational workflow), `edu_worker_4@zeroentry.example` (own acknowledgement),
and `engineer@zeroentry.example` (real-scope evidence review). They use the local generated seed password.

## Four-to-five-minute judge story

1. **Problem and domain (20 seconds).** Sanitation safety and municipal work-evidence accountability. Explain that
   missing records are a reason to review, not proof that someone entered or committed misconduct.
2. **Database design (30 seconds).** Show the ER diagram, composite crew key, personal versus shared serial inventory,
   normalized incident/victim/assessment rows and the source-linked holds. Table count is not the novelty claim.
3. **Real scope fails closed (25 seconds).** As the ordinary supervisor, open the seeded DRAFT on CHN-ADY-010 and ask
   for authorization. Explain the policy eligibility denial; a waiver and more PPE cannot override it. Show the retained
   negative receipt and classified legal/guidance/product sources. Do not quote an old fixed clause count.
4. **Actual participation (50 seconds).** As the educational supervisor, open the helper's permit ID. Ask for
   authorization: the unacknowledged fourth assignment denies it. In the worker's window open the same permit and
   acknowledge only their own participation. Return to the supervisor, refresh, and request authorization again.
   If another clause fails, show its real reason rather than hiding it. Inspect the positive receipt's revision and
   earliest expiry alongside the original authorization snapshot.
5. **Continuing safety and truthful exit (40 seconds).** Record a simulated open entry for an entrant. Submit a new
   BOTTOM gas reading with H2S 1000 and all other channels supplied, clearly marked SIMULATED. Show retained adverse
   evidence, ABORTED permission and the still-open person record. Record the actual simulated exit; stop does not erase
   occupancy or block an honest exit. Recovery uses a new permit, never reopening ABORTED.
6. **Completion evidence (40 seconds).** In Completion review, import a synthetic external claim using a stable external
   ID, status COMPLETED and a past/current time. It stays UNMATCHED until explicit reviewer linkage. Show a seeded
   complaint with no job and the separate Shadow entries screen. Explain grace, late-evidence human review and why
   current gas aging does not invalidate a properly documented historical completion.
7. **Unregistered victims (30 seconds).** In Incident reports record two aliases, no registered worker/job/permit, one
   FATAL and one INJURY. Show two pending internal assessments and zero paid. The browser test proves a dropped-response
   retry creates only one report; do not describe a second click after a successful response as that same-key retry.
8. **Proof and novelty (25 seconds).** Show Judge evidence and the current release report. Explain the bounded
   composition of actual participation, fresh evidence, shared resources, revision-bound admission, closure review and
   atomic unregistered intake. Electronic permits, triggers, gas checks and worker registries are not individually new.

## SQL and concurrency backup demonstrations

These commands target the same isolated directory as the server above:

```powershell
python scripts/run_sql.py database/queries/04_division_and_anti_join.sql --data-dir .pgdata/dbthon-ze2
python scripts/run_sql.py database/queries/06_transactions.sql --data-dir .pgdata/dbthon-ze2
python scripts/run_sql.py database/queries/08_cursor_and_assertion_lab.sql --data-dir .pgdata/dbthon-ze2
```

The first shows division/absence, the second real procedure rollback, and the third explicit OPEN/FETCH/CLOSE plus a
controlled cross-row constraint-trigger/exception exercise. PostgreSQL 16 has no CREATE ASSERTION; PL/pgSQL is its
runtime language, not Oracle PL/SQL. The original query assertions use the fresh seeded world; a demonstration that
adds new records naturally changes its counts. Do not treat those post-rehearsal counts as a regression failure.

For a local synthetic feed, after all acknowledgement/readiness requirements are satisfied:

```powershell
python scripts/simulate_gas.py --email edu_supervisor@zeroentry.example --permit PERMIT_ID --detector DETECTOR_ID --unsafe-after 2
```

Replace IDs with the helper's output. The feed uses software observations and stops on a real API denial; it is not
authenticated physical instrumentation. Shared-person/asset concurrency, receipt aging, raw-write refusal and financial
serialization are reproducible regression tests; show their named test evidence when a live race would take too long.

## Honest closing statement

This is a laboratory prototype, self-assessed TRL4. Synthetic tests prove stored-state behavior under stated assumptions,
not legal applicability, real gas truth, physical prevention, field detection accuracy, paid compensation or lives saved.
Use the current source-matching report; historical benchmark timings do not automatically apply to a new revision.
