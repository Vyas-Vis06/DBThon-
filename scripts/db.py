"""Database administration. Run from the repository root with the project's virtualenv active.

  python scripts/db.py migrate         apply every pending migration (MIGRATION_DATABASE_URL, else DATABASE_URL)
  python scripts/db.py current         show the applied revision
  python scripts/db.py bootstrap       create the database if missing, migrate, and give the `ze_app` role its login
                                       password (APP_DB_PASSWORD). Use this once against a real PostgreSQL server.
  python scripts/db.py new <name>      scaffold the next numbered migration: database/migrations/sql/NNNN_<name>.sql
                                       plus its Alembic revision. Edit the .sql file; never edit an applied migration.
  python scripts/db.py reset --yes     DROP and recreate the database named in the owner URL, then migrate
                                       (development only; refused when APP_ENV=production)
"""

import argparse
import re
import sys
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy.engine import make_url

from zeroentry.config import get_settings
from zeroentry.seed import to_psycopg_dsn

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "database" / "migrations" / "sql"
VERSIONS = ROOT / "database" / "migrations" / "versions"


def alembic_config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "database" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def maintenance_dsn(owner_url: str) -> tuple[str, str]:
    """(DSN of the server's `postgres` database, name of the application database)."""
    url = make_url(owner_url)
    return to_psycopg_dsn(url.set(database="postgres").render_as_string(hide_password=False)), url.database


def cmd_migrate(owner_url: str) -> None:
    command.upgrade(alembic_config(owner_url), "head")
    print("Migrations applied.")


def cmd_bootstrap(owner_url: str) -> None:
    settings = get_settings()
    if not settings.app_db_password or "CHANGE_ME" in settings.app_db_password:
        sys.exit("Set APP_DB_PASSWORD (not the CHANGE_ME placeholder) in .env or the environment first.")
    dsn, name = maintenance_dsn(owner_url)
    with psycopg.connect(dsn, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone():
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
            print(f"Created database {name}.")
    cmd_migrate(owner_url)
    with psycopg.connect(to_psycopg_dsn(owner_url), autocommit=True) as conn:        # ze_app exists after migration 0001
        conn.execute(sql.SQL("ALTER ROLE ze_app LOGIN PASSWORD {}").format(sql.Literal(settings.app_db_password)))
    print("Role ze_app can now log in with APP_DB_PASSWORD. Put the same password in DATABASE_URL.")


def cmd_new(name: str) -> None:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not slug:
        sys.exit("Give the migration a short name, for example: python scripts/db.py new add_shift_roster")
    numbers = sorted(int(m.group(1)) for f in SQL_DIR.glob("*.sql") if (m := re.match(r"(\d{4})_", f.name)))
    nxt, prev = f"{numbers[-1] + 1:04d}", f"{numbers[-1]:04d}"
    (SQL_DIR / f"{nxt}_{slug}.sql").write_text(
        f"-- {nxt}_{slug}.sql\n-- What this migration does and why (cite the PROJECT_SPEC rule, BR-nn, it implements).\n"
        "-- Forward-only. Grant ze_app only what it needs; add RLS policies for any new table holding tenant data.\n", encoding="utf-8")
    (VERSIONS / f"{nxt}_{slug}.py").write_text(
        f'"""{slug.replace("_", " ")}\n\nRevision ID: {nxt}\nRevises: {prev}\n"""\nfrom zeroentry.migrate import run_sql_file\n\n'
        f'revision = "{nxt}"\ndown_revision = "{prev}"\nbranch_labels = None\ndepends_on = None\n\n\n'
        f'def upgrade() -> None:\n    run_sql_file("{nxt}_{slug}.sql")\n\n\n'
        'def downgrade() -> None:\n    raise NotImplementedError("Forward-only: use `python scripts/db.py reset` on a development database.")\n',
        encoding="utf-8")
    print(f"Created database/migrations/sql/{nxt}_{slug}.sql and database/migrations/versions/{nxt}_{slug}.py\n"
          "Now write the SQL, add a test under tests/db/, and update DATABASE_DESIGN.md.")


def cmd_reset(owner_url: str, yes: bool) -> None:
    if get_settings().app_env == "production":
        sys.exit("Refusing to reset a production database.")
    dsn, name = maintenance_dsn(owner_url)
    if not yes:
        sys.exit(f"This DROPS database '{name}' and everything in it. Re-run with --yes to confirm.")
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    print(f"Database {name} recreated.")
    cmd_migrate(owner_url)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("migrate", "current", "bootstrap"):
        sub.add_parser(name)
    sub.add_parser("new").add_argument("name")
    sub.add_parser("reset").add_argument("--yes", action="store_true")
    args = parser.parse_args()
    if args.cmd == "new":
        return cmd_new(args.name)
    owner_url = get_settings().owner_database_url
    if args.cmd == "migrate":
        cmd_migrate(owner_url)
    elif args.cmd == "current":
        command.current(alembic_config(owner_url), verbose=True)
    elif args.cmd == "bootstrap":
        cmd_bootstrap(owner_url)
    elif args.cmd == "reset":
        cmd_reset(owner_url, args.yes)


if __name__ == "__main__":
    main()
