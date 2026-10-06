"""Engine and session factories. No module-level engine: the app factory owns the lifecycle."""

from psycopg.conninfo import conninfo_to_dict
from sqlalchemy import URL, Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker


def url_for(conninfo: str, database: str, user: str = "postgres", password: str | None = None) -> str:
    """SQLAlchemy URL for `database` on the server a libpq URI points at (used with the embedded pgserver).

    Host and port travel in the query string, so a Unix-socket directory (pgserver on Linux and macOS) works as well as
    host:port (pgserver on Windows).
    """
    info = conninfo_to_dict(conninfo)
    query = {key: info[key] for key in ("host", "port") if info.get(key)}
    return URL.create("postgresql+psycopg", username=user, password=password, database=database,
                      query=query).render_as_string(hide_password=False)


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
