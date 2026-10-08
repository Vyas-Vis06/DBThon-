"""Prepare one fresh educational DRAFT through authenticated local API routes.

No SQL, owner credentials, policy changes or automatic authorization. Every inserted
record is synthetic. An incomplete fourth acknowledgement is deliberately left for
the live demonstration. Repeated invocations create separate rehearsal work orders.
"""

import argparse
import getpass
import json
import os
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from uuid import uuid4

import httpx


def request(client, method, path, body=None):
    response = client.request(method, "/api/v1" + path, json=body,
                              headers={"Idempotency-Key": str(uuid4())} if method != "GET" else {})
    if not response.is_success:
        raise RuntimeError(f"Demo preparation stopped at {method} {path}: {response.status_code} {response.text[:500]}")
    return response.json()


def prepare(clients):
    engineer, supervisor = clients["engineer"], clients["supervisor"]
    actor = request(engineer, "GET", "/auth/me")["user"]
    sup = request(supervisor, "GET", "/auth/me")["user"]
    if (actor["role"] != "ENGINEER" or sup["role"] != "SUPERVISOR"
            or not actor.get("educational") or not sup.get("educational")
            or actor["ulb_id"] != sup["ulb_id"]):
        raise RuntimeError("Refusing preparation outside one explicitly EDUCATIONAL scope.")
    ulb = actor["ulb_id"]
    crew = [request(clients[f"worker_{i}"], "GET", "/auth/me")["user"] for i in range(1, 5)]
    if any(person["role"] != "WORKER" or person.get("worker_id") is None for person in crew):
        raise RuntimeError("Four distinct worker-linked educational login accounts are required.")
    if len({person["worker_id"] for person in crew}) != 4:
        raise RuntimeError("The demonstration requires four different actual crew members.")
    workers = request(engineer, "GET", "/workers?limit=200")["items"]
    own = {row["worker_id"]: row for row in workers}
    if any(person["worker_id"] not in own for person in crew):
        raise RuntimeError("A crew account is outside the educational engineer's scope.")
    contractors = {own[person["worker_id"]]["contractor_id"] for person in crew}
    if len(contractors) != 1:
        raise RuntimeError("All four synthetic crew members must belong to one scoped contractor.")
    sites = request(engineer, "GET", "/manholes?limit=200")["items"]
    site = next((row for row in sites if row["ulb_id"] == ulb), None)
    detectors = request(supervisor, "GET", "/detectors?limit=200")["items"]
    now = datetime.now(timezone.utc)
    detector = next((row for row in detectors if row["calibration_valid_until"] >= now.date().isoformat()), None)
    if site is None or detector is None:
        raise RuntimeError("Educational site and explicitly allocated, in-date detector are required.")
    rehearsal = uuid4().hex[:10]
    complaint = request(engineer, "POST", "/complaints", {
        "manhole_id": site["manhole_id"], "description": f"Synthetic educational rehearsal {rehearsal}; no field work."})
    job = request(engineer, "POST", "/jobs", {
        "complaint_id": complaint["complaint_id"], "contractor_id": next(iter(contractors))})
    request(engineer, "POST", f"/jobs/{job['job_id']}/waiver", {
        "reason_code": "NO_MACHINE_ACCESS",
        "justification": "Synthetic educational exception for a fictional inaccessible chamber; no real entry is authorized."})
    permit = request(supervisor, "POST", "/permits", {"job_id": job["job_id"]})
    pid = permit["permit_id"]
    for index, person in enumerate(crew, 1):
        request(supervisor, "POST", f"/permits/{pid}/crew", {
            "worker_id": person["worker_id"], "crew_role": ["ENTRANT", "ENTRANT", "STANDBY", "SUPERVISOR"][index-1]})
        if index != 4:
            request(clients[f"worker_{index}"], "POST", f"/permits/{pid}/acknowledge")
    catalogue = request(engineer, "GET", "/gear-items?limit=200")["items"]
    for item in catalogue:
        people = crew[:2] if item["requirement_scope"] == "ENTRANT" and item["statutory"] else []
        assignments = people if people else ([None] if item["requirement_scope"] == "SITE" else [])
        for person in assignments:
            serial = f"EDU-{rehearsal}-{item['gear_code']}-{person['worker_id'] if person else 'SITE'}"
            asset = request(engineer, "POST", "/reference/gear-assets", {
                "ulb_id": ulb, "gear_code": item["gear_code"], "serial_no": serial,
                "status": "USABLE", "inspection_valid_until": (now.date() + timedelta(days=30)).isoformat()})
            if person:
                request(supervisor, "POST", f"/permits/{pid}/gear", {
                    "worker_id": person["worker_id"], "gear_code": item["gear_code"],
                    "serial_no": serial, "gear_asset_id": asset["gear_asset_id"]})
            else:
                request(supervisor, "POST", f"/permits/{pid}/site-gear", {"gear_asset_id": asset["gear_asset_id"]})
    refs = {
        "STRUCTURE": {"inspection_ref": "EDU-SYNTHETIC", "qualified_person_ref": "EDU-PERSON"},
        "ISOLATION": {"isolation_ref": "EDU-ISOLATION"},
        "VENTILATION": {"opened_at": (now-timedelta(minutes=30)).isoformat(), "method_ref": "EDU-VENTILATION"},
        "RESCUE": {"plan_ref": "EDU-PLAN", "retrieval_asset_ref": "EDU-RETRIEVAL"},
        "COMMUNICATION": {"method_ref": "EDU-RADIO", "test_ref": "EDU-TEST"},
        "TRAFFIC": {"barrier_ref": "EDU-BARRIER"},
        "MEDICAL": {"contact_ref": "EDU-CONTACT", "first_aid_ref": "EDU-FIRST-AID"},
    }
    for kind, details in refs.items():
        request(supervisor, "POST", f"/permits/{pid}/readiness", {
            "kind": kind, "passed": True, "expires_at": (now+timedelta(hours=1)).isoformat(), "details": details})
    for depth in ("TOP", "MID", "BOTTOM"):
        request(supervisor, "POST", f"/permits/{pid}/readings", {
            "detector_id": detector["detector_id"], "depth_level": depth,
            "o2_pct": 20.9, "h2s_ppm": 0, "lel_pct": 0, "co_ppm": 0, "source_mode": "SIMULATED"})
    return {"permit_id": pid, "complaint_id": complaint["complaint_id"], "job_id": job["job_id"],
            "detector_id": detector["detector_id"], "policy": "EDUCATIONAL", "status": "DRAFT",
            "acknowledgement_still_required_from": crew[3]["email"],
            "supervisor_email": sup["email"],
            "limits": "All evidence is synthetic/typed for rehearsal; no field inspection or legal permission claimed."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    parsed = urlparse(args.url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password:
        parser.error("Use an ordinary local HTTP development server; never a remote or credential-bearing URL.")
    password = os.getenv("ZEROENTRY_DEMO_PASSWORD") or getpass.getpass("Local demo password: ")
    with ExitStack() as stack:
        clients = {}
        accounts = {"engineer": "edu_engineer", "supervisor": "edu_supervisor",
                    **{f"worker_{i}": f"edu_worker_{i}" for i in range(1, 5)}}
        for key, login in accounts.items():
            client = stack.enter_context(httpx.Client(base_url=args.url, timeout=20, follow_redirects=False))
            result = request(client, "POST", "/auth/login", {"email": login+"@zeroentry.example", "password": password})
            client.headers["Authorization"] = "Bearer " + result["session_token"]
            clients[key] = client
        print(json.dumps(prepare(clients), indent=2))


if __name__ == "__main__":
    main()
