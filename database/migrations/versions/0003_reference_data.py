"""reference data: roles, resolution types, legal clauses, detection rules, rule parameters, gear

Revision ID: 0003
Revises: 0002
"""
from zeroentry.migrate import run_sql_file

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0003_reference_data.sql")


def downgrade() -> None:
    raise NotImplementedError("Forward-only: use `python scripts/db.py reset` on a development database.")
