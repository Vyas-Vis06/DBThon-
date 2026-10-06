"""hardening: least-privilege grants for the runtime role

Revision ID: 0008
Revises: 0007
"""
from zeroentry.migrate import run_sql_file

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0008_hardening.sql")


def downgrade() -> None:
    raise NotImplementedError("Forward-only: use `python scripts/db.py reset` on a development database.")
