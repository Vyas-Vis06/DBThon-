# ZeroEntry: the judge pitch

**Rehearsal order:** opening → problem → people → product → demonstration → database → close.
The main script is **641 spoken words**: about five minutes at 125–140 words per minute, plus time for pauses and live clicks.
The [cue card](PITCH_CUE_CARD.md) condenses the story into six beats. The technical continuation is
optional: use it when the panel invites detail or when the allotted time permits.

Spoken paragraphs are written to be said aloud. Bracketed cues are directions, not part of the speech.
The opening describes a hypothetical workflow; it is not a reported incident. No real death statistics or
claims of field impact are needed to make the problem clear.

## Main pitch: earn their attention before explaining the schema

### 0:00–0:35 · The hook

[Start on the project title or dashboard. Speak slowly. Pause after the question.]

“A sewer complaint is marked **‘cleared.’** The contractor has submitted an invoice.

But there is no record of a machine clearing it. There is no authorized entry with a logged worker behind it.

Would you approve the payment?

That missing record cannot tell us exactly what happened. But it gives us a question that a ‘completed’ status
cannot answer: **what evidence supports this work?**

That is the question behind our project, ZeroEntry.”

### 0:35–1:20 · The problem and the people

“Sewer work brings together a worker, a supervisor, a contractor, and a municipal authority. Each holds a different part of the story.

The difficulty is connecting those records so decisions account for the whole job.

A sanitation worker faces the physical risk. A supervisor must decide whether conditions support entry.
An engineer or auditor must be able to explain the work afterward.

This matters because a decision happens at the site, while its evidence may arrive later. A system needs to
handle both the immediate decision and the later accountability.”

### 1:20–2:10 · Introduce the solution through three questions

“ZeroEntry is a municipal safety and accountability prototype built around three questions.

First: **can this worker be authorized to enter?** We start with mechanised cleaning. Exceptional human entry
needs an approved reason, a valid crew, the required configured gear, and fresh gas readings at three depths.
If a required check fails, the database denies authorization and explains why.

Second: **what should have been recorded if the work was completed?** We check a resolved complaint against
its machine or permit evidence.

Third: **what happens when evidence is missing?** The system raises a reviewable alert and holds the relevant
unpaid invoices. Late paperwork goes to a human reviewer. It does not silently erase the concern.”

### 2:10–3:00 · Let the product make the point

[Open the seeded DRAFT permit on CHN-ADY-010. Ask for authorization. Keep the checklist visible.]

“Here is a permit that looks ready to process. But the database says no.

It tells us what is missing: the standby crew member, required gear, and the depth readings. The supervisor has specific reasons to act on.

Once those records are complete and the configured checks pass, authorization becomes possible. The system
saves the evidence and policy values that supported that decision.

[Show an alert and its invoice hold; avoid spending this section filling every form.]

Here is the other side: a cleared complaint with an evidence gap. Its alert and invoice hold keep the question
visible until an engineer reviews it.

We are checking recorded evidence. A missing row is a reason to investigate, not proof that a person entered.”

### 3:00–4:00 · Why this is a database project

[Show the architecture diagram, then the entry-gate part of the ER diagram.]

“Now, why put the database at the center?

Because a safety rule should hold when the record changes, whichever application makes that change.

Our browser interface presents the workflow. FastAPI authenticates the user and passes the request on.
PostgreSQL decides whether the stored transition is allowed.

The same gate guards ordinary direct SQL updates, so changing the screen cannot bypass the permit checks.
Transactions keep incident consequences together. Locks coordinate competing decisions. Row-level security
limits workers and contractors to their own records.

The key relationship here is the permit crew: gear and entry records belong to a worker **on that permit**,
not just to a worker somewhere in the system.

That gives us the bridge into the database design: how do we prove that **every required record exists**,
and how do we find a completion claim whose expected records do not?”

### 4:00–4:45 · Evidence and close

“We tested those questions on real PostgreSQL with synthetic records, invalid writes, and concurrent requests.
In the published evaluation, the database refused all eighteen listed invalid-write probes. In twenty late-paperwork
cases, the alerts remained under review and their invoices stayed held.

Those results demonstrate the tested software behavior. Field validation and authenticated instruments are
the next step.

ZeroEntry brings the permit, the completion evidence, and the financial review into one connected workflow.
Our aim is that a worker’s entry has a recorded basis, and a claim of completion has evidence someone can inspect.

**A complaint can be closed. The question of how it was cleared should still have an answer.**”

[If more technical discussion is expected, continue below. Otherwise pause and invite the panel’s questions.]

## The segue into deeper database detail

Use this immediately after “every required record exists,” if the panel wants database depth before the close:

“Let me show you how those two questions become database operations. The first is an **‘all’ question**:
does every entrant have every required gear item? The second is a **‘missing’ question**: which resolved
complaints have no timely evidence? That is where our relational model does the work.”

Then use the technical continuation. Keep the main close for the end.

## Optional technical continuation: about three minutes

### 1 · Model the relationship before writing the check

[Show `entry_permit`, `permit_crew`, `worker`, `gear_issue`, and `entry_log` in the ER diagram.]

“The database has thirty-five application tables, but the most useful relationship to start with is this one.
One permit has several crew members, and a worker can serve on different permits. `permit_crew` joins them,
with a composite key of permit and worker, plus that person’s role.

Gear issues and entry logs reference that membership. A foreign key therefore rejects a record for someone
who is not on the permit’s crew. Contractor details stay in the contractor table; worker details stay in the
worker table. That avoids copying current facts into every job. Where we retain history, such as the original
authorization explanation, the snapshot is deliberate.”

### 2 · Turn ‘everyone has everything’ into relational division

[Show the checklist or the annotated division query.]

“Counting gear rows is insufficient: duplicates or the wrong items could give us the right count.
Instead, we look for an entrant and a required gear item with no matching issue. If any such pair exists,
the gear check fails. That is relational division, expressed with nested `NOT EXISTS`.

The gas checks select the latest reading at each required depth and check freshness, limits, and detector
calibration. An older safe reading cannot hide a newer unsafe one. The authorization function returns an
explanation, and the transition trigger enforces the gate on ordinary database writes as well.”

### 3 · Define expected evidence before looking for absence

[Show an SE1 alert and the evidence deadline.]

“For detection, we start from eligible resolved complaints, including ones that have no job at all. An
anti-join finds the missing timely machine or permit evidence across all their jobs. Exempt resolutions do
not require that evidence, and the grace window allows legitimate delayed recording.

We distinguish the reported event time from the server’s final-outcome receipt. Backdating the claimed work
does not make late evidence timely. A unique complaint-and-rule key keeps scans idempotent, and alert history
preserves the review. Late evidence can move an alert to `EVIDENCE_RECEIVED`; a human decides its outcome.”

### 4 · Keep the decision valid when requests overlap

[Use the conditions deck or the isolated showcase output.]

“A correct check can still fail if someone changes its evidence at the same time. Permit and evidence writers
use a shared lock protocol so authorization and crew changes cannot pass on contradictory states.

An exclusion constraint prevents overlapping recorded entries for a worker. Financial locks serialize holds
and payments. The incident procedure records its configured consequences in one transaction; a forced failure
rolls those changes back together.

Finally, an immutable authorization snapshot preserves its policy revisions and evidence, with a database
digest for checking the saved artifact. It is a local integrity check within the trusted database boundary.

That is the database contribution: relationships define the evidence, SQL evaluates it, and constraints,
triggers, and transactions keep the resulting records consistent.”

## Ninety-second fallback

“A sewer complaint is marked ‘cleared,’ and the contractor asks to be paid. But there is no machine-clearance
record and no authorized entry with a logged worker. What evidence supports the work?

That is the question behind ZeroEntry.

The people affected are sanitation workers, their supervisors, municipal engineers, and auditors. They need
both a basis for the decision before entry and records they can review afterward.

Our prototype connects three things. Before exceptional human entry, the database checks the approved waiver,
crew, gear, and fresh gas readings. If a configured requirement is missing, authorization is denied with reasons.
After completion, it checks whether the expected machine or permit evidence exists. Missing or late evidence
creates an alert and an invoice hold, with a human deciding the case.

The browser shows the workflow, FastAPI authenticates the request, and PostgreSQL owns the rules. A raw SQL
update faces the same permit gate. Transactions keep consequences together, and locks coordinate competing writes.

We have tested the prototype on synthetic records, including invalid writes and transaction races. It checks
recorded evidence; field validation is the next step.

A complaint can be closed. The question of how it was cleared should still have an answer.”

## Rehearsal and demo notes

- **Open with the question, not the technology list.** Let the panel consider approving that invoice before naming ZeroEntry.
- **Use the same thread throughout:** permit → evidence → review/payment. Avoid trying to introduce all 35 tables aloud.
- **Say “configured checks” and “suspected entry.”** This keeps the pitch aligned with what the prototype demonstrates.
- **Use two application screens in the main pitch, plus the diagrams:** the denied permit and one alert with its hold. Move form-filling and long SQL
  output to the technical discussion. For a prepared compliant permit or unsafe-reading demonstration, use the
  [verified demo sequence](development/DEMO_SCRIPT.md).
- **Prepare the visuals:** use the [architecture overview](diagrams/zeroentry-overview.svg) and
  [entry-gate ER export](diagrams/er-entry-gate.svg). The [current screenshots](img/README.md) are a fallback if the live demo is unavailable.
- **Keep a terminal fallback:** `python run.py showcase` runs 19 conditions in independent throwaway databases.
  The [commands guide](guide/DEMO_COMMANDS.md) and [conditions deck](guide/ZeroEntry_Conditions.pptx) explain the cases.
- **Respect rehearsal timing:** admission uses the configured 06:00–18:00 IST window and fresh readings. The isolated
  showcase explicitly widens the synthetic daylight window in its own copies. See the [judge’s guide](guide/README.md).
- **If interrupted, answer the question and return to the next story beat.** The technical continuation is optional;
  the opening, three questions, and closing are the core to remember.

## Short answers to likely interruptions

| Judge asks | Say |
|---|---|
| Why a database rather than another dashboard? | “The dashboard displays the decision. PostgreSQL enforces it across ordinary writers and links it to the evidence and financial records.” |
| Does missing evidence prove illegal entry? | “No. It creates a suspicion for review. We model exemptions, deadlines, and late evidence explicitly.” |
| What if the gas value is false? | “The prototype binds a recorded reading to a detector and recorder; it cannot authenticate physical truth. Real instrument integration is pilot work.” |
| What is distinctive? | “The tested integration of permit decisions, time-aware absence detection, human review, and source-specific invoice holds. The individual SQL techniques are established.” |
| Can a database administrator bypass it? | “A privileged owner remains trusted. The controls apply to ordinary writers and the least-privilege runtime; the saved digest has no external anchor.” |
| How far along is it? | “A working laboratory prototype with synthetic evaluation; self-assessed TRL 4. Field and domain validation remain.” |

## Claim receipts and further reading

| Pitch statement | Source |
|---|---|
| Mechanised-first workflow, configured entry checks, six roles, and field limitations | [PROJECT_SPEC.md](../PROJECT_SPEC.md) |
| 35 application tables, crew membership, division, anti-join, transaction design | [DATABASE_DESIGN.md](DATABASE_DESIGN.md), [TABLE_GUIDE.md](TABLE_GUIDE.md), [ER_DIAGRAM.md](ER_DIAGRAM.md) |
| Browser → FastAPI → PostgreSQL; least privilege and request transactions | [ARCHITECTURE.md](ARCHITECTURE.md), [SECURITY.md](../SECURITY.md) |
| All 18 listed probes refused; 20 late-paperwork cases retained with invoices held | [Published M6 results](EVALUATION_RESULTS.md), run dated 7 October 2026 on `7893c09`; synthetic scope and stated baseline |
| Receipt-time handling and SE1-only supplementary measurements | [Temporal results](evaluation/RESULTS.md), [evaluation method](EVALUATION.md) |
| Bounded differentiation, source classifications, and assumptions | [POLICY_AND_PRIOR_ART.md](POLICY_AND_PRIOR_ART.md) |
| Rubric mapping, SDGs, and TRL | [SUBMISSION.md](SUBMISSION.md) |
| Detailed prepared judge questions | [JUDGE_QA.md](guide/JUDGE_QA.md) |

The evaluation statements above describe the published runs. They are not a fresh benchmark of the current
checkout, a field-accuracy claim, or evidence that injuries have been prevented.
