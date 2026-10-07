# Demo commands (copy and paste)

Just the commands, in order. Every command is `python run.py ...`, so the same line works in PowerShell, cmd and bash.
Open each terminal in the project folder first:

```bash
cd "C:\Users\vyasv\Downloads\DB Hack"
```

---

## Terminal 1: the whole product (leave it running)

```bash
python run.py
```

When it prints `ZeroEntry is running`, open <http://127.0.0.1:8000/> and sign in as `supervisor@zeroentry.example` with
the password it printed. The browser tour is in [README.md §2](README.md#2-ten-minute-tour-in-the-browser).

Fresh demo data (use before presenting):

```bash
python run.py --reset
```

Stop with **Ctrl+C**.

---

## Terminal 2: every condition at once (no setup needed)

Runs 19 situations **at the same time**, each in its own throwaway copy of the database. For each one it prints the
situation, the action, how the database reacted and the state before and after. Takes about 30 seconds and never touches
Terminal 1's data.

```bash
python run.py showcase
```

Only some of them (numbers from the summary):

```bash
python run.py showcase --only 1,2,3
```

```bash
python run.py showcase --only 8,16,17
```

---

## Terminal 3: look inside the live database (needs Terminal 1 running)

The seven annotated SQL showcase files (joins, division, anti-join, transactions, refusals); everything is rolled back:

```bash
python run.py sql
```

One file at a time:

```bash
python run.py sql database/queries/06_transactions.sql
```

```bash
python run.py sql database/queries/07_trigger_refusals.sql
```

```bash
python run.py sql database/queries/04_division_and_anti_join.sql
```

Quick state checks:

```bash
python run.py sql "SELECT status, count(*) FROM shadow_entry_alert GROUP BY status"
```

```bash
python run.py sql "SELECT permit_id, status, valid_until FROM entry_permit ORDER BY permit_id"
```

```bash
python run.py sql "SELECT h.hold_id, i.invoice_no, h.alert_id, h.incident_id, h.released_at FROM invoice_hold h JOIN invoice i USING (invoice_id)"
```

Interactive SQL console as the owner (type SQL, `\q` to quit):

```bash
python run.py psql
```

Inside it, try to bypass the gate on a DRAFT permit. It is refused with `ZE001`:

```sql
UPDATE entry_permit SET status = 'AUTHORISED' WHERE permit_id = (SELECT max(permit_id) FROM entry_permit WHERE status = 'DRAFT');
```

The same console as the app's least-privileged role:

```bash
python run.py psql --app
```

---

## Terminal 4: proof (no setup needed)

The whole test suite (about 575 tests, 2-3 minutes):

```bash
python run.py test
```

Only the concurrency races:

```bash
python run.py test tests/db/test_concurrency.py tests/db/test_temporal_evidence_and_invoice_races.py
```

The one-minute measured comparison (accuracy, enforcement, latency):

```bash
python run.py evaluate --sizes 1000 --per-class 5 --out -
```

---

## If something goes wrong

| Symptom | Fix |
|---|---|
| `pg_ctl ... timed out` at start | the previous run was killed rather than stopped; run `python run.py` again |
| port 8000 is busy | `python run.py --port 8010`, then open <http://127.0.0.1:8010/> |
| "Python 3.11 or 3.12 is needed" | install Python 3.12 from python.org and run again |
| an entry can't be started in the evening | expected: entries are allowed 06:00-18:00 IST; the showcase widens this in its own copy, or see [README.md](README.md) for the policy change |
