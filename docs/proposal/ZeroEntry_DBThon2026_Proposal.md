# ZeroEntry: A Default-Deny Database that Enforces India's Sewer-Safety Law Before Anyone Enters a Manhole

**DBThon 2026 · VIT SCOPE · Database Systems Lab (BCSE302P)**
**Track:** 7, Safety & Security (also fits 8, Smart Community & Civic Life)
**Prepared:** 2 October 2026

---

## 1. Submission block (paste-ready)

**Title:** ZeroEntry: A Default-Deny Database that Enforces India's Sewer-Safety Law Before Anyone Enters a Manhole

**Novelty (49 words):**
> India's sewer-safety law defines the crime as missing safeguards; ZeroEntry turns that definition into database integrity. Manhole entry stays denied until relational division proves every statutory safeguard is present and current. Anti-joins expose unrecorded entries hiding behind closed complaints; a death atomically opens ₹30-lakh compensation and blacklists the contractor.

**Abstract (234 words):**
> Since 1993, 1,248 Indians have died cleaning sewers and septic tanks, and Tamil Nadu leads every state with 253. A 2022–23 government social audit found that in 49 of 54 deaths, workers had no safety gear at all. The law already says what must exist before anyone goes down: the 2013 Manual Scavengers Act defines "hazardous cleaning" as entry without the prescribed gear and precautions, and the Rules and CPHEEO SOP specify them (oxygen 19.5–21% tested at three depths, at least three persons including a supervisor, mechanised cleaning ruled out in writing). Yet these checks live on paper, and existing systems (NAMASTE worker profiling, DIGIT desludging, industrial permit-to-work tools) never refuse an entry. ZeroEntry is a PostgreSQL-backed municipal platform for engineers, supervisors, workers, contractors and auditors. Every blockage is routed mechanised-first; manual entry is an exception the database must be convinced of. A stored procedure authorises entry only when relational-division queries prove each entrant holds every statutory gear item, a calibrated detector logged in-limit readings at all three depths within 15 minutes, and a distinct standby and supervisor are present. Otherwise it returns the exact legal clause that failed. Triggers enforce daylight and 90-minute limits; exclusion constraints block overlapping entries. Anti-join views flag complaints closed with neither machine log nor permit, and hold contractor invoices. Recording a fatality runs one transaction that opens a ₹30-lakh compensation case with a deadline and blacklists the contractor.

---

## 2. The one-line idea (for a newcomer)

Indian law already lists what must be true before a person may enter a sewer: the right gear, safe gas levels, enough people on the surface, and no machine able to do the job. ZeroEntry stores those requirements as data and refuses to authorise entry unless the database itself can **prove** each one. When something goes wrong, the database also **enforces the consequences**: compensation, a deadline, and blacklisting the contractor.

**Analogy:** a bank's database will not let your balance go negative, however hard the teller presses the button. ZeroEntry gives sewer entry the same kind of rule. The safety law becomes a constraint the system cannot skip, not a checklist on a clipboard.

---

## 3. The problem: real, current, and local

| Evidence | Figure | Source |
|---|---|---|
| Deaths in sewer/septic-tank cleaning since 1993 (Rajya Sabha, 28 Nov 2024) | **1,248**; **Tamil Nadu highest at 253**, ahead of Gujarat 183, UP 133, Delhi 116 | [ETV Bharat](https://www.etvbharat.com/en/!bharat/1248-people-died-cleaning-sewer-and-septic-tanks-since-1993-government-enn24112805405) |
| Deaths 2019 to Jun 2026 (Lok Sabha, 5 Aug 2026, citing NCSK) | **498** (2023: 65 · 2024: 54 · 2025: 47 · Jan–Jun 2026: 16) | [Business Standard](https://www.business-standard.com/india-news/sanitation-workers-sewer-septic-tank-cleaning-deaths-since-2019-126080500881_1.html) |
| Government-commissioned social audit of 54 deaths (2022–23, 8 states) | **49 of 54** had no safety equipment at all; consent missing in 27; only 2 involved machines | [The Hindu via VisionIAS summary, 23 Jul 2025](https://visionias.in/current-affairs/upsc-daily-news-summary/article/2025-07-23/the-hindu/society/in-over-90-of-sewer-deaths-workers-had-no-safety-gear-government-audit) |
| Supreme Court, *Balram Singh v. Union of India* (20 Oct 2023) | ₹30 lakh death compensation; ₹10–20 lakh for disability; contract cancellation; portal/dashboard directions | [LiveLaw](https://www.livelaw.in/amp/top-stories/ensure-manual-sewer-cleaning-is-completely-eradicated-read-14-directions-issued-by-supreme-court-against-manual-scavenging-240749) |
| Supreme Court, 27 Jul 2026 | Contempt notices to state Chief Secretaries over continuing deaths | [LiveLaw](https://www.livelaw.in/top-stories/supreme-court-raises-concern-over-recurring-manual-scavenging-deaths-issues-contempt-notices-to-5-state-chief-secretaries-543038) · [Courtbook](https://courtbook.in/posts/supreme-court-issues-contempt-notices-to-15-states-over-continued-manual-scavenging-deaths-despite-earlier-directions) |
| Compensation lag (Lok Sabha, 13 Dec 2022) | e.g. 2019: only 87 of 117 families compensated | [SabrangIndia](https://sabrangindia.in/zero-reported-deaths-due-manual-scavenging-ramdas-athawale/) |
| Tamil Nadu example: Tiruppur, 19 May 2025 | 3 workers asphyxiated in a dyeing-mill sewage tank; NHRC suo motu notice for work "without safety gear" | [NHRC](https://nhrc.nic.in/node/122374) |
| Data quality | Official counts for 2017 onward fell by 46 cases (6.9%) between Feb and Mar 2026 | [Dataful](https://insights.dataful.in/articles/sewer-worker-deaths-continue-despite-ban-and-safety-policies) |

**Why it persists.** The rules exist but nothing *enforces* them at the moment of entry:
- Gas tests are optional in practice.
- Gear is "available" but not issued to the person going in.
- Permission is verbal.
- Deaths surface only after the fact, often under-counted.

Note that Parliament answers from different years disagree on the same year's count. We cite one answer per figure and name it.

### Users
- **Municipal engineers (ULB / Metro Water):** raise jobs and approve mechanisation waivers. The SOP calls this person the "head of local authority / Responsible Sanitation Authority".
- **Site supervisors:** run the permit, log gas readings, and confirm the crew.
- **Sanitation workers:** see their own permits and gear, and can trigger a **stop-work** refusal.
- **Contractors:** see only their own jobs and invoices.
- **Auditors (NCSK / district vigilance / NHRC-style):** read-only access to the shadow-entry and compensation dashboards.
- **Admin:** manages users, roles and the rule parameters.

---

## 4. The core insight: the law is already a database query

Section 2(1)(d) of the *Prohibition of Employment as Manual Scavengers and their Rehabilitation Act, 2013* defines **"hazardous cleaning"** as manual cleaning of a sewer or septic tank **without** the employer providing the protective gear, devices and precautions the rules require. Section 7 prohibits it and Section 9 makes it punishable with imprisonment, a fine, or both ([Act text](https://lddashboard.legislative.gov.in/sites/default/files/A2013-25.pdf)).

So the offence is defined by **absent records**. In relational terms, *"for every required safeguard, there must exist a matching record"* is **relational division** (∀ = NOT EXISTS … NOT EXISTS). And *"an event with no matching record"* is an **anti-join**. ZeroEntry is built on exactly these two operations.

| Legal / SOP requirement | Source | ZeroEntry database mechanism |
|---|---|---|
| Entrant must have **all** prescribed protective gear (breathing apparatus, 4-gas monitor, harness, helmet with lamp, wader suit, etc.) | 2013 Rules (protective-gear schedule) | `gear_item(statutory=true)` table + **relational division** over `gear_issue` for each entrant |
| Atmosphere tested at **top, middle and bottom**; O₂ 19.5–21% | 2013 Rules; CPHEEO SOP 2018 | Division over the three depth levels: each needs a reading **≤ 15 min old** and in limits |
| H₂S < 10 ppm, combustibles < 10% LEL | MoHUA ERSU advisory 2019 | Limits stored in the `rule_parameter` table (law as data, editable without code) |
| Detector must be valid | Good practice / ERSU book | FK to `gas_detector`; trigger rejects readings from a detector past `calibration_valid_until` |
| At least 3 persons including a supervisor; standby "top man" who does **not** enter | 2013 Rules; ERSU book | `permit_crew` roles + CHECK/trigger: standby ≠ entrant, count ≥ 3, supervisor present |
| Manual entry only after the local-authority head records reasons in writing | CPHEEO SOP 2018 | `mechanisation_waiver` (1:1 with job, approver must hold the RSA role, minimum-length justification) |
| Daylight only; max 90 min continuous work, then rest | 2013 Rules / ERSU | Trigger on `entry_log`; **exclusion constraint** on `tstzrange` blocks overlapping entries for a worker |
| Death means ₹30 lakh compensation, contract cancellation | SC, *Balram Singh* 2023 | `record_incident()` **transaction**: incident + compensation case + blacklist + invoice hold, all-or-nothing |

---

## 5. Novelty and prior art

### 5.1 What exists today (and what it does not do)

| System | What it does | What it lacks | Source |
|---|---|---|---|
| **NAMASTE BMS app/portal** (MoSJE, 2023) | Profiles and validates sewer/septic workers (84,902 validated by Aug 2025), PPE kit and insurance linkage, fatality upload | No per-job permit, no gas gate, no standby check; **never refuses an entry** | [Guideline](https://sudawb.org/assets/guideline/NAMASTE%20Scheme%20Guideline.pdf) · [PIB](https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/sep/doc2025910632601.pdf) |
| **DIGIT Sanitation / Odisha SUJOG-Garima** | Worker registry, assigns workers to desludging requests | Its own PRD says safety-equipment data "may not be accurate"; no gas or entry gating | [PRD](https://docs.digit.org/sanitation/reference-implementations/odisha-sujog/functional-customisation/garima-implementation/product-requirement-document-prd) |
| **Industrial permit-to-work tools** (IntelliPERMIT, EHS4Safety, etc.) | Confined-space permits, competency checks, audit trails | Built for factories and oil & gas; no municipal or Indian-statute model; no compensation or blacklisting workflow; no shadow-entry detection | [IntelliPERMIT](https://www.intellipermit.com/blog/confined-space-entry/) |
| **Genrobotics Bandicoot / G-Crow** | Robotic manhole cleaning with gas sensors and a monitoring app | Replaces humans where deployed; does **not govern the humans who still enter** | [YourStory](https://yourstory.com/socialstory/2025/01/kerala-startup-robots-manual-scavenging-maha-kumbh) |
| **Telangana Project SHUDH** (Jul 2026) | AI/GIS/robotics network monitoring to prevent manual entry | No worker permit or compensation workflow found | [Deccan Chronicle](https://www.deccanchronicle.com/southern-states/telangana/telangana-unveils-project-shudh-to-eliminate-manual-sewer-entry-1970226) |
| **TN Municipal Laws (Amendment) Act 2022** | Licensing of desludging operators, log books, GPS, fines | A paper-and-GPS regime, not an entry gate | [PRS](https://prsindia.org/files/bills_acts/acts_states/tamil-nadu/2022/ActNo34of2022TamilNadu.pdf) |
| **IoT gas-helmet / smart-drain projects** (e.g. EPJ Web Conf. 2026) | Detect gas and raise an alert | Alerts only; no authorisation, crew or legal model | [EPJ](https://www.epj-conferences.org/articles/epjconf/pdf/2026/23/epjconf_riact2026_03008.pdf) |

### 5.2 Our novelty claims

1. **Law-as-integrity.** The statutory definition of "hazardous cleaning" is encoded as relational division over versioned rule tables. Entry authorisation is a *database-proven* state, not a UI checkbox. We found no municipal or industrial system that models the Indian statute this way.
2. **Explainable denial.** `authorise_entry()` returns **which clause failed** (e.g. *"Entrant W-17 missing statutory item: 4-gas monitor · BOTTOM reading 22 min old · standby not distinct"*). A denial becomes a compliance report.
3. **Shadow-entry detection by absence.** An anti-join view finds blockage complaints marked *resolved* with **neither** a successful machine deployment **nor** a closed permit. These are likely unrecorded manual entries, which is exactly where the audit says deaths happen. Contractor invoices on such jobs are held automatically. We found no prior system that uses missing records to detect unrecorded entries.
4. **Consequence atomicity.** One ACID transaction turns a fatality record into a compensation case (₹30 lakh, deadline from a rule parameter), contractor blacklisting, permit abort and invoice hold. If any part fails, nothing commits, so a death cannot be half-recorded.

### 5.3 What we do **not** claim
- Gas detection, permit-to-work software and worker registries are **not** new. Our novelty is the *combination*, the *Indian-statute model*, the *absence-based audit* and the *consequence transaction*.
- The database cannot verify that a typed gas reading is physically real. We mitigate this with detector serials and calibration validity, a supervisor's digital sign-off, and a simulated sensor feed in the demo. Payment gating gives contractors a reason to record honestly.
- "We found no system that…" is based on our search, not proof that none exists.

### 5.4 Why this stands out from the current DBThon field
The 15 teams registered so far cluster around disaster resource allocation (2), batch recall genealogy (2), recycling, grievances, food redistribution, fraud rings, land records, prescriptions, lending and lost & found. **None addresses occupational safety or sewer deaths.** Several say "rules live in the database". ZeroEntry goes further: the rules are **the law itself, kept as data**, and the system proves compliance through classic relational algebra (division and anti-join) that DBMS faculty will recognise at once.

---

## 6. Database design

### 6.1 Primary entities (≥4) and key relationships (≥3)
**Primary entities:** Manhole/Asset, Complaint, Job, Worker, Contractor, Entry Permit, Gas Detector, Incident.

**Meaningful relationships:**
1. *Complaint* **generates** *Job* (1:N).
2. *Job* **is executed by** *Machine Deployment* **or** authorised through *Entry Permit* (1:N / 1:0..1).
3. *Entry Permit* **has crew** *Worker* in a role (M:N via `permit_crew`).
4. *Worker* **is issued** *Gear Item* under a permit (ternary via `gear_issue`).
5. *Gas Detector* **records** *Gas Reading* for a permit at a depth level (1:N).
6. *Incident* **creates** *Compensation Case* (1:1) and **blacklists** *Contractor*.

### 6.2 Relational schema (PostgreSQL 16, 3NF, 20 tables)

| # | Table | Key columns (PK **bold**, FK *italic*) | Notable constraints |
|---|---|---|---|
| 1 | `role` | **role_id**, name | UNIQUE(name) |
| 2 | `app_user` | **user_id**, *role_id*, *ulb_id*, email, password_hash | UNIQUE(email); bcrypt hash only |
| 3 | `ulb` (urban local body / zone) | **ulb_id**, name, district, state | — |
| 4 | `manhole` | **manhole_id**, *ulb_id*, type (SEWER/SEPTIC), depth_m, lat, lng | CHECK(depth_m > 0) |
| 5 | `complaint` | **complaint_id**, *manhole_id*, raised_at, status, resolved_at | CHECK(resolved_at ≥ raised_at) |
| 6 | `contractor` | **contractor_id**, licence_no, licence_valid_until, status | UNIQUE(licence_no); status ∈ {ACTIVE, SUSPENDED, BLACKLISTED} |
| 7 | `worker` | **worker_id**, *contractor_id*, namaste_id, medical_fit_until, trained_until | UNIQUE(namaste_id) |
| 8 | `job` | **job_id**, *complaint_id*, *contractor_id*, method, status | method ∈ {MECHANISED, MANUAL_EXCEPTION} |
| 9 | `machine` | **machine_id**, *ulb_id*, type (JETTING/SUCTION/ROBOT), status | — |
| 10 | `machine_deployment` | **deploy_id**, *job_id*, *machine_id*, started_at, ended_at, outcome | outcome ∈ {CLEARED, FAILED} |
| 11 | `mechanisation_waiver` | **waiver_id**, *job_id*, reason_code, justification, *approved_by* | UNIQUE(job_id); length(justification) ≥ 50; approver must hold RSA role (trigger) |
| 12 | `entry_permit` | **permit_id**, *job_id*, *supervisor_id*, status, authorised_at, valid_until | status state machine (trigger); permit only if a waiver exists |
| 13 | `permit_crew` | **(permit_id, worker_id)**, crew_role | crew_role ∈ {ENTRANT, STANDBY, SUPERVISOR} |
| 14 | `gear_item` | **gear_code**, name, statutory | — |
| 15 | `gear_issue` | **issue_id**, *permit_id*, *worker_id*, *gear_code*, serial_no | UNIQUE(permit_id, worker_id, gear_code) |
| 16 | `gas_detector` | **detector_id**, serial_no, calibration_valid_until | UNIQUE(serial_no) |
| 17 | `gas_reading` | **reading_id**, *permit_id*, *detector_id*, depth_level, o2_pct, h2s_ppm, lel_pct, co_ppm, taken_at | depth ∈ {TOP, MID, BOTTOM}; CHECK(o2_pct BETWEEN 0 AND 100) |
| 18 | `entry_log` | **entry_id**, *permit_id*, *worker_id*, period tstzrange | **EXCLUDE USING gist (worker_id WITH =, period WITH &&)**; duration ≤ 90 min |
| 19 | `incident` → `compensation_case` | **incident_id**, *permit_id*, *worker_id*, type, occurred_at → **case_id**, *incident_id*, amount_due, due_by, paid, status | UNIQUE(incident_id) on case |
| 20 | `invoice`, `rule_parameter`, `audit_log` | **invoice_id**, *job_id*, status · **param_key**, value, legal_ref · **log_id** (append-only) | REVOKE UPDATE/DELETE on audit_log |

**Normalisation:**
- Gear requirements, thresholds and legal references live in their own tables, not repeated per permit.
- Crew roles are an M:N relation, not repeated columns.
- No transitive dependencies: a contractor's status lives only in `contractor`, never copied into `job`.

All tables are in 3NF/BCNF.

### 6.3 The four signature queries

**(a) Relational division: does every entrant hold every statutory gear item?**
```sql
SELECT pc.worker_id
FROM permit_crew pc
WHERE pc.permit_id = :pid AND pc.crew_role = 'ENTRANT'
  AND EXISTS (                       -- at least one missing item → violation
    SELECT 1 FROM gear_item g
    WHERE g.statutory
      AND NOT EXISTS (SELECT 1 FROM gear_issue gi
                      WHERE gi.permit_id = pc.permit_id
                        AND gi.worker_id = pc.worker_id
                        AND gi.gear_code = g.gear_code));
```

**(b) Division over depth levels: fresh, in-limit readings at TOP, MID and BOTTOM from a calibrated detector.**
```sql
SELECT d.level FROM (VALUES ('TOP'),('MID'),('BOTTOM')) d(level)
WHERE NOT EXISTS (
  SELECT 1 FROM gas_reading r JOIN gas_detector gd USING (detector_id)
  WHERE r.permit_id = :pid AND r.depth_level = d.level
    AND r.taken_at > now() - interval '15 minutes'
    AND gd.calibration_valid_until >= current_date
    AND r.o2_pct BETWEEN 19.5 AND 21.0
    AND r.h2s_ppm < 10 AND r.lel_pct < 10);   -- thresholds read from rule_parameter in the real function
```

**(c) Anti-join view: suspected shadow entries.**
```sql
CREATE VIEW v_suspected_shadow_entry AS
SELECT c.complaint_id, c.manhole_id, j.contractor_id, c.resolved_at
FROM complaint c JOIN job j ON j.complaint_id = c.complaint_id
WHERE c.status = 'RESOLVED'
  AND NOT EXISTS (SELECT 1 FROM machine_deployment m
                  WHERE m.job_id = j.job_id AND m.outcome = 'CLEARED')
  AND NOT EXISTS (SELECT 1 FROM entry_permit p
                  WHERE p.job_id = j.job_id AND p.status = 'CLOSED');
```

**(d) Consequence transaction: `record_incident()`**
```sql
BEGIN;
  INSERT INTO incident(...) RETURNING incident_id;              -- the fact
  INSERT INTO compensation_case(incident_id, amount_due, due_by) -- ₹30,00,000; deadline from rule_parameter
  UPDATE contractor SET status = 'BLACKLISTED' WHERE ...;        -- Balram Singh direction
  UPDATE entry_permit SET status = 'ABORTED' WHERE ...;
  UPDATE invoice SET status = 'ON_HOLD' WHERE job_id = ...;
  INSERT INTO audit_log(...);
COMMIT;   -- any failure → ROLLBACK, nothing half-recorded
```

---

## 7. Coverage of all 23 DBThon requirements

| # | Requirement | Where in ZeroEntry |
|---|---|---|
| 1 | ER diagram | Section 6.1 entities and relationships (Chen + crow's-foot diagram in the build) |
| 2 | Relational schema | Section 6.2 |
| 3 | ≥ 8 related tables | 20 tables |
| 4 | ≥ 4 primary entities | Manhole, Complaint, Job, Worker, Contractor, Entry Permit, Gas Detector, Incident |
| 5 | ≥ 3 meaningful relationships | Six, including M:N crew and ternary gear issue |
| 6 | PK and FK | Every table; composite PK on `permit_crew` |
| 7 | Constraints | CHECK, UNIQUE, NOT NULL, **EXCLUDE** (overlap), state-machine triggers |
| 8 | 3NF+ | Section 6.2 normalisation note |
| 9 | CRUD | Complaints, jobs, workers, gear, permits, contractors |
| 10 | Multi-table JOINs | Permit dossier (permit ⋈ crew ⋈ worker ⋈ gear ⋈ readings ⋈ detector) |
| 11 | Aggregates | Deaths and incidents per ULB per year; % jobs mechanised; mean days to compensation; contractor risk score |
| 12 | VIEW | `v_suspected_shadow_entry`, `v_permit_compliance`, `v_compensation_overdue` |
| 13 | Transaction | `record_incident()`; permit authorisation with `SELECT … FOR UPDATE` |
| 14 | Trigger | Detector-calibration check, permit state machine, 90-min/daylight rule, append-only audit |
| 15 | Stored procedure/function | `authorise_entry(permit_id)` returns AUTHORISED or the list of failed legal clauses; `record_incident()` |
| 16 | Indexes | (permit_id, depth_level, taken_at DESC) on readings; GiST on `entry_log.period`; partial index on `complaint(status='RESOLVED')`; FK indexes |
| 17 | ORM | SQLAlchemy 2.0 models + Alembic migrations; procedures called through the ORM session |
| 18 | Authentication | bcrypt password hashes + JWT (short-lived access token) |
| 19 | ≥ 2 roles | Admin, Engineer/RSA, Supervisor, Worker, Contractor, Auditor |
| 20 | RBAC | App-level route guards **plus PostgreSQL Row-Level Security** (a contractor sees only their own rows; an auditor is read-only) |
| 21 | Search and filtering | Filter permits by status, ULB, date and contractor; search workers by NAMASTE ID; shadow-entry filter by zone |
| 22 | Validation and exceptions | Pydantic input schemas; DB exceptions mapped to readable legal messages |
| 23 | Secrets | `.env` / Docker secrets, no credentials in code; least-privilege DB role for the app; parameterised queries only |

---

## 8. Hackathon build plan (24 hours, 7–8 Oct)

**Stack:**
- Backend: PostgreSQL 16 (Docker), FastAPI, SQLAlchemy 2 and Alembic.
- Frontend: React (Vite) or Jinja + HTMX.
- Synthetic seed data: 3 Chennai zones, 60 manholes, 40 workers, 5 contractors, 2 detectors (one expired).

| Hours | Deliverable |
|---|---|
| 0–4 | Schema, constraints, seed data, ER diagram |
| 4–10 | `authorise_entry()`, triggers, exclusion constraint, views, `record_incident()` |
| 10–16 | FastAPI + ORM, JWT auth, RLS policies, CRUD endpoints |
| 16–21 | UI: permit wizard with red/green clause checklist, shadow-entry map/table, compensation dashboard |
| 21–24 | Demo script rehearsal, indexes with EXPLAIN ANALYZE screenshots |

**Three-minute demo:**
1. A complaint is routed to a jetting machine, which fails.
2. The engineer files a waiver.
3. The supervisor tries to authorise and is **DENIED**, with three legal reasons shown.
4. The supervisor fixes the gear, takes a fresh BOTTOM reading and adds a distinct standby: **AUTHORISED**.
5. A worker is logged at 95 minutes and the trigger blocks it.
6. The auditor dashboard shows 4 resolved complaints with no machine and no permit, and their invoices on hold.
7. An incident is recorded. In one transaction a ₹30 lakh case opens, the contractor is blacklisted and the invoice is held. A forced failure then shows a full rollback.

---

## 9. Anticipated judge questions

- **"Doesn't this legitimise manual entry, which the law wants eliminated?"** No. It is default-deny and mechanised-first. Manual entry is only possible as a documented exception, which is exactly the SOP's own "CEO records reasons in writing" clause. Every exception is counted, so the ULB's mechanisation rate becomes measurable.
- **"Most deaths happen with no paperwork at all."** That is why the shadow-entry anti-join and invoice hold exist. They target the *unrecorded* jobs that a normal permit system cannot see.
- **"Can't a supervisor just type fake gas values?"** The database enforces state, not physics. We bind readings to a detector serial with calibration validity, require digital sign-off, and show a simulated sensor feed. The audit log is append-only, so a fabrication leaves a permanent trail.
- **"Why a database and not app code?"** Several apps, contractors and APIs touch the same data. Only database constraints hold for *every* client. A rule enforced in one UI is bypassed by the next.

---

## 10. Alternatives we researched and rejected

| Idea | Why rejected |
|---|---|
| Snakebite antivenom capability routing (about 58,000 deaths a year, eLife 2020) | Strong burden. But national **ZooWIN** already tracks antivenom stock, Kerala's 108 service routes to antivenom hospitals, a GitHub DBMS "antivenom centre finder" exists, and it overlaps two disaster resource-matching teams in the sheet. |
| Rabies vaccine open-vial pooling scheduler | ZooWIN and the GARC Rabies Treatment Tracker cover stock and follow-ups. ICMR revised deaths down to about 5,726 a year, which weakens the hook. |

---

## 11. Sources

- Act 2013 text: https://lddashboard.legislative.gov.in/sites/default/files/A2013-25.pdf
- 2013 Rules (text): https://ielrc.org/content/e1314.pdf
- CPHEEO/MoHUA SOP for cleaning sewers and septic tanks (2018): https://susana.org/_resources/documents/default/3-4912-340-1647806344.pdf
- MoHUA ERSU book (2019): https://sudawb.org/uploads/events/SBM%20ERSU%20Book_Final.pdf
- Rajya Sabha 1,248 deaths and TN 253: https://www.etvbharat.com/en/!bharat/1248-people-died-cleaning-sewer-and-septic-tanks-since-1993-government-enn24112805405
- Lok Sabha Aug 2026 (498 deaths): https://www.business-standard.com/india-news/sanitation-workers-sewer-septic-tank-cleaning-deaths-since-2019-126080500881_1.html
- Social audit 49/54: https://visionias.in/current-affairs/upsc-daily-news-summary/article/2025-07-23/the-hindu/society/in-over-90-of-sewer-deaths-workers-had-no-safety-gear-government-audit
- Balram Singh directions: https://www.livelaw.in/amp/top-stories/ensure-manual-sewer-cleaning-is-completely-eradicated-read-14-directions-issued-by-supreme-court-against-manual-scavenging-240749
- SC contempt notices, Jul 2026: https://www.livelaw.in/top-stories/supreme-court-raises-concern-over-recurring-manual-scavenging-deaths-issues-contempt-notices-to-5-state-chief-secretaries-543038
- Compensation lag 2019: https://sabrangindia.in/zero-reported-deaths-due-manual-scavenging-ramdas-athawale/
- Tiruppur NHRC: https://nhrc.nic.in/node/122374
- Dataful: https://insights.dataful.in/articles/sewer-worker-deaths-continue-despite-ban-and-safety-policies
- NAMASTE guideline: https://sudawb.org/assets/guideline/NAMASTE%20Scheme%20Guideline.pdf · PIB: https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/sep/doc2025910632601.pdf
- DIGIT Garima PRD: https://docs.digit.org/sanitation/reference-implementations/odisha-sujog/functional-customisation/garima-implementation/product-requirement-document-prd
- IntelliPERMIT: https://www.intellipermit.com/blog/confined-space-entry/
- Genrobotics: https://yourstory.com/socialstory/2025/01/kerala-startup-robots-manual-scavenging-maha-kumbh
- Project SHUDH: https://www.deccanchronicle.com/southern-states/telangana/telangana-unveils-project-shudh-to-eliminate-manual-sewer-entry-1970226
- TN Act 34 of 2022: https://prsindia.org/files/bills_acts/acts_states/tamil-nadu/2022/ActNo34of2022TamilNadu.pdf
- EPJ gas sensor paper: https://www.epj-conferences.org/articles/epjconf/pdf/2026/23/epjconf_riact2026_03008.pdf

*Verification note:*
- Statistics are taken from the sources listed. Several are news reports of Parliament answers.
- The rule-level numbering of the 2013 Rules (which rule lists the gear, which sets working conditions) should be checked against the Gazette text before the final presentation.
- The proposal deliberately cites the Rules without rule numbers.
