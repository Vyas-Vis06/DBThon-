# Demo script (about 3 minutes)

Use a fresh, isolated synthetic demo directory without resetting an existing database:

```bash
python scripts/dev.py --data-dir .pgdata/presentation-release --port 8000
```

Keep the generated password at hand. For a presentation outside 06:00–18:00 IST, an ADMIN can widen the product daylight
proxy for this synthetic rehearsal only, supplying a reason such as “Synthetic evening presentation, no field operation”.
Show this change in policy history, and explain that astronomical daylight and real instruments remain outside the demo.

## 0:00 · The problem (20 s)

> "Indian law and operational guidance require safeguards for sewer entry. ZeroEntry links a recorded permit decision to municipal completion evidence. Its configured safeguards show their legal, guidance or product-policy basis, and missing records become reviewable gaps."

## 0:20 · Default deny (70 s), as `supervisor@`

1. **Permits** → open the **DRAFT** permit on manhole **CHN-ADY-010**. The checklist shows **5 of 11 clauses failing**: no
   standby; entrant NAM-TN-100002 lacks the breathing apparatus and harness; no TOP, MID or BOTTOM gas reading.
   > "This is relational division: every entrant must hold every configured required item, and every depth needs a fresh, in-limit
   > reading from a calibrated detector."
2. Press **Ask the database to authorise entry** → **denied**, with the five reasons. Nothing was authorised.
3. Fix it through the tabs: **Crew** → add a STANDBY (e.g. NAM-TN-100003); **Gear** → issue the two missing items to
   NAM-TN-100002; **Gas readings** → log TOP, MID and BOTTOM with detector **GD-4G-0001**.
   *Optional:* try detector **GD-4G-0002** first: refused, "calibration expired".
4. Press **Ask the database to authorise entry** again → **AUTHORISED**, valid for 4 hours.
5. Open **Original authorisation**: show the saved policy revisions, classified sources, evidence IDs and digest.
   Log an open entry. Attempt an overlapping entry for the same worker, or close the permit while they are inside: refused.
   Add a BOTTOM reading with O₂ 12%: the database aborts the permit and appends durable safety events. **Record exit** still
   works after the stop. Alternatively run the authenticated synthetic feed (complete crew/gear first):

   ```bash
   python scripts/simulate_gas.py --permit 2 --detector 1 --unsafe-after 2
   ```

   Enter the printed demo password at the hidden prompt. This script posts simulated values as a signed-in supervisor,
   not as an independently authenticated instrument. The original authorization artifact remains unchanged after stop.

## 1:30 · Detection by absence (50 s), as `engineer@`

6. **Shadow entries** → five alerts. Point at one with **no job at all** (CHN-ADY-004):
   > "A complaint closed as cleared, with no machine log and no closed permit with a logged entry. The anti-join finds the
   > records a lawful clearance would have left, and they are not there."
7. Open the alert on **CHN-ADY-006** (status **EVIDENCE_RECEIVED**): its machine log was recorded days late.
   > "Late paperwork never closes an alert by itself; a person decides."
   **Dismiss** it with a note → its invoice hold is released, and only that hold.
8. Press **Run the absence scan now** → nothing new, nothing re-opened (idempotent).

## 2:20 · Consequences (30 s)

9. **Incidents** → the seeded fatality: a ₹30-lakh compensation case with a due date, the contractor blacklisted, in one
   procedure call. In a terminal:

   ```bash
   python scripts/run_sql.py database/queries/06_transactions.sql
   ```

   > "If any step of that procedure fails, nothing is left behind: here is the rollback."

## 2:50 · Close (10 s)

10. **Admin → Policy and sources** (as `admin@`): show a parameter revision and its source classification; the change you made
    is in its revision history and the **Audit log**.
    > "The database owns the configured gate. Policy history explains the decision, and missing evidence remains reviewable."

## If asked "how do you know it is better?" (30 s)

Open [EVALUATION_RESULTS.md](../EVALUATION_RESULTS.md) (summary in [EVALUATION.md](../EVALUATION.md#results)): detection
precision and recall against the naive anti-join, 18 of 18 invalid writes refused against 1 of 18 when the rules live in
application code, and latency at 100,000 complaints. To show it is real, run a small version live (under a minute):

```bash
python scripts/evaluate.py --sizes 1000 --per-class 5 --out -
```

## Backup: the same story in SQL only

```bash
python scripts/run_sql.py database/queries/07_trigger_refusals.sql      # nine rules refusing nine bad writes
python scripts/run_sql.py database/queries/04_division_and_anti_join.sql
python scripts/run_sql.py database/queries/05_views_functions_procedures.sql
```
