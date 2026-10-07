"""Administration (users, law-as-data rules, audit trail), input validation, error shapes, injection, request plumbing."""

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.api.conftest import API, PASSWORD, login, ok, refused
from tests.api.test_workflow import build_permit
from zeroentry.deps import DB, get_db


# --- users --------------------------------------------------------------------------------------------------------
def test_an_admin_creates_users_with_validation_and_the_new_user_can_sign_in(app, api, world):
    admin = api("admin")
    body = {"email": "NewOfficer@ZeroEntry.example", "full_name": "New Officer", "role": "ENGINEER", "password": "Strong-Pass-123"}
    created = ok(admin.post(f"{API}/admin/users", json=body), 201)
    assert created["email"] == "newofficer@zeroentry.example" and created["role"] == "ENGINEER" and "password_hash" not in created
    login(app, "newofficer@zeroentry.example", "Strong-Pass-123")
    refused(admin.post(f"{API}/admin/users", json=body), 409, "duplicate")
    refused(admin.post(f"{API}/admin/users", json={**body, "email": "weak@zeroentry.example", "password": "weak"}), 422, message="12 characters")
    refused(admin.post(f"{API}/admin/users", json={**body, "email": "not-an-email"}), 422, "validation_error")
    refused(admin.post(f"{API}/admin/users", json={**body, "email": "c@zeroentry.example", "role": "CONTRACTOR"}), 422, "rule_violation", "CONTRACTOR")
    ok(admin.post(f"{API}/admin/users", json={**body, "email": "c@zeroentry.example", "role": "CONTRACTOR", "contractor_id": world["ca"]}), 201)
    refused(admin.post(f"{API}/admin/users", json={**body, "email": "d@zeroentry.example", "role": "ROOT"}), 422, "validation_error")
    users = ok(admin.get(f"{API}/admin/users?role=CONTRACTOR"))
    assert users["total"] == 3 and "password_hash" not in str(users)


def test_an_admin_cannot_lock_themselves_out_and_changes_sign_users_out(app, api, world):
    admin = api("admin")
    me = world["users"]["admin"]["id"]
    refused(admin.patch(f"{API}/admin/users/{me}", json={"is_active": False}), 403, message="lock the last administrator")
    refused(admin.patch(f"{API}/admin/users/{me}", json={"role": "AUDITOR"}), 403)
    victim = world["users"]["supervisor"]
    session = login(app, victim["email"])
    ok(admin.patch(f"{API}/admin/users/{victim['id']}", json={"role": "ENGINEER"}))
    refused(session.get(f"{API}/auth/me"), 401)                              # sessions revoked on a role change
    assert ok(login(app, victim["email"]).get(f"{API}/auth/me"))["user"]["role"] == "ENGINEER"
    ok(admin.patch(f"{API}/admin/users/{victim['id']}", json={"new_password": "Reset-Password-77"}))
    refused(TestClient(app, raise_server_exceptions=False).post(f"{API}/auth/login", json={"email": victim["email"], "password": PASSWORD}), 401)
    refused(admin.patch(f"{API}/admin/users/999999", json={"is_active": False}), 404)


# --- law as data ----------------------------------------------------------------------------------------------------
def test_rule_parameters_are_listed_with_legal_references_and_assumptions_are_flagged(api):
    rules = {r["param_key"]: r for r in ok(api("worker_a").get(f"{API}/rules"))["items"]}              # public to any signed-in user
    assert rules["gas_o2_min"]["legal_ref"] and rules["gas_o2_min"]["is_assumption"] is False
    assert rules["gas_co_max_ppm"]["is_assumption"] is True and "ASSUMPTION" in rules["gas_co_max_ppm"]["legal_ref"]
    assert float(rules["compensation_fatality_inr"]["value"]) == 3000000


def test_rule_changes_are_range_checked_audited_and_change_the_gate(api, world):
    admin, sup = api("admin"), api("supervisor")
    refused(admin.patch(f"{API}/rules/gas_max_age_min", json={"value": 100000, "reason": "Synthetic test policy adjustment"}), 422, message="between")
    refused(admin.patch(f"{API}/rules/min_crew_size", json={"value": 1, "reason": "Synthetic test policy adjustment"}), 422, message="between")      # cannot weaken below the statutory floor
    refused(admin.patch(f"{API}/rules/no_such_rule", json={"value": 1, "reason": "Synthetic test policy adjustment"}), 404)
    refused(admin.patch(f"{API}/rules/min_crew_size", json={"value": "abc", "reason": "Synthetic test policy adjustment"}), 422)
    _, _, permit = build_permit(api, world)
    ok(admin.patch(f"{API}/rules/min_crew_size", json={"value": 5, "reason": "Synthetic test policy adjustment"}))                                  # tighten: 4 people are now too few
    denied = ok(sup.post(f"{API}/permits/{permit['permit_id']}/authorise"))
    assert denied["failed"] == ["CREW_SIZE"] and "4 of the required 5" in denied["clauses"][5]["detail"]
    ok(admin.patch(f"{API}/rules/min_crew_size", json={"value": 4, "reason": "Synthetic test policy adjustment"}))
    assert ok(sup.post(f"{API}/permits/{permit['permit_id']}/authorise"))["authorised"] is True
    trail = ok(api("auditor").get(f"{API}/audit-log?table_name=rule_parameter&row_pk=min_crew_size"))
    # Migration-time provenance corrections are also audited with a NULL actor; keep this assertion
    # scoped to the two authenticated administrator changes performed by this test.
    admin_changes = [r for r in reversed(trail["items"]) if r["actor_user_id"] is not None]
    assert [r["new_data"]["value"] for r in admin_changes] == [5, 4]
    assert all(r["actor_user_id"] == world["users"]["admin"]["id"] for r in admin_changes)


def test_the_audit_log_is_filterable_and_never_contains_password_hashes(api, world):
    ok(api("admin").post(f"{API}/admin/users", json={"email": "x@zeroentry.example", "full_name": "X", "role": "AUDITOR", "password": "Strong-Pass-123"}), 201)
    log = ok(api("auditor").get(f"{API}/audit-log?table_name=app_user&action=INSERT"))
    assert log["total"] >= 1 and "$2b$" not in str(log) and "password_hash" not in str(log)
    assert ok(api("auditor").get(f"{API}/audit-log?table_name=nonexistent"))["total"] == 0
    assert ok(api("admin").get(f"{API}/audit-log?occurred_from=2099-01-01"))["total"] == 0


# --- validation and error shapes --------------------------------------------------------------------------------------
def test_validation_errors_share_one_shape_and_name_the_field(api, world):
    eng = api("engineer")
    error = refused(eng.post(f"{API}/complaints", json={"manhole_id": "abc", "description": ""}), 422, "validation_error")
    assert {d["field"] for d in error["details"]} == {"manhole_id", "description"}
    refused(eng.post(f"{API}/complaints", json={"manhole_id": world["manhole"], "description": "ok", "status": "RESOLVED"}), 422, "validation_error")   # no mass assignment
    refused(eng.post(f"{API}/complaints", content=b"{not json", headers={"Content-Type": "application/json"}), 422)
    refused(eng.post(f"{API}/jobs", json={"complaint_id": 999999, "contractor_id": world["ca"]}), 409, "reference_conflict")
    refused(eng.get(f"{API}/complaints/abc"), 422, "validation_error")
    refused(eng.get(f"{API}/no-such-endpoint"), 404, "not_found")
    refused(eng.delete(f"{API}/auth/me"), 405, "method_not_allowed")
    refused(eng.get(f"{API}/complaints?limit=100000"), 422)
    assert ok(eng.get(f"{API}/complaints?limit=200"))["limit"] == 200


def test_filters_are_type_checked_and_search_text_is_never_executed_as_sql(api, world):
    eng = api("engineer")
    refused(eng.get(f"{API}/manholes?ulb_id=banana"), 422, "unprocessable", "ulb_id")
    refused(eng.get(f"{API}/manholes?kind=SEWER&ulb_id=1;DROP TABLE manhole"), 422)
    for hostile in ("' OR '1'='1", "'; DROP TABLE complaint; --", "%", "_", "\\"):
        response = eng.get(f"{API}/complaints", params={"q": hostile})
        assert response.status_code == 200, (hostile, response.text)       # bound as data: matches nothing, breaks nothing
        assert response.json()["total"] == 0
        assert eng.get(f"{API}/manholes", params={"q": hostile}).status_code == 200
    refused(eng.get(f"{API}/complaints", params={"q": "a\x00b"}), 422, "bad_value")            # NUL cannot be stored: a 422, never a 500
    assert ok(eng.get(f"{API}/manholes?q=TST-"))["total"] == 1                                      # real prefix search still works
    assert ok(eng.get(f"{API}/workers?q=NAM-T"))["total"] == 10


def test_crud_on_reference_data_and_database_refusals_become_readable_errors(api, world):
    admin, eng = api("admin"), api("engineer")
    ulb = ok(admin.post(f"{API}/ulbs", json={"name": "GCC Zone 99", "district": "Chennai", "state": "Tamil Nadu"}), 201)
    refused(admin.post(f"{API}/ulbs", json={"name": "GCC Zone 99", "district": "Chennai", "state": "Tamil Nadu"}), 409, "duplicate")
    mh = ok(eng.post(f"{API}/manholes", json={"ulb_id": ulb["ulb_id"], "code": "ZZ-001", "kind": "SEWER", "depth_m": 3.5, "lat": 13.1, "lng": 80.2}), 201)
    refused(eng.post(f"{API}/manholes", json={"ulb_id": ulb["ulb_id"], "code": "ZZ-002", "kind": "SEWER", "depth_m": 0, "lat": 13.1, "lng": 80.2}), 422)
    refused(eng.post(f"{API}/manholes", json={"ulb_id": 999999, "code": "ZZ-003", "kind": "SEWER", "depth_m": 3, "lat": 13.1, "lng": 80.2}), 409, "reference_conflict")
    assert ok(eng.patch(f"{API}/manholes/{mh['manhole_id']}", json={"depth_m": 4.25}))["depth_m"] == 4.25
    refused(admin.delete(f"{API}/ulbs/{ulb['ulb_id']}"), 409, "reference_conflict")          # still has a manhole
    ok(admin.delete(f"{API}/manholes/{mh['manhole_id']}"))
    ok(admin.delete(f"{API}/ulbs/{ulb['ulb_id']}"))
    refused(admin.get(f"{API}/ulbs/{ulb['ulb_id']}"), 404)


def test_only_an_admin_can_blacklist_or_reinstate_a_contractor(api, world):
    eng, admin = api("engineer"), api("admin")
    refused(eng.patch(f"{API}/contractors/{world['ca']}", json={"status": "BLACKLISTED"}), 403, message="ADMIN")
    assert ok(eng.patch(f"{API}/contractors/{world['ca']}", json={"status": "SUSPENDED"}))["status"] == "SUSPENDED"
    assert ok(eng.patch(f"{API}/contractors/{world['ca']}", json={"status": "ACTIVE"}))["status"] == "ACTIVE"
    ok(admin.patch(f"{API}/contractors/{world['ca']}", json={"status": "BLACKLISTED"}))
    refused(eng.patch(f"{API}/contractors/{world['ca']}", json={"status": "ACTIVE"}), 403)
    assert ok(admin.patch(f"{API}/contractors/{world['ca']}", json={"status": "ACTIVE"}))["status"] == "ACTIVE"


# --- request plumbing ----------------------------------------------------------------------------------------------------
def test_the_request_context_never_leaks_to_the_next_request_on_a_pooled_connection(app, api, world):
    ok(api("admin").get(f"{API}/audit-log"))                                           # a request that set app.role = ADMIN
    with app.state.engine.connect() as raw:
        assert raw.execute(text("SELECT app_role(), app_user_id()")).one() == (None, None)


def test_a_failing_commit_is_an_error_response_not_a_phantom_success():
    """get_db must commit BEFORE the response is sent. Guards the scope='function' choice on the dependency."""
    class BrokenSession:
        def commit(self):
            raise HTTPException(status_code=500, detail="commit failed")

        def rollback(self): pass
        def close(self): pass

    probe = FastAPI()
    probe.state.sessionmaker = lambda: BrokenSession()

    @probe.post("/write")
    def write(db: DB):
        return {"ok": True}

    response = TestClient(probe, raise_server_exceptions=False).post("/write")
    assert response.status_code == 500 and response.json() != {"ok": True}
