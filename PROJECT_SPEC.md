# PROJECT_SPEC: ZeroEntry

**Authoritative for:** the problem definition, interpretation, scope, roles, business rules and assumptions.
If another document disagrees with this one, this one wins. Design and schema live in
[ARCHITECTURE.md](ARCHITECTURE.md) and [DATABASE_DESIGN.md](DATABASE_DESIGN.md); progress lives in [ROADMAP.md](ROADMAP.md).

Rule IDs (`BR-nn`) are stable. Code, SQL comments and tests cite them.

---

## 1. Problem statement and how it was interpreted

**Assigned problem:** *Zero-Entry / Shadow-Entry Detection by Absence.*

The wording does not name a domain, so the workspace was inspected first. It contains a complete DBThon 2026
proposal, [`docs/proposal/ZeroEntry_DBThon2026_Proposal.md`](docs/proposal/ZeroEntry_DBThon2026_Proposal.md)
(Track 7, Safety & Security), that uses exactly these terms. A second proposal in the folder
(*CampusContinuity*, Track 3) is a different project and is out of scope.

### Interpretations considered

| # | Reading of the problem | Verdict |
|---|---|---|
| A | **Sanitation safety.** Zero-entry: no one may enter a sewer unless every statutory safeguard is proven; the goal is zero human entries. Shadow-entry: an entry that happened with no record, found from the *absence* of the records a lawful clearance would leave. | **Adopted.** Matches the workspace proposal, its title and its novelty claims. |
| B | Generic attendance / expected-record monitoring (a person or event with no row). | Rejected: no workspace evidence, and it loses the "entry" in both terms. The detection *technique* (expected population minus actual records) is kept; it is what A uses. |
| C | Ledger reconciliation ("zero-value entries", off-book "shadow" entries). | Rejected: no workspace evidence. |
| D | Campus maintenance and class relocation. | Rejected: a separate proposal (`CampusContinuity_*`) with different tables and goals. |

### Working definitions (interpretation A)

* **Zero-entry (preventive).** Entry is denied by default. A permit becomes `AUTHORISED` only when relational
  division proves that *every* required safeguard has a matching record: gear for every entrant, fresh in-limit
  gas readings at all three depths, a full crew with distinct roles, a written reason why no machine can do the job.
  Zero entries is also the policy target: the system is mechanised-first and reports the share of jobs completed
  with no human entry (the **zero-entry rate**).
* **Shadow-entry (detective).** A suspected human entry for which the system holds no authorising record. It cannot
  be observed directly, so it is *inferred from absence*: a complaint closed as "cleared" with neither a machine
  clearance nor a closed, logged permit behind it.
* **Detection by absence.** Two set operations over an *explicit expected population*:
  1. **Relational division** (`NOT EXISTS ... NOT EXISTS`): "for every required item there is a matching record".
  2. **Anti-join** (`NOT EXISTS`): "an event with no matching record".

### What absence does and does not prove

A missing row is **not** proof that an entry happened. It is a *suspicion with evidence attached*. Alerts record
why they fired, can be dismissed as false positives with a written reason, and are never closed automatically
once raised (BR-31). The database also cannot verify that a typed gas reading is physically true; it binds each
reading to a detector serial, calibration date and signed-in recorder, and keeps an append-only trail.

---

## 2. The real-world problem

Indian law prohibits manual cleaning of sewers and septic tanks except under strict conditions, yet workers keep
dying. The proposal cites (these figures come from the proposal's sources and **must be re-verified before they are
quoted in a presentation**): 1,248 deaths since 1993 with Tamil Nadu highest at 253 (Rajya Sabha, Nov 2024); a
government-commissioned social audit finding no safety equipment in 49 of 54 deaths; and the Supreme Court's
*Balram Singh v. Union of India* (2023) directions of ₹30 lakh compensation per death.

The rules exist but nothing enforces them at the moment of entry: gas tests are optional in practice, gear is
"available" but not issued to the person going down, permission is verbal, and deaths are recorded after the fact.
Existing tools (worker registries, desludging apps, industrial permit-to-work) never *refuse* an entry.

## 3. Stakeholders and roles

| Role | Who | Can do | Cannot do |
|---|---|---|---|
| `ADMIN` | System / ULB administrator | Users, rule parameters, gear catalogue, detectors, everything below | n/a |
| `ENGINEER` | Municipal engineer; the SOP's "Responsible Sanitation Authority" (RSA) | Raise and resolve complaints, create jobs, record machine deployments, **approve mechanisation waivers**, review shadow-entry alerts, approve invoices, release holds, record compensation payments | Change rule parameters |
| `SUPERVISOR` | Site supervisor | Draft permits, assign crew and gear, log gas readings, **authorise**, log entries, close/abort permits, record incidents | Approve waivers, review alerts |
| `WORKER` | Sanitation worker | See own permits and gear; **stop-work** on a permit they are crewed on | Anything on other people's records |
| `CONTRACTOR` | Contractor's office | See only own jobs, workers, permits, invoices, incidents; submit invoices | See other contractors; see shadow-entry alerts |
| `AUDITOR` | NCSK / vigilance / NHRC-style reviewer | Read-only: shadow-entry alerts, compensation, reports, audit log | Any write |

Roles are enforced on the server (API guards) and, for row scoping, by PostgreSQL row-level security (see
[SECURITY.md](SECURITY.md)). Hiding a button is never the control.

## 4. Inputs and outputs

* **Inputs:** complaints against manholes; jobs and contractor assignments; machine deployments and outcomes;
  waivers; permit drafts, crew, gear issues; gas readings (detector, depth, O₂/H₂S/LEL/CO, time); entry/exit logs;
  incidents; invoices; rule parameters.
* **Outputs:** an explainable *entry decision* (one pass/fail line per legal clause with the failing detail); persisted
  **shadow-entry alerts** with reason, evidence snapshot and review history; compensation cases and invoice holds;
  dashboards and reports (zero-entry rate per ULB, deaths per ULB per year, mean days to compensation, contractor
  risk score); an append-only audit trail.

## 5. Business rules

Legal bases are quoted **as the proposal states them**. The proposal itself warns that rule-level numbering of the
2013 Rules must be checked against the Gazette; this project deliberately cites rules by name, not number.

### Entry gate (zero-entry)

| ID | Rule | Basis | Enforced by |
|---|---|---|---|
| BR-01 | Mechanised first: manual entry needs a written waiver approved by an `ENGINEER`; a permit cannot even be drafted without one. | CPHEEO SOP 2018 | `mechanisation_waiver` + triggers |
| BR-02 | Waiver justification ≥ 50 characters; reason `MACHINE_FAILED` requires a recorded `FAILED` deployment on that complaint. | Proposal §4 | CHECK + trigger |
| BR-03 | Crew ≥ 3 persons with ≥ 1 supervisor, ≥ 1 standby (top man) and ≥ 1 entrant. A worker holds exactly one role per permit, so a standby can never also be an entrant. | 2013 Rules; ERSU book | clause check; PK `(permit_id, worker_id)` |
| BR-04 | Every crew member is medically fit and trained on the authorisation date. | Proposal §6.2 | clause `CREW_FIT` |
| BR-05 | The job's contractor is `ACTIVE` with an unexpired licence. | *Balram Singh* 2023 | clause + job trigger |
| BR-06 | Every entrant holds **every** statutory gear item (relational division). The check fails if no statutory item is defined (no vacuous pass). | 2013 Rules, protective-gear schedule | clause `GEAR_ALL` |
| BR-07 | For each depth `TOP`, `MID`, `BOTTOM` the **latest** reading is ≤ 15 min old at authorisation, from a detector calibrated on the day it was taken, with O₂ 19.5-21.0 %, H₂S < 10 ppm, LEL < 10 %, CO below its limit. | 2013 Rules; CPHEEO SOP 2018; ERSU 2019 | clauses `GAS_TOP/MID/BOTTOM` |
| BR-08 | **Default deny:** status `AUTHORISED` is reachable only if every clause passes, for *every* client, including a raw `UPDATE`. | Core claim | `permit_clause_check()` called from `authorise_entry()` and a BEFORE UPDATE trigger |
| BR-09 | Crew and gear are frozen once authorised; gas readings are append-only. | Integrity | triggers |
| BR-10 | Entries only inside the permit's validity window, only by an `ENTRANT`, only in daylight, at most 90 minutes each, never overlapping for the same worker. | 2013 Rules / ERSU | trigger + exclusion constraint |
| BR-11 | Permit states: `DRAFT → AUTHORISED → CLOSED`; `DRAFT → CANCELLED`; `AUTHORISED → ABORTED`. `CLOSED` needs no open entries. Terminal states are final. | Integrity | state-machine trigger |
| BR-12 | Calibration: a reading from a detector whose calibration had lapsed on the reading's date is rejected. | ERSU / good practice | trigger |

### Consequences

| ID | Rule | Enforced by |
|---|---|---|
| BR-20 | **Fatality** in one transaction: incident + compensation case (₹30,00,000, due 30 days after the incident) + contractor `BLACKLISTED` + permits aborted + invoices on the job held. All or nothing. | `record_incident()` procedure |
| BR-21 | **Disability**: compensation case (₹20,00,000) + contractor `SUSPENDED`. **Near miss**: recorded only. | same |
| BR-22 | A suspended or blacklisted contractor cannot be assigned new jobs. | job trigger |
| BR-23 | An invoice on hold cannot be approved or paid. Every hold records its source (alert or incident) and is released only by that source (an alert dismissal never releases a fatality hold). | `invoice_hold` + trigger |

### Detection by absence (shadow-entry)

| ID | Rule |
|---|---|
| BR-30 | Expected population, rule **SE1**: complaints `RESOLVED` with a resolution type that requires evidence (`CLEARED`). Evidence is either (a) a machine deployment with outcome `CLEARED`, or (b) an `AUTHORISED→CLOSED` permit with at least one logged entry, on any job of that complaint. No evidence, or no job at all, is a candidate. |
| BR-31 | **Late evidence never auto-closes an alert.** Evidence counts only if it was *recorded* within the grace window after resolution (default 24 h). Evidence that arrives later moves an existing alert to `EVIDENCE_RECEIVED`, and a human decides (`CONFIRMED` or `DISMISSED`, with a written note). |
| BR-32 | Rule **SE2**: for each `CLOSED` permit, every `ENTRANT` should have at least one entry-log row recorded within the grace window. Entrants without one make the complaint a candidate. |
| BR-33 | Complaints resolved as `NO_BLOCKAGE_FOUND`, `DUPLICATE_COMPLAINT`, `REFERRED_OUT` or `WITHDRAWN` are *intentionally absent*: not expected to have evidence, never flagged. |
| BR-34 | One alert per `(complaint, rule)`; re-running the scan is idempotent. A dismissed alert is not re-opened by the scan. |
| BR-35 | Opening an alert holds the contractor's unpaid invoices on that complaint's jobs; dismissing it releases exactly those holds. |
| BR-36 | Every alert lifecycle change is stored in an append-only history table. |

### Platform

| ID | Rule |
|---|---|
| BR-40 | Thresholds, limits, amounts and grace periods are rows in `rule_parameter` with a legal reference; changing one is audited. |
| BR-41 | `audit_log` is append-only (trigger; privileges revoked from the application role). |
| BR-42 | The application connects as a least-privilege role; contractors and workers see only their own rows (RLS). |

## 6. Assumptions (explicit, configurable, to be confirmed)

Marked `is_assumption = true` in `rule_parameter` and shown as such in the admin screen.

| ID | Assumption | Why it is needed |
|---|---|---|
| A-01 | CO limit 35 ppm. | The 4-gas monitor records CO but the proposal gives no limit (NIOSH REL used as a placeholder). |
| A-02 | Permit validity 240 minutes. | The sources give no permit duration. |
| A-03 | Daylight is 06:00-18:00 IST. | "Daylight only" has no fixed hours; sunrise/sunset vary. |
| A-04 | No mandatory rest interval is modelled. | "Then rest" has no stated length; adding a made-up number would be false precision. |
| A-05 | Compensation due 30 days after the incident; disability amount ₹20 lakh (upper end of the ₹10-20 lakh range). | Deadline and slab are not specified in the proposal. |
| A-06 | Grace window 24 h for evidence to be recorded after resolution. | Field records sync late; an assumption trades false positives against delay. |
| A-07 | All ULBs are in India Standard Time (fixed +05:30). | True for the target; keeps the schema free of a tz database. |
| A-08 | Suspension (not blacklisting) for disability incidents. | The proposal covers death only. |
| A-09 | The gear catalogue in the seed data is illustrative. | The 2013 Rules' schedule must be checked against the Gazette. |

## 7. Limitations and edge cases

* The database enforces *state*, not physics: a typed gas value may be false. Mitigations: detector serial and
  calibration binding, signed-in recorder, append-only readings and audit log, invoice holds as a payment incentive.
* A 95-minute entry cannot be *recorded as a lawful entry* (the trigger rejects it); the real overrun must be reported
  as a `NEAR_MISS` incident. This is deliberate: the log never certifies a violation as compliant.
* Gas freshness is checked at authorisation, not continuously; field instruments must keep monitoring.
* Absence evidence is only as good as the complaint system feeding it; a ULB that never records resolutions is
  invisible to SE1.
* Deleting is restricted: evidence tables (readings, entries, waivers, incidents, audit) cannot be deleted; permits
  with readings cannot be deleted, only cancelled.
* Out of scope: GIS/map UI, real sensor integration (the demo uses typed/simulated readings), payment gateways,
  SMS/e-mail, ULB-scoped visibility (all `ENGINEER`/`SUPERVISOR` users see all ULBs).

## 8. Realistic end-to-end use cases

1. **Normal mechanised job.** Complaint → job → jetting machine `CLEARED` → complaint resolved. Counts toward the
   zero-entry rate; no alert.
2. **Denied, then authorised entry.** Machine `FAILED` → engineer files waiver → supervisor drafts permit with crew,
   tries to authorise → **DENIED** with the exact failing clauses (missing gear, stale `BOTTOM` reading, no standby)
   → supervisor fixes each → **AUTHORISED**.
3. **Overrun blocked.** A worker's entry logged at 95 minutes is rejected by the trigger; an overlapping entry for the
   same worker is rejected by the exclusion constraint.
4. **Shadow entry found.** A complaint is resolved as cleared with no machine log and no permit. After the grace window the
   scan raises an alert and holds the contractor's invoice; an engineer investigates and confirms it.
5. **False positive and late paperwork.** A legitimate machine log is recorded two days late: the alert moves to
   `EVIDENCE_RECEIVED`, the engineer inspects the log and dismisses it with a note; the hold is released.
6. **Fatality.** One transaction opens the ₹30-lakh case with a deadline, blacklists the contractor, aborts the permit
   and holds the invoice; a forced failure mid-way leaves nothing behind.

## 9. Open questions

| # | Question | Provisional answer |
|---|---|---|
| Q1 | Exact rule numbers and the full gear schedule in the 2013 Rules | Cited by name; gear catalogue is editable data (A-09). |
| Q2 | Should resolving a complaint without evidence be *blocked* instead of detected? | Detected: the complaint system belongs to the ULB's legacy process and ZeroEntry must see the gap, not hide it. |
| Q3 | Per-ULB visibility for engineers and supervisors | Not implemented; see ROADMAP backlog. |
