# Demonstration, presentation and defence

Status: rehearsal specification. No screenshot, performance number or test pass is implied. C owns visible assets; B owns deterministic API actions; A owns SQL explanations; L owns claim accuracy. Use only synthetic people/sites in the prototype.

## The story in one paragraph

ZeroEntry is a mechanisation-first municipal sanitation safety-evidence and accountability system. A worker assignment or green checklist is not proof of who actually entered, whether their evidence was current, whether another job was using the same equipment, or whether a completed claim has matching work evidence. Our PostgreSQL protocol links those facts, rechecks them at action time, and records accountable consequences atomically. It blocks inconsistent software decisions; it does not certify physical safety or override legal prohibitions.

Database systems technology: PostgreSQL16 relational DBMS, SQL and PL/pgSQL, normalization, keys/constraints, relational division/anti-joins, views, procedures/functions/cursors/triggers, ACID transactions, locking/exclusions, indexes/query plans and scoped access. Supporting stack: FastAPI/SQLAlchemy/Alembic and React/TypeScript. Domain: municipal sanitation, occupational safety and civic accountability; primary fit Safety & Security, secondary Smart Community & Civic Life.

Expected outcome: a local integrated prototype, reproducible correctness/concurrency/reconciliation measurements, database design evidence and a defendable demonstration. Actual claims depend on the worker team's executed results, not the ambition of this plan.

## Screen layout and information hierarchy

Common header: project | current actor/role | selected scope | server time | connection state. A permanent banner identifies REAL POLICY: DENIED/REVIEW or EDUCATIONAL SIMULATION — NOT DEPLOYABLE. Red/amber/green always have text and icons. A countdown is explanatory, not enforcement.

| View | Main region | Inspector/action region | Database idea visible |
|---|---|---|---|
| Workboard | Complaints and jobs; activity, scope, machine outcome, status | Job timeline, deployment proof, next permitted action | Correct one-complaint/many-job model; mechanical path first |
| Permit dossier | Crew acknowledgement, per-person gear, shared-site gear, depth samples/readiness | Gate results, provenance, exact missing pair, receipt ID/version/expiry, start/exit/stop | Division, current evidence, constrained transition, snapshot linkage |
| Accountability | Imported claim vs actual completion, invoice disposition; incidents/cases | Reason, reviewer, source status, linked evidence and audit | Anti-join/projection; one incident/many victims; atomic consequences |
| Judge evidence | Six LAB cards, ER/schema, executed tests and comparisons | Raw-run links, query plans, limitations, source register | Technical depth and measurable, reproducible outcomes |

Do not build a separate full administration page for every one of37 relations. The relational model supports four meaningful workflows. Expose an accessible detail table when judges ask, not37 competing navigation items. A valid historical completion remains valid when yesterday's atmospheric sample naturally ages.

## Pre-demo reset and deterministic sequence

B implements `scripts/demo.ps1` subcommands after the real API exists: `prepare`, `show-policy-denial`, `correct-edu`, `inject-adverse`, `show-reconciliation`, `record-incident`. They call normal authenticated endpoints and use idempotency keys per action; no direct table rewrites. Reset requires guarded demo-only confirmation as in the runbook. Keep sensitive development credentials in local environment, not the recording or source.

Seed full IDs from API_CONTRACT: job suffix010 mechanical Chennai; permit/job020 educational;030 imported evidence gap;040 legitimate alternate job;050 standalone synthetic incident. The reset time controls relative samples and validity windows. Fixtures that require different real actor acknowledgements are initialized transparently as seeded synthetic acknowledgements, not attributed to a human who never clicked. Live corrections use appropriate seeded actor sessions.

| Action | Before | Expected committed result | Evidence |
|---|---|---|---|
| Request real manual authorization | Chennai prohibited/unknown activity even with complete fields | DENIED byG0; no reservations; route to mechanical job | Receipt, no resource rows, machine success separately |
| Evaluate EDU020 | Missing personal harness, missing BOTTOM sample, assigned but unacknowledged standby; other prerequisites valid | At least G1/G2/G4 failures; no current usable receipt | Missing worker/item, depth and acknowledgement in dossier |
| Correct EDU020 | Same permit DENIED/DRAFT | Issue selected harness to entrant; append coherent BOTTOM sample; standby actor acknowledges; authorize yields current expiring receipt | Three normal endpoint responses, certificate evidence links |
| Attempt new entry after adverse sample | Receipt existed; no open entry for this short demonstration | Append newer unsafe BOTTOM observation, latch stop/suspend, reject old certificate at begin | Persisted reading/revision/stop +409 with G8/stale reason |
| Compare claims030 and040 | Imported COMPLETED030 lacks valid proof;040 has validated mechanical completion |030 review gap/invoice hold;040 no gap | Job-level anti-join/projection, no allegation of crime |
| Record standalone incident050 | No permit and no registered worker required | Incident+victims+pending cases; no fake entry; payment0; unknown contractor remains investigation/review | Procedure output and rows/audit in same transaction |

Some fixture IDs identify entities rather than meaning all related records share exactly the same suffix; use the API namespace table. Do not enable a failed real jurisdiction profile just to make the happy path green. If a live demo takes longer than evidence freshness, reset/re-evaluate through normal actions; never freeze server time in the production path.

## Three-minute golden path

| Time | Presenter/action | Say/show |
|---|---|---|
|0:00–0:25| L: problem and documented gap | “Existing systems already offer permits. We focus on actual participation, current evidence and closure consistency.” Cite Garima's documented scope/evidence limitation from REVIEW_AND_EVIDENCE. |
|0:25–0:45| C: Chennai card | “A green checklist cannot override eligibility. This job follows mechanisation.” Show G0 denial and the separate legitimate machine-completion result. |
|0:45–1:25| C+B: EDU dossier | Clearly announce educational fixture; show three concrete failures, run the prepared normal corrections and obtain receipt. Explain one missing worker/gear pair. |
|1:25–1:55| B: adverse reading/recheck | New observation invalidates the receipt; attempted start is refused. “The database checks at the action boundary, not only when the form was submitted.” |
|1:55–2:25| C: accountability | One unsupported completed claim held for review; legitimate second job not flagged. No claim of fraud from absence. |
|2:25–2:45| A: incident evidence | One pre-prepared or live short incident transaction, multiple pending cases and no payment. If slow, use the recorded real run and label it. |
|2:45–3:00| L: result and limits | One actual measured correctness result with sample size; if not run, say not yet measured. “Prototype evidence consistency, not physical safety certification.” |

Do not perform ten logins, teach every SQL construct or run a100k-row benchmark during these three minutes. Use trusted seeded sessions selected before the timed demonstration. If only one result fits, the receipt-invalidated-at-entry moment is the clearest mechanism.

## Longer technical backup: 8–12 minutes

1. A shows principal ER, actual schema dictionary, natural vs surrogate keys and one lossless decomposition. Show why permit_crew and gear_issue are distinct.
2. Execute one query from each LAB file; display result and explain its business use. For cursor, keep transaction open for both FETCH operations.
3. Two synchronized clients request the same resource; show exactly one valid committed allocation. Explain coarse per-ULB lock and exclusion trade-off. Optional separate on-call toy illustrates write skew/serializable retry without falsely calling it production code.
4. Read-only runtime login attempts direct authorization update; reject. A privileged owner could still tamper; disclose that threat boundary.
5. Inject an exception in a test-only incident transaction; verify no partial cases/holds/events. Retry a successful request with same key; same IDs, not duplicate cases.
6. Show no-permit incident, late truthful exit with violation, cross-permit rest, new incomplete reading and empty requirement set.
7. Show reference anti-join equals projection, a legitimate multi-job complaint, and historical completion not retroactively invalidated by current sample age.
8. Show fair benchmark manifest, one plan before/after, raw observations, median/p95 with sample size. Explain write cost and mutex contention; do not call any vendor slower without testing it.
9. End with scoped actor test, clean migration/restore evidence and known limitations.

## Slide outline: 10 slides, approximately 7 minutes plus questions

| Slide | Core content | Artifact/evidence | Speaker |
|---|---|---|---|
|1 Problem/domain/users | Actual evidence consistency in municipal sanitation, mechanism-first motivation | One qualified official statistic if needed, not a wall of tragedy | L |
|2 Existing work and specific gap | NAMASTE, Garima, industrial permit systems; acknowledge overlap | REVIEW_AND_EVIDENCE primary-source matrix | L |
|3 Our contribution | Five-part chain and what is genuinely different in this controlled workflow | Schema/routine linkages; no worldwide-first wording | A |
|4 Architecture and trust | Browser -> API -> protected DB commands; source devices treated as untrusted evidence | MASTER_PLAN architecture; honest owner/admin boundary | B |
|5 Relational model | Principal ER plus37-relation reference; actual crew, serial assets, versioned rules | SCHEMA_CONTRACT; two FDs and lossless split | A |
|6 Collective LAB integration | Six experiments connected in one authorization/incident/report workflow | Actual SQL excerpts/result captures | A |
|7 Live prototype | Short golden path; educational banner throughout success | Actual local running stack | C+B |
|8 Evaluation | Controlled cases, concurrency, projection equality and one timing comparison | Raw run/commit/seed/sample size; NOT YET MEASURED until executed | B |
|9 Impact and limitations | SDG8.8 worker safety,6.2 sanitation,16.6 accountability; no field-impact claims | Capability-to-target mapping below | L |
|10 Readiness and next steps | Evidence-based TRL, calibration/source review, stakeholder/ethics review, pilot plan | Readiness checklist, no imaginary deployment | C |

Optional official context: PIB's response reports332 deaths from hazardous sewer/septic-tank cleaning from1 January2021 to30 June2026, across18 States/UTs. Preserve that exact definition and interval; don't merge it with other lifetime totals or call it all sanitation deaths. Source S17 in REVIEW_AND_EVIDENCE. Avoid the statistic entirely if the team cannot explain its scope.

## SDG and readiness claims

| Target | Direct relevance | Prototype evidence | Claim not justified |
|---|---|---|---|
|8.8 Protect labour rights and safe working environments | Recorded refusal, current safeguards and resource availability | Refusal preserved; software transition blocked on missing evidence | Fewer actual deaths or certified safe workplaces |
|6.2 Adequate sanitation and hygiene | Mechanised municipal sanitation workflow | Complaint -> mechanical work -> evidenced completion | Population-level access improvement |
|16.6 Effective accountable transparent institutions | Linked claims, audit, pending-case review | Traceable decision and review reason, scoped auditor report | Elimination of corruption or government adoption |

Official target wording and context: [UN SDG8](https://sdgs.un.org/goals/goal8), [UN2030 Agenda](https://sdgs.un.org/2030agenda). Link the targets to capabilities, not imagined measured societal outcomes.

The supplied material is presently a concept/design package: claim concept formulation, not an integrated prototype. After isolated proof experiments, evidence may support TRL3; after implemented components are integrated and validated in a laboratory setting, target TRL4. A desk sensor or news replay alone does not establish a representative operational environment/TRL5. Use the [NASA TRL definitions](https://www.nasa.gov/pdf/458490main_TRL_Definitions.pdf) as a disclosed interpretive framework; the challenge asks for TRL/demo evidence but does not prove a specific assessment scheme. If a campus-specific definition is supplied later, map to it without inflating the achieved level.

## Judge Q&A: concise defensible answers

1. **What is novel?** The scoped integration of actual crew, versioned evidence, atomic transition/resource constraints and completion/incident accountability, demonstrated against defined baselines. Individual components are established.
2. **Why not an ordinary CRUD app?** Correctness spans rows, time and concurrent writers; editing a form cannot safely establish the required transition.
3. **Why PostgreSQL?** Relational constraints, stored commands, transactional locks, range exclusions, query plans and controlled grants express/test the selected invariants in one engine.
4. **Why37 tables?** Each represents a distinct fact/history/projection in the dictionary. Count is a consequence, not our innovation; only four UI workflows are needed.
5. **Could application code do this?** Yes, with equivalent atomic protocol and all writers coordinated. Our B1 comparison isolates that mechanism; it does not prove application enforcement impossible.
6. **Don't Sphera/Enablon already block work?** Their reviewed documentation establishes permit/control capabilities. We do not claim absence; our contribution is the municipal evidence/accountability chain and its explicit tested invariants.
7. **Does NAMASTE lack compensation tracking?** No. Our transaction-linked job/worker/evidence model is positioned as complementary, not a replacement based on a false gap.
8. **Does this legitimize manual cleaning?** No. G0 blocks prohibited/unknown activity; a waiver or safety checklist cannot override it. Positive entry is only an educational fixture.
9. **Why44 equipment items but only nine selected?** The Rules list a catalogue; work-appropriate requirements need policy review. Personal and site items differ. The educational subset is explicitly not a certified operational checklist.
10. **Are gas values real?** The demo labels synthetic data. A low-cost MQ module is not a calibrated four-channel instrument or oxygen sensor. Source authenticity and physical validity are separate.
11. **What if a safe sample is followed by incomplete data?** Latest coherent observation selection does not filter the incomplete record away; the requirement fails rather than falling back to older green data.
12. **What if an unsafe sample arrives late?** Preserve it, latch stop under the policy and do not let a delayed safe record clear the latch.
13. **What if evidence expires with no update?** Entry-start recheck denies immediately. A watchdog eventually updates ongoing display/state; ordinary triggers do not fire merely because time passes.
14. **Can two jobs reserve one breathing set?** Not under the tested ulb-first command protocol and exclusion constraints. Show the committed-state race evidence, not only HTTP responses.
15. **Why lock the whole municipality?** It is a simple, auditable MVP correctness boundary. It reduces concurrency; scaling requires finer-grained lock design and new tests, not unsupported throughput claims.
16. **What if someone sends direct SQL?** Runtime grants deny operational writes. A compromised owner/superuser is outside that guarantee; procedures are not protection against all administrators.
17. **Is the hash tamper-proof?** It detects modification relative to a trusted retained digest. An attacker rewriting both without an external anchor defeats that check.
18. **Is missing completion evidence fraud?** No. It is a reviewable gap with provenance and a reason; legitimate mechanical/cancelled/alternate-job cases are tested to avoid false flags.
19. **Does a receipt prove today's validity forever?** No. It is an immutable historical decision with source version, revision and expiry; usability is derived at the new action.
20. **Does an old completion become invalid when gas ages?** No. Historical validity is assessed at the event time; contradictory/retracted evidence may reopen review, natural age alone cannot.
21. **Why a cursor?** To demonstrate bounded audit report traversal across FETCH operations in one transaction. Set-based SQL still computes summaries; cursor is not claimed as a speed trick.
22. **What do triggers contribute?** Changes to evidence cause consistent invalidation/projections/audit within the transaction. They are paired with locks/grants and do not enforce time or concurrency magically.
23. **Are all tables in5NF?** We demonstrate stated dependencies and lossless normalization for core relations, plus4NF/5NF reasoning. We do not certify every historical JSON snapshot as5NF.
24. **What happens to compensation?** The prototype opens a pending review case with a source-qualified reference amount. It cannot award/disburse money or decide FIR sections.
25. **What benefit did you measure?** Quote actual run counts, false denials, conflicting committed allocations, projection correctness and timing with dataset size. No measurements yet means no claimed improvement percentage.
26. **Why not integrate every syllabus technology?** All six LAB experiments are in the real workflow. Theory coverage distinguishes implemented, controlled demonstration, explained and deferred topics; extra databases/BI systems without purpose would weaken coherence.
27. **What happens outside registered municipal work?** A standalone incident may have a private site, unknown contractor and unregistered victims. Preserve uncertainty; don't fabricate a prior permit or claim the software would have prevented it.
28. **Does NOTIFY guarantee delivery or instant safety?** No. Durable outbox supports replay, action checks enforce new transitions, and physical response still depends on people, devices and connectivity.

## Final rehearsal checklist

Every teammate can explain their own SQL/code without reading an AI answer. Every chart has a source/run. Every successful entry screen says educational. Every third-party limitation is sourced or marked unknown. The recording is labelled prerecorded. Reset succeeds twice. Actual demo SHA is recorded. Three-minute and technical backup paths both fit their allotted time. The fourth human can operate the presentation laptop if the usual presenter is unavailable.
