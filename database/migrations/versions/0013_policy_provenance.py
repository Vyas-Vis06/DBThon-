"""policy provenance, revision history and permit authorization snapshots

Revision ID: 0013
Revises: 0012
"""
from zeroentry.migrate import run_sql_file

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0013_policy_provenance.sql")


def downgrade() -> None:
    raise NotImplementedError("Forward-only: use `python scripts/db.py reset` on a development database.")
