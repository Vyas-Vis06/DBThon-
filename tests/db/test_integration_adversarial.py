"""Cross-migration adversarial integration probes that span the live gate and safety lifecycle."""

from datetime import datetime, timedelta, timezone
import threading
import time

import psycopg
import pytest
from psycopg.types.range import Range

from tests.factories import Factory, IST
from tests.helpers import act_as


def _invoice_world(conn, *, invoice_status="APPROVED"):
    f = Factory(conn)
    ulb = f.ulb()
    manhole = f.manhole(ulb)
    contractor = f.contractor()
    engineer = f.user("ENGINEER")
    complaint = f.resolved_complaint(manhole, datetime.now(timezone.utc) - timedelta(days=3))
    job = f.job(complaint, contractor)
    invoice = f.invoice(job, status=invoice_status, approver=engineer)
    return {"engineer": engineer, "manhole": manhole, "contractor": contractor, "complaint": complaint,
            "job": job, "invoice": invoice}


def _wait_for_lock(db, result):
    deadline = time.monotonic() + 5
    with db.connect() as observer:
        while time.monotonic() < deadline:
            pid = result.get("pid")
            if pid is not None:
                activity = observer.execute(
                    "SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", (pid,)
                ).fetchone()
                if activity and activity["wait_event_type"] == "Lock":
                    return
            time.sleep(0.01)
    pytest.fail("concurrent writer never waited on the expected database row lock")


def test_open_entry_cannot_be_closed_with_a_future_reported_exit(conn):
    """An exit event cannot be recorded before it physically occurs."""
    conn.execute("UPDATE rule_parameter SET value = 0 WHERE param_key = 'daylight_start_hour'")
    conn.execute("UPDATE rule_parameter SET value = 24 WHERE param_key = 'daylight_end_hour'")
    f = Factory(conn)
    scenario = f.gate_scenario(datetime.now(IST))
    conn.execute("SELECT * FROM authorise_entry(%s, %s, %s)",
                 (scenario["permit"], scenario["supervisor"], scenario["at"]))

    entered_at = datetime.now(timezone.utc) + timedelta(seconds=5)
    entry_id = conn.execute(
        "INSERT INTO entry_log (permit_id, worker_id, period, recorded_by) "
        "VALUES (%s, %s, tstzrange(%s, NULL, '[)'), %s) RETURNING entry_id",
        (scenario["permit"], scenario["e1"], entered_at, scenario["supervisor"]),
    ).fetchone()["entry_id"]

    with pytest.raises(psycopg.Error):
        conn.execute("UPDATE entry_log SET period = %s WHERE entry_id = %s",
                     (Range(entered_at, datetime.now(timezone.utc) + timedelta(minutes=15), "[)"), entry_id))


def test_runtime_cannot_forge_rule_update_metadata_without_a_revision(db, conn):
    f = Factory(conn)
    admin_id = f.user("ADMIN")
    other_admin_id = f.user("ADMIN")
    before = conn.execute(
        "SELECT updated_by, updated_at FROM rule_parameter WHERE param_key = 'gas_h2s_max_ppm'"
    ).fetchone()
    count_before = conn.execute(
        "SELECT count(*) AS n FROM rule_parameter_history WHERE param_key = 'gas_h2s_max_ppm'"
    ).fetchone()["n"]

    with db.connect("ze_app") as runtime:
        act_as(runtime, admin_id, "ADMIN")
        try:
            runtime.execute(
                "UPDATE rule_parameter SET updated_by = %s, updated_at = '2000-01-01' "
                "WHERE param_key = 'gas_h2s_max_ppm'",
                (other_admin_id,),
            )
        except psycopg.Error:
            # A column-level privilege or trigger may refuse the client-supplied metadata outright.
            pass

    after = conn.execute(
        "SELECT updated_by, updated_at FROM rule_parameter WHERE param_key = 'gas_h2s_max_ppm'"
    ).fetchone()
    count_after = conn.execute(
        "SELECT count(*) AS n FROM rule_parameter_history WHERE param_key = 'gas_h2s_max_ppm'"
    ).fetchone()["n"]
    assert after == before
    assert count_after == count_before


def test_authorisation_rechecks_gas_freshness_after_waiting_for_the_permit_row(db, conn):
    """A long lock wait must not authorize against the transaction-start clock."""
    conn.execute("UPDATE rule_parameter SET value = 0 WHERE param_key = 'daylight_start_hour'")
    conn.execute("UPDATE rule_parameter SET value = 24 WHERE param_key = 'daylight_end_hour'")
    conn.execute("UPDATE rule_parameter SET value = 1 WHERE param_key = 'gas_max_age_min'")
    f = Factory(conn)
    at = datetime.now(IST)
    s = f.gate_scenario(at, readings={
        "TOP": {"age_min": 0.95}, "MID": {"age_min": 0.95}, "BOTTOM": {"age_min": 0.95},
    })

    started = threading.Event()
    result = {}

    def authorise_after_wait():
        try:
            with db.connect("ze_app", autocommit=False) as app:
                act_as(app, s["supervisor"], "SUPERVISOR")
                result["decision_clock"] = app.execute("SELECT now() AS at").fetchone()["at"]
                result["pid"] = app.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
                app.execute("SET lock_timeout = '20s'")
                started.set()
                result["rows"] = app.execute(
                    "SELECT * FROM authorise_entry(%s, %s, now())", (s["permit"], s["supervisor"])
                ).fetchall()
                result["ok"] = True
        except psycopg.Error as exc:
            result["sqlstate"] = exc.sqlstate
            result["error"] = str(exc)
        finally:
            started.set()

    with db.connect(autocommit=False) as blocker:
        blocker.execute("SELECT permit_id FROM entry_permit WHERE permit_id = %s FOR UPDATE", (s["permit"],))
        thread = threading.Thread(target=authorise_after_wait, daemon=True)
        thread.start()
        assert started.wait(5)
        deadline = time.monotonic() + 5
        with db.connect() as observer:
            while time.monotonic() < deadline:
                pid = result.get("pid")
                if pid is not None:
                    activity = observer.execute(
                        "SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", (pid,)
                    ).fetchone()
                    if activity and activity["wait_event_type"] == "Lock":
                        break
                time.sleep(0.01)
            else:
                pytest.fail("authorisation session never waited for the blocked permit row")
        time.sleep(6)  # take the 57-second gas samples past the one-minute freshness limit
        blocker.commit()
    thread.join(timeout=25)
    assert not thread.is_alive() and result.get("ok"), result

    status = conn.execute("SELECT status FROM entry_permit WHERE permit_id = %s", (s["permit"],)).fetchone()["status"]
    current_failures = conn.execute(
        "SELECT count(*) AS n FROM permit_clause_check(%s, clock_timestamp()) WHERE NOT passed", (s["permit"],)
    ).fetchone()["n"]
    assert status == "DRAFT"
    assert current_failures >= 3


@pytest.mark.parametrize("path", ["authorise_entry", "raw_update"])
def test_repeatable_read_authorization_cannot_use_a_stale_draft_dependency(db, conn, path):
    """A runtime RR snapshot must not authorize after a DRAFT crew member becomes inactive."""
    conn.execute("UPDATE rule_parameter SET value = 0 WHERE param_key = 'daylight_start_hour'")
    conn.execute("UPDATE rule_parameter SET value = 24 WHERE param_key = 'daylight_end_hour'")
    s = Factory(conn).gate_scenario(datetime.now(IST))

    with db.connect("ze_app", autocommit=False) as runtime:
        runtime.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        runtime.execute("SET lock_timeout = '8s'")
        runtime.execute("SET statement_timeout = '12s'")
        act_as(runtime, s["supervisor"], "SUPERVISOR")
        assert runtime.execute(
            "SELECT is_active FROM worker WHERE worker_id = %s", (s["e1"],)
        ).fetchone()["is_active"]

        # The dependency trigger serializes DRAFT permits but intentionally does not rewrite their state.
        conn.execute("UPDATE worker SET is_active = false WHERE worker_id = %s", (s["e1"],))
        with pytest.raises(psycopg.Error) as error:
            if path == "authorise_entry":
                runtime.execute("SELECT * FROM authorise_entry(%s, %s, now())", (s["permit"], s["supervisor"]))
            else:
                runtime.execute(
                    "UPDATE entry_permit SET status = 'AUTHORISED', authorised_at = now(), authorised_by = %s "
                    "WHERE permit_id = %s",
                    (s["supervisor"], s["permit"]),
                )
        assert error.value.sqlstate == "40001"
        runtime.rollback()

    assert conn.execute("SELECT status FROM entry_permit WHERE permit_id = %s", (s["permit"],)).fetchone()["status"] == "DRAFT"
    assert conn.execute(
        "SELECT count(*) AS n FROM permit_authorization_decision WHERE permit_id = %s", (s["permit"],)
    ).fetchone()["n"] == 0


def test_repeatable_read_payment_waiting_for_new_alert_hold_is_rejected(db, conn):
    """A stale transaction snapshot cannot pay through an alert hold that won the invoice lock."""
    world = _invoice_world(conn)
    prepared, proceed = threading.Event(), threading.Event()
    outcome = {}

    def pay_from_repeatable_read_snapshot():
        try:
            with db.connect("ze_app", autocommit=False) as payment:
                payment.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                act_as(payment, world["engineer"], "ENGINEER")
                outcome["holds_before"] = payment.execute(
                    "SELECT count(*) AS n FROM invoice_hold WHERE invoice_id = %s AND released_at IS NULL",
                    (world["invoice"],),
                ).fetchone()["n"]
                outcome["pid"] = payment.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
                prepared.set()
                assert proceed.wait(10)
                payment.execute("SET lock_timeout = '10s'")
                payment.execute("UPDATE invoice SET status = 'PAID' WHERE invoice_id = %s", (world["invoice"],))
                payment.commit()
                outcome["paid"] = True
        except psycopg.Error as exc:
            outcome["sqlstate"] = exc.sqlstate
            outcome["error"] = str(exc)
        finally:
            prepared.set()

    payment_thread = threading.Thread(target=pay_from_repeatable_read_snapshot, daemon=True)
    payment_thread.start()
    assert prepared.wait(5)
    assert outcome.get("holds_before") == 0

    with db.connect("ze_app", autocommit=False) as source:
        act_as(source, world["engineer"], "ENGINEER")
        assert source.execute("SELECT * FROM scan_shadow_entries(clock_timestamp())").fetchall()
        assert source.execute(
            "SELECT count(*) AS n FROM invoice_hold WHERE invoice_id = %s AND released_at IS NULL",
            (world["invoice"],),
        ).fetchone()["n"] == 1
        proceed.set()
        _wait_for_lock(db, outcome)
        source.commit()

    payment_thread.join(timeout=12)
    assert not payment_thread.is_alive(), "payment session did not finish after the alert released its invoice lock"
    assert outcome.get("sqlstate") == "40001", outcome
    after = conn.execute("SELECT status FROM invoice WHERE invoice_id = %s", (world["invoice"],)).fetchone()["status"]
    holds = conn.execute(
        "SELECT reason FROM invoice_hold WHERE invoice_id = %s AND released_at IS NULL", (world["invoice"],)
    ).fetchall()
    assert after == "APPROVED"
    assert [h["reason"] for h in holds] == ["SHADOW_ENTRY"]


def test_repeatable_read_invoice_creation_after_alert_fails_with_retryable_error(db, conn):
    """Invoice creation must not use a pinned snapshot to miss a just-committed source alert."""
    world = _invoice_world(conn, invoice_status="SUBMITTED")
    invoice_tx = db.connect("ze_app", autocommit=False)
    invoice_tx.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
    act_as(invoice_tx, world["engineer"], "ENGINEER")
    assert invoice_tx.execute("SELECT count(*) AS n FROM shadow_entry_alert").fetchone()["n"] == 0

    with db.connect("ze_app", autocommit=False) as source:
        act_as(source, world["engineer"], "ENGINEER")
        assert source.execute("SELECT * FROM scan_shadow_entries(clock_timestamp())").fetchall()
        with pytest.raises(psycopg.Error) as error:
            invoice_tx.execute(
                "INSERT INTO invoice (job_id, invoice_no, amount_inr) VALUES (%s, 'RR-AFTER-ALERT', 900)",
                (world["job"],),
            )
        assert error.value.sqlstate == "40001"
        invoice_tx.rollback()
        source.commit()

    assert conn.execute("SELECT count(*) AS n FROM invoice WHERE invoice_no = 'RR-AFTER-ALERT'").fetchone()["n"] == 0
    alert = conn.execute(
        "SELECT alert_id FROM shadow_entry_alert WHERE complaint_id = %s", (world["complaint"],)
    ).fetchone()
    assert alert is not None


@pytest.mark.parametrize("source", ["alert", "incident"])
def test_repeatable_read_source_creation_fails_with_retryable_error(db, conn, source):
    """Both source writers must reject pinned snapshots before hold placement can miss invoices."""
    world = _invoice_world(conn)
    worker = Factory(conn).worker(world["contractor"])
    with db.connect("ze_app", autocommit=False) as runtime:
        runtime.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        act_as(runtime, world["engineer"], "ENGINEER")
        if source == "alert":
            statement = "SELECT * FROM scan_shadow_entries(clock_timestamp())"
            params = ()
        else:
            statement = (
                "CALL record_incident('FATALITY', clock_timestamp(), %s, %s, "
                "'A worker collapsed at the work site.', %s, NULL, %s, NULL::bigint)"
            )
            params = (worker, world["manhole"], world["engineer"], world["job"])
        with pytest.raises(psycopg.Error) as error:
            runtime.execute(statement, params)
        assert error.value.sqlstate == "40001"
        runtime.rollback()

    assert conn.execute(
        "SELECT count(*) AS n FROM shadow_entry_alert WHERE complaint_id = %s", (world["complaint"],)
    ).fetchone()["n"] == 0
    assert conn.execute("SELECT count(*) AS n FROM incident WHERE job_id = %s", (world["job"],)).fetchone()["n"] == 0


def test_runtime_cannot_call_financialrace_trigger_helper(db):
    with db.connect("ze_app") as runtime:
        assert not runtime.execute(
            "SELECT has_function_privilege('ze_app', "
            "'public.require_read_committed_financialrace()', 'EXECUTE') AS allowed"
        ).fetchone()["allowed"]
        with pytest.raises(psycopg.errors.InsufficientPrivilege) as error:
            runtime.execute("SELECT public.require_read_committed_financialrace()")
        assert error.value.sqlstate == "42501"
