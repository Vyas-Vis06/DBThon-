"""Shadow-entry detection over HTTP: resolve with no evidence -> scan -> alert + invoice hold -> human review."""

from datetime import timedelta

from tests.api.conftest import API, ok, refused
from tests.api.test_workflow import NOW, iso, new_job


def resolved_without_evidence(api, world, conn, *, hours_ago=30):
    """A complaint an engineer resolved as CLEARED with no machine log and no permit, resolved `hours_ago` hours ago."""
    eng = api("engineer")
    complaint, job = new_job(api, world, waiver=False)
    resolved = ok(eng.post(f"{API}/complaints/{complaint['complaint_id']}/resolve", json={"resolution_code": "CLEARED"}))
    assert resolved["evidence_on_file"] is False and "absence scan" in resolved["warning"]
    conn.execute("UPDATE complaint SET raised_at = now() - %s, resolved_at = now() - %s WHERE complaint_id = %s",
                 (timedelta(hours=hours_ago + 24), timedelta(hours=hours_ago), complaint["complaint_id"]))   # time passes
    return complaint, job


def test_the_scan_raises_an_alert_holds_the_invoice_and_a_person_dismisses_it(api, world, conn):
    eng, auditor, contractor = api("engineer"), api("auditor"), api("contractor_a")
    complaint, job = resolved_without_evidence(api, world, conn, hours_ago=2)             # still inside the 24 h grace window
    invoice = ok(contractor.post(f"{API}/invoices", json={"job_id": job["job_id"], "invoice_no": "INV-7", "amount_inr": 90000}), 201)

    pending = ok(eng.get(f"{API}/detections/candidates"))
    assert pending["total"] == 1 and pending["items"][0]["past_grace"] is False and pending["items"][0]["alert_id"] is None
    assert ok(eng.post(f"{API}/detections/scan")) == {"opened": 0, "moved_to_review": 0, "pending_in_grace": 1}

    conn.execute("UPDATE complaint SET raised_at = now() - interval '60 hours', resolved_at = now() - interval '30 hours' WHERE complaint_id = %s",
                 (complaint["complaint_id"],))
    assert ok(eng.post(f"{API}/detections/scan"))["opened"] == 1
    assert ok(eng.post(f"{API}/detections/scan"))["opened"] == 0                           # idempotent

    alerts = ok(auditor.get(f"{API}/detections/alerts?status=OPEN"))
    assert alerts["total"] == 1
    alert = alerts["items"][0]
    assert alert["rule_code"] == "SE1_NO_CLEARANCE_EVIDENCE" and alert["contractor_name"] and alert["manhole_code"] and alert["rule_title"]
    assert ok(contractor.get(f"{API}/invoices?on_hold=true"))["items"][0]["hold_reasons"] == "SHADOW_ENTRY"
    refused(eng.post(f"{API}/invoices/{invoice['invoice_id']}/approve"), 409, "invalid_state", "on hold")

    # an auditor may look but not decide; the contractor cannot even see the alert
    refused(auditor.post(f"{API}/detections/alerts/{alert['alert_id']}/review", json={"decision": "DISMISSED", "note": "An auditor must not decide."}), 403)
    refused(contractor.get(f"{API}/detections/alerts"), 403)
    refused(eng.post(f"{API}/detections/alerts/{alert['alert_id']}/review", json={"decision": "DISMISSED", "note": "short"}), 422)

    reviewed = ok(eng.post(f"{API}/detections/alerts/{alert['alert_id']}/review",
                           json={"decision": "DISMISSED", "note": "Repair was done by the ULB's own crew; log attached."}))
    assert reviewed["status"] == "DISMISSED" and reviewed["reviewed_by"] == world["users"]["engineer"]["id"]
    detail = ok(auditor.get(f"{API}/detections/alerts/{alert['alert_id']}"))
    assert [e["to_status"] for e in detail["events"]] == ["OPEN", "DISMISSED"]
    assert detail["holds"][0]["released_at"] is not None and "dismissed" in detail["holds"][0]["release_note"]
    ok(eng.post(f"{API}/invoices/{invoice['invoice_id']}/approve"))                         # the hold is gone
    refused(eng.post(f"{API}/detections/alerts/{alert['alert_id']}/review", json={"decision": "CONFIRMED", "note": "Trying to change my mind"}),
            409, "invalid_state", "final")
    assert ok(eng.post(f"{API}/detections/scan"))["opened"] == 0                            # a dismissed alert is never reopened


def test_confirming_an_alert_keeps_the_hold_and_hits_the_risk_score(api, world, conn):
    eng = api("engineer")
    complaint, job = resolved_without_evidence(api, world, conn)
    ok(api("contractor_a").post(f"{API}/invoices", json={"job_id": job["job_id"], "invoice_no": "INV-8", "amount_inr": 1000}), 201)
    ok(eng.post(f"{API}/detections/scan"))
    alert = ok(eng.get(f"{API}/detections/alerts"))["items"][0]
    ok(eng.post(f"{API}/detections/alerts/{alert['alert_id']}/review", json={"decision": "CONFIRMED", "note": "Crew admitted entering without a permit."}))
    assert ok(eng.get(f"{API}/invoice-holds"))["total"] == 1
    risk = {r["contractor_id"]: r for r in ok(api("auditor").get(f"{API}/reports/contractor-risk"))["items"]}[world["ca"]]
    assert risk["confirmed_alerts"] == 1 and risk["risk_score"] == 3
    summary = ok(api("auditor").get(f"{API}/reports/shadow-summary"))["items"]
    assert summary[0]["rule_code"] == "SE1_NO_CLEARANCE_EVIDENCE" and summary[0]["status"] == "CONFIRMED" and summary[0]["alerts"] == 1


def test_late_evidence_moves_an_open_alert_to_review_it_never_closes_it(api, world, conn):
    eng = api("engineer")
    complaint, job = resolved_without_evidence(api, world, conn)
    ok(eng.post(f"{API}/detections/scan"))
    deployment = ok(eng.post(f"{API}/jobs/{job['job_id']}/deployments", json={"machine_id": world["machine"], "started_at": iso(NOW() - timedelta(hours=3))}), 201)
    ok(eng.post(f"{API}/deployments/{deployment['deploy_id']}/finish", json={"ended_at": iso(NOW() - timedelta(hours=2)), "outcome": "CLEARED"}))
    assert ok(eng.post(f"{API}/detections/scan"))["moved_to_review"] == 1
    (alert,) = ok(eng.get(f"{API}/detections/alerts"))["items"]
    assert alert["status"] == "EVIDENCE_RECEIVED" and alert["reviewed_by"] is None


def test_exempt_resolutions_and_unresolved_complaints_are_never_flagged(api, world, conn):
    eng = api("engineer")
    for code in ("NO_BLOCKAGE_FOUND", "DUPLICATE_COMPLAINT", "REFERRED_OUT", "WITHDRAWN"):
        c = ok(eng.post(f"{API}/complaints", json={"manhole_id": world["manhole"], "description": f"Complaint to be closed as {code}"}), 201)
        resolved = ok(eng.post(f"{API}/complaints/{c['complaint_id']}/resolve", json={"resolution_code": code}))
        assert resolved["warning"] is None
    ok(eng.post(f"{API}/complaints", json={"manhole_id": world["manhole"], "description": "Still open"}), 201)
    conn.execute("UPDATE complaint SET raised_at = now() - interval '90 days', resolved_at = now() - interval '60 days' WHERE status = 'RESOLVED'")
    assert ok(eng.post(f"{API}/detections/scan")) == {"opened": 0, "moved_to_review": 0, "pending_in_grace": 0}
    refused(eng.post(f"{API}/complaints/{c['complaint_id']}/resolve", json={"resolution_code": "CLEARED"}), 409, "conflict", "already resolved")


def test_an_admin_can_switch_a_detection_rule_off(api, world, conn):
    eng, admin = api("engineer"), api("admin")
    resolved_without_evidence(api, world, conn)
    refused(eng.patch(f"{API}/detections/rules/SE1_NO_CLEARANCE_EVIDENCE", json={"enabled": False}), 403)
    assert ok(admin.patch(f"{API}/detections/rules/SE1_NO_CLEARANCE_EVIDENCE", json={"enabled": False}))["enabled"] is False
    assert ok(eng.post(f"{API}/detections/scan"))["opened"] == 0
    ok(admin.patch(f"{API}/detections/rules/SE1_NO_CLEARANCE_EVIDENCE", json={"enabled": True}))
    assert ok(eng.post(f"{API}/detections/scan"))["opened"] == 1
    refused(admin.patch(f"{API}/detections/rules/NO_SUCH_RULE", json={"enabled": True}), 404)
