"""transactional command receipts, durable events, and standalone incident intake

Revision ID: 0016
Revises: 0015
"""
from zeroentry.migrate import run_sql_file

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0016_durable_commands_and_incident_intake.sql")


def downgrade() -> None:
    raise NotImplementedError("Forward-only: use `python scripts/db.py reset` on a development database.")
