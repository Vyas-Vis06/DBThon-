"""Run a .sql file against the development database and print every result set (and every NOTICE) as a text table.

    python scripts/run_sql.py database/queries/04_division_and_anti_join.sql

Targets the embedded database started by `python scripts/dev.py` (it must be running), or any server named by
MIGRATION_DATABASE_URL / DATABASE_URL when --url is given. Runs with autocommit ON, so the explicit BEGIN / ROLLBACK in
database/queries/06_transactions.sql behave exactly as written.
"""

import argparse
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]


def table(columns: list[str], rows: list[tuple]) -> str:
    cells = [[("" if v is None else str(v)) for v in row] for row in rows]
    widths = [min(60, max(len(c), *(len(r[i]) for r in cells), 0)) for i, c in enumerate(columns)]
    line = lambda parts: " | ".join(p[:w].ljust(w) for p, w in zip(parts, widths))  # noqa: E731
    return "\n".join([line(columns), "-+-".join("-" * w for w in widths), *(line(r) for r in cells), f"({len(rows)} row{'s' if len(rows) != 1 else ''})"])


def dsn_for_dev() -> str:
    import pgserver
    server = pgserver.get_server(ROOT / ".pgdata" / "cluster", cleanup_mode=None)      # attaches to the running dev database
    return server.get_uri().rsplit("/", 1)[0] + "/zeroentry"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file")
    parser.add_argument("--url", help="postgresql://... instead of the embedded dev database")
    args = parser.parse_args()
    script = Path(args.file).read_text(encoding="utf-8")
    dsn = args.url or dsn_for_dev()
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.add_notice_handler(lambda n: print(f"NOTICE: {n.message_primary}"))
        cur = conn.cursor()
        cur.execute(script)
        while True:
            if cur.description:
                print(table([c.name for c in cur.description], cur.fetchall()), end="\n\n")
            if not cur.nextset():
                break


if __name__ == "__main__":
    sys.exit(main())
