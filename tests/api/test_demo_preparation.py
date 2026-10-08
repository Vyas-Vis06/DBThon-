"""Rehearsal preparation uses the real authenticated workflow, never owner SQL."""

import importlib.util
from pathlib import Path

import pytest

from tests.api.conftest import API, ok


spec = importlib.util.spec_from_file_location(
    "ze_prepare_demo", Path(__file__).resolve().parents[2] / "scripts/prepare_demo.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def clients(api):
    return {"engineer": api("engineer"), "supervisor": api("supervisor"),
            **{f"worker_{i}": api("worker_a" if i == 1 else f"worker_a_{i-1}") for i in range(1, 5)}}


def test_preparation_is_draft_with_one_real_missing_ack_and_complete_other_evidence(api, conn):
    result = demo.prepare(clients(api))
    pid = result["permit_id"]
    assert result["policy"] == "EDUCATIONAL" and result["status"] == "DRAFT"
    assert result["acknowledgement_still_required_from"] == "worker_a_3@zeroentry.example"
    row = conn.execute("SELECT status FROM entry_permit WHERE permit_id=%s", (pid,)).fetchone()
    assert row["status"] == "DRAFT"
    clauses = ok(api("supervisor").get(f"{API}/permits/{pid}"))["clauses"]
    failed = {item["clause_code"] for item in clauses if not item["passed"]}
    # The real current daylight rule may also deny a rehearsal run outside its configured hours.
    assert "CREW_ACK" in failed and failed <= {"CREW_ACK", "DAYLIGHT"}
    assert conn.execute("SELECT count(*) AS n FROM permit_readiness WHERE permit_id=%s", (pid,)).fetchone()["n"] == 7
    assert conn.execute("SELECT count(*) AS n FROM gas_reading WHERE permit_id=%s AND source_mode='SIMULATED'", (pid,)).fetchone()["n"] == 3
    assert conn.execute("SELECT count(*) AS n FROM permit_authorization_decision").fetchone()["n"] == 0


def test_preparation_refuses_real_scope_before_any_business_mutation(api, conn, world):
    conn.execute("UPDATE ulb SET policy_mode='REVIEW_REQUIRED' WHERE ulb_id=%s", (world["ulb"],))
    with pytest.raises(RuntimeError, match="EDUCATIONAL"):
        demo.prepare(clients(api))
    assert conn.execute("SELECT count(*) AS n FROM complaint").fetchone()["n"] == 0
    assert conn.execute("SELECT count(*) AS n FROM gear_asset").fetchone()["n"] == 0
