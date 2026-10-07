# Policy provenance, permit decisions, and prior art

This document records how the current ZeroEntry prototype distinguishes legal text, court directions, government
guidance and local product choices. It also describes the scope of the saved permit decision and a bounded comparison
with primary-source documentation for related products. It is a design and research note, not a legal opinion, a field
safety certification, or a claim of worldwide novelty.

## How to read the configured gate

The database still runs a fixed set of reviewed SQL checks. The value rows and citation links make the source and
applicability of those checks visible; they do not compile legal text into executable rules. `policy_source` classifies
each citation as `LAW`, `COURT_DIRECTION`, `GUIDANCE` or `PRODUCT_POLICY`. Each entry-gate clause can link to multiple
sources where the SQL combines a statutory duty, operational guidance and a stricter product control.

The initial source history is a cutover baseline created by migration 0013. It records the values present at that
migration and states that earlier value/reason history was unavailable. Later changes to an active parameter append a
revision with its source code, version, server effective time, actor and required reason. The current row remains the
input to new gate checks. The history is not a retroactive law engine and this release does not promise replay of a
past decision under every then-effective rule.

Every successful `DRAFT → AUTHORISED` transition writes one `permit_authorization_decision` row in the same database
transaction. Its JSONB snapshot contains the clause outcomes and explanations, source classifications and
applicability notes, the parameter values and revision numbers, and relevant permit evidence: waiver, contractor
status/licence date, crew roles and fitness/training dates, gear issue identifiers and values, plus the latest
TOP/MID/BOTTOM reading identifiers, raw values, detector identity and calibration date. The stored SHA-256 is computed
inside PostgreSQL over the UTF-8 bytes of PostgreSQL 16's `snapshot::text` rendering. A verifier should hash that exact
rendering; this is not a cross-version JSON canonicalization standard.

The snapshot is an explanation of the database decision at that instant. It does not prove that typed readings reflect
the physical atmosphere, worker identity, gear use, or what happened on site. It is protected against edits through the
application role and ordinary row triggers, but a database owner or superuser can alter the table, trigger or hash.
There is no external signature or anchor. Denied attempts remain explainable in the authorisation response but are not
persisted as decision snapshots in this release. The gate uses current parameter values; preserving an old explanation
does not promise historical replay.

## Source mapping and interpretation limits

| Implemented check or parameter | Classification and source location | What the current gate actually means |
|---|---|---|
| Minimum crew size and supervisor | **LAW** — 2013 Rules, r. 6(3)(a) | At least three employees, including a supervisor. The distinct entrant/supervisor/standby roles are an additional product structure. |
| Standby/top-man role | **PRODUCT_POLICY**, informed by MoHUA ERSU handbook role descriptions | The app requires a separate standby. The Rule's three-person count does not itself define three distinct roles. |
| Fit/training dates | **PRODUCT_POLICY** pending exact applicability review | Current database fields must be active and unexpired. Do not present these date checks as a complete statutory competence scheme. |
| Mechanisation waiver | **PRODUCT_POLICY**, compared with 2013 Rules r. 3(1)(a)–(e) | The app requires an engineer-approved written waiver for every permit. Rule 3(1)(e) is the residual absolutely-necessary case; the approval language is not imposed in the same words on each enumerated case (a)–(d). The app rule is stricter and should be checked against the applicable ULB/state process. |
| Contractor active/licence gate | **PRODUCT_POLICY**, with *Balram Singh* context | The app checks status and licence expiry. The judgment's ¶96(6)–(7) directions concern government accountability and a model-contract consequence that may include blacklisting; they do not define this exact database predicate. |
| Gear division | **LAW** source link plus an explicit **PRODUCT_POLICY** link | The rules require protective gear and devices with applicability conditions. Rule 4's schedule mixes personal protection and site equipment. The current catalogue's global `statutory` flag and per-entrant division are illustrative; they do not establish that every item is personally required for every entrant. |
| O₂ minimum and three sampling depths | **LAW** — 2013 Rules r. 6(3)(p) | The rule identifies bottom, middle and top measurements and a 19.5% minimum. The published English wording around the 21% boundary is conjunctive and ambiguous, so the configured upper limit is classified separately. |
| O₂ upper limit | **GUIDANCE** — CPHEEO 2018 SOP Step 4(ii) | The SOP explicitly states the 19.5%–21% oxygen band. The app uses that guidance for its 21% upper threshold; this does not resolve the ambiguity in the Rules' English wording. |
| H₂S and combustible-gas thresholds | **GUIDANCE** — ERSU handbook Annexure 2 (CPHEEO manual extract) | The configured H₂S and LEL values are guidance thresholds, not numeric limits from Rule 6(3)(b). |
| CO limit | **PRODUCT_POLICY** referencing the NIOSH Pocket Guide | NIOSH describes 35 ppm as an occupational time-weighted average and 200 ppm as a ceiling. Using 35 ppm as an individual spot-reading cutoff is a product assumption; it does not calculate time-weighted exposure and is not an Indian sewer-entry legal limit. |
| 15-minute reading age | **PRODUCT_POLICY** | No 15-minute freshness requirement was identified in the cited Rules or reviewed CPHEEO/ERSU guidance. The value is configurable and should be shown as an assumption. |
| Daylight window | **PRODUCT_POLICY** — 2013 Rules r. 6(3)(k) supplies the daylight requirement | Fixed 06:00–18:00 hours are a proxy, not an astronomical daylight calculation. |
| 90-minute stretch and 30-minute rest | **LAW** — Rules r. 6(3)(k)(i)–(ii); CPHEEO SOP Step 4(xiv) | The entry-log guard enforces the configured 30-minute rest per worker after a recorded stretch of at least 90 minutes, starting from the later of reported exit and server receipt. The Rule says a 30-minute interval between stretches; this implementation does not assert an automatic rest timer after shorter stretches. |
| Fatality compensation | **COURT_DIRECTION** — *Balram Singh*, ¶96(4) | The judgment directs ₹30 lakh for sewer deaths. The app's amount does not make an entitlement determination or set a general 30-day deadline. |
| Disability compensation and due time | **PRODUCT_POLICY** informed by *Balram Singh*, ¶96(5) | The judgment uses severity-sensitive minimums: ₹10 lakh minimum, and ₹20 lakh minimum for the stated permanent-disability/economic-helplessness condition. The app's flat ₹20 lakh and 30-day due period are product assumptions, not a universal court amount/ceiling or judgment deadline. |
| Automatic blacklist on fatality | **PRODUCT_POLICY** informed by *Balram Singh*, ¶96(6)–(7) | The prototype's automatic state change is a team sanction choice. The judgment describes accountability/cancellation and possible model-contract blacklisting; it does not make this automatic for every record. |
| 24-hour evidence grace | **PRODUCT_POLICY** | A configurable synchronization window, not an identified statutory period. |

Primary documents linked from the database source rows:

- [Official Gazette: 2013 Manual Scavengers Rules (G.S.R. 776(E))](https://socialjustice.gov.in/public/ckeditor/upload/86751727950899.pdf)
- [Supreme Court: *Balram Singh v. Union of India*, 20 October 2023](https://api.sci.gov.in/supremecourt/2020/4072/4072_2020_8_1502_47917_Judgement_20-Oct-2023.pdf)
- [MoHUA/CPHEEO: 2018 sewer and septic-tank cleaning SOP](https://cpheeo.gov.in/upload/5c0a062b23e94SOPforcleaningofSewersSepticTanks.pdf)
- [MoHUA ERSU handbook](https://static.pib.gov.in/WriteReadData/userfiles/SBM%20ERSU%20Book_Final.pdf)
- [CDC/NIOSH Pocket Guide: Carbon monoxide exposure limits](https://www.cdc.gov/niosh/npg/npgd0105.html)

## Bounded comparison with documented products

This comparison concerns public primary product documentation reviewed on 7 October 2026. It is not a feature-by-feature
product test. Undocumented capabilities are unknown, and a configurable product may support workflows not described on
the cited page.

| Product/source | Documented overlap | Difference visible in the reviewed documentation | Careful claim |
|---|---|---|---|
| [IntelliPERMIT electronic PTW](https://www.intellipermit.com/capabilities/electronic-permit-to-work/), [confined-space example](https://www.intellipermit.com/blog/confined-space-work-permit/), and [competencies](https://www.intellipermit.com/blog/competencies/) | Electronic permit lifecycle, competence/medical prerequisites, spotter/standby, gas testing and device service/calibration controls, audit history, configurable site rules and possible access-control integration. | The reviewed industrial PTW material does not document ZeroEntry's specific municipal complaint/job graph, complaint-anchored missing-clearance alerts, or linked compensation and invoice-hold workflow. Its flexible rules/integration mean an undocumented feature cannot be assumed absent. | Existing ePTW products already document real authorization and safety gates. ZeroEntry's distinguishable research direction is the specific sanitation-record integration and absence-review workflow, pending measured evaluation. |
| [OPEREX Permit to Work and product updates](https://operex.eu/permit-to-work/whats-new/) | Current public documentation describes configurable competence and time-valid gas gates, a one-worker/one-open-permit lock, immutable chained signatures, audit fingerprints stored off-server, and evidence checks. | The reviewed product pages do not document ZeroEntry's complaint-resolution expected population, SE1/SE2 evidence-gap alerts, or the app's exact Indian municipal linkage. Public pages are not an exhaustive configuration inventory. | A permit snapshot or hash chain alone is not novel. ZeroEntry's in-database SHA-256 is weaker than an externally anchored trail and should be described with its database-owner trust limit. |
| [DIGIT FSM/Garima product requirements](https://docs.digit.org/sanitation/water-sanitation-product-suite/waste-management-system/faecal-sludge-management-fsm/product-requirement-document) and [SUJOG-FSSM SOP](https://docs.digit.org/sanitation/reference-implementations/odisha-sujog/standard-operating-procedure-sop) | Public documents describe municipal sanitation requests, vendor/worker assignment, service-delivery records, worker identity/training context and reconciliation across service requests and trips. | The reviewed documentation centers on faecal-sludge service management and workforce records; it does not describe a PostgreSQL permit transition that snapshots all cited evidence or the same SE1/SE2 alert lifecycle. The product requirement document describes scope/plans and is not proof that every capability is deployed everywhere. | DIGIT/SUJOG is a close municipal service-record comparator. The defensible distinction is the exact configured integration in this prototype, not a claim that comparable software cannot provide it. |

Relational division, anti-joins, SQL triggers, row locks, transaction atomicity, and stored hashes are established database
techniques. The prototype's contribution is a specific, testable composition of configured entry checks with a
complaint/job/permit evidence graph and a human-reviewed absence workflow. No source review here proves first use,
patentability, worldwide novelty, legal completeness or production superiority. Research claims should be evaluated with
adjudicated cases, false-alert rates, detection latency and load measurements before quantitative benefits are stated.
