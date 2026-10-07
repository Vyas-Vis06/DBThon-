# ZeroEntry: rehearsal cue card

Use this to remember the story; the words to say are in [PITCH_SCRIPT.md](PITCH_SCRIPT.md).
Allow about five minutes for speech and extra time for clicks or questions.

## Six beats to remember

| Beat | Anchor phrase | Show |
|---|---|---|
| Hook | **“Cleared. Invoice submitted. Where is the evidence?”** Ask whether they would approve payment. | Title or dashboard; make eye contact for the question. |
| People and problem | **“Worker takes the risk; supervisor decides; engineer reviews.”** The records need to connect at the decision point. | Keep the screen still. |
| Product | **“Before entry. After completion. During review.”** Explain authorization, expected evidence, and source-specific invoice holds. | No table list yet. |
| Demonstration | **“The database says no—and tells us why.”** Then show an evidence gap that remains reviewable. | DRAFT permit on CHN-ADY-010; alert on CHN-ADY-006 and its hold. |
| Database bridge | **“Every required record. Missing expected records.”** The interface asks; PostgreSQL enforces the stored rules. | [Architecture overview](diagrams/zeroentry-overview.svg), then the permit/crew part of [ER_DIAGRAM.md](ER_DIAGRAM.md). |
| Evidence and close | **“18 listed invalid writes refused; 20 late cases still reviewed and held.”** Name the synthetic scope. | Published [evaluation results](EVALUATION_RESULTS.md), if needed. End with the closing line. |

**Closing line:** “A complaint can be closed. The question of how it was cleared should still have an answer.”

## If they ask for database depth

Say: **“Let me show how ‘all’ and ‘missing’ become database operations.”**

Then follow this sequence:

1. **Crew membership:** `(permit_id, worker_id)` binds gear and entries to a worker on this permit.
2. **Relational division:** find any required entrant/item pair without a matching gear issue.
3. **Anti-join:** start with eligible complaints, then find missing timely evidence across all jobs.
4. **Time and review:** final-outcome receipt distinguishes timely from late evidence; late records need a human decision.
5. **Concurrency and atomicity:** locks coordinate evidence, authorization, holds, and payments; an incident transaction rolls back together.
6. **History:** retain the original authorization explanation and policy revisions; the digest is a local integrity check.

Return to the closing line. Use the [technical continuation](PITCH_SCRIPT.md#optional-technical-continuation-about-three-minutes)
for the spoken explanation and [DATABASE_HANDBOOK.md](DATABASE_HANDBOOK.md) for supporting details.

## Prepare the screens before speaking

- Launch an isolated rehearsal: `python run.py --data-dir .pgdata/pitch-rehearsal --port 8010`.
  If that directory already exists, it retains its earlier state; use a new directory for untouched seed scenarios.
- Use **supervisor** for the permit. Rehearse the denial on CHN-ADY-010 and the five failing clauses before the event.
- Use **engineer** for alerts and invoice review. Switching accounts takes time; have the alert location ready.
  The main speech only needs to show the alert and hold. Dismiss it only when demonstrating the review transition.
- Keep the diagrams and this card open separately. The full 35-table ER is a reference; the domain diagram is easier to explain aloud.
- Prepare authorization evidence shortly before showing a passing decision: old readings can become stale.
  For entry/exit demonstrations, remember the configured 06:00–18:00 IST admission window.
- Keep `python run.py showcase` as a terminal fallback. It creates independent throwaway databases and checks 19 conditions.
  Use the [verified command sheet](guide/DEMO_COMMANDS.md) for the complete sequence.

## When time is cut

Use the [90-second version](PITCH_SCRIPT.md#ninety-second-fallback). Preserve the payment question, the three product decisions,
the sentence that PostgreSQL owns the rules, and the closing line. Skip live form-filling and the optional deep dive.

## Three boundaries to say clearly

**Missing evidence is suspicion. Recorded gas is not independently verified physical truth. Published measurements use synthetic data.**
These make the story accurate without interrupting every sentence with qualifications. Exact claim receipts are linked
at the end of [PITCH_SCRIPT.md](PITCH_SCRIPT.md).
