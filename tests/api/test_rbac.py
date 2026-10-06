"""Role-based access control, enforced on the server. For every endpoint, every role is probed:
  * a role that is allowed gets PAST the guard (it may then get 404/422 from a nonexistent id or an empty body, never 401/403);
  * every other role gets 403; an anonymous caller gets 401.
The probes use id 999999 and an empty JSON body, so nothing is ever created or changed by an allowed role."""

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import API, STAFF

ALL = {"admin", "engineer", "supervisor", "auditor", "contractor_a", "worker_a"}
MUNICIPAL = {"admin", "engineer"}
STAFF_AND_CONTRACTOR = STAFF | {"contractor_a"}
EVERYONE_SIGNED_IN = ALL
ANALYSTS = {"admin", "engineer", "auditor"}
X = 999999

MATRIX = [
    # (method, path, roles allowed)
    ("GET", "/ulbs", STAFF), ("POST", "/ulbs", {"admin"}), ("PATCH", f"/ulbs/{X}", {"admin"}), ("DELETE", f"/ulbs/{X}", {"admin"}),
    ("GET", f"/ulbs/{X}", STAFF),
    ("GET", "/manholes", STAFF), ("POST", "/manholes", MUNICIPAL), ("PATCH", f"/manholes/{X}", MUNICIPAL), ("DELETE", f"/manholes/{X}", {"admin"}),
    ("GET", "/machines", STAFF), ("POST", "/machines", MUNICIPAL), ("DELETE", f"/machines/{X}", {"admin"}),
    ("GET", "/gear-items", STAFF), ("POST", "/gear-items", {"admin"}), ("PATCH", "/gear-items/NOPE", {"admin"}),
    ("GET", "/detectors", STAFF), ("POST", "/detectors", {"admin"}), ("DELETE", f"/detectors/{X}", {"admin"}),
    ("GET", "/contractors", STAFF_AND_CONTRACTOR), ("POST", "/contractors", MUNICIPAL), ("PATCH", f"/contractors/{X}", MUNICIPAL),
    ("DELETE", f"/contractors/{X}", {"admin"}),
    ("GET", "/workers", STAFF_AND_CONTRACTOR | {"worker_a"}), ("POST", "/workers", MUNICIPAL), ("PATCH", f"/workers/{X}", MUNICIPAL),
    ("DELETE", f"/workers/{X}", {"admin"}),
    ("GET", "/complaints", STAFF), ("POST", "/complaints", MUNICIPAL), ("GET", f"/complaints/{X}", STAFF),
    ("PATCH", f"/complaints/{X}", MUNICIPAL), ("POST", f"/complaints/{X}/resolve", MUNICIPAL),
    ("GET", "/jobs", STAFF_AND_CONTRACTOR), ("POST", "/jobs", MUNICIPAL), ("GET", f"/jobs/{X}", STAFF_AND_CONTRACTOR),
    ("PATCH", f"/jobs/{X}", MUNICIPAL), ("POST", f"/jobs/{X}/deployments", MUNICIPAL),
    ("POST", f"/deployments/{X}/finish", MUNICIPAL), ("POST", f"/jobs/{X}/waiver", {"engineer"}),
    ("GET", "/permits", STAFF_AND_CONTRACTOR | {"worker_a"}), ("POST", "/permits", {"supervisor"}),
    ("GET", f"/permits/{X}", STAFF_AND_CONTRACTOR | {"worker_a"}), ("GET", f"/permits/{X}/clauses", STAFF_AND_CONTRACTOR | {"worker_a"}),
    ("POST", f"/permits/{X}/crew", {"supervisor"}), ("DELETE", f"/permits/{X}/crew/1", {"supervisor"}),
    ("POST", f"/permits/{X}/gear", {"supervisor"}), ("DELETE", f"/permits/{X}/gear/1", {"supervisor"}),
    ("POST", f"/permits/{X}/readings", {"supervisor", "engineer"}), ("POST", f"/permits/{X}/authorise", {"supervisor", "engineer"}),
    ("POST", f"/permits/{X}/entries", {"supervisor"}), ("POST", f"/permits/{X}/entries/1/exit", {"supervisor"}),
    ("POST", f"/permits/{X}/close", {"supervisor", "engineer"}), ("POST", f"/permits/{X}/abort", {"supervisor", "engineer"}),
    ("POST", f"/permits/{X}/cancel", {"supervisor", "engineer"}),
    ("POST", f"/permits/{X}/stop-work", {"supervisor", "engineer", "worker_a"}),
    ("GET", "/detections/candidates", ANALYSTS), ("GET", "/detections/alerts", ANALYSTS), ("GET", f"/detections/alerts/{X}", ANALYSTS),
    ("POST", "/detections/scan", MUNICIPAL), ("POST", f"/detections/alerts/{X}/review", MUNICIPAL),
    ("GET", "/detections/rules", ANALYSTS), ("PATCH", "/detections/rules/NOPE", {"admin"}),
    ("POST", "/incidents", {"admin", "engineer", "supervisor"}), ("GET", "/incidents", STAFF_AND_CONTRACTOR),
    ("GET", f"/incidents/{X}", STAFF_AND_CONTRACTOR),
    ("GET", "/compensation-cases", STAFF_AND_CONTRACTOR), ("POST", f"/compensation-cases/{X}/payments", MUNICIPAL),
    ("GET", "/invoices", STAFF_AND_CONTRACTOR), ("POST", "/invoices", MUNICIPAL | {"contractor_a"}),
    ("POST", f"/invoices/{X}/approve", MUNICIPAL), ("POST", f"/invoices/{X}/reject", MUNICIPAL), ("POST", f"/invoices/{X}/pay", MUNICIPAL),
    ("GET", "/invoice-holds", ANALYSTS), ("POST", f"/invoice-holds/{X}/release", MUNICIPAL),
    ("GET", "/reports/dashboard", EVERYONE_SIGNED_IN), ("GET", "/reports/summary", ANALYSTS), ("GET", "/reports/ulb-kpis", ANALYSTS),
    ("GET", "/reports/contractor-risk", ANALYSTS), ("GET", "/reports/compensation-overdue", ANALYSTS),
    ("GET", "/reports/shadow-summary", ANALYSTS), ("GET", "/reports/permit-readiness", STAFF),
    ("GET", "/admin/users", {"admin"}), ("POST", "/admin/users", {"admin"}), ("PATCH", f"/admin/users/{X}", {"admin"}),
    ("GET", "/rules", EVERYONE_SIGNED_IN), ("PATCH", "/rules/NOPE", {"admin"}),
    ("GET", "/audit-log", {"admin", "auditor"}),
    ("GET", "/auth/me", EVERYONE_SIGNED_IN),
]


def probe(client: TestClient, method: str, path: str):
    kwargs = {"json": {}} if method in ("POST", "PATCH") else {}
    return client.request(method, f"{API}{path}", **kwargs)


@pytest.mark.parametrize("method,path,allowed", MATRIX, ids=[f"{m} {p}" for m, p, _ in MATRIX])
def test_every_role_gets_exactly_the_access_it_is_meant_to_have(shared, method, path, allowed):
    for who in sorted(ALL):
        status = probe(shared.api(who), method, path).status_code
        if who in allowed:
            assert status not in (401, 403), f"{who} should be allowed {method} {path}, got {status}"
        else:
            assert status == 403, f"{who} must be refused {method} {path}, got {status}"


@pytest.mark.parametrize("method,path,allowed", MATRIX, ids=[f"{m} {p}" for m, p, _ in MATRIX])
def test_anonymous_callers_get_401_everywhere(shared, method, path, allowed):
    assert probe(TestClient(shared.app, raise_server_exceptions=False), method, path).status_code == 401


def test_the_health_check_and_login_are_the_only_public_endpoints(shared):
    app, spec = shared.app, shared.app.openapi()
    public = []
    for path, operations in spec["paths"].items():
        for method in operations:
            if method.upper() in ("GET", "POST", "PATCH", "PUT", "DELETE"):
                response = TestClient(app, raise_server_exceptions=False).request(method.upper(), path.replace("{", "1").replace("}", ""))
                if response.status_code != 401:
                    public.append((method.upper(), path, response.status_code))
    assert sorted(p for _, p, _ in public) == ["/api/v1/auth/login", "/health"], public


def test_a_client_cannot_claim_a_role_or_identity(shared):
    """Nothing the client sends changes who it is: not a role header, not a user id in the body or query."""
    world, contractor = shared.world, shared.api("contractor_a")
    forged = {"X-Role": "ADMIN", "X-User-Id": str(world["users"]["admin"]["id"]), "X-Forwarded-User": "admin@zeroentry.example"}
    assert contractor.get(f"{API}/admin/users", headers=forged).status_code == 403
    assert contractor.get(f"{API}/admin/users?role=ADMIN&user_id=1").status_code == 403
    assert contractor.post(f"{API}/complaints", json={"manhole_id": world["manhole"], "description": "x", "role": "ADMIN"}).status_code in (403, 422)
