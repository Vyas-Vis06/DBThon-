"""Actual runtime-role periodic maintenance, including commit isolation across its two tasks."""

import time

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from tests.factories import Factory, yesterday_ist
from zeroentry.config import Settings
from zeroentry.main import create_app
from zeroentry.maintenance import run_maintenance


def expired_permit(conn):
    s = Factory(conn).gate_scenario(yesterday_ist())
    conn.execute("SELECT * FROM authorise_entry(%s, %s, %s)", (s["permit"], s["supervisor"], s["at"]))
    return s["permit"]


def test_maintenance_commits_stop_even_if_detection_fails(db, conn):
    permit = expired_permit(conn)
    conn.execute("""CREATE OR REPLACE FUNCTION scan_shadow_entries(p_at timestamptz DEFAULT now())
        RETURNS TABLE (opened int, moved_to_review int, pending_in_grace int)
        LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Injected detection failure'; END $$""")
    engine = create_engine(db.app_url)
    try:
        result = run_maintenance(engine)
        assert result["safety"] == {"stopped": 1}
        assert "error" in result["detection"]
        assert conn.execute("SELECT status FROM entry_permit WHERE permit_id=%s", (permit,)).fetchone()["status"] == "ABORTED"
        assert conn.execute("SELECT count(*) AS n FROM permit_safety_event WHERE permit_id=%s", (permit,)).fetchone()["n"] >= 1
        assert run_maintenance(engine)["safety"] == {"stopped": 0}
    finally:
        engine.dispose()


def test_lifespan_tick_stops_expired_permit_without_an_http_write(db, conn):
    permit = expired_permit(conn)
    app = create_app(Settings(app_env="test", database_url=db.app_url, safety_sweep_interval_seconds=1))
    with TestClient(app):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            status = conn.execute("SELECT status FROM entry_permit WHERE permit_id=%s", (permit,)).fetchone()["status"]
            if status == "ABORTED":
                break
            time.sleep(.02)
        assert status == "ABORTED"
    assert app.state.maintenance["safety"]["stopped"] == 1
