# Judge's guide: run it, try it, question it

In reading order:

| Read | If you want |
|---|---|
| [PITCH_SCRIPT.md](../PITCH_SCRIPT.md) | the problem-first spoken pitch, 90-second fallback, and optional database continuation |
| [PITCH_CUE_CARD.md](../PITCH_CUE_CARD.md) | six story beats, prepared screens, technical transition and closing line |
| [DATABASE_HANDBOOK.md](../DATABASE_HANDBOOK.md) · [TABLE_GUIDE.md](../TABLE_GUIDE.md) | a database walkthrough and all 35 tables explained, with keys and relationships |
| [DEMO_COMMANDS.md](DEMO_COMMANDS.md) | **just the commands**, terminal by terminal, ready to copy and paste |
| **this page** | to run the whole product with one command and try it live (10 minutes) |
| [ZeroEntry_Conditions.pptx](ZeroEntry_Conditions.pptx) | the slide deck: the 19 showcase conditions and how the database reacts to each (speaker notes included) |
| [PROJECT_EXPLAINED.md](PROJECT_EXPLAINED.md) | the project in plain words, assuming no database or domain background |
| [TECH_STACK_AND_GUARANTEES.md](TECH_STACK_AND_GUARANTEES.md) | the stack, and how ACID, concurrency, integrity, security and performance are handled, each with the test that proves it |
| [JUDGE_QA.md](JUDGE_QA.md) | the questions a review panel asks, with the answers and the evidence behind them |

## 1. Run it (one command)

You need **Python 3.11 or 3.12**. No Docker, no PostgreSQL install: an embedded PostgreSQL 16 comes from pip.

```bash
python run.py
```

The first run creates `.venv` and installs the dependencies (about a minute). Every run then does the following:

1. starts PostgreSQL 16 from `.pgdata/` (the data survives restarts),
2. applies the 14 migrations, which create the tables, rules, triggers, views, roles and row-level security,
3. loads the synthetic demo data once (scenarios S0-S10) and runs the absence scan,
4. serves the UI and API at <http://127.0.0.1:8000/>, with interactive API docs at `/docs`.

It prints the **demo password** (the same for every login) and the commands for exploring the database (section 3). Ctrl+C
stops everything, including PostgreSQL.

| Login (`@zeroentry.example`) | Role | Sees |
|---|---|---|
| `supervisor@` | field supervisor | permits, crew, gear, gas readings, entries |
| `engineer@` | sanitation authority | waivers, shadow-entry alerts (decides them) |
| `admin@` | administrator | policy parameters with history, audit log |
| `contractor@`, `worker@` | tenants | only their own rows (row-level security) |
| `auditor@` | read-only | everything, changes nothing |

**If a start fails** with `pg_ctl ... timed out` after the previous run was killed rather than stopped with Ctrl+C,
PostgreSQL is still recovering; run the command again a few seconds later.

**Useful flags:** `python run.py --reset` starts from a fresh demo database. `python run.py --data-dir .pgdata/judges --port 8010`
runs a separate, isolated copy, so a rehearsal never touches your main data.

## 2. Ten-minute tour in the browser

1. **Default deny** (as `supervisor@`). Open **Permits**, then the **DRAFT** permit on **CHN-ADY-010**, and press
   *Ask the database to authorise entry*. It is **denied with five named reasons**: no standby, an entrant without breathing
   apparatus and harness, and no TOP/MID/BOTTOM gas reading. The checklist is computed by a SQL function
   (`permit_clause_check`), not by JavaScript.
2. **Fix it** through the tabs. Under **Crew**, add a STANDBY (NAM-TN-100003). Under **Gear**, issue the two missing items to
   NAM-TN-100002. Under **Gas readings**, log TOP, MID and BOTTOM with detector **GD-4G-0001**. Ask again and the permit is
   **AUTHORISED**. Try detector **GD-4G-0002** first if you like: the database refuses it because its calibration has expired.
3. **Evidence that cannot be rewritten.** **Original authorisation** shows the saved snapshot of policy values, sources and
   evidence IDs, with a SHA-256 digest computed by PostgreSQL.
4. **Detection by absence** (as `engineer@`). **Shadow entries** lists five alerts: complaints closed as "cleared" without the
   evidence a lawful clearance leaves behind. Open the one on **CHN-ADY-006** (late paperwork, `EVIDENCE_RECEIVED`) and
   dismiss it with a note: exactly its own invoice hold is released. Press *Run the absence scan now*: nothing is duplicated
   or re-opened, because the scan is idempotent.
5. **Consequences.** **Incidents & compensation** shows a seeded fatality. One procedure call opened a ₹30-lakh case with a
   deadline, blacklisted the contractor and held the invoices.
6. **Accountability** (as `admin@`). Under **Admin**, change a policy parameter (a reason is required), then see it in the
   revision history and the **Audit log**.

> **Evening caveat.** Entries may only be *started* between 06:00 and 18:00 IST (the `daylight_start_hour` and
> `daylight_end_hour` parameters). Steps 1 to 4 work at any hour. To log an entry in an evening session, change
> `daylight_end_hour` as `admin@` on a **separate demo data directory**, giving a reason such as "synthetic evening rehearsal".
> That change shows up in policy history, which is itself part of the demo.

## 3. Every condition at once

```bash
python run.py showcase
```

This runs 19 situations **at the same time**, each in its own throwaway copy of the database. It takes about 30 seconds,
needs no running server and never touches your data. The situations cover:

- the entry gate: denied, bypass refused, authorised, bad detector, frozen crew;
- the work itself: an overlapping entry, the standby entering, unsafe air stopping a permit;
- detection: an idempotent scan, late evidence, a dismissal, the wrong role deciding;
- money: a held invoice, an atomic fatality, a failure rolled back;
- two concurrency races;
- row-level security and least privilege.

Each one prints the situation, the action, the database's reaction and the state before and after. It exits non-zero if
any reaction differs from the expected one, and `tests/db/test_showcase.py` runs it in CI. The deck
[ZeroEntry_Conditions.pptx](ZeroEntry_Conditions.pptx) presents the same 19 conditions.

## 4. Experiment with the database directly

Leave `python run.py` running and open a second terminal:

```bash
python run.py sql
```

That runs the seven annotated showcase files in `database/queries/` in order: joins, aggregates, search, relational division
and anti-join, views/functions/procedures, **transactions with commit and rollback**, and **nine trigger refusals**. Each file
is safe: anything it changes is rolled back.

```bash
python run.py sql "SELECT * FROM v_permit_compliance"
```

```bash
python run.py sql "SELECT status, count(*) FROM shadow_entry_alert GROUP BY status"
```

Add `--data-dir .pgdata/judges` to any `sql` or `psql` command if the server was started with that flag.

**A full SQL console** uses the `psql` bundled with the embedded server, so nothing extra is installed (`\q` quits):

```bash
python run.py psql
```

That connects as the **owner**, who sees everything, but triggers still fire. While the permit on CHN-ADY-010 is still
DRAFT, try `UPDATE entry_permit SET status = 'AUTHORISED' WHERE permit_id = 2;`: the gate refuses it with SQLSTATE `ZE001`,
giving the same reasons the UI showed. `SELECT permit_id FROM entry_permit WHERE status = 'DRAFT';` lists the drafts.

```bash
python run.py psql --app
```

That connects as **ze_app**, the API's own least-privileged role. It owns nothing, cannot run DDL and cannot rewrite
evidence. Row-level security hides tenant rows until a request context is set, so a bare session sees no scoped rows.

## 5. Proof, not promises

```bash
python run.py test
```

This runs about 570 tests, each on its own fresh copy of the migrated database, in about 2-3 minutes. On this merged code,
Windows, Python 3.11: **574 passed**.

```bash
python run.py evaluate --sizes 1000 --per-class 5 --out -
```

That is a one-minute live version of the measured comparison. It uses its own throwaway server and prints only. The published
full results are in [EVALUATION_RESULTS.md](../EVALUATION_RESULTS.md): detection precision and recall of 100 % against 40 % and
50 % for a naive query, 18 of 18 invalid writes refused against 1 of 18 when the rules live in application code, and an entry
decision in about 2 ms that stays flat from 1,000 to 100,000 complaints.

## Where to look next

[SUBMISSION.md](../SUBMISSION.md) maps the DBThon brief and rubric to evidence. [DEMO_SCRIPT.md](../development/DEMO_SCRIPT.md)
is the timed three-minute version of the tour. [SETUP.md](../SETUP.md) covers a real PostgreSQL server and troubleshooting.
