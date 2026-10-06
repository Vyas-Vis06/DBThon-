# CLAUDE.md

Follow [AGENTS.md](AGENTS.md); it is the single source of repository rules. Claude-specific notes only:

* **Start of session:** read `docs/development/DEV_LOG.md` (latest entry) and the current milestone in `ROADMAP.md`;
  resume from "Next step". Do not reconstruct the plan from chat history.
* **Python:** use the project venv. Windows: `.\.venv\Scripts\python.exe -m pytest`; macOS/Linux:
  `.venv/bin/python -m pytest`. Quote paths: clones often live in folders with spaces.
* **PostgreSQL:** tests and `scripts/dev.py` use the embedded PostgreSQL 16 from the `pgserver` wheel, so no Docker or
  system install is needed. It has **no `btree_gist` and no IANA time-zone database**: never write
  `AT TIME ZONE 'Asia/Kolkata'`; use `local_ts()`, `local_date()`, `from_local()` (fixed +05:30).
* **Windows PowerShell:** never write SQL or Markdown with `Set-Content -Encoding UTF8` (it adds a BOM that breaks
  migrations). Use the editor tools or Python.
* **Use the right tool for each job:** read files with the Read tool, search with Grep/Glob, and keep SQL in
  `database/migrations/sql/`, not inline in Python.
* **When you finish a milestone:** update `ROADMAP.md` statuses (only `[x]` for verified work), append a dated entry
  to `DEV_LOG.md` (what changed, files, tests run and their real result, known issues, next step), then stop or continue.
* **Never** commit, push or reset a database unless the user asked in this conversation.
