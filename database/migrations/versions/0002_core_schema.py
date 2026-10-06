"""core schema: 30 tables, constraints, indexes

Revision ID: 0002
Revises: 0001
"""
from zeroentry.migrate import run_sql_file

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0002_core_schema.sql")


def downgrade() -> None:
    raise NotImplementedError("Forward-only: use `python scripts/db.py reset` on a development database.")
