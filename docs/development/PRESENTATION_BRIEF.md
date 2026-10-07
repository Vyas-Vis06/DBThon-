# ZeroEntry presentation brief

## Problem and domain

Municipal sewer work links complaints, contractors, machine attempts and exceptional human entry. A reviewer needs to know
whether the recorded safeguards supported admission and whether a resolved complaint has credible completion evidence.
ZeroEntry supplies a working PostgreSQL/FastAPI/browser prototype for six roles. All demonstrated records are synthetic.
Intended SDG contribution: safer occupational work (SDG 8) and accountable sanitation services (SDG 6). No observed reduction
in injury/deaths or field deployment is claimed.

## Existing approaches and limits

Digital permit tools already offer gas/competence gates, controlled lifecycles and audit trails. IntelliPERMIT and OPEREX
are relevant comparators. DIGIT/SUJOG offer municipal work/service and workforce records with reconciliation. Relational
division, anti-joins, transactions, row locks, RLS and hashes are established techniques. Public documentation does not prove
that competitors cannot configure our workflow. The [primary-source comparison](../POLICY_AND_PRIOR_ART.md) records the
documented capabilities and limits of the search.

## Proposed approach

The database owns permit admission, evidence freshness, crew/gear invariants and financial consequences. The API identifies
the caller, supplies scoped context and returns the SQL explanation. An immutable decision artifact preserves original
evidence and policy revisions. Current reading/dependency changes and periodic sweeps stop permits, while exits preserve
what the operator reports and retain violations.

SE1/SE2 begin from an explicit expected population. Resolution exemptions and evidence deadlines distinguish legitimate
absence from an evidence gap. Machine finalization uses its own receipt time. Persisted alerts need human review, and a
dismissal releases only that alert's invoice holds. Payment and source creation use a tested lock protocol.

## Defensible contribution

An open, reproducibly tested municipal integration links default-deny permits to time-aware evidence gaps, human review
and source-specific financial holds. The study includes adversarial raw-SQL mutations and synchronized transaction races,
rather than relying on a UI checkbox. Policy/source snapshots explain the recorded decision over time.

This is integration differentiation. We make no claim of a new relational algorithm, worldwide priority, patentability,
complete executable law, independently authenticated instruments or owner-resistant evidence.

## Measurable validation

The main [M6 results](../EVALUATION_RESULTS.md) cover ten labeled complaint categories, all 18 invalid-write probes,
late-evidence invoice holds and indexed/materialized comparisons. The supplementary
[evaluation results](../evaluation/RESULTS.md) report synthetic evidence-gap precision/recall, query latency and persisted
scan cost at 1k/10k/100k complaints. Raw samples, exact baseline SQL, data categories, source hashes and EXPLAIN plans are
in [results.json](../evaluation/results.json). The baseline deliberately omits grace, exemptions and outcome receipt time.
It answers a simpler question, so query timing does not establish equal-task speedup. Synthetic labels establish behavior
on those cases, not field accuracy. The full real-PostgreSQL regression suite separately covers gates, roles and race orders.

## Demonstration order

1. Show the draft's named failed clauses. Complete crew/gear/readings and authorize.
2. Show the original authorization artifact, policy/source classifications and digest.
3. Log an open entry. Insert a synthetic unsafe BOTTOM reading. Show ABORTED status and durable safety evidence.
4. Record the exit after stop. Show that permission and physical history are separate facts.
5. Review a late/no-job evidence alert. Dismiss one and show only its hold releases. Rescan: no duplicate alert.
6. Show the evaluation table and one synchronized payment/hold regression. State the synthetic-data boundary.

Use [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for startup and the short narrative. For a terminal fallback run
`pytest -q tests/db/test_temporal_evidence_and_invoice_races.py tests/db/test_policy_provenance.py` and the evaluation script.

## Likely questions

**Can the database prove real safety?** It checks recorded evidence. Physical measurement, rescue response and equipment
use require field controls and independently authenticated records.

**Why PostgreSQL?** Foreign keys, exclusion constraints, trigger-owned transitions and real transaction locks express the
invariants close to the data. The thin API shares those rules across UI and SQL clients.

**Is missing evidence proof of entry?** It supports a suspicion that a human reviews. Exemptions, grace and late receipts
make that population explicit and reduce the simplistic baseline's synthetic errors.

**Is the legal model complete?** Selected sources are classified and cited. Gear applicability, local waiver authority,
severity-sensitive compensation and physical operating procedures still require domain review.

**What remains?** Real authenticated instruments/registry integration, external notification delivery and anchoring,
ULB-specific engineer/supervisor scope, headless browser coverage, multilingual/mobile operator testing and a validated pilot.
