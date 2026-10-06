# Setup

**Authoritative for:** getting ZeroEntry running on your machine. Two ways: the **embedded** route (recommended: nothing to
install but Python) and the **real PostgreSQL** route (Docker or a native server).

## Requirements

| | Embedded route | Real-server route |
|---|---|---|
| Python | **3.11 or 3.12** (the embedded PostgreSQL wheel, `pgserver`, has no build for 3.13+) | 3.11+ |
| PostgreSQL | none: PostgreSQL 16 ships inside the `pgserver` wheel | 15 or newer (16 recommended); no extensions needed |
| OS | Windows, macOS, Linux (CI runs Windows and Linux) | any |

**Have only Python 3.13 or newer?** Install 3.12 next to it, then use it for this project's venv:

* Windows: install 3.12 from python.org, then `py -3.12 -m venv .venv`
* macOS / Linux: `brew install python@3.12` or your package manager, then `python3.12 -m venv .venv`
* any OS with [uv](https://docs.astral.sh/uv/): `uv venv --python 3.12 .venv` (downloads 3.12 for you), then
  `uv pip install -e ".[dev]"`

## Embedded route (recommended)

```bash
git clone https://github.com/Vyas-Vis06/DBThon-.git zeroentry
cd zeroentry
python -m venv .venv                       # must be Python 3.11 or 3.12: check with  python --version
```

Activate the venv: `source .venv/bin/activate` (macOS/Linux) or `.venv\Scripts\Activate.ps1` (Windows PowerShell; if scripts
are blocked, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once). Then:

```bash
python -m pip install -e ".[dev]"
python scripts/dev.py
```

`dev.py` starts PostgreSQL 16 (about 10 seconds the first time), applies the migrations, loads the demo data, runs the absence
scan and serves **http://127.0.0.1:8000/**. It prints six demo logins:

| E-mail | Role | Scope |
|---|---|---|
| `admin@zeroentry.example` | ADMIN | everything, rules, users |
| `engineer@zeroentry.example` | ENGINEER (the SOP's Responsible Sanitation Authority) | waivers, alerts, invoices |
| `supervisor@zeroentry.example` | SUPERVISOR | permits: crew, gear, readings, authorise, entries |
| `worker@zeroentry.example` | WORKER | own permits; stop-work |
| `contractor@zeroentry.example` | CONTRACTOR | own jobs, workers, permits, invoices |
| `auditor@zeroentry.example` | AUDITOR | read-only: alerts, compensation, reports, audit log |

The password is the same for all six, generated on first run, printed in the console and stored in the git-ignored
`.pgdata/dev_secrets.json`. Useful flags: `--reset` (wipe and reload the demo data), `--no-seed` (empty database),
`--port 8001`. API documentation: `/docs`; health: `/health`. Stop with Ctrl+C; the data survives restarts.

**Run the demonstration queries** (while `dev.py` is running, in a second terminal):

```bash
python scripts/run_sql.py database/queries/04_division_and_anti_join.sql
```

**Run the tests:** `python -m pytest -n auto` ([TESTING.md](TESTING.md)). They start their own throwaway server.

## Real PostgreSQL route

1. Start a server. With Docker (not exercised in CI; the official image needs nothing extra):

   ```bash
   docker run -d --name zeroentry-pg -e POSTGRES_PASSWORD=<choose-one> -p 5432:5432 postgres:16
   ```

   Or use a native PostgreSQL 15+ and a superuser (or a role with `CREATEDB` and `CREATEROLE`).
2. `cp .env.example .env` and replace every `CHANGE_ME`:
   * `MIGRATION_DATABASE_URL`: the owner/superuser connection (used for migrations and seeding);
   * `APP_DB_PASSWORD`: a new password for the runtime role `ze_app`;
   * `DATABASE_URL`: `postgresql+psycopg://ze_app:<APP_DB_PASSWORD>@localhost:5432/zeroentry`;
   * `SEED_USER_PASSWORD`: 12+ characters, upper and lower case and a digit (demo logins).
3. Create, migrate and enable the runtime login, then load the demo data:

   ```bash
   python scripts/db.py bootstrap
   python scripts/seed.py
   ```

4. Serve: `python -m uvicorn --factory zeroentry.main:create_app --port 8000`
5. Run the absence scan once: sign in as `engineer@` and press **Run the absence scan now** on the shadow-entry screen (or
   `POST /api/v1/detections/scan`). In a real deployment schedule it (cron or `pg_cron`); see
   [ARCHITECTURE.md](ARCHITECTURE.md#detection-runs-as-a-scan-not-a-daemon).

`scripts/db.py bootstrap` and `reset` are tested against a PostgreSQL 16 server (`tests/db/test_db_script.py`).

Other database commands: `python scripts/db.py migrate | current | new <name> | reset --yes` (see the script's `--help`).
For production set `APP_ENV=production` and `COOKIE_SECURE=true`, terminate HTTPS in front of the app, and never run the
seeder (it refuses).

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `No matching distribution found for pgserver` or the tests stop with "pgserver ... Python 3.9-3.12 only" | The venv is Python 3.13+. Recreate it with 3.11 or 3.12 (above). |
| Entries are refused with "daylight only (06:00 to 18:00 IST)" | The demo runs on your clock. Sign in as `admin@`, open **Admin → Rules (law as data)** and widen `daylight_start_hour` / `daylight_end_hour` (the change is audited), or demo in Indian daytime. |
| A permit is denied because a gas reading is "N min old" | Readings must be at most 15 minutes old when you authorise. Log fresh TOP, MID and BOTTOM readings, then authorise. |
| `Address already in use` | Another program uses port 8000: `python scripts/dev.py --port 8001`. |
| The demo data looks wrong after experiments | `python scripts/dev.py --reset` |
| `TimeoutExpired ... pg_ctl ... start` or an `AssertionError` from pgserver right after a crash or a forced kill | PostgreSQL is replaying its log (crash recovery), which can outlast pgserver's 10-second start timeout. Wait half a minute and run `dev.py` again. Stop it with Ctrl+C, not by killing the window, to avoid this. |
| PowerShell will not run `Activate.ps1` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or skip activation and call `.venv\Scripts\python` directly. |
| `docs/SCHEMA_REFERENCE.md is out of date` in the tests | You changed a migration or router: `python scripts/gen_docs.py` and commit the result. |
