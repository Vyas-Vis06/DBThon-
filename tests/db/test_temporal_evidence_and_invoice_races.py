"""Temporal clearance evidence and invoice/hold serialization (BR-23, BR-31, BR-35)."""

import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from tests.factories import Factory
from tests.helpers import act_as

ROOT = Path(__file__).resolve().parents[2]


def _invoice_world(conn, *, status="APPROVED"):
    f = Factory(conn)
    ulb = f.ulb()
    manhole = f.manhole(ulb)
    contractor = f.contractor()
    engineer = f.user("ENGINEER")
    complaint = f.resolved_complaint(manhole, datetime.now(timezone.utc) - timedelta(days=3))
    job = f.job(complaint, contractor)
    invoice = f.invoice(job, status=status, approver=engineer)
    worker = f.worker(contractor)
    return {"complaint": complaint, "job": job, "manhole": manhole, "contractor": contractor,
            "engineer": engineer, "worker": worker, "invoice": invoice}


def _background(db, actor, role, sql, params=(), *, contractor_id=None):
    started = threading.Event()
    result = {}

    def run():
        try:
            with db.connect("ze_app") as conn:
                act_as(conn, actor, role, contractor_id=contractor_id)
                result["pid"] = conn.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
                conn.execute("SET lock_timeout = '8s'")
                conn.execute("SET statement_timeout = '10s'")
                started.set()
                cursor = conn.execute(sql, params)
                result["row"] = cursor.fetchone() if cursor.description is not None else None
                result["ok"] = True
        except psycopg.Error as exc:
            result["sqlstate"] = exc.sqlstate
            result["error"] = str(exc)
        finally:
            started.set()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert started.wait(5), "background PostgreSQL session did not start"
    return thread, result


def _wait_for_lock(db, result):
    deadline = time.monotonic() + 5
    with db.connect() as observer:
        while time.monotonic() < deadline:
            pid = result.get("pid")
            if pid is not None:
                row = observer.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", (pid,)).fetchone()
                if row and row["wait_event_type"] == "Lock":
                    return
            time.sleep(0.01)
    pytest.fail("second session never waited on the expected database row lock")


def _source_statement(source, world):
    if source == "alert":
        return "SELECT * FROM scan_shadow_entries(now())", ()
    return ("CALL record_incident('FATALITY', now(), %s, %s, 'A worker collapsed at the work site.', %s, "
            "NULL, %s, NULL::bigint)",
            (world["worker"], world["manhole"], world["engineer"], world["job"]))


@pytest.mark.parametrize("source", ["alert", "incident"])
def test_invoice_creation_waiting_on_a_source_gets_that_source_hold(source, db, conn):
    world = _invoice_world(conn, status="SUBMITTED")
    sql, params = _source_statement(source, world)
    with db.connect("ze_app", autocommit=False) as source_tx:
        act_as(source_tx, world["engineer"], "ENGINEER")
        source_tx.execute(sql, params)
        thread, outcome = _background(
            db, world["engineer"], "ENGINEER",
            "INSERT INTO invoice (job_id, invoice_no, amount_inr) VALUES (%s, 'RACE-AFTER', 900)", (world["job"],))
        _wait_for_lock(db, outcome)
        source_tx.commit()
    thread.join(timeout=10)
    assert not thread.is_alive() and outcome.get("ok"), outcome

    with db.connect() as check:
        invoice_id = check.execute("SELECT invoice_id FROM invoice WHERE invoice_no = 'RACE-AFTER'").fetchone()["invoice_id"]
        holds = check.execute("SELECT reason FROM invoice_hold WHERE invoice_id = %s AND released_at IS NULL", (invoice_id,)).fetchall()
        assert [h["reason"] for h in holds] == (["SHADOW_ENTRY"] if source == "alert" else ["INCIDENT"])


@pytest.mark.parametrize("source", ["alert", "incident"])
def test_invoice_insert_waiting_on_source_gets_the_committed_source_hold(source, db, conn):
    world = _invoice_world(conn, status="SUBMITTED")
    sql, params = _source_statement(source, world)
    with db.connect("ze_app", autocommit=False) as invoice_tx:
        act_as(invoice_tx, world["engineer"], "ENGINEER")
        invoice_tx.execute("INSERT INTO invoice (job_id, invoice_no, amount_inr) VALUES (%s, 'RACE-BEFORE', 900)",
                           (world["job"],))
        invoice_id = invoice_tx.execute("SELECT invoice_id FROM invoice WHERE invoice_no = 'RACE-BEFORE'").fetchone()["invoice_id"]
        thread, outcome = _background(db, world["engineer"], "ENGINEER", sql, params)
        _wait_for_lock(db, outcome)
        invoice_tx.commit()
    thread.join(timeout=10)
    assert not thread.is_alive() and outcome.get("ok"), outcome

    with db.connect() as check:
        holds = check.execute("SELECT reason FROM invoice_hold WHERE invoice_id = %s AND released_at IS NULL", (invoice_id,)).fetchall()
        assert [h["reason"] for h in holds] == (["SHADOW_ENTRY"] if source == "alert" else ["INCIDENT"])


@pytest.mark.parametrize("source", ["alert", "incident"])
def test_payment_committing_before_a_source_hold_stays_paid_without_a_hold(source, db, conn):
    world = _invoice_world(conn, status="APPROVED")
    sql, params = _source_statement(source, world)
    with db.connect("ze_app", autocommit=False) as payment:
        act_as(payment, world["engineer"], "ENGINEER")
        payment.execute("UPDATE invoice SET status = 'PAID' WHERE invoice_id = %s", (world["invoice"],))
        thread, outcome = _background(db, world["engineer"], "ENGINEER", sql, params)
        _wait_for_lock(db, outcome)
        payment.commit()
    thread.join(timeout=10)
    assert not thread.is_alive() and outcome.get("ok"), outcome

    with db.connect() as check:
        assert check.execute("SELECT status FROM invoice WHERE invoice_id = %s", (world["invoice"],)).fetchone()["status"] == "PAID"
        assert check.execute("SELECT count(*) AS n FROM invoice_hold WHERE invoice_id = %s AND released_at IS NULL",
                             (world["invoice"],)).fetchone()["n"] == 0
        if source == "alert":
            source_count = check.execute("SELECT count(*) AS n FROM shadow_entry_alert WHERE complaint_id = %s",
                                         (world["complaint"],)).fetchone()["n"]
        else:
            source_count = check.execute("SELECT count(*) AS n FROM incident WHERE job_id = %s",
                                         (world["job"],)).fetchone()["n"]
        assert source_count == 1


@pytest.mark.parametrize("source", ["alert", "incident"])
@pytest.mark.parametrize(("initial_status", "decision"), [("SUBMITTED", "APPROVED"), ("APPROVED", "PAID")])
def test_source_hold_committing_before_approval_or_payment_blocks_it(source, db, conn, initial_status, decision):
    world = _invoice_world(conn, status=initial_status)
    sql, params = _source_statement(source, world)
    with db.connect("ze_app", autocommit=False) as scanner:
        act_as(scanner, world["engineer"], "ENGINEER")
        scanner.execute(sql, params)
        assert scanner.execute("SELECT count(*) AS n FROM invoice_hold WHERE invoice_id = %s AND released_at IS NULL",
                               (world["invoice"],)).fetchone()["n"] == 1

        if decision == "APPROVED":
            sql = "UPDATE invoice SET status = 'APPROVED', decided_by = %s WHERE invoice_id = %s"
            params = (world["engineer"], world["invoice"])
        else:
            sql = "UPDATE invoice SET status = 'PAID' WHERE invoice_id = %s"
            params = (world["invoice"],)
        thread, outcome = _background(db, world["engineer"], "ENGINEER", sql, params)
        _wait_for_lock(db, outcome)
        scanner.commit()
    thread.join(timeout=10)
    assert not thread.is_alive() and outcome.get("sqlstate") == "ZE003", outcome

    with db.connect() as check:
        assert check.execute("SELECT status FROM invoice WHERE invoice_id = %s", (world["invoice"],)).fetchone()["status"] == initial_status
        assert check.execute("SELECT count(*) AS n FROM invoice_hold WHERE invoice_id = %s AND released_at IS NULL",
                             (world["invoice"],)).fetchone()["n"] == 1


def test_a_late_machine_finalization_uses_server_receipt_not_the_old_deployment_receipt(conn, db):
    f = Factory(conn)
    ulb = f.ulb()
    manhole = f.manhole(ulb)
    contractor = f.contractor()
    engineer = f.user("ENGINEER")
    resolved_at = datetime.now(timezone.utc) - timedelta(days=3)
    complaint = f.resolved_complaint(manhole, resolved_at)
    job = f.job(complaint, contractor)
    machine = f.machine(ulb)
    deploy = f.deployment(job, machine, None, started_at=resolved_at - timedelta(hours=2),
                          recorded_at=resolved_at - timedelta(hours=1))
    assert conn.execute("SELECT outcome_recorded_at FROM machine_deployment WHERE deploy_id = %s", (deploy,)).fetchone()["outcome_recorded_at"] is None

    with db.connect("ze_app") as runtime:
        act_as(runtime, engineer, "ENGINEER")
        # `ended_at` is supplied by the field user; the outcome receipt is assigned independently by the server.
        runtime.execute("UPDATE machine_deployment SET ended_at = %s, outcome = 'CLEARED' WHERE deploy_id = %s",
                        (resolved_at + timedelta(days=2), deploy))

    finalized = conn.execute("SELECT recorded_at, outcome_recorded_at FROM machine_deployment WHERE deploy_id = %s",
                             (deploy,)).fetchone()
    assert finalized["recorded_at"] == resolved_at - timedelta(hours=1)
    assert finalized["outcome_recorded_at"] > resolved_at + timedelta(hours=24)
    assert conn.execute("SELECT count(*) AS n FROM v_shadow_se1 WHERE complaint_id = %s", (complaint,)).fetchone()["n"] == 1

    # This must be caught even when no earlier scan created an alert.
    scan = conn.execute("SELECT * FROM scan_shadow_entries(now())").fetchone()
    assert scan["opened"] == 1
    alert = conn.execute("SELECT status FROM shadow_entry_alert WHERE complaint_id = %s", (complaint,)).fetchone()
    assert alert["status"] == "EVIDENCE_RECEIVED"

    with pytest.raises(psycopg.Error) as err:
        conn.execute("UPDATE machine_deployment SET outcome = 'FAILED', ended_at = %s WHERE deploy_id = %s",
                     (resolved_at + timedelta(days=2), deploy))
    assert err.value.sqlstate == "ZE003"
    with pytest.raises(psycopg.Error) as err:
        conn.execute("UPDATE machine_deployment SET ended_at = %s WHERE deploy_id = %s",
                     (resolved_at + timedelta(hours=1), deploy))
    assert err.value.sqlstate == "ZE003"


def test_runtime_role_cannot_set_or_rewrite_the_machine_outcome_receipt(conn, db):
    f = Factory(conn)
    ulb = f.ulb()
    manhole = f.manhole(ulb)
    contractor = f.contractor()
    engineer = f.user("ENGINEER")
    complaint = f.complaint(manhole)
    job = f.job(complaint, contractor)
    machine = f.machine(ulb)

    with db.connect("ze_app") as runtime:
        act_as(runtime, engineer, "ENGINEER")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            runtime.execute("INSERT INTO machine_deployment (job_id, machine_id, started_at, ended_at, outcome, recorded_at) "
                            "VALUES (%s, %s, now(), now(), 'CLEARED', now() - interval '2 days')",
                            (job, machine))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            runtime.execute("UPDATE machine_deployment SET outcome_recorded_at = now() - interval '2 days'")


def test_migration_backfills_audited_finalization_and_leaves_unverifiable_legacy_outcomes_null(cluster):
    """The old row receipt is not used as the finalization time when an outcome was added later."""
    database = f"ze_backfill_{uuid4().hex[:10]}"
    with cluster.connect("postgres") as admin:
        admin.execute(f'CREATE DATABASE "{database}"')
    try:
        with cluster.connect(database) as conn:
            conn.execute("CREATE TABLE alembic_version (version_num varchar(32) PRIMARY KEY NOT NULL)")
            sql_dir = ROOT / "database" / "migrations" / "sql"
            # A pre-0012 database has only the numbered migration SQL available at this point.
            for migration in sorted(sql_dir.glob("00*.sql")):
                if int(migration.name[:4]) <= 11:
                    conn.execute(migration.read_text(encoding="utf-8"))

            f = Factory(conn)
            ulb = f.ulb()
            manhole = f.manhole(ulb)
            contractor = f.contractor()
            complaint = f.complaint(manhole)
            job = f.job(complaint, contractor)
            machine = f.machine(ulb)
            old_receipt = datetime(2026, 1, 1, tzinfo=timezone.utc)
            transitioned = f.deployment(job, machine, None, started_at=old_receipt,
                                        recorded_at=old_receipt + timedelta(minutes=1))
            conn.execute("UPDATE machine_deployment SET ended_at = %s, outcome = 'CLEARED' WHERE deploy_id = %s",
                         (old_receipt + timedelta(hours=1), transitioned))
            audit_at = conn.execute("SELECT occurred_at FROM audit_log WHERE table_name = 'machine_deployment' "
                                    "AND row_pk = %s AND action = 'UPDATE' ORDER BY log_id DESC LIMIT 1",
                                    (str(transitioned),)).fetchone()["occurred_at"]

            # Simulate an old row whose audit evidence was removed/never captured: migration must not promote its
            # original row receipt to a fabricated finalization receipt.
            conn.execute("ALTER TABLE machine_deployment DISABLE TRIGGER trg_audit")
            unverifiable = conn.execute(
                "INSERT INTO machine_deployment (job_id, machine_id, started_at, ended_at, outcome, recorded_at) "
                "VALUES (%s, %s, %s, %s, 'CLEARED', %s) RETURNING deploy_id",
                (job, machine, old_receipt, old_receipt + timedelta(hours=1), old_receipt + timedelta(minutes=2)))
            unverifiable_id = unverifiable.fetchone()["deploy_id"]
            conn.execute("ALTER TABLE machine_deployment ENABLE TRIGGER trg_audit")

            conn.execute((sql_dir / "0012_temporal_evidence_invoice_serialization.sql").read_text(encoding="utf-8"))
            rows = conn.execute("SELECT deploy_id, recorded_at, outcome_recorded_at FROM machine_deployment "
                                "WHERE deploy_id = ANY(%s) ORDER BY deploy_id",
                                ([transitioned, unverifiable_id],)).fetchall()

        known, unknown = rows
        assert known["recorded_at"] == old_receipt + timedelta(minutes=1)
        assert known["outcome_recorded_at"] == audit_at
        assert known["outcome_recorded_at"] != known["recorded_at"]
        assert unknown["recorded_at"] == old_receipt + timedelta(minutes=2)
        assert unknown["outcome_recorded_at"] is None
    finally:
        with cluster.connect("postgres") as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
