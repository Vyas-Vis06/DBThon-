"""Test harness.

One embedded PostgreSQL cluster per test session, one migrated template database, and a brand-new
clone of that template for EVERY test (CREATE DATABASE ... TEMPLATE). Consequences:

* Nothing is wrapped in an outer transaction, so commit / rollback / lock behaviour is tested for real.
* No test can see another test's rows, and none can touch a developer database or real data.
* Migrations are applied exactly once per session, through the same Alembic path teammates use.
"""

import itertools
import pathlib
from dataclasses import dataclass

import pgserver
import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_PASSWORD = "ze_test_only"  # throwaway cluster on 127.0.0.1; never reused anywhere else
_counter = itertools.count(1)


def migrate(url: str) -> None:
    """Apply all migrations to `url` using the repository's Alembic setup."""
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "database" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(cfg, "head")


@dataclass(frozen=True)
class Cluster:
    host: str
    port: int

    def owner_url(self, db: str) -> str:
        return f"postgresql+psycopg://postgres@{self.host}:{self.port}/{db}"

    def app_url(self, db: str) -> str:
        return f"postgresql+psycopg://ze_app:{APP_PASSWORD}@{self.host}:{self.port}/{db}"

    def connect(self, db: str, user: str = "postgres", autocommit: bool = True) -> psycopg.Connection:
        password = APP_PASSWORD if user == "ze_app" else None
        return psycopg.connect(host=self.host, port=self.port, dbname=db, user=user, password=password,
                               autocommit=autocommit, row_factory=dict_row)


@dataclass(frozen=True)
class Db:
    """A throwaway database cloned from the migrated template."""
    cluster: Cluster
    name: str

    @property
    def owner_url(self) -> str:
        return self.cluster.owner_url(self.name)

    @property
    def app_url(self) -> str:
        return self.cluster.app_url(self.name)

    def connect(self, user: str = "postgres", autocommit: bool = True) -> psycopg.Connection:
        """Owner connection by default (bypasses RLS); pass user='ze_app' for the runtime role."""
        return self.cluster.connect(self.name, user, autocommit)


@pytest.fixture(scope="session")
def cluster(tmp_path_factory) -> Cluster:
    srv = pgserver.get_server(tmp_path_factory.mktemp("pg"), cleanup_mode="delete")
    info = conninfo_to_dict(srv.get_uri())
    try:
        yield Cluster(host=info["host"], port=int(info["port"]))
    finally:
        srv.cleanup()


@pytest.fixture(scope="session")
def template_db(cluster: Cluster) -> str:
    with cluster.connect("postgres") as admin:
        admin.execute("CREATE DATABASE ze_template")
    migrate(cluster.owner_url("ze_template"))
    with cluster.connect("postgres") as admin:
        admin.execute(f"ALTER ROLE ze_app LOGIN PASSWORD '{APP_PASSWORD}'")
    return "ze_template"


def _clone(cluster: Cluster, template: str, prefix: str):
    name = f"{prefix}{next(_counter)}"
    with cluster.connect("postgres") as admin:
        admin.execute(f'CREATE DATABASE "{name}" TEMPLATE {template}')
    try:
        yield Db(cluster, name)
    finally:
        with cluster.connect("postgres") as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture
def db(cluster: Cluster, template_db: str) -> Db:
    """A private database for ONE test."""
    yield from _clone(cluster, template_db, "ze_t")


@pytest.fixture(scope="module")
def module_db(cluster: Cluster, template_db: str) -> Db:
    """One database shared by a whole test module. ONLY for modules whose tests never change data (read-only probes)."""
    yield from _clone(cluster, template_db, "ze_m")


@pytest.fixture
def conn(db: Db) -> psycopg.Connection:
    """Autocommit owner connection. Use `with conn.transaction():` for an explicit atomic block."""
    with db.connect() as c:
        yield c
