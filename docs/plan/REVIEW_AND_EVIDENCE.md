# Review, research decisions and source register

Access/review date: 7 October 2026. The supplied `astra prompt.txt` is the task specification. The three course/challenge PDFs govern academic requirements. Friend files are proposals and evidence leads. Every member's Part B text was checked against the combined pack and found included there. No application source or executed results were present in that folder.

## What is retained, corrected and declined

| Friend or earlier assumption | Decision | Reason / implementation consequence |
|---|---|---|
| Eight-row rubric including TRL | Retain; correct earlier seven-row reading | Official challenge p4 supplies the missing 2 marks; total 30 |
| Four research lanes and one later giant build session | Reorganise | Lead retains domain/evidence/integration; A/B/C implement in parallel from frozen contracts |
| Every listed item is an official mandatory minimum | Correct | The official four-page PDF does not list the 23-item checklist; preserve it as a team target |
| Broad statute-enforcing title | Narrow | Database records cannot establish all physical/legal facts; use evidence-driven work control |
| Offence defined by absent records | Reject wording | Missing safeguards and missing records are not equivalent; store evidence and uncertainty |
| SQL assertion novelty; no major DB supports it | Correct | Oracle 26 documents CREATE ASSERTION; PG16 lists assertions unsupported. Use bounded triggers, not an invention claim [S07,S08] |
| Deferred triggers for everything | Narrow | Commit-time structural checks only; adverse observations must commit and suspend permission; synchronize all writers [S09] |
| Continuous authorisation | Rename operationally | Event-driven invalidation plus expiry/watchdog. No observation means no new trigger; no hard real-time/physical-stop guarantee |
| NOTIFY replaces polling and is reliable delivery | Correct | NOTIFY is a wake-up; durable outbox is replay source. Reconcile after reconnect, keep watchdog and low-frequency snapshot recovery [S10,S11] |
| Incremental shadow ledger | Retain after reference query | Useful database innovation; update affected job, measure read benefit AND write overhead; retain equality checks |
| Standby write skew | Retain as controlled demo | Operational code uses scope lock and reservations; separate READ COMMITTED/SSI experiment explains the anomaly |
| Hashed immutable proof | Narrow | Receipt plus digest; compare with previously exported digest. A privileged actor can rewrite data and hashes |
| Private premises and no-permit incidents | Retain | Asset type/ownership and incident without a work order; no forced registered worker/contractor identity |
| Non-gas incidents and rescuers | Retain | Structural/readiness attestation, distinct standby, refusal/stop-work, explicit limits of gas monitoring |
| Missing MS Act section means incorrect FIR | Reject automatic classification | Record what is reported; legal-review flag only. Evidence cannot force a legal offence classification |
| 30-40 incident records | Use the 23 supplied leads first | No invented expansion; missing conditions remain U. This is scenario motivation, not causal prevention evidence |
| Real MQ rig proves complete gas compliance | Reject | Hardware raw path demonstrates ingestion only; complete numerical educational samples come from labelled simulator |
| Generate a gas spike with lighter fuel/vapour | Replace | Electrical/button or software event injection is sufficient for the data-path demonstration |
| Sensor signature proves safe conditions | Reject | HMAC establishes possession of a key and protects signed bytes; it does not establish measurement truth |
| Automatic blacklist and compensation | Replace | Internal restriction and pending victim-specific assessment case; external award/payment/authority remain distinct |
| PG18 temporal keys, partitioning, pg_ivm, pg_cron | Defer | PG16 ranges and ordinary tables meet scope; changing DB platform or installing extensions adds integration risk |
| Maps, all admin screens, hosted backup | Defer | Four offline-capable local views, local assets and recorded backup maximise rehearsal time |
| Hardware plus news replay means TRL5 | Reject | TRL5 needs relevant-environment validation; target documented lab integration for TRL4, if achieved [S12] |
| Prove our system beats the baseline | Correct | Test the hypothesis, publish neutral/negative results and cost trade-offs |
| Competing team descriptions | Treat as team-reported context | They do not establish other teams' actual implementations or novelty. Differentiate by problem and measured mechanism |

## Ten candidate mechanisms ranked

Scores are our design judgement (1 low, 5 high), not empirical novelty findings. Hours are rough implementation increments with overlap; do not add them as independent promises.

| Candidate | Project value / distinctiveness | Effort | Decision and evidence |
|---|---|---:|---|
| Assertion-style final-state guard | 4 / 2 | 1-2h | One bounded deferred check plus synchronized mutation; source-known mechanism |
| Division with explanatory missing items | 5 / 3 | 1-2h | Core; SQL failure rows match frontend reasons |
| Evidence-triggered invalidation | 5 / 3 | 2-3h | Core; commit/rollback and reconnect timing |
| Incremental reconciliation | 4 / 3 | 1-2h | Core after indexed reference; property equality and read/write costs |
| Write-skew/SSI demonstration | 4 / 2 | 1h | Controlled experiment; operational coarse-lock strategy remains explicit |
| Evidence certificate + digest | 4 / 2 | 0.5-1h | Receipt core; digest external comparison optional |
| Temporal validity and exclusion | 5 / 2 | 1-2h | Core on PG16; lower/upper bounds and open intervals |
| Versioned policy | 4 / 2 | 1h | Fixed evaluators with typed data; no generated arbitrary SQL |
| RLS and restricted DB writes | 5 / 1 | 1-2h | Required supporting security; trust boundaries tested |
| Legal-classification data quality | 2 / 2 | 0.5h | Review state only; never mandatory legal conclusion |

## Closest systems and bounded comparison

Legend: D = documented in reviewed material; A = vendor-advertised; O = explicitly out of scope in reviewed design; U = unknown from inspected material. U is not evidence of absence. These entries summarise the actual sources; no commercial code audit was performed.

| System | Evidence established | Relevant unknown or boundary | Consequence |
|---|---|---|---|
| Garima/DIGIT | D worker-to-request linkage; O mismatch between assigned and actual workers; stated limitations of equipment feedback [S01] | Current deployed treatment of those scenarios U | Strongest specific motivation for participation/evidence consistency |
| Sphera | A permit blocking when isolation confirmation is missing [S02] | Internal SQL invariants and municipal closure linkage U | Hard-block novelty alone fails |
| Enablon | A gas-verification intervals, suspension and isolation management [S03] | Our exact scenario coverage U | Demonstrate temporal integrity; do not claim monitoring is new |
| IntelliPERMIT | A permit/workman registers and customised confined-space checks [S04] | Municipal payment/reconciliation workflow U | Acknowledge mature domain controls |
| NAMASTE | D national sanitation information and incident/FIR/compensation tracking [S05] | Transactional link to our selected job evidence U | Case dashboards are supporting features, not sole novelty |
| Bandicoot/G-Crow | A robotics plus complaints, assets, operators and job evidence [S06a,S06b] | Exact concurrent relational enforcement U | Mechanised completion is part of our workflow; no claim robot platforms lack governance |
| Solinas | A inspection/cleaning/analytics ecosystem [S06c] | Our proposed invariant package U | Defer robotics, mapping and prediction |
| BeaconHS | D README describes PG/RLS/audits/permits [S06d] | Security behaviour not independently tested | RLS is not our differentiator; respect licence before any reuse |
| OpenFisca/OPA/ProvSQL | D policy/provenance patterns [S06e-S06g] | Not direct sanitation competitors | Acknowledge technical prior art; implement small local patterns |

For the friend's F1-F15 comparison, only mark a feature D/A/O when the row's cited document supports it. F1 permit and F2 blocking are already established elsewhere; F3 policy data and F15 provenance have technique-side prior art. F4-F8, F10, F12-F14 vary by implementation; leave unsupported cells U. Replace F9 'detect unrecorded work' with 'flag unsupported completion claims' and F11 'atomic legal consequences' with 'atomic internal case workflow'. We have not established that any feature is globally unoccupied. The supplied broad patent/15-paper research list is a future research programme, not a prerequisite for this implementation plan.

## New primary-source findings

The official NCSK-hosted 2013 Rules PDF was retrieved and inspected locally after web retrieval failed [S13]. Relevant locations are PDF pp3-6, printed Gazette pp20-23. This replaces the old statement that none of the exact rule text was retrievable.

| Requirement | Source locator | Implementation treatment |
|---|---|---|
| Limited manual-cleaning circumstances and written reasons | Rule 3(1); some activities require emptying under 3(2) | Eligibility precedes safeguard checks; later orders still apply |
| Protective equipment catalogue | Rule 4(i)-(xliv); applicability definition 2(1)(g) | 44-item source catalogue, not 44 mandatory personal issues; profile scope must be reviewed |
| Periodic gear checks | Rule 6(1) | Asset inspection validity; calendar six months, not assumed 180 days |
| Depth-related bodysuit provisions | Rule 6(2) | Educational profile uses full suit; exact-five-foot boundary is not silently invented as statutory |
| Minimum onsite people and supervisor | Rule 6(3)(a) | At least three distinct acknowledged people in EDU profile |
| Atmospheric testing and nearby industrial risk | Rule 6(3)(b)-(c) | Complete gas vector and readiness evidence; numerical toxic-gas bounds separate |
| Structural, traffic and medical controls | Rule 6(3)(d)-(h),(v) | Structured readiness, training/fitness and scope caveats |
| Training cadence | Rule 6(3)(i) | Store validity period; two years, with changes in technique also relevant |
| Hospital details and work/rest | Rule 6(3)(j)-(k) | Hospital readiness; daylight; 90 minutes continuous/30 minutes rest |
| Isolation, rescue, retrieval and first aid | Rule 6(3)(l)-(o) | Site evidence and distinct standby policy, not just individual gear |
| O2 and depths | Rule 6(3)(p) | 19.5-21% inclusive; bottom/middle/top |
| Opening/ventilation and monitoring | Rule 6(3)(q)-(u) | Source-classified readiness; one-hour opening condition; ongoing records |
| Rescue equipment, ambulance, insurance | Rule 7 | Site safeguards; life-insurance record review; no claim all field obligations are enforced |

Fifteen-minute freshness, fixed 06:00-18:00 demonstration hours, H2S/LEL/CO numeric limits in our fixture, and the software review SLA remain OPERATIONAL_DEMO values unless separately verified. A fixed clock window is not astronomical daylight. Our implemented EDU profile is a deliberately bounded demonstration of a policy mechanism; it is not a complete statutory compliance certificate.

Later court materials [S14-S16] require cautious activity/jurisdiction treatment. Retain the conservative Chennai manual-cleaning DENY profile. The 2026 compensation clarification distinguishes historical cases; do not retroactively award a uniform amount to every news incident. A current fatality fixture creates a pending review with the judgment's reference amount, not a payment.

An official PIB release reports **332 deaths during hazardous sewer/septic cleaning from 1 January 2021 to 30 June 2026 across 18 states/UTs** [S17]. Use that single dated/category-qualified figure if a national statistic is needed. Do not mix its time window with the friend's 498/1,248 totals or claim a current Tamil Nadu ranking from an old answer.

The NHRC's September 2025 release, reproduced in its official press compilation, explicitly describes uncertainty about the workers' protective equipment in the Tiruchirappalli case [S18]. This is a valuable data-model lesson: unknown PPE must remain unknown. The notice reports allegations and requests an investigation; it is not a final factual adjudication. The CSV retains FRIEND_REPORTED for all supplied leads until each row receives an explicit source review.

## Incident replay design

`data/incident_replay.csv` contains 23 supplied leads, not a representative national sample. Keep Y/N/U for facts; no mention becomes U. Do not fill missing gas values, authorisation, dates or compensation times. Run synthetic variations motivated by patterns, separately labelled as such. Record `scope_match`, `known_condition_failures`, `missing_evidence_failures`, `outcome=DENIED/REVIEW/INDETERMINATE`, and why. Report counts per category and known-value denominators, not 'deaths prevented'. A cave-in illustrates the limit of atmospheric monitoring. A machine being present does not establish successful mechanisation. Private-premises incidents remain recordable even when no municipal job exists.

No automatic requirement to invoke a particular criminal section: preserve reported FIR sections verbatim, mark uncertain source classifications and allow qualified review. No retrospective 'payment improvement' is inferred from case creation latency.

## Source register

All links below are evidence pointers with the supported claim above. PRIMARY means source text/documentation, not universal correctness, current legal clearance or audited vendor performance.

| ID | Source and supported subject | Status |
|---|---|---|
| S01 | [DIGIT Garima PRD](https://docs.digit.org/sanitation/reference-implementations/odisha-sujog/functional-customisation/garima-implementation/product-requirement-document-prd) | PRIMARY; reviewed design limitations |
| S02 | [Sphera case](https://sphera.com/resources/case-study/reducing-operational-risk-while-improving-productivity/) | PRIMARY vendor claim |
| S03 | [Enablon brief](https://assets.contenthub.wolterskluwer.com/api/public/content/86aecc259fb54dbebafe23269b622e3d?v=2707fb35) | PRIMARY vendor brief |
| S04 | [IntelliPERMIT case](https://www.intellipermit.com/success-stories/tronox-namakwa-sands-reinforces-safety-with-intellipermit/) | PRIMARY vendor case; historical deployment |
| S05 | [MoSJE report, pp39-40](https://socialjustice.gov.in/writereaddata/UploadFile/94031776788202.pdf) | PRIMARY government |
| S06a | [Bandicoot](https://sanitation.genrobotics.com/bandicoot) | PRIMARY vendor |
| S06b | [G-Crow](https://sanitation.genrobotics.com/gcrow) | PRIMARY vendor |
| S06c | [Solinas](https://solinas.in/) | PRIMARY vendor |
| S06d | [BeaconHS](https://github.com/braedonsaunders/beaconhs) | PRIMARY README only |
| S06e | [OpenFisca parameters](https://openfisca.org/doc/coding-the-legislation/legislation_parameters.html) | PRIMARY technical |
| S06f | [OPA decision logs](https://www.openpolicyagent.org/docs/management-decision-logs) | PRIMARY technical |
| S06g | [ProvSQL paper](https://www.vldb.org/pvldb/vol11/p2034-senellart.pdf) | PRIMARY research |
| S07 | [Oracle CREATE ASSERTION](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/create-assertion.html) | PRIMARY; corrects friend claim |
| S08 | [PG16 unsupported SQL features](https://www.postgresql.org/docs/16/unsupported-features-sql-standard.html) | PRIMARY; assertions unsupported |
| S09 | [PG16 CREATE TRIGGER](https://www.postgresql.org/docs/16/sql-createtrigger.html) | PRIMARY; deferred checks and transition-table limits |
| S10 | [PG16 NOTIFY](https://www.postgresql.org/docs/16/sql-notify.html) | PRIMARY; transaction delivery semantics |
| S11 | [PG16 LISTEN](https://www.postgresql.org/docs/16/sql-listen.html) | PRIMARY; initial listen/snapshot race |
| S12 | [NASA TRL definitions](https://www.nasa.gov/pdf/458490main_TRL_Definitions.pdf) | PRIMARY; lab versus relevant environment |
| S13 | [Official 2013 Rules](https://ncsk.nic.in/sites/default/files/MSRULES2013HINDIPDF10022026_0-1.pdf) | PRIMARY text retrieved with local PDF reader |
| S14 | [Supreme Court 20 October 2023](https://api.sci.gov.in/supremecourt/2020/4072/4072_2020_8_1502_47917_Judgement_20-Oct-2023.pdf) | PRIMARY; paragraphs84-85,96 |
| S15 | [Official February2025 office report](https://api.sci.gov.in/officereport/2020/4072/4072_2020_2025-02-19.pdf) and [19 February order](https://clpr.org.in/wp-content/uploads/2025/02/Order-dated-19-02-2025.pdf) | PRIMARY documents; latter hosted by intervenor |
| S16 | [Supreme Court 20 January 2026](https://api.sci.gov.in/supremecourt/2020/4072/4072_2020_16_39_67600_Order_20-Jan-2026.pdf) | PRIMARY; compensation clarification |
| S17 | [PIB 21 July2026](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2287317) | PRIMARY; dated death/FIR reporting; not our source for penalty interpretation |
| S18 | [NHRC official press compilation, 30 September2025](https://nhrc.nic.in/sites/default/files/2025-9-30_compressed.pdf) | PRIMARY reproduced NHRC release; search Tiruchirappalli |
| S19 | [Winsen MQ136](https://www.winsen-sensor.com/product/mq136.html) | PRIMARY manufacturer; one target sensor does not establish a four-gas instrument |
| S20 | [FastAPI authentication](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/) | PRIMARY; Argon2/JWT implementation reference |
| S21 | [PostgreSQL isolation](https://www.postgresql.org/docs/16/transaction-iso.html) and [retry handling](https://www.postgresql.org/docs/16/mvcc-serialization-failure-handling.html) | PRIMARY technical |
| S22 | [PostgreSQL range types](https://www.postgresql.org/docs/16/rangetypes.html), [RLS](https://www.postgresql.org/docs/16/ddl-rowsecurity.html), [time](https://www.postgresql.org/docs/16/functions-datetime.html) | PRIMARY technical |
| S23 | [Claude Code project memory](https://code.claude.com/docs/en/memory) | PRIMARY; keep project instructions concise and versioned |
| S24 | [UN Goal8](https://sdgs.un.org/goals/goal8), [2030 Agenda](https://sdgs.un.org/2030agenda) | PRIMARY; targets8.8,6.2,16.6 |
| S25 | [Tamil Nadu 2022 amendment](https://prsindia.org/files/bills_acts/acts_states/tamil-nadu/2022/ActNo34of2022TamilNadu.pdf) | PRIMARY gazette mirrored by PRS; operator licensing context |

## Consequential verification queue and deliberate research cuts

| Issue | Current treatment | Owner / time limit |
|---|---|---|
| Subsequent2026 orders and real jurisdiction applicability | Real manual-cleaning profile remains DENY/REVIEW; no permission claim | Lead; verify before any pilot |
| July2026 five-versus-fifteen contempt claim | Conflicting secondary reports; excluded from slides | Lead; no build dependency |
| Complete CPHEEO/ERSU annexures, exact H2S/LEL/CO source | EDU values labelled operational; do not claim full Indian statutory coverage | Lead; bounded lookup, then queue |
| Complete equipment applicability / five-foot boundary | Catalogue separate from explicit EDU subset | Lead with qualified future reviewer |
| Historical compensation and alleged 3-week deadline | No universal payment deadline; pending review and separately labelled internal SLA | Lead |
| 616/one-conviction, social-audit percentages, Tamil Nadu current ranking | Excluded until primary support and denominator found | Lead; optional |
| Patent landscape, 15 papers, current competing-team implementations | Not proven; no world-first or patentability claim | Future research |
| European AnnexG TRL URL | Official download returned403; use retrieved NASA definition, no false claim of reading annex | Lead; nonblocking |
| Hardware model, wiring and calibration | Simulator core; board integration only after actual inventory | B; 60-90min cap |

Decisions: retain the documented gap, temporal integrity and incremental reconciliation; use source-classified policy; reduce infrastructure. Open questions are limited to deployment/legal/hardware verification and do not block this local educational prototype. Ordered build work and acceptance checks are in the runbook and worker packets.
