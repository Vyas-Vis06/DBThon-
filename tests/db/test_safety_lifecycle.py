"""Continuing safety authorization, dependency revocation, sweeps, exits and parent-identity immutability."""

import threading
from datetime import datetime, timedelta

import pytest

from tests.factories import Factory, IST
from tests.helpers import act_as, expect


def authorize(conn, scenario):
    rows = conn.execute("SELECT * FROM authorise_entry(%s, %s, %s)",
                        (scenario["permit"], scenario["supervisor"], scenario["at"])).fetchall()
    return rows


def current_permit(conn, f, *, at=None):
    """A permit whose readings are fresh now and whose synthetic daylight spans the full day."""
    conn.execute("UPDATE rule_parameter SET value = 0 WHERE param_key = 'daylight_start_hour'")
    conn.execute("UPDATE rule_parameter SET value = 24 WHERE param_key = 'daylight_end_hour'")
    scenario = f.gate_scenario(at or datetime.now(IST))
    rows = authorize(conn, scenario)
    assert rows and all(row["passed"] for row in rows)
    return scenario


def test_unsafe_latest_gas_reading_aborts_the_active_permit(conn):
    f = Factory(conn)
    s = current_permit(conn, f)
    f.reading(s["permit"], s["detector"], "TOP", datetime.now(IST), s["supervisor"], o2=18.0)
    permit = conn.execute("SELECT status, end_reason FROM entry_permit WHERE permit_id = %s", (s["permit"],)).fetchone()
    assert permit["status"] == "ABORTED" and "GAS_TOP" in permit["end_reason"]
    events = conn.execute("SELECT event_type, reason_code FROM permit_safety_event WHERE permit_id = %s", (s["permit"],)).fetchall()
    assert {row["event_type"] for row in events} >= {"PERMIT_ABORTED", "SAFETY_STOP"}
    assert any(row["reason_code"] == "CURRENT_CLAUSE_FAILED" for row in events)


def test_entry_recheck_commits_safety_stop_without_admitting_the_row(conn):
    f = Factory(conn)
    at = datetime.now(IST) - timedelta(minutes=16)
    s = current_permit(conn, f, at=at)
    assert conn.execute("SELECT status FROM entry_permit WHERE permit_id = %s", (s["permit"],)).fetchone()["status"] == "AUTHORISED"

    inserted = conn.execute("INSERT INTO entry_log (permit_id, worker_id, period, recorded_by) "
                            "VALUES (%s, %s, tstzrange(%s, NULL, '[)'), %s) RETURNING entry_id",
                            (s["permit"], s["e1"], datetime.now(IST), s["supervisor"])).fetchone()
    assert inserted is None
    permit = conn.execute("SELECT status, end_reason FROM entry_permit WHERE permit_id = %s", (s["permit"],)).fetchone()
    assert permit["status"] == "ABORTED" and "GAS_TOP" in permit["end_reason"]
    assert conn.execute("SELECT count(*) AS n FROM entry_log WHERE permit_id = %s", (s["permit"],)).fetchone()["n"] == 0


@pytest.mark.parametrize("cause", ["expired_gas", "expired_permit"])
def test_server_sweep_stops_time_expired_authorization_with_durable_idempotent_evidence(conn, cause):
    f = Factory(conn)
    at = datetime.now(IST) - (timedelta(minutes=16) if cause == "expired_gas" else timedelta(hours=5))
    s = current_permit(conn, f, at=at)
    stopped = conn.execute("SELECT sweep_permit_safety() AS n").fetchone()["n"]
    assert stopped == 1
    permit = conn.execute("SELECT status, end_reason FROM entry_permit WHERE permit_id = %s", (s["permit"],)).fetchone()
    expected = "GAS_TOP" if cause == "expired_gas" else "PERMIT_EXPIRED"
    assert permit["status"] == "ABORTED" and expected in permit["end_reason"]
    event_count = conn.execute("SELECT count(*) AS n FROM permit_safety_event WHERE permit_id = %s", (s["permit"],)).fetchone()["n"]
    assert event_count >= 2
    assert conn.execute("SELECT sweep_permit_safety() AS n").fetchone()["n"] == 0
    assert conn.execute("SELECT count(*) AS n FROM permit_safety_event WHERE permit_id = %s", (s["permit"],)).fetchone()["n"] == event_count


def test_sweep_stops_an_overstayed_open_entry_without_losing_its_later_exit(conn):
    f = Factory(conn)
    s = current_permit(conn, f)
    entered = datetime.now(IST)
    entry_id = conn.execute("INSERT INTO entry_log (permit_id, worker_id, period, recorded_by) "
                             "VALUES (%s, %s, tstzrange(%s, NULL, '[)'), %s) RETURNING entry_id",
                             (s["permit"], s["e1"], entered, s["supervisor"])).fetchone()["entry_id"]
    future_check = datetime.now(IST) + timedelta(minutes=91)
    assert conn.execute("SELECT sweep_permit_safety_at(%s) AS n", (future_check,)).fetchone()["n"] == 1
    assert conn.execute("SELECT sweep_permit_safety_at(%s) AS n", (future_check,)).fetchone()["n"] == 0
    overstay = conn.execute("SELECT event_id FROM permit_safety_event WHERE entry_id = %s AND event_type = 'OPEN_ENTRY_OVERSTAY'",
                            (entry_id,)).fetchall()
    assert len(overstay) == 1

    exit_at = datetime.now(IST) + timedelta(minutes=2)
    conn.execute("UPDATE entry_log SET period = tstzrange(%s, %s, '[)') WHERE entry_id = %s", (entered, exit_at, entry_id))
    exit_row = conn.execute("SELECT upper(period) AS exited_at, exit_recorded_at FROM entry_log WHERE entry_id = %s", (entry_id,)).fetchone()
    permit = conn.execute("SELECT status, end_reason FROM entry_permit WHERE permit_id = %s", (s["permit"],)).fetchone()
    assert exit_row["exited_at"] == exit_at and exit_row["exit_recorded_at"] is not None
    assert permit["status"] == "ABORTED" and "OPEN_ENTRY_OVERSTAY" in permit["end_reason"]


@pytest.mark.parametrize("field", ["is_active", "medical_fit_until", "trained_until"])
def test_worker_credential_changes_stop_authorized_permits(conn, field):
    f = Factory(conn)
    s = current_permit(conn, f)
    value = "false" if field == "is_active" else "CURRENT_DATE - 1"
    conn.execute(f"UPDATE worker SET {field} = {value} WHERE worker_id = %s", (s["e1"],))
    permit = conn.execute("SELECT status, end_reason FROM entry_permit WHERE permit_id = %s", (s["permit"],)).fetchone()
    assert permit["status"] == "ABORTED" and "CREW_FIT" in permit["end_reason"]


def test_contractor_detector_and_job_dependency_changes_stop_active_permits(conn):
    f = Factory(conn)
    s = current_permit(conn, f)
    conn.execute("UPDATE gas_detector SET calibration_valid_until = CURRENT_DATE - 1 WHERE detector_id = %s", (s["detector"],))
    detector_reason = conn.execute("SELECT end_reason FROM entry_permit WHERE permit_id = %s", (s["permit"],)).fetchone()["end_reason"]
    assert "GAS_TOP" in detector_reason

    s2 = current_permit(conn, f)
    conn.execute("UPDATE contractor SET status = 'SUSPENDED' WHERE contractor_id = %s", (s2["contractor"],))
    contractor_reason = conn.execute("SELECT end_reason FROM entry_permit WHERE permit_id = %s", (s2["permit"],)).fetchone()["end_reason"]
    assert "CONTRACTOR_OK" in contractor_reason

    s3 = current_permit(conn, f)
    new_contractor = f.contractor()
    conn.execute("UPDATE job SET contractor_id = %s WHERE job_id = %s", (new_contractor, s3["job"]))
    job_reason = conn.execute("SELECT end_reason FROM entry_permit WHERE permit_id = %s", (s3["permit"],)).fetchone()["end_reason"]
    assert "JOB_CONTRACTOR_CHANGED" in job_reason


def test_permit_and_crew_parent_ids_cannot_be_reassigned_by_runtime_raw_sql(db, conn):
    f = Factory(conn)
    s = current_permit(conn, f)
    with db.connect(user="ze_app") as app:
        act_as(app, s["supervisor"], "SUPERVISOR", ulb_id=s["ulb"])
        with expect("ZE003", "identifiers are immutable"):
            app.execute("UPDATE permit_crew SET permit_id = 999999 WHERE permit_id = %s AND worker_id = %s", (s["permit"], s["e1"]))
        with expect("ZE003", "identifiers are immutable"):
            app.execute("UPDATE permit_crew SET worker_id = %s WHERE permit_id = %s AND worker_id = %s",
                        (s["e2"], s["permit"], s["e1"]))
        with expect("ZE003", "identifiers are immutable"):
            app.execute("UPDATE gear_issue SET permit_id = 999999 WHERE permit_id = %s AND worker_id = %s",
                        (s["permit"], s["e1"]))
        with expect("ZE003", "identifiers are immutable"):
            app.execute("UPDATE gear_issue SET worker_id = %s WHERE permit_id = %s AND worker_id = %s",
                        (s["e2"], s["permit"], s["e1"]))
        with expect("42501"):
            app.execute("SELECT lock_permit(%s)", (s["permit"],))


@pytest.mark.parametrize("dependency", ["worker", "detector"])
def test_dependency_revoke_waits_for_inflight_authorization_then_rechecks(conn, db, dependency):
    f = Factory(conn)
    s = f.gate_scenario(datetime.now(IST))
    auth = db.connect(autocommit=False)
    rows = auth.execute("SELECT * FROM authorise_entry(%s, %s, %s)",
                        (s["permit"], s["supervisor"], s["at"])).fetchall()
    assert rows and all(row["passed"] for row in rows)
    started, finished = threading.Event(), threading.Event()
    errors = []

    def revoke():
        try:
            with db.connect() as other:
                started.set()
                if dependency == "worker":
                    other.execute("UPDATE worker SET is_active = false WHERE worker_id = %s", (s["e1"],))
                else:
                    other.execute("UPDATE gas_detector SET calibration_valid_until = CURRENT_DATE - 1 WHERE detector_id = %s",
                                  (s["detector"],))
        except Exception as exc:  # noqa: BLE001 - surface thread failures to pytest
            errors.append(exc)
        finally:
            finished.set()

    thread = threading.Thread(target=revoke, daemon=True)
    thread.start()
    assert started.wait(timeout=3)
    assert not finished.wait(timeout=0.25), "dependency update did not wait for the in-flight permit decision"
    auth.commit()
    thread.join(timeout=8)
    auth.close()
    assert not thread.is_alive() and not errors, errors
    permit = conn.execute("SELECT status, end_reason FROM entry_permit WHERE permit_id = %s", (s["permit"],)).fetchone()
    expected = "CREW_FIT" if dependency == "worker" else "GAS_TOP"
    assert permit["status"] == "ABORTED" and expected in permit["end_reason"]


@pytest.mark.parametrize("dependency", ["worker", "detector"])
def test_dependency_change_first_serializes_before_permit_authorization(conn, db, dependency):
    f = Factory(conn)
    s = f.gate_scenario(datetime.now(IST))
    dep = db.connect(autocommit=False)
    if dependency == "worker":
        dep.execute("UPDATE worker SET is_active = false WHERE worker_id = %s", (s["e1"],))
    else:
        dep.execute("UPDATE gas_detector SET calibration_valid_until = CURRENT_DATE - 1 WHERE detector_id = %s",
                    (s["detector"],))

    started, finished = threading.Event(), threading.Event()
    result, errors = [], []

    def authorize_while_dependency_uncommitted():
        try:
            with db.connect() as other:
                started.set()
                result.extend(other.execute("SELECT * FROM authorise_entry(%s, %s, %s)",
                                            (s["permit"], s["supervisor"], s["at"])).fetchall())
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            finished.set()

    thread = threading.Thread(target=authorize_while_dependency_uncommitted, daemon=True)
    thread.start()
    assert started.wait(timeout=3)
    assert not finished.wait(timeout=0.25), "authorisation did not wait for dependency revalidation lock"
    dep.commit()
    thread.join(timeout=8)
    dep.close()
    assert not thread.is_alive() and not errors, errors
    assert result and not all(row["passed"] for row in result)
    assert conn.execute("SELECT status FROM entry_permit WHERE permit_id = %s", (s["permit"],)).fetchone()["status"] == "DRAFT"
