"""One command to run the whole system locally: NO Docker and NO system PostgreSQL needed.

    python scripts/dev.py              embedded PostgreSQL 16 -> migrate -> demo data (first run) -> absence scan -> serve
    python scripts/dev.py --reset      wipe the development database first (demo data is loaded again)
    python scripts/dev.py --no-seed    start with an empty database
    python scripts/dev.py --port 8001

The database lives in ./.pgdata (git-ignored) and survives restarts. Random passwords for the application database role
and for the demo logins are generated on first run and kept in ./.pgdata/dev_secrets.json: nothing secret is in the source.
Stop with Ctrl+C. For a real PostgreSQL server (Docker or native) see docs/SETUP.md.
"""

import argparse
import json
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_NAME = "zeroentry"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--no-seed", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".pgdata", help="Isolated demo cluster directory")
    args = parser.parse_args()

    try:
        import pgserver
        import psycopg
        import uvicorn
        from psycopg import sql
    except ImportError as exc:
        if exc.name == "pgserver" and sys.version_info >= (3, 13):
            sys.exit("The embedded PostgreSQL (pgserver) has wheels for Python 3.9-3.12 only. Recreate the venv with "
                     "Python 3.11 or 3.12, or run against a real PostgreSQL server: see docs/SETUP.md.")
        sys.exit(f"Missing dependency ({exc.name}). From the repository root run:  pip install -e \".[dev]\"")
    from alembic import command

    from zeroentry.db import url_for
    from zeroentry.seed import DEMO_USERS, EMAIL_DOMAIN, run_seed
    sys.path.insert(0, str(Path(__file__).parent))
    from db import alembic_config

    home = args.data_dir.resolve()
    home.mkdir(parents=True, exist_ok=True)
    secrets_file = home / "dev_secrets.json"
    keep = json.loads(secrets_file.read_text()) if secrets_file.exists() else {}
    for key in ("app_db_password", "demo_password"):
        keep.setdefault(key, secrets.token_urlsafe(12) + "Aa1")            # "Aa1" guarantees the password-strength rule
    secrets_file.write_text(json.dumps(keep), encoding="utf-8")

    print("Starting the embedded PostgreSQL 16 (first start takes about 10 seconds) ...")
    server = pgserver.get_server(home / "cluster", cleanup_mode="stop")
    try:
        owner_url = url_for(server.get_uri(), DB_NAME)
        app_url = url_for(server.get_uri(), DB_NAME, "ze_app", keep["app_db_password"])

        with psycopg.connect(server.get_uri(), autocommit=True) as admin:
            if args.reset:
                admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(DB_NAME)))
            if not admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,)).fetchone():
                admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB_NAME)))
        command.upgrade(alembic_config(owner_url), "head")

        with psycopg.connect(owner_url.replace("+psycopg", ""), autocommit=True) as conn:
            conn.execute(sql.SQL("ALTER ROLE ze_app LOGIN PASSWORD {}").format(sql.Literal(keep["app_db_password"])))
            seeded = conn.execute("SELECT count(*) FROM app_user").fetchone()[0] > 0
            if not seeded and not args.no_seed:
                print("Loading deterministic demo data ...")
                counts = run_seed(owner_url, keep["demo_password"])
                scan = conn.execute("SELECT * FROM scan_shadow_entries(now())").fetchone()
                print("  loaded:", ", ".join(f"{k}={v}" for k, v in counts.items()))
                print(f"  absence scan: {scan[0]} alert(s) opened, {scan[1]} sent to review, {scan[2]} still in the grace window")
                seeded = True

        os.environ.update({"APP_ENV": "development", "DATABASE_URL": app_url, "MIGRATION_DATABASE_URL": owner_url})
        print(f"\nZeroEntry is running:  http://{args.host}:{args.port}/   (API docs: /docs, health: /health)")
        if seeded:
            print(f"Demo logins (password for all: {keep['demo_password']}):")
            for login, role, name, _ in DEMO_USERS:
                print(f"  {login + '@' + EMAIL_DOMAIN:<32} {role:<11} {name}")
        where = "" if home == (ROOT / ".pgdata").resolve() else f" --data-dir {args.data_dir}"
        print("Explore the database from another terminal:")
        print(f"  python run.py psql{where}          SQL console as the owner (\\q to quit)")
        print(f"  python run.py psql --app{where}    as ze_app, the API's least-privileged role")
        print(f"  python run.py sql{where}           the seven annotated showcase queries")
        print("Ctrl+C to stop.\n")
        uvicorn.run("zeroentry.main:create_app", factory=True, host=args.host, port=args.port, log_level="info")
    finally:
        server.cleanup()


if __name__ == "__main__":
    main()
