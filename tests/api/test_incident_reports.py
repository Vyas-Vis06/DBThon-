"""Standalone no-permit incidents use one transaction and one exact idempotency key."""

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from tests.api.conftest import API, login, ok, refused


def _report(ulb_id: int, *, description="Synthetic incident report"):
    return {
        "ulb_id": ulb_id,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "site_label": "Unregistered private access shaft",
        "hazard_type": "STRUCTURAL_COLLAPSE",
        "description": description,
        "victims": [
            {"victim_key": "victim-a", "display_alias": "Person A", "outcome": "FATAL"},
            {"victim_key": "victim-b", "display_alias": "Person B", "outcome": "INJURY"},
        ],
    }


def test_no_permit_multi_victim_report_is_pending_and_exact_retry_is_idempotent(api, world, conn):
    client = api("engineer")
    key = str(uuid4())
    body = _report(world["ulb"])
    headers = {"Idempotency-Key": key}

    first = client.post(f"{API}/incident-reports", json=body, headers=headers)
    result = ok(first, 201)
    retry = client.post(f"{API}/incident-reports", json=body, headers=headers)
    assert ok(retry, 201) == result
    assert result["outcome"] == "RECORDED" and result["payment_status"] == "NOT_PAID"
    assert len(result["case_ids"]) == 2
    assert conn.execute("SELECT count(*) AS n FROM incident_report").fetchone()["n"] == 1
    assert conn.execute("SELECT count(*) AS n FROM incident_report_victim").fetchone()["n"] == 2
    cases = conn.execute("SELECT status, paid_amount FROM incident_assessment_case ORDER BY assessment_case_id").fetchall()
    assert [row["status"] for row in cases] == ["PENDING_REVIEW", "PENDING_REVIEW"]
    assert all(row["paid_amount"] == 0 for row in cases)
    assert conn.execute("SELECT count(*) AS n FROM command_dedup").fetchone()["n"] == 1

    events = ok(client.get(f"{API}/events", params={"ulb_id": world["ulb"], "after": 0}))
    report_events = [event for event in events["items"] if event["event_type"] == "INCIDENT_RECORDED"]
    assert len(report_events) == 1 and report_events[0]["entity_id"] == result["report_id"]


def test_reused_report_key_with_changed_body_conflicts_without_second_report(api, world, conn):
    client = api("engineer")
    key = str(uuid4())
    ok(client.post(f"{API}/incident-reports", json=_report(world["ulb"]), headers={"Idempotency-Key": key}), 201)
    changed = client.post(f"{API}/incident-reports", json=_report(world["ulb"], description="Changed body"),
                          headers={"Idempotency-Key": key})
    refused(changed, 409, "idempotency_mismatch")
    assert conn.execute("SELECT count(*) AS n FROM incident_report").fetchone()["n"] == 1


def test_structural_link_conflict_rolls_back_without_generic_500(api, world, conn):
    client = api("engineer")
    body = _report(world["ulb"])
    complaint = world["f"].complaint(world["manhole"])
    first_job = world["f"].job(complaint, world["ca"])
    world["f"].waiver(first_job, world["users"]["engineer"]["id"])
    body["permit_id"] = world["f"].permit(first_job, world["users"]["supervisor"]["id"])
    other_job = world["f"].job(complaint, world["cb"])
    body["job_id"] = other_job
    response = client.post(f"{API}/incident-reports", json=body, headers={"Idempotency-Key": str(uuid4())})
    refused(response, 409, "invalid_state")
    assert conn.execute("SELECT count(*) AS n FROM incident_report").fetchone()["n"] == 0
    assert conn.execute("SELECT count(*) AS n FROM incident_report_victim").fetchone()["n"] == 0
    assert conn.execute("SELECT count(*) AS n FROM incident_assessment_case").fetchone()["n"] == 0


def test_report_holds_future_invoice_but_does_not_retroactively_hold_paid_invoice(api, world, conn):
    client = api("engineer")
    complaint = world["f"].complaint(world["manhole"])
    job = world["f"].job(complaint, world["ca"])
    body = _report(world["ulb"])
    body.update(job_id=job, contractor_id=world["ca"])
    ok(client.post(f"{API}/incident-reports", json=body, headers={"Idempotency-Key": str(uuid4())}), 201)
    invoice = ok(client.post(f"{API}/invoices", json={"job_id": job, "invoice_no": "AFTER-REPORT", "amount_inr": "125.00"}), 201)
    assert invoice["on_hold"] is True
    refused(client.post(f"{API}/invoices/{invoice['invoice_id']}/pay"), 409, "invalid_state")

    complaint2 = world["f"].complaint(world["manhole"])
    job2 = world["f"].job(complaint2, world["cb"])
    paid = ok(client.post(f"{API}/invoices", json={"job_id": job2, "invoice_no": "PAID-FIRST", "amount_inr": "75.00"}), 201)
    ok(client.post(f"{API}/invoices/{paid['invoice_id']}/approve"))
    ok(client.post(f"{API}/invoices/{paid['invoice_id']}/pay"))
    paid_report = _report(world["ulb"], description="report after payment")
    paid_report.update(job_id=job2, contractor_id=world["cb"])
    result = ok(client.post(f"{API}/incident-reports", json=paid_report, headers={"Idempotency-Key": str(uuid4())}), 201)
    assert result["invoice_effects"] == 0
    assert conn.execute("SELECT count(*) AS n FROM invoice_hold WHERE invoice_id=%s AND report_id IS NOT NULL",
                        (paid["invoice_id"],)).fetchone()["n"] == 0


def test_report_and_payment_serialize_without_deadlock_or_paid_hold_race(app, world, conn):
    engineer = login(app, world["users"]["engineer"]["email"])
    payer = login(app, world["users"]["engineer"]["email"])
    complaint = world["f"].complaint(world["manhole"])
    job = world["f"].job(complaint, world["ca"])
    invoice = ok(engineer.post(f"{API}/invoices", json={"job_id": job, "invoice_no": "RACE-REPORT-PAY",
                                                        "amount_inr": "125.00"}), 201)
    ok(engineer.post(f"{API}/invoices/{invoice['invoice_id']}/approve"))
    body = _report(world["ulb"], description="Concurrent report and payment serialization regression")
    body.update(job_id=job, contractor_id=world["ca"])
    barrier = Barrier(2)

    def report():
        barrier.wait(timeout=10)
        return engineer.post(f"{API}/incident-reports", json=body, headers={"Idempotency-Key": str(uuid4())})

    def pay():
        barrier.wait(timeout=10)
        return payer.post(f"{API}/invoices/{invoice['invoice_id']}/pay")

    with ThreadPoolExecutor(max_workers=2) as pool:
        report_future, pay_future = pool.submit(report), pool.submit(pay)
        report_response, pay_response = report_future.result(timeout=20), pay_future.result(timeout=20)
    report_result = ok(report_response, 201)
    assert pay_response.status_code in {200, 409}, pay_response.text
    if pay_response.status_code == 409:
        refused(pay_response, 409, "invalid_state")

    final = conn.execute("SELECT status FROM invoice WHERE invoice_id=%s", (invoice["invoice_id"],)).fetchone()["status"]
    holds = conn.execute("SELECT count(*) AS n FROM invoice_hold WHERE invoice_id=%s AND report_id=%s AND released_at IS NULL",
                         (invoice["invoice_id"], report_result["report_id"])).fetchone()["n"]
    if final == "PAID":
        assert holds == 0, "a report committed after payment must not retroactively hold paid funds"
    else:
        assert final == "APPROVED" and holds == 1, "a committed report must hold a not-yet-paid invoice"
