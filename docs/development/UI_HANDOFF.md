# Browser UI handoff

The existing no-build, same-origin ES-module UI remains in place. User text is rendered through DOM text nodes, no third-party scripts/styles are loaded, and the shell's strict CSP is unchanged. New screens are `incident_reports`, `completion_review`, and `judge_evidence`; the incident intake works without a linked permit or registered worker. Permit workflow surfaces policy provenance, acknowledgement, typed readiness, serial personal/site gear, incomplete gas channels, and server-issued decision receipts. Positive permit decisions are described only as educational simulations when the server marks the scope educational. A visible connection state reports event polling health; polling is incremental and never makes an authorization decision.

Mutation retries use a stable session-scoped idempotency key for the same method, route, and canonical body. A successful response clears that key; a changed body gets a new key. The standalone incident form retains victim aliases and keys on an error so the same report can be safely submitted again after a lost response.

## Browser verification

Run with the repository virtual environment and an available Chromium installation:

```powershell
.venv/Scripts/python.exe -m pytest -m browser tests/browser -q
```

The browser suite starts the real FastAPI app against pytest's disposable PostgreSQL database. Latest result: **3 passed** (`tests/browser/test_workflows.py`; 26.23s), with JavaScript syntax checks passing for every static ES module. Coverage includes:

- Login under a real `DENIED` policy, request and display of a committed denial receipt, then submit blank gas channels and verify the stored values remain `null`/UNKNOWN.
- Submit a standalone two-victim report without a linked worker or permit; the first response is deliberately dropped after server commit. The next submit must replay the identical body and idempotency key, with no duplicate cases. A second client commits a report and the screen refreshes through event polling. Completion review and judge evidence render from live routes; logout stops polling and worker navigation remains role-scoped.
- In an explicit educational fixture, record an adverse latest gas observation, verify the permit enters terminal `ABORTED`, and record a truthful exit afterward.

The denial-receipt panel screenshot is preserved in [denied-permit-receipt.png](../evidence/screenshots/denied-permit-receipt.png). The first test stubs only its otherwise-idle event poll to keep the receipt screen stable; cross-client polling behavior is exercised separately in the incident workflow.

The gas channel fields are optional in the UI: omitted values remain unknown, rather than being silently coerced to zero. A deterministic sample-fill action is available only in an educational scope and explicitly selects `SIMULATED`; typed observations remain attributed as typed. The current test suite does not claim the absence of unknown channels is a pass.

Completion claims/reconciliation and judge evidence use the integrated API; the evidence page presents `NOT_YET_MEASURED` when no source-fingerprinted current result exists. The exit time defaults one minute ahead at minute boundaries to avoid submitting an exit earlier than a recently opened entry. Browser status and countdowns remain advisory; only committed server/database decisions control authorization.
