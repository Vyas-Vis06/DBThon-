"""Test harness.

One embedded PostgreSQL cluster per test session, one migrated template database, and a brand-new
clone of that template for EVERY test (CREATE DATABASE ... TEMPLATE). Consequences:

* Nothing is wrapped in an outer transaction, so commit / rollback / lock behaviour is tested for real.
* No test can see another test's rows, and none can touch a developer database or real data.
* Migrations are applied exactly once per session, through the same Alembic path teammates use.
"""

import itertools
import os
import pathlib
import uuid
from dataclasses import dataclass

import psycopg
import pytest

try:
    import pgserver
except ImportError:                              # external disposable service can run without the embedded wheel
    pgserver = None
    if not os.getenv("ZEROENTRY_TEST_PG_URI"):
        pytest.exit("The tests start an embedded PostgreSQL from the `pgserver` wheel, which exists for Python 3.9-3.12 only. "
                "Create the venv with Python 3.11 or 3.12 (see docs/SETUP.md), then: pip install -e \".[dev]\"", returncode=4)
from alembic import command
from alembic.config import Config
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from zeroentry.db import url_for

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_PASSWORD = "ze_test_only"  # throwaway local cluster; never reused anywhere else
_counter = itertools.count(1)


def migrate(url: str) -> None:
    """Apply all migrations to `url` using the repository's Alembic setup."""
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "database" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(cfg, "head")


@dataclass(frozen=True)
class Cluster:
    uri: str            # libpq URI from pgserver: TCP on Windows, a Unix-socket directory on Linux and macOS

    def owner_url(self, db: str) -> str:
        return url_for(self.uri, db, password=conninfo_to_dict(self.uri).get("password"))

    def app_url(self, db: str) -> str:
        return url_for(self.uri, db, "ze_app", APP_PASSWORD)

    def connect(self, db: str, user: str = "postgres", autocommit: bool = True) -> psycopg.Connection:
        password = APP_PASSWORD if user == "ze_app" else conninfo_to_dict(self.uri).get("password", "")
        return psycopg.connect(make_conninfo(self.uri, dbname=db, user=user, password=password),
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
    external = os.getenv("ZEROENTRY_TEST_PG_URI")
    if external:
        # Opt-in only: use a disposable CI/test server, never a development/production server.
        # The harness creates/drops private databases and changes the shared ze_app test role.
        yield Cluster(external)
        return
    srv = pgserver.get_server(tmp_path_factory.mktemp("pg"), cleanup_mode="delete")
    try:
        yield Cluster(srv.get_uri())
    finally:
        srv.cleanup()


@pytest.fixture(scope="session")
def template_db(cluster: Cluster) -> str:
    name = "ze_template_" + uuid.uuid4().hex[:12]
    with cluster.connect("postgres") as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    try:
        migrate(cluster.owner_url(name))
        with cluster.connect("postgres") as admin:
            admin.execute(f"ALTER ROLE ze_app LOGIN PASSWORD '{APP_PASSWORD}'")
        yield name
    finally:
        with cluster.connect("postgres") as admin:
            admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


def _clone(cluster: Cluster, template: str, prefix: str):
    name = f"{prefix}{next(_counter)}_{uuid.uuid4().hex[:12]}"
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
