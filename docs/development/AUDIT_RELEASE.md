# Audit implementation and handoff

The audited foundation was commit `e8632699e85c4167940194649444d45ff5537621`. It already implemented the central
database design: mechanisation-first jobs, written waivers, a database entry gate, crew/gear division, gas checks,
entry intervals, atomic incident consequences, SE1/SE2 evidence-gap detection, source-linked invoice holds,
authentication, RBAC, RLS and a working UI. Its original 509-test suite passed locally. This release extends that
foundation through migrations 0012–0014; migrations 0001–0010 are unchanged.

## Audit findings and implemented corrections

| Finding | Resulting behavior | Main regression evidence |
|---|---|---|
| Updating a crew/gear row's permit ID could move it out of an authorized permit | Parent identities are immutable, so frozen evidence cannot be moved to a draft | `test_safety_lifecycle.py` |
| A stopped permit or excessive duration could prevent recording a real exit | Open intervals remain closable after stop. The reported exit and server receipt are retained alongside immutable violations | `test_safety_lifecycle.py`, `test_workflow.py` |
| Authorization could survive later unsafe gas or expired dependencies | Relevant evidence changes and new admission revalidate authorization; periodic sweeps detect time-based expiry/overstay | `test_safety_lifecycle.py`, `test_maintenance.py` |
| A finalized machine outcome reused the deployment's original receipt | Finalization has its own server receipt. Late finalization cannot erase the SE1 evidence gap before the first scan | `test_temporal_evidence_and_invoice_races.py`, `test_temporal_evidence.py` |
| Payment/approval or invoice creation could race with alert/incident holds | Common complaint and invoice locks serialize both orders; stale snapshot isolation is refused with `40001` | `test_temporal_evidence_and_invoice_races.py`, `test_integration_adversarial.py` |
| Checks after lock waits could use the transaction's stale start time | Runtime authorization samples a fresh server clock after locks, including raw runtime updates | `test_integration_adversarial.py` |
| Active policy rows had no revision explanation and ordinary metadata was editable | Only values are runtime-editable. Each change records a reason, actor, server time and revision | `test_policy_provenance.py` |
| Later changes could obscure why an authorization passed | A successful transition saves the exact configured checks, source classifications, revisions and relevant evidence with a DB-computed digest | `test_policy_provenance.py`, `test_decision_history_api.py` |
| A definer lock helper was directly executable by runtime users | Private helpers have explicit revoked execution privileges; intended trigger paths remain usable | `test_safety_lifecycle.py`, `test_integration_adversarial.py` |
| The built wheel omitted the HTML shell | Installed-wheel smoke checks serve the shell, JavaScript and CSS | `scripts/check_wheel.py` |

The rest interval is now 30 minutes after a 90-minute stretch, using the cited 2013 Rules. Source classification corrects
the former 15-minute statutory claim and distinguishes law, court directions, guidance and product choices.
See [POLICY_AND_PRIOR_ART.md](../POLICY_AND_PRIOR_ART.md) for the primary-source review and its interpretation limits.

## Relationship to the earlier schema

The earlier SQL-first design's core path is retained: complaint → mechanized job or waived permit → recorded completion
evidence → reviewable missing-evidence alert → source-specific financial hold. Vyas had already built most of that
architecture, plus a much fuller authenticated application and documentation set. Rebuilding these tables would add
little value under the presentation deadline.

This release concentrates the additional work on continuing authorization, truthful temporal evidence, concurrency,
policy provenance, preserved decision explanations and measured evaluation. It adds five tables and keeps the API
thin. A typed reading is still an assertion, and an evidence-gap alert still requires review.

## Presentation evidence

The [demo script](DEMO_SCRIPT.md) covers denial, complete authorization, a saved decision, unsafe gas stop and exit after
stop. The new tabs show original authorisation, safety history and policy revisions. The authenticated local
`scripts/simulate_gas.py` feed was run against a fresh synthetic demo cluster. Browser verification confirmed the exit
after stop, and an API check confirmed that a subsequent policy revision left the original decision bytes unchanged.
The UI is manually verified; an automated browser suite remains a backlog item.

The [evaluation results](../evaluation/RESULTS.md) and raw JSON reproduce six labeled synthetic SE1 categories at
1,000, 10,000 and 100,000 complaints. They include confusion matrices, timings, row counts, query plans and source
fingerprints. They measure evidence-gap semantics, not physical entry detection or field safety. Do not claim a speedup
over an equal-task baseline: the simple baseline deliberately omits temporal/applicability semantics.

Use the [presentation brief](PRESENTATION_BRIEF.md) for the problem, prior art, contribution and judge questions.
The defensible contribution is the integration and tested behavior; e-permits, continuous gas monitoring and broad
claims of database safety are established prior art.

## Remaining work

The presentation prototype is not a production safety certification. The next work is a domain/legal pilot review,
task-specific equipment applicability, ULB scope, independently authenticated physical instruments, field alert
validation, external artifact signing/retention, notifications, production operations and automated browser coverage.
The new revision history starts at migration 0014 and is not a retroactive rule-replay engine. These items are tracked
in [ROADMAP.md](../../ROADMAP.md).
