"""permit evidence locking

Revision ID: 0010
Revises: 0009
"""
from zeroentry.migrate import run_sql_file

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0010_permit_evidence_locking.sql")


def downgrade() -> None:
    raise NotImplementedError("Forward-only: use `python scripts/db.py reset` on a development database.")
