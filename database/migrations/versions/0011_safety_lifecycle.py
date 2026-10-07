"""safety lifecycle

Revision ID: 0011
Revises: 0010
"""
from zeroentry.migrate import run_sql_file

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0011_safety_lifecycle.sql")


def downgrade() -> None:
    raise NotImplementedError("Forward-only: use `python scripts/db.py reset` on a development database.")
