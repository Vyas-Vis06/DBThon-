# Repository instruction template

L may adapt this into root CLAUDE.md and AGENTS.md after copying the reviewed package into docs/plan. These files provide context, not automatic communication between accounts. Fill verified commands after scaffold implementation; do not claim absent commands exist.

- Project: ZeroEntry, mechanisation-first municipal safety-evidence/accountability prototype.
- Contract: ZE-1.0 in docs/plan/SCHEMA_CONTRACT.md, ROUTINES_AND_INVARIANTS.md and API_CONTRACT.md. Read before code; no silent interface changes.
- Owners: L root/config/contracts/release; A db and tests/db; B backend, integration/benchmarks; C frontend/demo assets. No cross-owner edits without approval.
- PostgreSQL16 is authoritative. Alembic migrations owned by A; no ORM create_all or alternate SQLite engine.
- Operational writes use named DB commands, scope mutex first, narrow runtime grants. Do not replace transactional enforcement with UI checks.
- Real jurisdiction defaults deny/review. Successful entry is educational-only and prominently labelled. No claims of physical safety or legal permission.
- Latest unsafe/incomplete evidence is not filtered away; unknown fails closed. Old receipts must fail entry recheck. Preserve true late exits and stop/refusal history.
- All six LAB experiments need actual evidence. Synthetic benchmark results need raw files and run metadata; no invented speedups, lives saved or worldwide-first claim.
- Review data provenance and legal applicability separately. Reference compensation is not an award/payment. Missing completion evidence means review, not proven crime.
- No secrets or personal sensitive records in commits, logs or demo output. Use synthetic accounts and local development credentials.
- Work in a small milestone branch; run checks, fetch/merge main, retest, push and send runbook handoff. L alone merges main. No force push or destructive reset.
- Preserve unrelated working changes. Request CCR-### for cross-lane contract changes.
- Repetitive delegated tasks: GPT-6 Luna if available; do not use Astra for them.
- On restart read docs/coordination/STATE.md and exact current SHA. Report implemented/tested/planned separately.
- Expected scaffold targets to verify after implementation: scripts/dev.ps1 up/check/reset-demo; Python pytest; frontend build/typecheck; Alembic single head. L replaces this line with commands actually tested in the repository.
