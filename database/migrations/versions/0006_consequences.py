"""consequences: record_incident, invoice holds, compensation payments, report views

Revision ID: 0006
Revises: 0005
"""
from zeroentry.migrate import run_sql_file

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0006_consequences.sql")


def downgrade() -> None:
    raise NotImplementedError("Forward-only: use `python scripts/db.py reset` on a development database.")
