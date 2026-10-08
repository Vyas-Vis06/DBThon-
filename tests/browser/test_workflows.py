"""Real Chromium workflows against the same isolated PostgreSQL-backed FastAPI app."""

from __future__ import annotations

import socket
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Error as PlaywrightError, expect, sync_playwright

from tests.api.conftest import PASSWORD, build_world, login as api_login, make_settings
from tests.factories import Factory
from zeroentry.main import create_app
from zeroentry.security import hash_password


@pytest.fixture
def browser_env(db):
    with db.connect() as conn:
        world = build_world(conn)
        f = Factory(conn)
        conn.execute("UPDATE ulb SET policy_mode='DENIED' WHERE ulb_id=%s", (world["ulb"],))
        complaint = f.complaint(world["manhole"])
        job = f.job(complaint, world["ca"])
        f.waiver(job, world["users"]["engineer"]["id"])
        permit = f.permit(job, world["users"]["supervisor"]["id"])
        world["permit"] = permit
    app = create_app(make_settings(db))
    yield app, world


@pytest.fixture
def browser_safety_env(db):
    with db.connect() as conn:
        factory = Factory(conn)
        scenario = factory.gate_scenario(datetime.now(timezone.utc))
        conn.execute("UPDATE app_user SET ulb_id=%s,password_hash=%s WHERE user_id=%s",
                     (scenario["ulb"], hash_password(PASSWORD, rounds=4), scenario["supervisor"]))
        conn.execute("UPDATE rule_parameter SET value=0 WHERE param_key='daylight_start_hour'")
        conn.execute("UPDATE rule_parameter SET value=24 WHERE param_key='daylight_end_hour'")
    app = create_app(make_settings(db))
    with db.connect() as conn:
        supervisor_email = conn.execute("SELECT email FROM app_user WHERE user_id=%s", (scenario["supervisor"],)).fetchone()["email"]
    supervisor = api_login(app, supervisor_email)
    decision = supervisor.post(f"/api/v1/permits/{scenario['permit']}/authorise", headers={"Idempotency-Key": str(uuid4())})
    assert decision.status_code == 200 and decision.json()["authorised"] is True, decision.text
    entry = supervisor.post(f"/api/v1/permits/{scenario['permit']}/entries", headers={"Idempotency-Key": str(uuid4())}, json={
        "worker_id": scenario["e1"], "entered_at": (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
        "receipt_id": decision.json()["receipt_id"],
    })
    assert entry.status_code == 201, entry.text
    yield app, {**scenario, "supervisor_email": supervisor_email, "receipt_id": decision.json()["receipt_id"]}


@contextmanager
def serve(app):
    import uvicorn

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=3)
        raise RuntimeError("Uvicorn did not start for browser test")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def login(page, base_url: str, email: str):
    page.goto(base_url + "/app/login")
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("**/app/dashboard")
    expect(page.get_by_role("navigation")).to_be_visible()


def await_required(page, label: str) -> bool:
    return page.get_by_label(label).evaluate("el => el.required")


@pytest.mark.browser
def test_login_shows_policy_and_real_denial_receipt(browser_env, tmp_path):
    app, world = browser_env
    with serve(app) as base_url, sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=True)
        except PlaywrightError as error:
            pytest.skip(f"Chromium is not installed for this environment: {error}")
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        # This scenario has no second writer; keep its screen stable while the separate polling
        # scenario below verifies cross-client refresh behavior.
        page.route("**/api/v1/events?**", lambda route: route.fulfill(
            status=200, content_type="application/json",
            body='{"items":[],"next_after":0,"has_more":false,"reset_required":false}'))
        login(page, base_url, world["users"]["engineer"]["email"])
        expect(page.locator("#policy-banner")).to_contain_text("REAL POLICY: DENIED")
        page.goto(f"{base_url}/app/permit?id={world['permit']}")
        expect(page.get_by_role("heading", name=f"Entry permit #{world['permit']}")).to_be_visible()
        expect(page.get_by_label("Permit policy status")).to_contain_text("REAL POLICY: DENIED")
        page.get_by_role("button", name="Ask the database to authorise entry").click()
        expect(page.locator(".banner.bad").filter(has_text="DENIED")).to_be_visible(timeout=8000)
        page.get_by_role("tab", name="Receipts").click()
        expect(page.get_by_role("tabpanel")).to_contain_text("DENIED", timeout=8000)
        expect(page.get_by_role("tabpanel")).to_contain_text("Receipt")
        expect(page.get_by_role("tabpanel")).to_contain_text("POLICY_ELIGIBILITY")
        expect(page.get_by_role("tabpanel")).to_contain_text("POLICY_ELIGIBILITY: Scope policy explicitly denies manual entry")
        expect(page.get_by_role("tabpanel")).not_to_contain_text("UNKNOWN;")
        expect(page.get_by_text("Refreshing this view from the server…")).to_have_count(0, timeout=8000)
        page.get_by_role("tabpanel").screenshot(path=str(tmp_path / "denied-permit-receipt.png"), animations="disabled", timeout=0)
        page.get_by_role("tab", name="Observations").click()
        expect(page.get_by_label("O₂ %")).to_be_visible()
        for label in ("O₂ %", "H₂S ppm", "Combustibles % LEL", "CO ppm"):
            assert await_required(page, label) is False, f"unknown {label} must remain optional"
        page.get_by_label("Detector").select_option(str(world["detector"]))
        page.get_by_label("Depth").select_option("TOP")
        posted_readings = []
        page.on("request", lambda req: posted_readings.append(req.post_data_json) if req.url.endswith("/readings") and req.method == "POST" else None)
        page.get_by_role("button", name="Sign off this reading").click()
        expect(page.get_by_text("UNKNOWN").first).to_be_visible(timeout=10000)
        assert posted_readings and all(posted_readings[-1].get(key) is None for key in ("o2_pct", "h2s_ppm", "lel_pct", "co_ppm")), posted_readings
        assert not page_errors, page_errors
        browser.close()


@pytest.mark.browser
def test_incident_report_lost_response_exact_retry_and_worker_navigation_scope(browser_env):
    app, world = browser_env
    with serve(app) as base_url, sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=True)
        except PlaywrightError as error:
            pytest.skip(f"Chromium is not installed for this environment: {error}")
        page = browser.new_page()
        page_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        login(page, base_url, world["users"]["engineer"]["email"])
        expect(page.locator("#policy-banner")).to_contain_text("REAL POLICY: DENIED")
        page.goto(base_url + "/app/incident_reports")
        expect(page.get_by_role("heading", name="Incident reports")).to_be_visible()

        calls = []

        def commit_then_drop_response(route):
            request = route.request
            if request.method != "POST":
                route.continue_()
                return
            calls.append((request.headers.get("idempotency-key"), request.post_data))
            if len(calls) == 1:
                route.fetch()
                route.abort("connectionreset")
            else:
                route.continue_()

        page.route("**/api/v1/incident-reports", commit_then_drop_response)
        page.get_by_label("Site or location description").fill("Unregistered access shaft")
        page.get_by_label("Reported hazard").fill("Structural collapse report")
        page.get_by_label("What was reported").fill("Two people were reported affected; identity not yet confirmed.")
        page.get_by_label("Victim alias").nth(0).fill("Person A")
        page.get_by_label("Outcome").nth(0).select_option("FATAL")
        page.get_by_role("button", name="Add another victim").click()
        page.get_by_label("Victim alias").nth(1).fill("Person B")
        page.get_by_label("Outcome").nth(1).select_option("INJURY")
        submit = page.get_by_role("button", name="Record pending report")
        submit.click()
        expect(page.locator(".toast.bad")).to_contain_text("Failed to fetch", timeout=8000)
        expect(page.get_by_label("Victim alias").nth(1)).to_have_value("Person B")
        submit.click()
        expect(page.get_by_text("Person A · FATAL", exact=False)).to_be_visible(timeout=10000)
        expect(page.get_by_text("Person B · INJURY", exact=False)).to_be_visible()
        assert len(calls) == 2 and calls[0] == calls[1], "retry must reuse identical key and exact body after a dropped response"

        from fastapi.testclient import TestClient

        client = TestClient(app)
        logged_in = client.post("/api/v1/auth/login", json={"email": world["users"]["engineer"]["email"], "password": PASSWORD})
        assert logged_in.status_code == 200, logged_in.text
        client.headers["X-CSRF-Token"] = logged_in.json()["csrf_token"]
        reports = client.get("/api/v1/incident-reports?limit=50").json()["items"]
        assert len(reports) == 1
        assert len(reports[0]["victims"]) == 2
        assert all(v["case"]["status"] == "PENDING_REVIEW" for v in reports[0]["victims"])
        assert all(float(v["case"]["paid_amount"]) == 0 for v in reports[0]["victims"])

        # A different authorized reporter commits an event. The current screen must pick it up by
        # durable cursor polling and refresh from the server without a page reload.
        admin_client = TestClient(app)
        admin_login = admin_client.post("/api/v1/auth/login", json={"email": world["users"]["admin"]["email"], "password": PASSWORD})
        assert admin_login.status_code == 200, admin_login.text
        admin_client.headers["X-CSRF-Token"] = admin_login.json()["csrf_token"]
        from datetime import datetime, timezone
        from uuid import uuid4

        event_report = admin_client.post("/api/v1/incident-reports", headers={"Idempotency-Key": str(uuid4())}, json={
            "ulb_id": world["ulb"], "occurred_at": datetime.now(timezone.utc).isoformat(),
            "site_label": "Second report delivered by polling", "hazard_type": "Reported hazard",
            "description": "A separately submitted pending reference report.",
            "victims": [{"victim_key": "poll-victim", "display_alias": "Person C", "outcome": "OTHER"}],
        })
        assert event_report.status_code == 201, event_report.text
        expect(page.get_by_text("Second report delivered by polling", exact=False)).to_be_visible(timeout=12000)
        reports = client.get("/api/v1/incident-reports?limit=50").json()["items"]
        assert len(reports) == 2

        page.goto(base_url + "/app/completion_review")
        expect(page.get_by_role("heading", name="Completion accountability")).to_be_visible()
        expect(page.get_by_role("heading", name="Current job reconciliation")).to_be_visible()
        expect(page.get_by_role("heading", name="Import an external completion claim")).to_be_visible()
        page.goto(base_url + "/app/judge_evidence")
        expect(page.get_by_role("heading", name="Judge evidence")).to_be_visible()
        for title in ("DDL and DML", "Constraints", "Single-row functions", "Operators and group functions",
                      "Subqueries, views and joins", "Functions, procedures, cursors and triggers"):
            expect(page.get_by_role("heading", name=title)).to_be_visible()
        expect(page.get_by_text("NOT_YET_MEASURED", exact=False).first).to_be_visible()

        page.unroute("**/api/v1/incident-reports")
        event_requests = []
        page.on("request", lambda request: event_requests.append(request.url) if "/api/v1/events?" in request.url else None)
        page.get_by_role("button", name="Sign out").click()
        page.wait_for_url("**/app/login")
        expect(page.get_by_role("heading", name="Sign in")).to_be_visible()
        await_login_events = len(event_requests)
        page.wait_for_timeout(5500)
        assert len(event_requests) == await_login_events, "event polling must stop after logout"
        page.goto(base_url + "/app/login")
        page.get_by_label("Email").fill(world["users"]["worker_a"]["email"])
        page.get_by_label("Password").fill(PASSWORD)
        page.get_by_role("button", name="Sign in").click()
        page.wait_for_url("**/app/dashboard")
        expect(page.get_by_role("navigation")).to_contain_text("Permits")
        expect(page.get_by_role("navigation")).not_to_contain_text("Incident reports")
        expect(page.get_by_role("navigation")).not_to_contain_text("Judge evidence")
        assert not page_errors, page_errors
        browser.close()


@pytest.mark.browser
def test_adverse_reading_stops_work_and_ui_records_truthful_exit(browser_safety_env):
    app, scenario = browser_safety_env
    with serve(app) as base_url, sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=True)
        except PlaywrightError as error:
            pytest.skip(f"Chromium is not installed for this environment: {error}")
        page = browser.new_page()
        page_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        login(page, base_url, scenario["supervisor_email"])
        page.goto(f"{base_url}/app/permit?id={scenario['permit']}#entries")
        expect(page.locator("#policy-banner")).to_contain_text("EDUCATIONAL SIMULATION")
        expect(page.get_by_text("INSIDE NOW")).to_be_visible(timeout=10000)

        page.get_by_role("tab", name="Observations").click()
        page.get_by_label("Detector").select_option(str(scenario["detector"]))
        page.get_by_label("Depth").select_option("TOP")
        page.get_by_label("H₂S ppm").fill("1000")
        reading_responses = []
        page.on("response", lambda response: reading_responses.append(response.status)
                if response.url.endswith("/readings") and response.request.method == "POST" else None)
        page.get_by_role("button", name="Sign off this reading").click()
        page.wait_for_timeout(500)
        assert reading_responses, page.locator('#toasts').inner_text()
        expect(page.get_by_role("heading", name=f"Entry permit #{scenario['permit']} ABORTED")).to_be_visible(timeout=10000)
        assert reading_responses and reading_responses[-1] == 201, reading_responses
        page.get_by_role("tab", name="Entries").click()
        expect(page.get_by_text("INSIDE NOW")).to_be_visible()
        page.get_by_text("Record exit after stop").click()
        page.get_by_role("button", name="Record exit").click()
        expect(page.get_by_text("INSIDE NOW")).to_have_count(0, timeout=10000)
        expect(page.locator("#main")).to_contain_text("Exited")
        assert not page_errors, page_errors
        browser.close()
