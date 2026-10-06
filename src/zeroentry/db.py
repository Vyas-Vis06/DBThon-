"""Engine and session factories. No module-level engine: the app factory owns the lifecycle."""

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker


def make_engine(url: str) -> Engine:
    # pool_pre_ping: a restarted embedded/dev database must not poison pooled connections.
    return create_engine(url, pool_pre_ping=True)


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def database_status(engine: Engine) -> dict[str, str]:
    """Real round-trip: server version plus the applied migration (used by /health)."""
    with engine.connect() as conn:
        version = conn.execute(text("SHOW server_version")).scalar_one()
        rev = conn.execute(text("SELECT to_regclass('public.alembic_version')")).scalar_one()
        schema = conn.execute(text("SELECT version_num FROM alembic_version")).scalar() if rev else None
    return {"server_version": version, "schema_version": schema or "unmigrated"}
