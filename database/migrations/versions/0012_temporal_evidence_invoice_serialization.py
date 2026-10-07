"""temporal evidence and invoice hold serialization

Revision ID: 0012
Revises: 0011
"""
from zeroentry.migrate import run_sql_file

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0012_temporal_evidence_invoice_serialization.sql")


def downgrade() -> None:
    raise NotImplementedError("Forward-only: use `python scripts/db.py reset` on a development database.")
