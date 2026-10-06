"""Helpers for running migrations. The schema lives in numbered .sql files, not in Python.

Each Alembic revision under database/migrations/versions/ calls `run_sql_file()` with the matching
file in database/migrations/sql/. The file is sent over the raw driver connection with no bind
parameters, so SQLAlchemy never parses `:name` / `%` inside function bodies, and it joins the same
transaction Alembic opened (a failing migration rolls back completely).
"""

from pathlib import Path

from alembic import op

ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = ROOT / "database" / "migrations" / "sql"


def run_sql_file(name: str) -> None:
    sql = (SQL_DIR / name).read_text(encoding="utf-8")
    op.get_bind().connection.driver_connection.execute(sql)  # type: ignore[union-attr]
