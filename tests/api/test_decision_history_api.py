"""Scoped historical explanations remain stable when current policy changes."""

import hashlib

from tests.api.conftest import API, ok, refused
from tests.api.test_workflow import build_permit


def test_saved_decision_hash_scope_and_history(api, world):
    _, _, permit = build_permit(api, world)
    pid = permit["permit_id"]
    supervisor, admin = api("supervisor"), api("admin")
    refused(supervisor.get(f"{API}/permits/{pid}/decision"), 404)
    assert ok(supervisor.post(f"{API}/permits/{pid}/authorise"))["authorised"]
    original = ok(api("worker_a").get(f"{API}/permits/{pid}/decision"))
    assert original["digest_verified"]
    assert hashlib.sha256(original["canonical_snapshot"].encode()).hexdigest() == original["snapshot_sha256"]
    refused(api("contractor_b").get(f"{API}/permits/{pid}/decision"), 404)
    refused(admin.patch(f"{API}/rules/gas_h2s_max_ppm", json={"value": 9}), 422)
    reason = "Reviewed stricter synthetic demonstration threshold"
    ok(admin.patch(f"{API}/rules/gas_h2s_max_ppm", json={"value": 9, "reason": reason}))
    history = ok(api("auditor").get(f"{API}/rules/gas_h2s_max_ppm/history"))["items"]
    assert [h["revision"] for h in history] == [2, 1]
    assert history[0]["change_reason"] == reason
    assert history[0]["actor_user_id"] == world["users"]["admin"]["id"]
    current = ok(supervisor.get(f"{API}/permits/{pid}/decision"))
    assert current["canonical_snapshot"] == original["canonical_snapshot"]
    sources = ok(api("worker_a").get(f"{API}/policy-sources"))["items"]
    assert {s["source_type"] for s in sources} == {"LAW", "COURT_DIRECTION", "GUIDANCE", "PRODUCT_POLICY"}


def test_stop_history_is_visible_only_with_the_permit(api, world):
    _, _, permit = build_permit(api, world)
    pid = permit["permit_id"]
    sup = api("supervisor")
    assert ok(sup.post(f"{API}/permits/{pid}/authorise"))["authorised"]
    reason = "Worker reports unsafe conditions and requests evacuation"
    ok(api("worker_a").post(f"{API}/permits/{pid}/stop-work", json={"reason": reason}))
    events = ok(api("worker_a").get(f"{API}/permits/{pid}/safety-events"))["items"]
    assert any(reason in e["detail"].get("end_reason", "") for e in events)
    refused(api("contractor_b").get(f"{API}/permits/{pid}/safety-events"), 404)
