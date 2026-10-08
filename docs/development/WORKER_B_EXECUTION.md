# Worker B: integrated backend implementation

Execution model: GPT-6 Luna, shared selected clone with A database/C web and parent review. Read all instructions and complete system design described in INTEGRATION_CONTRACT, including original three worker prompts. Adopt the existing implementation's stronger sessions, schema, UI and financial histories; the historical plan is not a rewrite order.

Own backend except models.py/seed.py/web, new API/integration tests and scripts; migration0016 down0015 only for dedup/outbox/standalone incident/report tables. A owns0015, models and seeds. Parent owns root/docs/generated output, branch and commits. Freeze exact fields to A and JSON to C before implementing consumers.

1. Preserve revocable opaque sessions, cookie/CSRF, stored actor identity, transaction-local scope and commit-before-response. Do not duplicate SQL gate rules in Python. Any optional retry must restart the full transaction.
2. Transactional command dedup: actor+operation+key, canonical body digest, stored HTTP status/JSON, concurrent lock, identical replay returns same IDs, changed body409. Required new command keys are UUIDs; legacy clients retain compatible behavior.
3. Durable per-scope ordered outbox; actor-filtered bounded replay/polling, rollback emits no event, reconnect catches up. Counter locking must address commit order; no sensitive victim/private rows in general event payloads.
4. New own-worker acknowledgement, sitegear/readiness/receipt endpoints plus policy/revision/provenance dossier fields from A. Stale receipt and evidence recheck remain DB-authoritative.
5. Standalone multi-victim incident reports: optional registered links, attributed private site, pending reference cases, zero paid, scoped rows, atomic procedure and dedup. Preserve existing legacy external-payment recording and invoice hold sources; internal restrictions are not legal orders.
6. Completion claim/reconciliation endpoints retaining complaint-level expected population and human review, not fabricated internal completion. Judge evidence comes from actual metadata/fingerprints; stale metrics are historical or NOT_YET_MEASURED.
7. Safe deterministic sensor simulator with provenance; signed/raw hardware only after core integration. HMAC proves signed bytes/key possession, not measurement truth.

Test same-key concurrency, changed body, failed transaction/rollback, multiple/unknown victims, scope boundaries, event replay and ordinary successful API paths. Test meaningful committed state, not only response shape. Use .venv and isolated PostgreSQL. Do not edit A/C paths or old migrations, commit/push or introduce undocumented dependency. Follow apply_patch fallback in INTEGRATION_CONTRACT. Report concrete progress and actual execution results; parent runs final full suite. No Astra or additional agents.
