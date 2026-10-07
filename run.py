"""ZeroEntry in one command. Needs only Python 3.11 or 3.12: no Docker, no PostgreSQL install.

    python run.py                    first run: creates .venv and installs (about a minute), then starts everything:
                                     embedded PostgreSQL 16 -> migrations -> demo data -> absence scan -> http://127.0.0.1:8000/
    python run.py --reset            the same with a fresh demo database (any scripts/dev.py flag works: --port, --data-dir)

Any time (own throwaway server, nothing else needs to run):
    python run.py showcase           19 situations AT THE SAME TIME, each in its own database copy: the database's reaction
                                     and the state before/after (docs/guide/ZeroEntry_Conditions.pptx explains each one)

While it runs, in a second terminal:
    python run.py sql                run the seven annotated showcase queries in database/queries/
    python run.py sql FILE.sql       run one file;   python run.py sql "SELECT * FROM v_permit_compliance"
    python run.py psql               interactive SQL console as the owner (sees everything; triggers still refuse bad writes)
    python run.py psql --app         ... as ze_app, the API's least-privileged role (row-level security hides scoped rows)
    python run.py test               the whole test suite (about 570 tests, each on its own fresh database)
    python run.py evaluate --sizes 1000 --per-class 5 --out -     a one-minute measured comparison (own throwaway server)
    python run.py <script> ...       any scripts/<script>.py, run inside the project venv

The judge's guide is docs/guide/README.md.
"""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(cmd: list[str], env: dict | None = None) -> int:
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env)
    while True:
        try:
            return proc.wait()
        except KeyboardInterrupt:      # Ctrl+C reached the child too; let it stop PostgreSQL (or cancel a psql query) cleanly
            pass


def psql(args: list[str]) -> int:
    """The psql bundled with the embedded server, on the running database (runs inside .venv)."""
    import json
    import pgserver
    from psycopg.conninfo import make_conninfo
    data_dir = (Path(args[args.index("--data-dir") + 1]) if "--data-dir" in args else ROOT / ".pgdata").resolve()
    dsn = make_conninfo(pgserver.get_server(data_dir / "cluster", cleanup_mode=None).get_uri(), dbname="zeroentry")
    env = dict(os.environ)
    if "--app" in args:                # the API's own least-privileged role, password from dev.py's secrets file
        dsn = make_conninfo(dsn, user="ze_app")
        env["PGPASSWORD"] = json.loads((data_dir / "dev_secrets.json").read_text())["app_db_password"]
    return run([str(Path(pgserver.__file__).parent / "pginstall" / "bin" / "psql"), dsn], env)


def base_python() -> list[str]:
    if sys.version_info[:2] in ((3, 11), (3, 12)):
        return [sys.executable]
    for candidate in (["py", "-3.12"], ["py", "-3.11"], ["python3.12"], ["python3.11"]):
        try:
            if subprocess.run([*candidate, "-c", ""], capture_output=True).returncode == 0:
                return candidate
        except FileNotFoundError:
            pass
    sys.exit("ZeroEntry needs Python 3.11 or 3.12 (the embedded PostgreSQL has wheels only for those). "
             "Install one from python.org and run this again.")


def ensure_venv() -> None:
    if not VENV_PY.exists():
        print("First run: creating .venv ...")
        subprocess.run([*base_python(), "-m", "venv", str(VENV)], check=True)
    stamp, wanted = VENV / ".zeroentry-installed", hashlib.sha256((ROOT / "pyproject.toml").read_bytes()).hexdigest()
    if not stamp.exists() or stamp.read_text() != wanted:      # reinstall only when the dependencies change
        print("Installing dependencies into .venv (once; about a minute) ...")
        subprocess.run([str(VENV_PY), "-m", "pip", "install", "-q", "-e", ".[dev]"], cwd=ROOT, check=True)
        stamp.write_text(wanted)


def main() -> int:
    ensure_venv()
    args = sys.argv[1:]
    command = args[0] if args and not args[0].startswith("-") else None
    if command is None:
        return run([str(VENV_PY), "scripts/dev.py", *args])
    if command == "test":
        return run([str(VENV_PY), "-m", "pytest", "-n", "auto", *args[1:]])
    if command == "sql" and (len(args) == 1 or args[1].startswith("-")):
        codes = []
        for f in sorted((ROOT / "database" / "queries").glob("*.sql")):
            print(f"\n===== {f.relative_to(ROOT).as_posix()} =====\n", flush=True)
            codes.append(run([str(VENV_PY), "scripts/run_sql.py", str(f), *args[1:]]))
        return max(codes)
    if command == "psql":
        return run([str(VENV_PY), __file__, "_psql", *args[1:]])
    if command == "_psql":
        return psql(args[1:])
    script = ROOT / "scripts" / f"{'run_sql' if command == 'sql' else command}.py"
    if not script.exists():
        sys.exit(__doc__)
    return run([str(VENV_PY), str(script), *args[1:]])


if __name__ == "__main__":
    sys.exit(main())
