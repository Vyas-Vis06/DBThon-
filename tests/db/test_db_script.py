"""scripts/db.py: the commands a teammate runs against a real server (bootstrap, reset) and the migration scaffold (new)."""

import importlib.util
import shutil

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from tests.conftest import APP_PASSWORD, ROOT
from zeroentry.config import get_settings

spec = importlib.util.spec_from_file_location("db_script", ROOT / "scripts" / "db.py")
db_script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(db_script)
HEAD = sorted(p.name[:4] for p in (ROOT / "database" / "migrations" / "sql").glob("*.sql"))[-1]


@pytest.fixture
def fresh(cluster, monkeypatch):
    """A database name that does not exist yet, settings pointing at it, and ze_app's cluster-wide password restored after."""
    name = "ze_script_target"
    monkeypatch.setenv("DATABASE_URL", cluster.owner_url(name))
    monkeypatch.setenv("APP_DB_PASSWORD", "Bootstrap_Pass_42")
    monkeypatch.setenv("APP_ENV", "development")
    get_settings.cache_clear()
    yield name
    get_settings.cache_clear()
    with cluster.connect("postgres") as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.execute(f"ALTER ROLE ze_app PASSWORD '{APP_PASSWORD}'")


def _revision(cluster, name, user="postgres", password=""):
    with psycopg.connect(make_conninfo(cluster.uri, dbname=name, user=user, password=password)) as c:
        return c.execute("SELECT version_num FROM alembic_version").fetchone()[0]


def test_bootstrap_creates_migrates_and_lets_the_runtime_role_log_in(cluster, fresh):
    db_script.cmd_bootstrap(cluster.owner_url(fresh))
    assert _revision(cluster, fresh, "ze_app", "Bootstrap_Pass_42") == HEAD
    db_script.cmd_bootstrap(cluster.owner_url(fresh))                   # running it again is harmless
    assert _revision(cluster, fresh) == HEAD


def test_bootstrap_refuses_the_placeholder_password(cluster, fresh, monkeypatch):
    monkeypatch.setenv("APP_DB_PASSWORD", "CHANGE_ME")
    get_settings.cache_clear()
    with pytest.raises(SystemExit, match="APP_DB_PASSWORD"):
        db_script.cmd_bootstrap(cluster.owner_url(fresh))


def test_reset_needs_yes_then_recreates_an_empty_migrated_database(cluster, fresh):
    db_script.cmd_bootstrap(cluster.owner_url(fresh))
    with psycopg.connect(make_conninfo(cluster.uri, dbname=fresh, user="postgres"), autocommit=True) as c:
        c.execute("INSERT INTO ulb (name, district, state) VALUES ('Doomed', 'x', 'y')")
    with pytest.raises(SystemExit, match="--yes"):
        db_script.cmd_reset(cluster.owner_url(fresh), yes=False)
    db_script.cmd_reset(cluster.owner_url(fresh), yes=True)
    with psycopg.connect(make_conninfo(cluster.uri, dbname=fresh, user="postgres")) as c:
        assert c.execute("SELECT count(*) FROM ulb").fetchone()[0] == 0
        assert c.execute("SELECT version_num FROM alembic_version").fetchone()[0] == HEAD


def test_reset_refuses_production(cluster, fresh, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("COOKIE_SECURE", "true")
    get_settings.cache_clear()
    with pytest.raises(SystemExit, match="production"):
        db_script.cmd_reset(cluster.owner_url(fresh), yes=True)


def test_new_scaffolds_the_next_numbered_migration_and_its_revision(tmp_path, monkeypatch):
    sql_dir, versions = tmp_path / "sql", tmp_path / "versions"
    shutil.copytree(ROOT / "database" / "migrations" / "sql", sql_dir)
    versions.mkdir()
    monkeypatch.setattr(db_script, "SQL_DIR", sql_dir)
    monkeypatch.setattr(db_script, "VERSIONS", versions)
    db_script.cmd_new("Add shift roster!")
    nxt = f"{int(HEAD) + 1:04d}"
    assert (sql_dir / f"{nxt}_add_shift_roster.sql").is_file()
    revision = (versions / f"{nxt}_add_shift_roster.py").read_text(encoding="utf-8")
    assert f'revision = "{nxt}"' in revision and f'down_revision = "{HEAD}"' in revision
