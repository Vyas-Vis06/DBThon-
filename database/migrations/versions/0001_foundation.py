"""foundation: app role, session-context helpers, business time zone

Revision ID: 0001
Revises:
"""
from zeroentry.migrate import run_sql_file

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0001_foundation.sql")


def downgrade() -> None:
    raise NotImplementedError("Forward-only: use `python scripts/db.py reset` on a development database.")
