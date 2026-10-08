# Worker A: integrated database implementation

Execution model: GPT-6 Luna, three workers sharing the selected clone, parent integration/review. Read AGENTS/CLAUDE, PROJECT_SPEC, ROADMAP, latest DEV_LOG, INTEGRATION_CONTRACT, REPOSITORY_REVIEW, all docs/plan design/research/syllabus/validation contracts and the original three prompts before coding. The integration contract adapts them to actual code and is binding. Inspect the matching SQL and test before each change.

Own migration0015 down0014, models.py, seed.py/database/seeds, database queries, new tests/db and factories. B alone owns0016 down0015 and all backend; C owns web/browser. Parent owns root/docs/generation/branch/commits. Communicate exact schema/functions early. Send B/C normalized response fields rather than asking them to infer them from your code. Never edit historical migrations or remove regression assertions to mask failures.

Preserve bigint IDs/public schema, ENGINEER, embeddedPG16, fixed IST helpers and integer-range GiST technique, terminal ABORTED/new-permit recovery, successful original snapshots, temporal final-outcome evidence and invoice source histories. Extend these in order:

1. Policy mode defaults REVIEW_REQUIRED; real DENIED/unknown fail before all green evidence. Positive fixtures explicitly EDUCATIONAL and labelled. Waiver cannot override eligibility.
2. Own-worker acknowledgement and actual crew; personal vs site requirements; physical serial assets and all-crew/equipment reservation conflicts with actual two-session proof. Standby cannot serve simultaneous active operations. Retain occupied resources until true final exit even after abort.
3. Seven readiness kinds with latest/expiry/provenance; incomplete and adverse gas remains evidence and fails closed. Stop must commit with evidence rather than roll back the bad observation.
4. Evidence revision, committed negative/positive receipt and earliest expiry; existing original successful decision unchanged; optional supplied receipt rejected when stale; raw admission still checks current evidence.
5. Completion claim/reference/projection preserving existing complaint-no-job expected population and late review. Show equality and explicit time-driven grace refresh; current gas aging alone cannot rewrite valid historical completion.
6. Every new table model/grant/RLS and real test; B sends his six added model shapes. Provide all six LAB demonstrations including cursor lifecycle; no gratuitous second database or generic rule compiler.

Use the existing isolated PG harness and .venv. Run focused tests while schema stabilizes; coordinate whole-suite runs with parent. Report actual commands, observed results, new interfaces, changed files, omissions and any blocking assumption. No worker commit/push. Use apply_patch, with the approved CLI fallback from INTEGRATION_CONTRACT if the default sandbox helper fails. Do not use Astra or spawn extra workers.
