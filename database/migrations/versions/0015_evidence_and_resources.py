"""add current evidence, readiness, policy and resource reservations

Revision ID: 0015
Revises: 0014
"""
from zeroentry.migrate import run_sql_file

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0015_evidence_and_resources.sql")


def downgrade() -> None:
    raise NotImplementedError("Forward-only: use `python scripts/db.py reset` on a development database.")
