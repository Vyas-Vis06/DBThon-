"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
"""
from zeroentry.migrate import run_sql_file

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("${up_revision}_${slug}.sql")


def downgrade() -> None:
    raise NotImplementedError("Forward-only: use `python scripts/db.py reset` on a development database.")
