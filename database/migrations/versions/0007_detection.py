"""detection by absence: SE1/SE2 candidate views, alerts lifecycle, scan_shadow_entries, review

Revision ID: 0007
Revises: 0006
"""
from zeroentry.migrate import run_sql_file

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0007_detection.sql")


def downgrade() -> None:
    raise NotImplementedError("Forward-only: use `python scripts/db.py reset` on a development database.")
