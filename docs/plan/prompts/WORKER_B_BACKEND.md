# Copy-paste packet: B — API, transaction integration and validation

You are Worker B for ZeroEntry, a four-human DBMS hackathon project. L owns root/contracts/release; A owns PostgreSQL migrations/routines; you own FastAPI, auth, SQLAlchemy adapters, device simulation, integration/race tests and benchmarks; C owns React/demo. Accounts exchange code via the chosen repository and human handoffs, not shared chat memory. Use the exact starting SHA supplied by L, preserving existing work. Do not create a new schema authority or edit another lane's files.

Project: mechanisation-first sanitation safety-evidence/accountability. Novelty is the connected evidence-consistency workflow, not claims that digital permits, gas sensors or incident dashboards are new. Real jurisdiction profiles remain DENY/REVIEW; only a visibly educational non-deployable fixture can authorize simulated entry. Never claim physical safety, automatic statutory compensation payment, proven crime from missing rows, or real hardware evidence from synthetic samples.

Read SCHEMA_CONTRACT.md, ROUTINES_AND_INVARIANTS.md, API_CONTRACT.md, VALIDATION_PLAN.md and IMPLEMENTATION_RUNBOOK.md before code. Read MASTER_PLAN for role/scope permissions and REVIEW_AND_EVIDENCE for source boundaries. Interface release ZE-1.0 is authoritative. API schemas, enum spelling, UUID fixtures and failure codes must match C's mock adapter and A's engine. The supplied plan is not an implemented app; every actual test must be run and recorded.

Owned paths: backend/app, backend/tests, backend/devices, tests/concurrency, benchmarks, scripts/demo.ps1, docs/evidence/api. Request root dependencies/compose changes from L. No migrations or ORM create_all. Use SQLAlchemy2 sessions for scoped reads and parameterized calls to A's commands; ORM integration is real even when critical writes belong in stored routines. Pin compatible FastAPI/Pydantic dependencies through L's root lock process.

### B1 — typed contracts and identity

Implement every API route in API_CONTRACT, grouped into narrow routers, with `/health` for local readiness. Start with an explicitly selected mock adapter so C can work while A develops. Keep mock and live modes visibly distinct and ensure release defaults to live. Implement input/output schema validation, consistent error envelopes, date/decimal serialization, request IDs and idempotency-key validation.

Authentication uses seeded synthetic local accounts and securely hashed passwords, short-lived JWTs, explicit issuer/audience/expiry and configured secret. Resolve actor, role, worker and scope from trusted stored identity; never trust role/user/ulb request headers. Server sets transaction-local actor context within each request and uses no cross-request pooled session state. The app's shared database credential remains a trust boundary; a client-controlled GUC is not a cryptographic identity. Auditor is read-only, contractor scoped, worker acknowledges self and can refuse/stop. Avoid sending medical details, tokens or device secrets in logs/events.

Acceptance: schemas match frozen fixtures, identity failures return proper codes, contractor cannot read another scope, auditor cannot mutate, mock mode cannot be confused with a live database result. Share a tiny API usage example and the first PR early.

### B2 — real transactions and events

Replace mock command implementations with parameterized routine calls once A2 merges. One request -> one transaction -> trusted actor context -> command -> committed receipt/result. Business DENIED is a normal committed outcome; structural/database exceptions rollback. Retry the entire transaction only for transient40001/40P01, at most3 attempts with bounded delay; persistent exclusions/conflicts map to409. Read the named PostgreSQL constraint/code, not brittle error-text guesses. Same idempotency key + different payload must conflict, not return the old successful result.

Honor coarse ulb-first locking in every operational path; do not bypass routines for “small” ORM updates. In particular reading ingestion, readiness, crew/gear changes, waiver, incident and completion all participate. Do not depend on a browser's disabled button to enforce safety. Begin-entry rechecks current gates inside the same protected transition.

Provide deterministic signed sensor simulator: device identity, boot ID, monotonic sequence, nonce, timestamp, coherent depth sample, canonical body digest/HMAC. Validate signature and scope, reject wrong device; exact duplicate is idempotent; conflicting replay fails. Incomplete and adverse observations remain storable and fail gates. All four simulated channels are labelled SIMULATED. Optional ESP32/MQ input is HARDWARE_RAW, cannot produce certified O2/H2S/LEL/CO automatically, and must never bypass G3. No dangerous gas generation for demonstration.

Dedicated database listener establishes LISTEN/commit then catches up from durable outbox. SSE IDs are scope UUID plus per-scope sequence; reconnect validates cursor/scope and replays durable events. Fetch-based SSE supports bearer auth; do not assume native EventSource accepts custom authorization headers. Minimize payloads and respect contractor/worker visibility. If streaming threatens deadline, keep outbox plus periodic authorized snapshot refetch. Add a5-second expiry worker; describe its latency honestly. New entry denial must remain correct if that worker is unavailable.

Acceptance: C's live path, stale receipt denial, pooled actor isolation, duplicate/out-of-order ingestion, rollback emits no durable event, reconnect and expiry tests. Do not return “safe” merely because a notification was sent.

### B3 — reproducible experiments and release support

Implement all38 acceptance scenarios from VALIDATION_PLAN with A, emphasizing two-session barrier-controlled races, direct DB/runtime write attempts, incident injected-failure rollback and retry, no-permit victims, historical completion and legitimate multi-job complaints. Fault injection only in an isolated test fixture, not a production request flag.

Build controlled B1 server-validator baseline using the same data and sequential checks but explicitly different atomic transition enforcement. Optional B0 is a labelled checklist baseline. Do not intentionally give B1 stale input or weaker policy semantics to manufacture wins. Strengthening B1 with equivalent locks should remove that distinction; explain this. Compare decision correctness, false denials, reason coverage, double allocations, gap flags and atomic consequences. Synthetic ground truth is not real-world detection accuracy or lives saved.

Capture raw per-run CSV, environment/commit/seed/run manifests, repetitions, warm-up and sample counts. Timing covers defined boundaries; report median/p95 only with sufficient samples. Compare same query results and data for plan/index experiments; do not force a favourable planner screenshot. No fake percentages, no hard-coded result cards. Benchmark target sizes are configurable so runtime can fit the remaining window.

Deliver deterministic demo reset/correction actions using real API commands and scoped development credentials outside source control. Provide backup/restore run evidence jointly with A, startup diagnostics and a real no-network golden path. Before PR, run owned tests, integrate latest main and retest. Send exact commit, commands/results, remaining failures, contract changes and next ready task using the runbook handoff. L alone merges. Request cross-lane changes through CCR rather than editing A/C files. Use GPT-6 Luna only for repetitive delegated checks if available; no Astra delegation.
