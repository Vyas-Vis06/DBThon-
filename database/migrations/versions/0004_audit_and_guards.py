"""audit trail, rule_num(), append-only evidence tables

Revision ID: 0004
Revises: 0003
"""
from zeroentry.migrate import run_sql_file

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0004_audit_and_guards.sql")


def downgrade() -> None:
    raise NotImplementedError("Forward-only: use `python scripts/db.py reset` on a development database.")
