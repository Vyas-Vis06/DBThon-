"""Consequences: the atomic fatality transaction, invoice holds with provenance, compensation, report views.
PROJECT_SPEC BR-20 .. BR-23."""

from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from tests.factories import Factory, yesterday_ist
from tests.helpers import expect


@pytest.fixture
def f(conn):
    return Factory(conn)


@pytest.fixture
def world(conn, f):
    """An authorised permit with e1 inside, plus invoices in each state and an unrelated job with an invoice."""
    s = f.gate_scenario(yesterday_ist(10, 0))
    rows = conn.execute("SELECT * FROM authorise_entry(%s, %s, %s)", (s["permit"], s["supervisor"], s["at"])).fetchall()
    assert all(r["passed"] for r in rows)
    s["inv_submitted"] = f.invoice(s["job"])
    s["inv_approved"] = f.invoice(s["job"], status="APPROVED", approver=s["engineer"])
    s["inv_paid"] = f.invoice(s["job"], status="PAID", approver=s["engineer"])
    other_contractor = f.contractor()
    s["other_job"] = f.job(f.complaint(s["manhole"]), other_contractor)
    s["other_invoice"] = f.invoice(s["other_job"])
    s["other_contractor"] = other_contractor
    return s


def record(conn, s, kind="FATALITY", *, occurred_at=None, worker="e1", permit=True, job=None, by=None, worker_id=None):
    occurred_at = occurred_at or s["at"] + timedelta(minutes=30)
    row = conn.execute(
        "CALL record_incident(%s, %s, %s, %s, %s, %s, %s, %s, NULL::bigint)",
        (kind, occurred_at, worker_id or s[worker], s["manhole"], "Worker collapsed inside the chamber",
         by or s["engineer"], s["permit"] if permit else None, job)).fetchone()
    return row["p_incident_id"]


def n(conn, sql, *params):
    return conn.execute(sql, params).fetchone()["n"]


# --- the consequence transaction -------------------------------------------------------------------------
def test_a_fatality_runs_the_whole_consequence_in_one_call(conn, world):
    s = world
    occurred = s["at"] + timedelta(minutes=30)
    iid = record(conn, s)
    assert iid is not None

    case = conn.execute("SELECT * FROM compensation_case WHERE incident_id = %s", (iid,)).fetchone()
    assert case["amount_due"] == 3_000_000 and case["status"] == "OPEN" and case["amount_paid"] == 0
    expected_due = conn.execute("SELECT local_date(%s) + 30 AS d", (occurred,)).fetchone()["d"]
    assert case["due_by"] == expected_due                                           # deadline from rule_parameter

    assert conn.execute("SELECT status FROM contractor WHERE contractor_id = %s", (s["contractor"],)).fetchone()["status"] == "BLACKLISTED"
    permit = conn.execute("SELECT status, end_reason FROM entry_permit WHERE permit_id = %s", (s["permit"],)).fetchone()
    assert permit["status"] == "ABORTED" and f"incident #{iid}" in permit["end_reason"]

    held = {r["invoice_id"] for r in conn.execute("SELECT invoice_id FROM invoice_hold WHERE incident_id = %s AND released_at IS NULL", (iid,))}
    assert held == {s["inv_submitted"], s["inv_approved"]}                          # not the PAID one, not the other job's
    assert n(conn, "SELECT count(*) AS n FROM invoice_hold WHERE invoice_id = %s", s["other_invoice"]) == 0

    for table in ("incident", "compensation_case", "contractor", "entry_permit", "invoice_hold"):
        assert n(conn, "SELECT count(*) AS n FROM audit_log WHERE table_name = %s", table) >= 1, table


def test_disability_suspends_and_opens_a_smaller_case_and_a_near_miss_only_records(conn, world):
    s = world
    iid = record(conn, s, "DISABILITY")
    assert conn.execute("SELECT amount_due FROM compensation_case WHERE incident_id = %s", (iid,)).fetchone()["amount_due"] == 2_000_000
    assert conn.execute("SELECT status FROM contractor WHERE contractor_id = %s", (s["contractor"],)).fetchone()["status"] == "SUSPENDED"

    s2 = world.copy()
    iid2 = record(conn, s2, "NEAR_MISS", worker="e2", permit=False)
    assert iid2 and n(conn, "SELECT count(*) AS n FROM compensation_case WHERE incident_id = %s", iid2) == 0
    assert conn.execute("SELECT status FROM contractor WHERE contractor_id = %s", (s["contractor"],)).fetchone()["status"] == "SUSPENDED"


def test_a_near_miss_alone_changes_nothing_else(conn, world):
    s = world
    record(conn, s, "NEAR_MISS")
    assert conn.execute("SELECT status FROM contractor WHERE contractor_id = %s", (s["contractor"],)).fetchone()["status"] == "ACTIVE"
    assert conn.execute("SELECT status FROM entry_permit WHERE permit_id = %s", (s["permit"],)).fetchone()["status"] == "AUTHORISED"
    assert n(conn, "SELECT count(*) AS n FROM invoice_hold") == 0


def test_forced_failure_inside_the_procedure_leaves_nothing_behind(conn, world):
    """The compensation amount is mis-set to 0: the CHECK on the case fails AFTER the incident row was written."""
    s = world
    conn.execute("UPDATE rule_parameter SET value = 0 WHERE param_key = 'compensation_fatality_inr'")
    with expect("23514"):
        record(conn, s)
    assert n(conn, "SELECT count(*) AS n FROM incident") == 0
    assert n(conn, "SELECT count(*) AS n FROM compensation_case") == 0
    assert n(conn, "SELECT count(*) AS n FROM invoice_hold") == 0
    assert conn.execute("SELECT status FROM contractor WHERE contractor_id = %s", (s["contractor"],)).fetchone()["status"] == "ACTIVE"
    assert conn.execute("SELECT status FROM entry_permit WHERE permit_id = %s", (s["permit"],)).fetchone()["status"] == "AUTHORISED"
    assert n(conn, "SELECT count(*) AS n FROM audit_log WHERE table_name = 'incident'") == 0     # even the audit rows rolled back


def test_commit_and_rollback_are_visible_across_connections(db, conn, world):
    """Session A runs the transaction; session B sees nothing until A commits, and nothing after A rolls back."""
    s = world
    observer = db.connect()
    seen = lambda: n(observer, "SELECT count(*) AS n FROM compensation_case")  # noqa: E731

    with conn.transaction() as tx:
        record(conn, s)
        assert n(conn, "SELECT count(*) AS n FROM compensation_case") == 1       # visible inside the transaction
        assert seen() == 0                                                       # invisible outside
        raise psycopg.Rollback(tx)
    assert seen() == 0 and n(conn, "SELECT count(*) AS n FROM incident") == 0
    assert observer.execute("SELECT status FROM contractor WHERE contractor_id = %s", (s["contractor"],)).fetchone()["status"] == "ACTIVE"

    with conn.transaction():
        record(conn, s)
        assert seen() == 0
    assert seen() == 1                                                           # committed: now everyone sees it all
    assert observer.execute("SELECT status FROM contractor WHERE contractor_id = %s", (s["contractor"],)).fetchone()["status"] == "BLACKLISTED"
    observer.close()


def test_the_same_death_cannot_be_recorded_twice(conn, world):
    s = world
    record(conn, s)
    with expect("23505"):
        record(conn, s)
    assert n(conn, "SELECT count(*) AS n FROM compensation_case") == 1


def test_incident_inputs_are_validated(conn, f, world):
    s = world
    with expect("ZE002", "Unknown incident type"):
        record(conn, s, "ACCIDENT")
    with expect("ZE004", "Worker 999999"):
        record(conn, s, worker_id=999999)
    with expect("ZE004", "Permit"):
        conn.execute("CALL record_incident('FATALITY', now(), %s, %s, 'x', %s, 999999, NULL, NULL::bigint)",
                     (s["e1"], s["manhole"], s["engineer"]))
    with expect("ZE002", "belongs to job"):
        conn.execute("CALL record_incident('FATALITY', now(), %s, %s, 'x', %s, %s, %s, NULL::bigint)",
                     (s["e1"], s["manhole"], s["engineer"], s["permit"], s["other_job"]))
    outsider = f.worker(s["contractor"])                                         # not on this permit's crew
    with expect("23503"):                                                        # composite FK (permit_id, worker_id)
        record(conn, s, worker_id=outsider)
    worker_login = f.user("WORKER", worker_id=f.worker(s["contractor"]))
    with expect("ZE006"):
        record(conn, s, by=worker_login)
    assert n(conn, "SELECT count(*) AS n FROM incident") == 0


def test_a_death_with_no_permit_at_all_still_sanctions_the_employer(conn, world):
    s = world
    iid = record(conn, s, permit=False)                                          # no permit, no job: the typical shadow death
    assert conn.execute("SELECT job_id, permit_id FROM incident WHERE incident_id = %s", (iid,)).fetchone() == {"job_id": None, "permit_id": None}
    assert conn.execute("SELECT status FROM contractor WHERE contractor_id = %s", (s["contractor"],)).fetchone()["status"] == "BLACKLISTED"
    assert n(conn, "SELECT count(*) AS n FROM compensation_case WHERE incident_id = %s", iid) == 1
    assert n(conn, "SELECT count(*) AS n FROM invoice_hold") == 0                # no job known, so no invoice to hold


def test_a_death_on_a_known_job_without_a_permit_holds_that_jobs_invoices(conn, world):
    s = world
    iid = record(conn, s, permit=False, job=s["job"])
    assert n(conn, "SELECT count(*) AS n FROM invoice_hold WHERE incident_id = %s", iid) == 2


# --- invoice holds ----------------------------------------------------------------------------------------
def test_an_invoice_on_hold_can_be_neither_approved_nor_paid_until_released_by_a_person(conn, f, world):
    s = world
    iid = record(conn, s)
    with expect("ZE003", "on hold"):
        conn.execute("UPDATE invoice SET status = 'APPROVED', decided_by = %s WHERE invoice_id = %s", (s["engineer"], s["inv_submitted"]))
    with expect("ZE003", "on hold"):
        conn.execute("UPDATE invoice SET status = 'PAID' WHERE invoice_id = %s", (s["inv_approved"],))
    view = conn.execute("SELECT on_hold, hold_reasons FROM v_invoice_status WHERE invoice_id = %s", (s["inv_submitted"],)).fetchone()
    assert view == {"on_hold": True, "hold_reasons": "INCIDENT"}

    hold = conn.execute("SELECT hold_id FROM invoice_hold WHERE invoice_id = %s", (s["inv_submitted"],)).fetchone()["hold_id"]
    with expect("ZE002", "written note"):
        conn.execute("SELECT release_invoice_hold(%s, %s, 'ok')", (hold, s["engineer"]))
    conn.execute("SELECT release_invoice_hold(%s, %s, 'Reviewed with the contractor; payment may resume.')", (hold, s["engineer"]))
    conn.execute("UPDATE invoice SET status = 'APPROVED', decided_by = %s WHERE invoice_id = %s", (s["engineer"], s["inv_submitted"]))
    with expect("ZE003", "already released"):
        conn.execute("SELECT release_invoice_hold(%s, %s, 'Releasing it twice should fail.')", (hold, s["engineer"]))
    assert iid


def test_holds_have_provenance_two_sources_need_two_releases(conn, f, world):
    s = world
    first = record(conn, s, "DISABILITY", occurred_at=s["at"] + timedelta(minutes=20))
    second = record(conn, s, "FATALITY", worker="e2", occurred_at=s["at"] + timedelta(minutes=40), permit=False, job=s["job"])
    holds = conn.execute("SELECT hold_id, incident_id FROM invoice_hold WHERE invoice_id = %s ORDER BY hold_id", (s["inv_submitted"],)).fetchall()
    assert [h["incident_id"] for h in holds] == [first, second]
    conn.execute("SELECT release_invoice_hold(%s, %s, 'First incident reviewed and closed out.')", (holds[0]["hold_id"], s["engineer"]))
    with expect("ZE003", "on hold"):                                             # the second source still blocks it
        conn.execute("UPDATE invoice SET status = 'APPROVED', decided_by = %s WHERE invoice_id = %s", (s["engineer"], s["inv_submitted"]))


def test_an_invoice_submitted_after_the_fatality_is_held_from_the_start(conn, f, world):
    s = world
    record(conn, s)
    late = f.invoice(s["job"])
    assert conn.execute("SELECT on_hold FROM v_invoice_status WHERE invoice_id = %s", (late,)).fetchone()["on_hold"] is True
    assert f.scalar("SELECT on_hold FROM v_invoice_status WHERE invoice_id = %s", s["other_invoice"]) is False


def test_invoice_state_machine_and_fixed_fields(conn, f, world):
    s = world
    with expect("ZE003", "SUBMITTED to PAID"):
        conn.execute("UPDATE invoice SET status = 'PAID' WHERE invoice_id = %s", (s["other_invoice"],))
    with expect("ZE003", "fixed once submitted"):
        conn.execute("UPDATE invoice SET amount_inr = 1 WHERE invoice_id = %s", (s["other_invoice"],))
    conn.execute("UPDATE invoice SET status = 'APPROVED', decided_by = %s WHERE invoice_id = %s", (s["engineer"], s["other_invoice"]))
    row = conn.execute("SELECT decided_at FROM invoice WHERE invoice_id = %s", (s["other_invoice"],)).fetchone()
    assert row["decided_at"] is not None
    conn.execute("UPDATE invoice SET status = 'PAID' WHERE invoice_id = %s", (s["other_invoice"],))
    with expect("ZE003", "PAID to REJECTED"):
        conn.execute("UPDATE invoice SET status = 'REJECTED' WHERE invoice_id = %s", (s["other_invoice"],))


# --- compensation -----------------------------------------------------------------------------------------
def test_compensation_payments_move_the_case_through_partial_to_paid(conn, world):
    s = world
    iid = record(conn, s)
    case = conn.execute("SELECT case_id FROM compensation_case WHERE incident_id = %s", (iid,)).fetchone()["case_id"]
    pay = lambda amount, at=None: conn.execute("SELECT * FROM record_compensation_payment(%s, %s, COALESCE(%s, now()))",  # noqa: E731
                                              (case, amount, at)).fetchone()
    row = pay(1_000_000)
    assert (row["status"], row["amount_paid"], row["paid_at"]) == ("PARTIAL", 1_000_000, None)
    with expect("ZE002", "exceed"):
        pay(2_000_001)
    with expect("ZE002", "positive"):
        pay(0)
    done = pay(2_000_000, datetime(2026, 10, 1, 12, tzinfo=timezone.utc))
    assert (done["status"], done["amount_paid"]) == ("PAID", 3_000_000) and done["paid_at"] is not None
    with expect("ZE002", "exceed"):
        pay(1)
    with expect("ZE004"):
        conn.execute("SELECT * FROM record_compensation_payment(424242, 1)")
    with expect("ZE003", "append-only|not allowed"):
        conn.execute("DELETE FROM compensation_case WHERE case_id = %s", (case,))


def test_overdue_view_lists_only_unpaid_cases_past_their_deadline(conn, f, world):
    s = world
    old = datetime.now(timezone.utc) - timedelta(days=90)
    overdue = record(conn, s, "FATALITY", occurred_at=old, permit=False, job=s["job"])
    recent = record(conn, s, "FATALITY", worker="e2", occurred_at=yesterday_ist(), permit=False)
    paid_case = conn.execute("SELECT case_id FROM compensation_case WHERE incident_id = %s", (recent,)).fetchone()["case_id"]
    conn.execute("SELECT * FROM record_compensation_payment(%s, 3000000)", (paid_case,))
    rows = conn.execute("SELECT * FROM v_compensation_overdue").fetchall()
    assert [r["incident_id"] for r in rows] == [overdue]
    assert rows[0]["amount_outstanding"] == 3_000_000 and 59 <= rows[0]["days_overdue"] <= 61     # 90 days ago, due after 30


# --- report views -----------------------------------------------------------------------------------------
def test_contractor_risk_score_and_kpi_aggregates(conn, f, world):
    s = world
    record(conn, s, "FATALITY", permit=False, job=s["job"], occurred_at=datetime.now(timezone.utc) - timedelta(days=90))
    record(conn, s, "DISABILITY", worker="e2", permit=False, occurred_at=yesterday_ist())
    f.insert("shadow_entry_alert", "alert_id", complaint_id=s["complaint"], rule_code="SE1_NO_CLEARANCE_EVIDENCE",
             contractor_id=s["contractor"], reason="r", evidence_deadline=s["at"])
    risk = conn.execute("SELECT * FROM v_contractor_risk WHERE contractor_id = %s", (s["contractor"],)).fetchone()
    assert (risk["fatalities"], risk["disabilities"], risk["open_alerts"], risk["overdue_cases"]) == (1, 1, 1, 1)
    assert risk["risk_score"] == 10 + 5 + 1 + 2
    assert conn.execute("SELECT risk_score FROM v_contractor_risk WHERE contractor_id = %s", (s["other_contractor"],)).fetchone()["risk_score"] == 0

    kpi = conn.execute("SELECT SUM(jobs) AS jobs, SUM(mechanised_jobs) AS mech, SUM(manual_exception_jobs) AS manual FROM v_ulb_year_kpi").fetchone()
    assert (kpi["jobs"], kpi["mech"], kpi["manual"]) == (2, 1, 1)                # the waiver job is manual; the other mechanised
    rate = conn.execute("SELECT zero_entry_rate_pct FROM v_ulb_year_kpi WHERE ulb_id = %s", (s["ulb"],)).fetchone()["zero_entry_rate_pct"]
    assert float(rate) == 50.0


def test_mean_days_to_compensation_is_computed_from_payment_dates(conn, f, world):
    s = world
    occurred = datetime(2026, 6, 1, 6, tzinfo=timezone.utc)
    iid = record(conn, s, "FATALITY", occurred_at=occurred, permit=False)
    case = conn.execute("SELECT case_id FROM compensation_case WHERE incident_id = %s", (iid,)).fetchone()["case_id"]
    conn.execute("SELECT * FROM record_compensation_payment(%s, 3000000, %s)", (case, occurred + timedelta(days=12)))
    row = conn.execute("SELECT * FROM v_ulb_year_incidents WHERE year = 2026").fetchone()
    assert (row["incidents"], row["deaths"], float(row["mean_days_to_compensation"])) == (1, 1, 12.0)
    assert row["compensation_paid"] == 3_000_000
