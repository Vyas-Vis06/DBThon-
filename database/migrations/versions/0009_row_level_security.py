"""row-level security, definer helpers, stop_work, audit rows written only by trigger

Revision ID: 0009
Revises: 0008
"""
from zeroentry.migrate import run_sql_file

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0009_row_level_security.sql")


def downgrade() -> None:
    raise NotImplementedError("Forward-only: use `python scripts/db.py reset` on a development database.")
