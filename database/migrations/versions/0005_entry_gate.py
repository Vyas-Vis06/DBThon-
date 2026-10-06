"""entry gate: permit_clause_check, authorise_entry, state machine, freeze, gas/entry/waiver guards

Revision ID: 0005
Revises: 0004
"""
from zeroentry.migrate import run_sql_file

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0005_entry_gate.sql")


def downgrade() -> None:
    raise NotImplementedError("Forward-only: use `python scripts/db.py reset` on a development database.")
