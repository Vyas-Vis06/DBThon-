# ZeroEntry: reviewed implementation package

**Repository adaptation:** this is the original ZE-1.0 planning reference. The implemented repository has stronger existing bigint identities, opaque sessions, no-build UI, complaint-level late-evidence review and source-specific financial holds. Current implementation work follows [INTEGRATION_CONTRACT](../development/INTEGRATION_CONTRACT.md) and [REPOSITORY_REVIEW](../development/REPOSITORY_REVIEW.md). Preserve those existing choices; do not perform the earlier UUID/React/JWT/Docker rebuild merely to match this historical design. The three current worker packets are [database](../development/WORKER_A_EXECUTION.md), [backend](../development/WORKER_B_EXECUTION.md) and [frontend](../development/WORKER_C_EXECUTION.md).

Prepared7 October2026. Contract release **ZE-1.0**. This package executes the planning assignment in `astra prompt.txt`, combines the strongest aspects of Friend_progress, corrects unsupported claims, and supplies a complete four-person implementation procedure. It is not a finished or benchmarked application.

## Start here

1. Read [MASTER_PLAN.md](MASTER_PLAN.md) for scope, architecture and the selected contribution.
2. Read [IMPLEMENTATION_RUNBOOK.md](IMPLEMENTATION_RUNBOOK.md) for immediate actions, setup, time plan and exactly what happens when a worker finishes and wants to push.
3. Give each account its own prompt below, the frozen contracts and the actual repository baseline commit.

| Person | Copy-paste prompt | Ownership |
|---|---|---|
|L|[Lead coordinator](prompts/LEAD_COORDINATOR.md)|Contracts, sources, root scaffold, integration and release|
|A|[Database worker](prompts/WORKER_A_DATABASE.md)|PostgreSQL schema/engine and LAB evidence|
|B|[Backend worker](prompts/WORKER_B_BACKEND.md)|FastAPI/auth, ingestion, tests and measurements|
|C|[Frontend worker](prompts/WORKER_C_FRONTEND.md)|Four views, live demo and presentation|

The three available subscriptions serve three coding lanes; the fourth person coordinates. Humans and versioned Git files carry messages, not automatic shared account memory. Repetitive delegated extraction/checks in preparing this package used GPT-6 Luna, not Astra. The packets are provider-independent and do not assume additional subscription entitlements.

## Important conclusions

- Preserve the domain and mechanisation-first approach. Strengthen actual participation, current evidence, exclusive resources, expiring receipts/rechecks and closure/incident accountability as one contribution.
- Retain the friend's event-triggered invalidation, incremental ledger, race demonstration, non-gas readiness and no-permit incident insights. Narrow overclaims and define their transaction boundaries.
- The official challenge has **eight rubric rows totaling30 marks**, including2 for TRL & Demonstration. The old28-mark photo discrepancy is resolved. The23-item proposal checklist is a team target, not a verified official minimum.
- Integrate all six LAB experiments. Map every theory topic honestly to implementation, controlled demonstration, explanation or deferral.
- PostgreSQL16 is the selected engine. There are37 canonical relations and one migration owner; four user workflows avoid37 separate CRUD screens.
- The Rules catalogue contains44 equipment items. Applicable personal/site requirements are separate; the educational subset is not a certified operational checklist.
- Real activity remains DENY/REVIEW; successful entry is a non-deployable educational fixture. No physical safety certification, legal permission, payment or prevented-death claim follows from this prototype.

## All16 requested outputs

|#|Deliverable|Artifact|
|---:|---|---|
|1|Assessment, corrections and strongest contribution|[Master plan](MASTER_PLAN.md)|
|2|Prior work, correction/source/legal registers, verification queue|[Review and evidence](REVIEW_AND_EVIDENCE.md)|
|3|Core scope, extensions and deferrals|[Master plan](MASTER_PLAN.md)|
|4|Architecture/workflow, permissions and trust|[Master plan](MASTER_PLAN.md), [routines](ROUTINES_AND_INVARIANTS.md)|
|5|ER,37-relation dictionary, keys/dependencies and normalization|[Schema contract](SCHEMA_CONTRACT.md)|
|6|Frozen rules, functions, procedure, cursor and transaction protocol|[Routines and invariants](ROUTINES_AND_INVARIANTS.md)|
|7|Endpoints, JSON/errors, device/event protocol|[API contract](API_CONTRACT.md)|
|8|Six LAB experiments and all theory-topic traceability|[Syllabus matrix](SYLLABUS_AND_RUBRIC.md), [SQL blueprint](LAB_SQL_BLUEPRINT.md)|
|9|Rubric and23-item checklist mapped to evidence|[Syllabus and rubric](SYLLABUS_AND_RUBRIC.md)|
|10|Scaffold, ownership, migrations, startup/reset and seed plan|[Runbook](IMPLEMENTATION_RUNBOOK.md)|
|11|Three separate complete worker prompts|[A](prompts/WORKER_A_DATABASE.md), [B](prompts/WORKER_B_BACKEND.md), [C](prompts/WORKER_C_FRONTEND.md)|
|12|Git/PR/status/contract-change procedures and merge sequence|[Runbook](IMPLEMENTATION_RUNBOOK.md)|
|13|Correctness, concurrency, rollback/recovery and fair measurements|[Validation plan](VALIDATION_PLAN.md):38 scenarios and7 experiments|
|14|Hour-by-hour schedule, checkpoints and cut hierarchy|[Runbook](IMPLEMENTATION_RUNBOOK.md)|
|15|Demo, slide outline, SDG/TRL evidence and28 judge answers|[Demo and pitch](DEMO_AND_PITCH.md)|
|16|Exact immediate actions and human/account handoffs|[Runbook](IMPLEMENTATION_RUNBOOK.md), [lead packet](prompts/LEAD_COORDINATOR.md)|

## Included data

|File|Rows|Interpretation|
|---|---:|---|
|[gear_catalogue_seed.csv](data/gear_catalogue_seed.csv)|44|Source-labelled catalogue, not automatic requirements; [notes](data/GEAR_CATALOGUE_README.md)|
|[legal_clause_seed.csv](data/legal_clause_seed.csv)|11|Selected source clauses plus operational-demo source; not complete law|
|[rule_parameter_seed.csv](data/rule_parameter_seed.csv)|33|Educational fixed-vocabulary parameters,9 selected gear and7 readiness conditions; [mapping notes](data/POLICY_SEED_README.md)|
|[incident_replay.csv](data/incident_replay.csv)|23|Friend-provided leads with unknown/provenance flags; [limits](data/INCIDENT_DATA_README.md)|

These are validated staging files, not direct SQL COPY inputs. A maps symbolic source/gear/profile codes to keys. Incident leads motivate synthetic scenarios; they do not establish what ZeroEntry would have prevented. Unknown facts must not be converted into confirmed absent safeguards.

## What to supply to each account

Supply its own prompt, MASTER_PLAN, the three frozen contracts, IMPLEMENTATION_RUNBOOK, VALIDATION_PLAN and actual repository SHA. Copy this whole package into `docs/plan/` so every account can consult the same version. A additionally needs LAB_SQL_BLUEPRINT, SYLLABUS_AND_RUBRIC and data; B needs device/source limits and incident notes; C needs DEMO_AND_PITCH and the rubric/source register.

Keep the original **DATABASE-SYSTEMS-LAB.pdf**, **DATABASE-SYSTEMS.pdf** and **DBTHON2026 Challenge.pdf** available to all four humans. These are the academic sources. L retains `astra prompt.txt`, all six Friend_progress files and the original proposal if available as historical context. The complete challenge PDF supersedes the partial rubric photographs; those images are optional backup. Do not send old competing prompts as new instructions—mark them superseded research context.

L can adapt the [repository instruction template](prompts/REPOSITORY_INSTRUCTIONS_TEMPLATE.md) into CLAUDE.md/AGENTS.md after scaffolding. It does not launch workers or grant repository access.

## Verification and limits

[PACKAGE_VALIDATION.md](PACKAGE_VALIDATION.md) records planning-package checks. No application migration, SQL execution, race experiment, hardware calibration, legal deployment approval, frontend build or benchmark has been claimed as complete. The implementation team must produce those results against actual commits. Desk research cannot prove worldwide novelty; the evidence register states retrieval and applicability limits.

Next action: L selects the team repository and records the baseline. A starts A1 while B/C start B1/C1 against the same contracts. Do not begin with three independent whole-app generations.
