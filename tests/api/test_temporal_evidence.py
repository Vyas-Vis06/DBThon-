"""The machine outcome receipt is assigned by PostgreSQL, independently of client event times (BR-31)."""

from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from tests.api.conftest import API, ok
from tests.api.test_workflow import iso


def test_predeadline_unfinished_deployment_finalized_late_stays_a_candidate(api, world, conn):
    engineer = api("engineer")
    complaint = ok(engineer.post(f"{API}/complaints", json={
        "manhole_id": world["manhole"], "description": "Machine work recorded after a delayed sync."}), 201)
    job = ok(engineer.post(f"{API}/jobs", json={
        "complaint_id": complaint["complaint_id"], "contractor_id": world["ca"]}), 201)
    ok(engineer.post(f"{API}/complaints/{complaint['complaint_id']}/resolve", json={"resolution_code": "CLEARED"}))

    resolved_at = datetime.now(timezone.utc) - timedelta(days=3)
    conn.execute("UPDATE complaint SET raised_at = %s, resolved_at = %s WHERE complaint_id = %s",
                 (resolved_at - timedelta(days=1), resolved_at, complaint["complaint_id"]))
    deployment = ok(engineer.post(f"{API}/jobs/{job['job_id']}/deployments", json={
        "machine_id": world["machine"], "started_at": iso(resolved_at - timedelta(hours=2))}), 201)
    # Model an old deployment receipt. Its outcome is still NULL when the complaint's evidence deadline passes.
    conn.execute("UPDATE machine_deployment SET recorded_at = %s WHERE deploy_id = %s",
                 (resolved_at - timedelta(hours=1), deployment["deploy_id"]))
    assert conn.execute("SELECT count(*) AS n FROM v_shadow_se1 WHERE complaint_id = %s",
                        (complaint["complaint_id"],)).fetchone()["n"] == 1

    # The client gives an event end time inside the grace window, but submits the outcome after the deadline.
    finished = ok(engineer.post(f"{API}/deployments/{deployment['deploy_id']}/finish", json={
        "ended_at": iso(resolved_at + timedelta(hours=1)), "outcome": "CLEARED"}))
    outcome_received = datetime.fromisoformat(finished["outcome_recorded_at"])
    assert outcome_received > resolved_at + timedelta(hours=24)
    assert datetime.fromisoformat(finished["recorded_at"]) == resolved_at - timedelta(hours=1)
    assert conn.execute("SELECT count(*) AS n FROM v_shadow_se1 WHERE complaint_id = %s",
                        (complaint["complaint_id"],)).fetchone()["n"] == 1

    scan = ok(engineer.post(f"{API}/detections/scan"))
    assert scan["opened"] == 1
    alert = conn.execute("SELECT status FROM shadow_entry_alert WHERE complaint_id = %s",
                          (complaint["complaint_id"],)).fetchone()
    assert alert["status"] == "EVIDENCE_RECEIVED"

    # A later correction cannot reuse the original row receipt or the earlier outcome timestamp.
    with pytest.raises(psycopg.Error) as err:
        conn.execute("UPDATE machine_deployment SET outcome = 'FAILED' WHERE deploy_id = %s",
                     (deployment["deploy_id"],))
    assert err.value.sqlstate == "ZE003"
    with pytest.raises(psycopg.Error) as err:
        conn.execute("UPDATE machine_deployment SET ended_at = %s WHERE deploy_id = %s",
                     (resolved_at - timedelta(hours=1), deployment["deploy_id"]))
    assert err.value.sqlstate == "ZE003"
