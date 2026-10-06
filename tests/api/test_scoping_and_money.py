"""Who sees what (contractors and workers see only their own rows) and the money endpoints: invoices, holds, compensation."""

from datetime import datetime, timedelta, timezone

from tests.api.conftest import API, ok, refused
from tests.api.test_workflow import build_permit, new_job


# --- scoping -----------------------------------------------------------------------------------------------------
def test_a_contractor_sees_only_its_own_jobs_workers_permits_and_invoices(api, world):
    a, b, eng = api("contractor_a"), api("contractor_b"), api("engineer")
    c1, job_a = new_job(api, world, contractor=world["ca"])
    c2, job_b = new_job(api, world, contractor=world["cb"])
    ok(a.post(f"{API}/invoices", json={"job_id": job_a["job_id"], "invoice_no": "A-1", "amount_inr": 1000}), 201)
    ok(b.post(f"{API}/invoices", json={"job_id": job_b["job_id"], "invoice_no": "B-1", "amount_inr": 2000}), 201)

    assert [j["job_id"] for j in ok(a.get(f"{API}/jobs"))["items"]] == [job_a["job_id"]]
    assert [j["job_id"] for j in ok(b.get(f"{API}/jobs"))["items"]] == [job_b["job_id"]]
    assert ok(eng.get(f"{API}/jobs"))["total"] == 2
    assert ok(a.get(f"{API}/workers"))["total"] == 5 and ok(b.get(f"{API}/workers"))["total"] == 5
    assert {w["contractor_id"] for w in ok(a.get(f"{API}/workers"))["items"]} == {world["ca"]}
    assert [c["contractor_id"] for c in ok(a.get(f"{API}/contractors"))["items"]] == [world["ca"]]
    assert [i["invoice_no"] for i in ok(a.get(f"{API}/invoices"))["items"]] == ["A-1"]
    refused(a.get(f"{API}/jobs/{job_b['job_id']}"), 404)                                      # not 403: it does not exist for A
    refused(a.get(f"{API}/contractors/{world['cb']}"), 404)
    refused(a.post(f"{API}/invoices", json={"job_id": job_b["job_id"], "invoice_no": "STEAL", "amount_inr": 1}), 404)   # B's job does not exist for A
    refused(a.get(f"{API}/workers/{world['workers_b'][0]}"), 404)


def test_permits_are_visible_to_their_contractor_and_crew_only(api, world):
    sup, a, b, worker, other_worker = api("supervisor"), api("contractor_a"), api("contractor_b"), api("worker_a"), api("auditor")
    _, _, permit = build_permit(api, world)
    pid = permit["permit_id"]
    assert ok(sup.get(f"{API}/permits"))["total"] == 1
    assert ok(a.get(f"{API}/permits"))["total"] == 1 and ok(worker.get(f"{API}/permits"))["total"] == 1
    assert ok(b.get(f"{API}/permits"))["total"] == 0
    refused(b.get(f"{API}/permits/{pid}"), 404)
    dossier = ok(worker.get(f"{API}/permits/{pid}"))
    assert dossier["permit"]["permit_id"] == pid and len(dossier["crew"]) == 4
    assert ok(worker.get(f"{API}/workers"))["total"] == 1       # the list is stricter than RLS: themself; crew-mates appear only in the dossier
    assert ok(other_worker.get(f"{API}/permits"))["total"] == 1                              # an auditor sees all


def test_a_worker_who_is_not_on_the_crew_sees_no_permit(app, api, world, conn):
    """A second worker login (same contractor, different person) is not crewed on the permit: it does not exist for them."""
    from tests.api.conftest import PASSWORD, login
    from zeroentry.security import hash_password
    world["f"].user("WORKER", email="spare@zeroentry.example", password_hash=hash_password(PASSWORD, rounds=4), worker_id=world["workers_a"][4])
    _, _, permit = build_permit(api, world)                          # crew is workers_a[0..3]
    spare = login(app, "spare@zeroentry.example")
    assert ok(spare.get(f"{API}/permits"))["total"] == 0
    refused(spare.get(f"{API}/permits/{permit['permit_id']}"), 404)
    refused(spare.post(f"{API}/permits/{permit['permit_id']}/stop-work", json={"reason": "I am not on this crew"}), 404)

def test_dashboards_are_shaped_by_role(api, world):
    build_permit(api, world)
    assert set(ok(api("engineer").get(f"{API}/reports/dashboard"))) >= {"complaints", "permits", "alerts", "invoices_on_hold", "compensation_overdue", "zero_entry_rate_pct"}
    assert "draft_permits_not_ready" in ok(api("supervisor").get(f"{API}/reports/dashboard"))
    assert set(ok(api("contractor_a").get(f"{API}/reports/dashboard"))) == {"jobs", "permits", "invoices_on_hold", "incidents"}
    assert ok(api("worker_a").get(f"{API}/reports/dashboard")) == {"my_permits": {"DRAFT": 1}}


# --- invoices and holds -----------------------------------------------------------------------------------------
def test_invoice_lifecycle_and_validation(api, world):
    contractor, eng = api("contractor_a"), api("engineer")
    _, job = new_job(api, world)
    refused(contractor.post(f"{API}/invoices", json={"job_id": job["job_id"], "invoice_no": "X", "amount_inr": 0}), 422)
    refused(contractor.post(f"{API}/invoices", json={"job_id": job["job_id"], "invoice_no": "X", "amount_inr": 10, "status": "PAID"}), 422)
    refused(contractor.post(f"{API}/invoices", json={"job_id": 999999, "invoice_no": "X", "amount_inr": 10}), 404)
    inv = ok(contractor.post(f"{API}/invoices", json={"job_id": job["job_id"], "invoice_no": "INV-1", "amount_inr": 12500.50}), 201)
    refused(contractor.post(f"{API}/invoices", json={"job_id": job["job_id"], "invoice_no": "INV-1", "amount_inr": 5}), 409, "duplicate")
    refused(contractor.post(f"{API}/invoices/{inv['invoice_id']}/approve"), 403)                          # cannot approve its own
    refused(eng.post(f"{API}/invoices/{inv['invoice_id']}/pay"), 409, "invalid_state", "SUBMITTED to PAID")
    assert ok(eng.post(f"{API}/invoices/{inv['invoice_id']}/approve"))["status"] == "APPROVED"
    assert ok(eng.post(f"{API}/invoices/{inv['invoice_id']}/pay"))["status"] == "PAID"
    assert ok(contractor.get(f"{API}/invoices?status=PAID"))["total"] == 1


def test_incident_holds_need_a_written_release(api, world):
    sup, eng, contractor = api("supervisor"), api("engineer"), api("contractor_a")
    _, job = new_job(api, world)
    inv = ok(contractor.post(f"{API}/invoices", json={"job_id": job["job_id"], "invoice_no": "INV-2", "amount_inr": 100}), 201)
    ok(sup.post(f"{API}/incidents", json={"incident_type": "DISABILITY", "occurred_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                                          "worker_id": world["workers_a"][0], "manhole_id": world["manhole"], "job_id": job["job_id"],
                                          "description": "Permanent injury to a hand"}), 201)
    (hold,) = ok(eng.get(f"{API}/invoice-holds"))["items"]
    assert hold["reason"] == "INCIDENT" and hold["invoice_no"] == "INV-2"
    refused(eng.post(f"{API}/invoice-holds/{hold['hold_id']}/release", json={"note": "ok"}), 422)
    ok(eng.post(f"{API}/invoice-holds/{hold['hold_id']}/release", json={"note": "Reviewed with the contractor; payment may resume."}))
    ok(eng.post(f"{API}/invoices/{inv['invoice_id']}/approve"))
    assert ok(eng.get(f"{API}/invoice-holds"))["total"] == 0 and ok(eng.get(f"{API}/invoice-holds?active=false"))["total"] == 1
    assert ok(api("contractor_a").get(f"{API}/contractors/{world['ca']}"))["status"] == "SUSPENDED"          # disability: suspended, not blacklisted


# --- compensation -------------------------------------------------------------------------------------------------
def test_compensation_payments_and_the_overdue_report(api, world, conn):
    eng, sup, auditor = api("engineer"), api("supervisor"), api("auditor")
    occurred = datetime.now(timezone.utc) - timedelta(days=45)
    result = ok(sup.post(f"{API}/incidents", json={"incident_type": "FATALITY", "occurred_at": occurred.isoformat(), "worker_id": world["workers_a"][0],
                                                   "manhole_id": world["manhole"], "description": "Collapsed in the chamber, no permit on file"}), 201)
    case = result["compensation_case"]
    assert case["amount_due"] == 3000000 and result["permit_id"] is None
    overdue = ok(auditor.get(f"{API}/reports/compensation-overdue"))["items"]
    assert len(overdue) == 1 and overdue[0]["amount_outstanding"] == 3000000 and 14 <= overdue[0]["days_overdue"] <= 16
    assert ok(eng.get(f"{API}/compensation-cases?overdue=true"))["total"] == 1

    refused(eng.post(f"{API}/compensation-cases/{case['case_id']}/payments", json={"amount": 0}), 422)
    refused(eng.post(f"{API}/compensation-cases/{case['case_id']}/payments", json={"amount": 4000000}), 422, "rule_violation", "exceed")
    assert ok(eng.post(f"{API}/compensation-cases/{case['case_id']}/payments", json={"amount": 1000000}))["status"] == "PARTIAL"
    paid = ok(eng.post(f"{API}/compensation-cases/{case['case_id']}/payments", json={"amount": 2000000}))
    assert paid["status"] == "PAID" and paid["paid_at"]
    assert ok(auditor.get(f"{API}/reports/compensation-overdue"))["items"] == []
    refused(auditor.post(f"{API}/compensation-cases/{case['case_id']}/payments", json={"amount": 1}), 403)
    kpi = ok(auditor.get(f"{API}/reports/ulb-kpis"))["incidents"][0]
    assert kpi["deaths"] == 1 and kpi["compensation_paid"] == 3000000 and float(kpi["mean_days_to_compensation"]) >= 45
    summary = ok(auditor.get(f"{API}/reports/summary"))["compensation"]
    assert summary["cases"] == 1 and summary["total_due"] == 3000000 and summary["total_paid"] == 3000000


def test_incident_filters_and_validation(api, world):
    sup, eng = api("supervisor"), api("engineer")
    now = datetime.now(timezone.utc)
    refused(sup.post(f"{API}/incidents", json={"incident_type": "FATALITY", "occurred_at": (now + timedelta(days=1)).isoformat(),
                                               "worker_id": 1, "manhole_id": 1, "description": "from the future"}), 422, message="future")
    refused(sup.post(f"{API}/incidents", json={"incident_type": "FATALITY", "occurred_at": now.replace(tzinfo=None).isoformat(),
                                               "worker_id": 1, "manhole_id": 1, "description": "no offset"}), 422, message="offset")
    ok(sup.post(f"{API}/incidents", json={"incident_type": "NEAR_MISS", "occurred_at": (now - timedelta(hours=2)).isoformat(),
                                          "worker_id": world["workers_a"][0], "manhole_id": world["manhole"], "description": "Slipped on the ladder"}), 201)
    assert ok(eng.get(f"{API}/incidents?incident_type=NEAR_MISS"))["total"] == 1
    assert ok(eng.get(f"{API}/incidents?incident_type=FATALITY"))["total"] == 0
    assert ok(eng.get(f"{API}/incidents?contractor_id={world['ca']}"))["items"][0]["worker_name"]
    assert ok(api("contractor_b").get(f"{API}/incidents"))["total"] == 0
