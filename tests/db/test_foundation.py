"""Foundation: migrations apply, the app boots against them, the runtime role is least-privilege."""

import psycopg
import pytest
from fastapi.testclient import TestClient

from zeroentry.config import Settings
from zeroentry.main import create_app


def _client(db) -> TestClient:
    return TestClient(create_app(Settings(app_env="test", database_url=db.app_url)))


def test_health_does_a_real_database_round_trip(db):
    with _client(db) as client:
        body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["database"] == "up"
    assert body["server_version"].startswith("16")
    assert body["schema_version"] >= "0001"


def test_health_reports_503_when_database_is_unreachable(db):
    app = create_app(Settings(app_env="test", database_url=db.app_url.replace("/ze_t", "/no_such_db_")))
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "version": "0.1.0", "database": "down"}


def test_runtime_role_is_not_privileged(db):
    with db.connect(user="ze_app") as c:
        flags = c.execute("SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls "
                          "FROM pg_roles WHERE rolname = current_user").fetchone()
        assert not any(flags.values())
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("CREATE TABLE should_not_exist (id int)")


def test_request_context_helpers_default_to_null_and_read_settings(conn):
    assert conn.execute("SELECT app_role() AS r, app_user_id() AS u").fetchone() == {"r": None, "u": None}
    with conn.transaction():
        conn.execute("SELECT set_config('app.role', 'AUDITOR', true), set_config('app.user_id', '42', true)")
        row = conn.execute("SELECT app_role() AS r, app_user_id() AS u").fetchone()
        assert row == {"r": "AUDITOR", "u": 42}
    # transaction-local: nothing leaks to the next transaction on the same (pooled) connection
    assert conn.execute("SELECT app_role() AS r").fetchone()["r"] is None


@pytest.mark.parametrize("offset", ["+00:00", "-08:00", "+09:00"])
def test_business_time_is_ist_whatever_the_session_zone(conn, offset):
    conn.execute(f"SET TIME ZONE INTERVAL '{offset}' HOUR TO MINUTE")  # fixed offsets work on every build
    # 20:00 UTC on 6 Oct is already 01:30 on 7 Oct in India (UTC+05:30)
    row = conn.execute("SELECT local_date('2026-10-06 20:00:00+00') AS d, "
                       "local_ts('2026-10-06 20:00:00+00') AS t, "
                       "from_local('2026-10-07 01:30:00') = '2026-10-06 20:00:00+00'::timestamptz AS roundtrip"
                       ).fetchone()
    assert str(row["d"]) == "2026-10-07"
    assert str(row["t"]) == "2026-10-07 01:30:00"
    assert row["roundtrip"] is True
