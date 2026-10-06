"""Alembic environment. Online-only: migrations are raw SQL files executed in one transaction each."""

from alembic import context
from sqlalchemy import create_engine, pool

from zeroentry.config import get_settings

config = context.config


def _url() -> str:
    # Programmatic callers (tests, scripts/dev.py) pass the URL via set_main_option().
    return config.get_main_option("sqlalchemy.url") or get_settings().owner_database_url


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Offline (--sql) migrations are not supported: the schema is raw PL/pgSQL.")
run_migrations_online()
