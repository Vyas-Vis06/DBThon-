"""External claims and serial assets retain provenance and server-enforced scope."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from tests.api.conftest import API, ok, refused


def test_completion_claim_is_unmatched_and_exact_retry_is_idempotent(api, world, conn):
    client = api("engineer")
    body = {"source": "WORKS_REGISTER", "external_id": "ext-77", "external_job_ref": "job-A7",
            "claimed_status": "COMPLETED", "claimed_at": datetime.now(timezone.utc).isoformat(),
            "payload": {"external_note": "claimed complete"}}
    headers = {"Idempotency-Key": str(uuid4())}
    first = ok(client.post(f"{API}/completion-claims", json=body, headers=headers), 201)
    assert first["match_status"] == "UNMATCHED" and first["matched_job_id"] is None
    assert ok(client.post(f"{API}/completion-claims", json=body, headers=headers), 201) == first
    changed = {**body, "claimed_status": "CLOSED"}
    refused(client.post(f"{API}/completion-claims", json=changed, headers=headers), 409, "idempotency_mismatch")
    complaint = world["f"].resolved_complaint(
        world["manhole"], datetime.now(timezone.utc) - timedelta(days=2)
    )
    job_id = world["f"].job(complaint, world["ca"])
    view = ok(client.get(f"{API}/completion-reconciliation", params={"ulb_id": world["ulb"]}))
    assert view["total"] == 1
    assert view["items"][0]["gap_code"] == "UNMATCHED_CLAIM"
    assert view["job_candidates"]

    matched = ok(client.post(f"{API}/completion-claims/{first['claim_id']}/match",
                             json={"decision": "MATCHED", "job_id": job_id,
                                   "reason": "External register row was checked against this scoped work order."},
                             headers={"Idempotency-Key": str(uuid4())}))
    assert matched["match_status"] == "MATCHED" and matched["matched_job_id"] == job_id
    reviewed = ok(client.get(f"{API}/completion-reconciliation", params={"ulb_id": world["ulb"]}))
    assert reviewed["items"][0]["gap_code"] == "COMPLETION_EVIDENCE_MISSING"
    assert conn.execute("SELECT count(*) AS n FROM audit_log WHERE table_name='completion_claim_review'").fetchone()["n"] == 1


def test_completion_claim_cannot_be_manually_matched_across_ulbs(api, world):
    client = api("engineer")
    other = world["f"].ulb(name="Other Claim Zone")
    other_manhole = world["f"].manhole(other)
    complaint = world["f"].complaint(other_manhole)
    other_job = world["f"].job(complaint, world["cb"])
    body = {"source": "WORKS_REGISTER", "external_id": "ext-cross", "external_job_ref": "foreign-ref",
            "claimed_status": "COMPLETED", "claimed_at": datetime.now(timezone.utc).isoformat()}
    claim = ok(client.post(f"{API}/completion-claims", json=body, headers={"Idempotency-Key": str(uuid4())}), 201)
    refused(client.post(f"{API}/completion-claims/{claim['claim_id']}/match",
                        json={"decision": "MATCHED", "job_id": other_job,
                              "reason": "Checking that a foreign municipality job cannot be linked."},
                        headers={"Idempotency-Key": str(uuid4())}), 409, "invalid_state")
    assert claim["match_status"] == "UNMATCHED"


def test_gear_asset_register_and_scoped_inventory_do_not_invent_inspection(api, world):
    client = api("engineer")
    gear_code = client.get(f"{API}/gear-items").json()["items"][0]["gear_code"]
    key = str(uuid4())
    body = {"ulb_id": world["ulb"], "gear_code": gear_code, "serial_no": "SERIAL-UNINSPECTED"}
    asset = ok(client.post(f"{API}/reference/gear-assets", json=body,
                           headers={"Idempotency-Key": key}), 201)
    assert asset["inspection_valid_until"] is None
    items = ok(client.get(f"{API}/reference/gear-assets", params={"ulb_id": world["ulb"]}))
    row = next(item for item in items["items"] if item["gear_asset_id"] == asset["gear_asset_id"])
    assert row["available"] is False


def test_engineer_cannot_read_another_ulb_and_auditor_must_choose_scope(api, world, conn):
    other = world["f"].ulb(name="Other Accountability Zone")
    other_manhole = world["f"].manhole(other)
    assert ok(api("engineer").get(f"{API}/manholes", params={"ulb_id": other}))["items"] == []
    refused(api("engineer").get(f"{API}/events", params={"ulb_id": other}), 404)
    refused(api("auditor").get(f"{API}/incident-reports"), 404, "not_found")
    auditor_reports = ok(api("auditor").get(f"{API}/incident-reports", params={"ulb_id": other}))
    assert auditor_reports["items"] == []
    assert other_manhole is not None


def test_onboarding_uses_explicit_contractor_and_detector_scope_assignments(api, world, db):
    engineer, supervisor, admin = api("engineer"), api("supervisor"), api("admin")
    other_ulb = world["f"].ulb(name="Unassigned Onboarding Zone")
    contractor = world["f"].contractor()
    worker = world["f"].worker(contractor)

    before = ok(engineer.get(f"{API}/contractors"))
    assert contractor not in {row["contractor_id"] for row in before["items"]}
    assert ok(engineer.get(f"{API}/workers", params={"contractor_id": contractor}))["items"] == []
    reason = "Verified onboarding request for the municipal service agreement."
    refused(engineer.post(f"{API}/ulbs/{other_ulb}/contractors/{contractor}/scope", json={"reason": reason},
                          headers={"Idempotency-Key": str(uuid4())}), 404, "not_found")
    refused(supervisor.post(f"{API}/ulbs/{world['ulb']}/contractors/{contractor}/scope", json={"reason": reason},
                            headers={"Idempotency-Key": str(uuid4())}), 403, "forbidden")

    key = str(uuid4())
    assigned = ok(engineer.post(f"{API}/ulbs/{world['ulb']}/contractors/{contractor}/scope", json={"reason": reason},
                                headers={"Idempotency-Key": key}), 201)
    assert assigned["ulb_id"] == world["ulb"] and assigned["contractor_id"] == contractor
    assert assigned["assigned_by"] == world["users"]["engineer"]["id"] and assigned["assignment_reason"] == reason
    assert ok(engineer.post(f"{API}/ulbs/{world['ulb']}/contractors/{contractor}/scope", json={"reason": reason},
                            headers={"Idempotency-Key": key}), 201) == assigned
    assert contractor in {row["contractor_id"] for row in ok(engineer.get(f"{API}/contractors"))["items"]}
    assert any(row["worker_id"] == worker
               for row in ok(engineer.get(f"{API}/workers", params={"contractor_id": contractor}))["items"])
    refused(engineer.get(f"{API}/ulbs/{other_ulb}/contractor-scopes"), 404, "not_found")
    assert ok(api("auditor").get(f"{API}/ulbs/{other_ulb}/contractor-scopes"))["items"] == []

    # Detectors remain an ADMIN-created global instrument catalog, then an ADMIN explicitly allocates them.
    detector = ok(admin.post(f"{API}/detectors", json={"serial_no": "GD-ONBOARD-TEST", "model": "Verified 4-gas",
        "calibration_valid_until": "2099-12-31"}), 201)
    assert detector["detector_id"] not in {row["detector_id"] for row in ok(engineer.get(f"{API}/detectors"))["items"]}
    refused(engineer.post(f"{API}/ulbs/{world['ulb']}/detectors/{detector['detector_id']}/scope", json={"reason": reason},
                          headers={"Idempotency-Key": str(uuid4())}), 403, "forbidden")
    detector_scope = ok(admin.post(f"{API}/ulbs/{world['ulb']}/detectors/{detector['detector_id']}/scope",
                                   json={"reason": reason}, headers={"Idempotency-Key": str(uuid4())}), 201)
    assert detector_scope["assigned_by"] == world["users"]["admin"]["id"]
    assert detector["detector_id"] in {row["detector_id"] for row in ok(engineer.get(f"{API}/detectors"))["items"]}

    # RLS, not only the HTTP role guard, prevents a contractor/worker from enumerating allocation metadata.
    with db.connect(user="ze_app") as runtime:
        runtime.execute("SELECT set_config('app.role','WORKER',false),set_config('app.ulb_id','',false)")
        assert runtime.execute("SELECT count(*) AS n FROM ulb_contractor_scope").fetchone()["n"] == 0
        assert runtime.execute("SELECT count(*) AS n FROM ulb_detector_scope").fetchone()["n"] == 0


def test_judge_evidence_never_claims_unmeasured_labs_are_current(api):
    response = ok(api("auditor").get(f"{API}/judge/evidence"))
    if response["measurements"]["status"] == "NOT_YET_MEASURED":
        assert response["labs"] == []
        assert "No source-matching" in response["measurements"]["limitations"][0]
    else:
        assert response["measurements"]["status"] == "TESTED"
        assert response["measurements"]["runs"]
        assert all(lab["status"] == "TESTED" for lab in response["labs"])
