"""Supervisor-authenticated synthetic gas feed for a LOCAL demonstration.

    python scripts/simulate_gas.py --permit 2 --detector 1 --unsafe-after 2

Complete crew/gear first. The script logs safe TOP/MID/BOTTOM readings, requests authorization
if the permit is still DRAFT, then introduces a low-oxygen BOTTOM reading at the selected cycle.
Uses existing authenticated API controls. No instrument authentication or physical readings are
claimed. Password comes from a hidden prompt or ZEROENTRY_DEMO_PASSWORD, never a CLI argument.
"""

import argparse
import getpass
import os
import time
from uuid import uuid4
from urllib.parse import urlparse

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--permit", type=int, required=True)
    parser.add_argument("--detector", type=int, required=True)
    parser.add_argument("--email", default="supervisor@zeroentry.example")
    parser.add_argument("--unsafe-after", type=int, default=2)
    parser.add_argument("--interval", type=float, default=2)
    args = parser.parse_args()
    if urlparse(args.url).hostname not in ("127.0.0.1", "localhost", "::1"):
        parser.error("This synthetic demo only targets a local server.")
    if not 2 <= args.unsafe_after <= 50 or not 0 <= args.interval <= 60:
        parser.error("unsafe-after must be 2..50 cycles and interval must be 0..60 seconds")
    password = os.getenv("ZEROENTRY_DEMO_PASSWORD") or getpass.getpass("Local demo password: ")
    with httpx.Client(base_url=args.url.rstrip("/") + "/api/v1", timeout=15) as client:
        login = client.post("/auth/login", json={"email": args.email, "password": password})
        login.raise_for_status()
        client.headers["Authorization"] = f"Bearer {login.json()['session_token']}"
        dossier = client.get(f"/permits/{args.permit}")
        dossier.raise_for_status()
        if not dossier.json().get("policy", {}).get("educational"):
            raise SystemExit("Synthetic readings are restricted to an explicitly EDUCATIONAL ULB policy.")
        for cycle in range(1, args.unsafe_after + 1):
            for depth in ("TOP", "MID", "BOTTOM"):
                unsafe = cycle == args.unsafe_after and depth == "BOTTOM"
                start = time.perf_counter()
                response = client.post(f"/permits/{args.permit}/readings", json={
                    "detector_id": args.detector, "depth_level": depth, "o2_pct": 12 if unsafe else 20.9,
                    "h2s_ppm": 0, "lel_pct": 0, "co_ppm": 0, "source_mode": "SIMULATED"},
                    headers={"Idempotency-Key": str(uuid4())})
                response.raise_for_status()
                elapsed = (time.perf_counter() - start) * 1000
                print(f"Synthetic cycle {cycle}, {depth}, reading #{response.json()['reading_id']}: {elapsed:.1f} ms HTTP round trip")
            dossier = client.get(f"/permits/{args.permit}")
            dossier.raise_for_status()
            if dossier.json()["permit"]["status"] == "DRAFT":
                decision = client.post(f"/permits/{args.permit}/authorise")
                decision.raise_for_status()
                if not decision.json()["authorised"]:
                    raise SystemExit("Complete the permit first: " + ", ".join(decision.json()["failed"]))
            state = client.get(f"/permits/{args.permit}").json()["permit"]
            print(f"Permit #{args.permit}: {state['status']}")
            if state["status"] == "ABORTED":
                print(state["end_reason"])
                events = client.get(f"/permits/{args.permit}/safety-events").json()
                print(f"Durable safety events: {events['total']}. Open exits remain recordable.")
                break
            if cycle != args.unsafe_after:
                time.sleep(args.interval)


if __name__ == "__main__":
    main()
