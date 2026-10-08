# Copy-paste packet: C — visible workflow, demonstration and pitch

You are Worker C in the four-person ZeroEntry DBMS hackathon team. L owns architecture/root/release and source review, A PostgreSQL, B API/auth/integration tests, you React UI, accessible workflow, demo assets and presentation evidence. Start from the actual repository SHA supplied by L; preserve existing changes. No automatic cross-account messaging or fourth paid account is assumed. If repetitive tasks are delegated, use GPT-6 Luna when available, not Astra.

Read MASTER_PLAN.md, API_CONTRACT.md, DEMO_AND_PITCH.md, SYLLABUS_AND_RUBRIC.md, VALIDATION_PLAN.md and IMPLEMENTATION_RUNBOOK.md. Consult schema/routines for exact meanings. ZE-1.0 names and fixtures are frozen. Do not invent backend endpoints, gate thresholds, receipt states or benchmark values. Submit a contract-change request if a missing field materially blocks the UI.

Context: ZeroEntry links municipal work, actual workers, current evidence and payment accountability in a relational workflow. The meaningful gap is evidence consistency and actual-vs-assigned participation, not the alleged absence of permit blocking. Real-city manual activity is denied/review-only; the successful entry demonstration is a clearly labelled educational simulation. No “safe to enter”, “death prevented”, “fraud confirmed”, “compensation paid” or “world first” labels. The prototype can block inconsistent software decisions, not physical entry.

Owned paths: frontend (including its package.json and lockfile), docs/evidence/ui. L owns final source/legal decisions; B owns scripts/demo.ps1. Do not edit SQL, API or root build files. Use React/Vite/TypeScript with one typed API adapter and centralized request/error handling. Currency is formatted from decimal strings; timestamps display Asia/Kolkata with explicit zone. Runtime data originates in API responses, not a second client-side rule engine.

### C1 — complete mock-compatible journey

Build four meaningful views, not a giant admin portal:

1. Workboard: complaint/site, job activity, mechanism-first routing, jurisdiction/status, mechanical evidence and next action. Mechanical completion has no fake human permit.
2. Permit dossier: assigned vs acknowledged actual crew, personal vs shared serial gear, three-depth coherent samples, calibration/source, readiness, gate failures, receipt version/expiry and begin/exit/stop actions. Always show policy mode and source provenance.
3. Accountability: imported completed claims, matched job, real completion evidence, review/hold reason, legitimate comparison and incident with multiple/no-registry victims. Reference amount, pending review, award and paid are different fields; only pending workflow implemented.
4. Judge evidence: ER/schema link, six LAB demonstrations, baseline/ZE test runs and measured charts, source/limitation register, query-plan and concurrency traces. “Not yet measured” until raw result manifests exist.

Use API_CONTRACT examples as typed fixtures in a mock adapter, visibly marked MOCK. Model empty/loading/error/stale/refused states, not just happy screens. Common top banner: REAL POLICY: DENIED/REVIEW or EDUCATIONAL SIMULATION — NOT DEPLOYABLE. Gate status must use text/icons as well as color. Missing data is UNKNOWN/INCOMPLETE, never green. Distinguish preview from committed certificate. Render exact explanatory failure codes and affected worker/item/depth with understandable labels.

Acceptance: frontend typecheck and production build, navigation through four views, mock denial/correction/stale/incident cases, keyboard-accessible controls and readable projector-scale layout. Commit a small C1 PR while database work proceeds.

### C2 — live API integration

Switch through one adapter to B's live endpoints after B2; no hardcoded success or fallback-to-mock on a live server error. Failed requests stay failed with a recoverable message. Authorization must display server denial even when the browser had previously shown green evidence. Begin-entry uses exact certificate ID; a stale or expired result prompts refresh, not client-generated approval. Server expiry governs correctness; browser countdown is advisory.

Use fetch-based authenticated SSE supplied by B, or authorized polling fallback. Refresh dossier after relevant event and display connection/staleness state. An absent notification cannot mean the permit remains valid. Support multiple participants, one participant's missing gear, site equipment, no-permit incident and worker stop/refusal without requiring a fabricated registry entry. Keep protective action available to the worker role; do not let supervisor editing erase refusal history.

Acceptance: live mechanical closure; EDU three-failure diagnosis/correction and committed receipt; newer unsafe data causes stop and old-receipt rejection; one imported evidence gap and legitimate comparison; incident pending case state. Verify at least one session isolation failure is explained, not hidden. Record screenshots with run/commit metadata and source mode.

### C3 — demonstration, evaluation and pitch

Prepare the3-minute golden path and longer technical backup from DEMO_AND_PITCH, plus slide source covering problem, documented existing gap, contribution, architecture/ER, six LAB integration, real demo, controlled measurements, SDG and limits/TRL. Use a concise restrained interface optimized for explaining the relational mechanism. Maps, animations, streaming polish and custom admin CRUD are first to cut.

Charts must read B's actual raw/exported results; if data is absent label NOT YET MEASURED, no invented improvement. Show sample size, synthetic baseline scope and units. Credit existing government/vendor functionality accurately. Describe social relevance (worker safety/accountability), not measured reductions in deaths. Current package is planning; do not claim TRL4 until integrated lab evidence exists, or TRL5 from a sensor on a desk.

Record a fallback screen capture of the real tested workflow and label its date/commit; screenshots must not masquerade as live execution. Help all teammates rehearse their own feature and SQL explanation. Export final assets locally, with no runtime network dependency. Share production build result, test evidence, demo recording path, exact commit, omissions and remaining API blockers. Follow the runbook PR/handoff process; L merges. Do not silently change backend semantics to make a prettier demo.
