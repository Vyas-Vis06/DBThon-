# Demo script (about 3 minutes)

Every step below was run against freshly seeded data on 2026-10-07 and behaved as written. Start from a clean database so the
story matches: `python scripts/dev.py --reset`. Keep the printed password at hand.

**Before you start:** entries are allowed only in daylight (06:00-18:00 IST, assumption A-03). If you present outside those
hours, sign in as `admin@`, open **Admin → Rules (law as data)** and set `daylight_start_hour` to 0 and `daylight_end_hour` to 24.
That edit is itself part of the story ("the law is data, and changing it is audited"). Run the SQL refusal demo
(step 5) **before** authorising the demo permit: two of its nine refusals need a draft permit.

## 0:00 · The problem (20 s)

> "Indian law already says no one may enter a sewer without gear, gas tests and a standby. People still die, because nothing
> enforces the rule at the moment of entry, and an entry nobody records leaves no trace. ZeroEntry makes the database refuse
> the unsafe entry, and finds the unrecorded ones from what is missing."

## 0:20 · Default deny (70 s), as `supervisor@`

1. **Permits** → open the **DRAFT** permit on manhole **CHN-ADY-010**. The checklist shows **5 of 11 clauses failing**: no
   standby; entrant NAM-TN-100002 lacks the breathing apparatus and harness; no TOP, MID or BOTTOM gas reading.
   > "This is relational division: every entrant must hold every statutory item, and every depth needs a fresh, in-limit
   > reading from a calibrated detector."
2. Press **Ask the database to authorise entry** → **denied**, with the five reasons. Nothing was authorised.
3. Fix it through the tabs: **Crew** → add a STANDBY (e.g. NAM-TN-100003); **Gear** → issue the two missing items to
   NAM-TN-100002; **Gas readings** → log TOP, MID and BOTTOM with detector **GD-4G-0001**.
   *Optional:* try detector **GD-4G-0002** first: refused, "calibration expired".
4. Press **Ask the database to authorise entry** again → **AUTHORISED**, valid for 4 hours.
5. **Entries** → log an entry of **95 minutes** for an entrant → refused: "exceeds the 90 minute continuous-work limit". Log a
   lawful open entry, then a second, overlapping one for the same worker → refused by the exclusion constraint. Try to **close**
   the permit while the worker is inside → refused.
   > "The API did not decide any of this. A raw SQL `UPDATE ... SET status = 'AUTHORISED'` is refused the same way."

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

10. **Admin → Rules** (as `admin@`): thresholds and amounts are rows with legal references; the change you made is in the
    **Audit log**.
    > "The law is data, the gate is the database, and absence is a query."

## Backup: the same story in SQL only

```bash
python scripts/run_sql.py database/queries/07_trigger_refusals.sql      # nine rules refusing nine bad writes
python scripts/run_sql.py database/queries/04_division_and_anti_join.sql
python scripts/run_sql.py database/queries/05_views_functions_procedures.sql
```
