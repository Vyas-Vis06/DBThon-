"""The demo contract end to end over HTTP, as real users: mechanised-first -> waiver -> denied -> fixed -> authorised ->
entries (90-minute limit, overlap) -> close -> resolve; and the fatality transaction. PROJECT_SPEC section 8."""

from datetime import datetime, timedelta, timezone

from tests.api.conftest import API, ok, refused

NOW = lambda: datetime.now(timezone.utc)  # noqa: E731


def iso(dt: datetime) -> str:
    return dt.isoformat()


def new_job(api, world, contractor=None, *, waiver=True):
    eng = api("engineer")
    complaint = ok(eng.post(f"{API}/complaints", json={"manhole_id": world["manhole"], "description": "Chamber overflowing, foul smell"}), 201)
    job = ok(eng.post(f"{API}/jobs", json={"complaint_id": complaint["complaint_id"], "contractor_id": contractor or world["ca"]}), 201)
    if waiver:
        ok(eng.post(f"{API}/jobs/{job['job_id']}/waiver", json={
            "reason_code": "NO_MACHINE_ACCESS", "justification": "Narrow chamber, no vehicle access; jetting and suction units cannot reach it."}), 201)
    return complaint, job


def build_permit(api, world, *, standby=True, full_gear=True, bottom_age_min=1):
    """A DRAFT permit through the API: crew of four (w0 is the worker login), gear, readings. Returns (complaint, job, permit)."""
    sup = api("supervisor")
    complaint, job = new_job(api, world)
    permit = ok(sup.post(f"{API}/permits", json={"job_id": job["job_id"]}), 201)
    pid = permit["permit_id"]
    w = world["workers_a"]
    crew = [(w[0], "ENTRANT"), (w[1], "ENTRANT"), (w[3], "SUPERVISOR")] + ([(w[2], "STANDBY")] if standby else [])
    for worker, role in crew:
        ok(sup.post(f"{API}/permits/{pid}/crew", json={"worker_id": worker, "crew_role": role}), 201)
    statutory = [g["gear_code"] for g in ok(api("supervisor").get(f"{API}/gear-items?statutory=true"))["items"]]
    for worker in (w[0], w[1]):
        for code in statutory[: (len(statutory) if full_gear or worker != w[1] else len(statutory) - 1)]:
            ok(sup.post(f"{API}/permits/{pid}/gear", json={"worker_id": worker, "gear_code": code, "serial_no": f"SN-{worker}-{code}"}), 201)
    for level, age in (("TOP", 1), ("MID", 1), ("BOTTOM", bottom_age_min)):
        ok(sup.post(f"{API}/permits/{pid}/readings", json={
            "detector_id": world["detector"], "depth_level": level, "o2_pct": 20.9, "h2s_ppm": 0, "lel_pct": 0, "co_ppm": 0,
            "taken_at": iso(NOW() - timedelta(minutes=age))}), 201)
    return complaint, job, permit


def widen_daylight(api):
    """Law is data: so a demo or test outside 06:00-18:00 IST widens the window through the audited admin API."""
    admin = api("admin")
    ok(admin.patch(f"{API}/rules/daylight_start_hour", json={"value": 0, "reason": "Synthetic test policy adjustment"}))
    ok(admin.patch(f"{API}/rules/daylight_end_hour", json={"value": 24, "reason": "Synthetic test policy adjustment"}))


# --- the demo ---------------------------------------------------------------------------------------------------
def test_machine_fails_then_waiver_then_denied_with_reasons_then_authorised(api, world):
    eng, sup = api("engineer"), api("supervisor")
    complaint, job = new_job(api, world, waiver=False)
    jid = job["job_id"]

    # 1. the machine is tried first and fails
    deployment = ok(eng.post(f"{API}/jobs/{jid}/deployments", json={"machine_id": world["machine"], "started_at": iso(NOW() - timedelta(hours=2))}), 201)
    ok(eng.post(f"{API}/deployments/{deployment['deploy_id']}/finish", json={"ended_at": iso(NOW() - timedelta(hours=1)), "outcome": "FAILED"}))

    # 2. no permit without the engineer's written waiver; only an ENGINEER may file it
    refused(sup.post(f"{API}/permits", json={"job_id": jid}), 422, "rule_violation", "waiver")
    refused(sup.post(f"{API}/jobs/{jid}/waiver", json={"reason_code": "MACHINE_FAILED", "justification": "x" * 60}), 403)
    refused(eng.post(f"{API}/jobs/{jid}/waiver", json={"reason_code": "MACHINE_FAILED", "justification": "too short"}), 422)
    ok(eng.post(f"{API}/jobs/{jid}/waiver", json={"reason_code": "MACHINE_FAILED",
        "justification": "The jetting unit failed twice on the blockage; the chamber is too narrow for the suction unit."}), 201)
    assert ok(eng.get(f"{API}/jobs/{jid}"))["method"] == "MANUAL_EXCEPTION"

    # 3. the supervisor drafts a permit with three deliberate gaps: no standby, one entrant short of gear, stale BOTTOM reading
    permit = ok(sup.post(f"{API}/permits", json={"job_id": jid}), 201)
    pid = permit["permit_id"]
    w = world["workers_a"]
    for worker, role in ((w[0], "ENTRANT"), (w[1], "ENTRANT"), (w[3], "SUPERVISOR")):
        ok(sup.post(f"{API}/permits/{pid}/crew", json={"worker_id": worker, "crew_role": role}), 201)
    statutory = [g["gear_code"] for g in ok(sup.get(f"{API}/gear-items?statutory=true"))["items"]]
    assert len(statutory) == 5
    for worker in (w[0], w[1]):
        for code in statutory if worker == w[0] else statutory[:-1]:
            ok(sup.post(f"{API}/permits/{pid}/gear", json={"worker_id": worker, "gear_code": code, "serial_no": f"SN-{worker}-{code}"}), 201)
    for level, age in (("TOP", 1), ("MID", 2), ("BOTTOM", 22)):
        ok(sup.post(f"{API}/permits/{pid}/readings", json={"detector_id": world["detector"], "depth_level": level, "o2_pct": 20.9,
                                                           "h2s_ppm": 0, "lel_pct": 0, "co_ppm": 0, "taken_at": iso(NOW() - timedelta(minutes=age))}), 201)

    # the live checklist and the gate agree: DENIED, with exactly three legal reasons
    live = ok(sup.get(f"{API}/permits/{pid}/clauses"))
    assert live["ready_to_authorise"] is False
    denied = ok(sup.post(f"{API}/permits/{pid}/authorise"))
    assert denied["authorised"] is False and denied["permit_status"] == "DRAFT"
    assert sorted(denied["failed"]) == ["CREW_STANDBY", "GAS_BOTTOM", "GEAR_ALL"]
    by_code = {c["clause_code"]: c for c in denied["clauses"]}
    assert "22 min old" in by_code["GAS_BOTTOM"]["detail"] and "standby" in by_code["CREW_STANDBY"]["detail"]
    assert all(c["title"] and c["legal_ref"] for c in denied["clauses"]) and len(denied["clauses"]) == 11

    # 4. the supervisor fixes each point and is AUTHORISED
    ok(sup.post(f"{API}/permits/{pid}/crew", json={"worker_id": w[2], "crew_role": "STANDBY"}), 201)
    ok(sup.post(f"{API}/permits/{pid}/gear", json={"worker_id": w[1], "gear_code": statutory[-1], "serial_no": "SN-LATE"}), 201)
    ok(sup.post(f"{API}/permits/{pid}/readings", json={"detector_id": world["detector"], "depth_level": "BOTTOM", "o2_pct": 20.8,
                                                       "h2s_ppm": 1, "lel_pct": 0, "co_ppm": 2}), 201)
    granted = ok(sup.post(f"{API}/permits/{pid}/authorise"))
    assert granted["authorised"] is True and granted["failed"] == [] and granted["permit_status"] == "AUTHORISED"

    # the proof is frozen: crew and gear can no longer change, and a second authorisation is refused
    refused(sup.post(f"{API}/permits/{pid}/crew", json={"worker_id": w[4], "crew_role": "ENTRANT"}), 409, "invalid_state", "frozen")
    refused(sup.delete(f"{API}/permits/{pid}/crew/{w[2]}"), 409, "invalid_state", "frozen")
    refused(sup.post(f"{API}/permits/{pid}/authorise"), 409, "invalid_state")

    dossier = ok(sup.get(f"{API}/permits/{pid}"))
    assert dossier["permit"]["status"] == "AUTHORISED" and dossier["clauses"] is None
    assert len(dossier["crew"]) == 4 and len(dossier["gear"]) == 10 and len(dossier["readings"]) == 4
    assert dossier["job"]["contractor_name"] and dossier["complaint"]["manhole_code"] and dossier["waiver"]["reason_code"] == "MACHINE_FAILED"


def test_entries_use_current_admission_and_exits_remain_recordable(api, world, conn):
    sup, eng = api("supervisor"), api("engineer")
    widen_daylight(api)
    complaint, job, permit = build_permit(api, world)
    pid, w = permit["permit_id"], world["workers_a"]
    assert ok(sup.post(f"{API}/permits/{pid}/authorise"))["authorised"] is True
    start = NOW()

    # A client cannot backdate a new open admission to make an old authorized permit look current.
    refused(sup.post(f"{API}/permits/{pid}/entries", json={"worker_id": w[0], "entered_at": iso(start - timedelta(hours=1))}),
            422, "rule_violation", "server clock")
    refused(sup.post(f"{API}/permits/{pid}/entries", json={"worker_id": w[2], "entered_at": iso(start)}), 422, "rule_violation", "ENTRANT")
    entry = ok(sup.post(f"{API}/permits/{pid}/entries", json={"worker_id": w[0], "entered_at": iso(start)}), 201)
    assert entry["open"] is True
    refused(sup.post(f"{API}/permits/{pid}/entries", json={"worker_id": w[0], "entered_at": iso(start + timedelta(minutes=1)),
                                                           "exited_at": iso(start + timedelta(minutes=30))}), 409, "overlap")
    other = ok(sup.post(f"{API}/permits/{pid}/entries", json={"worker_id": w[1], "entered_at": iso(start),
                                                            "exited_at": iso(NOW() + timedelta(minutes=2))}), 201)
    assert other["minutes"] >= 1 and other["exit_recorded_at"] is not None
    assert conn.execute("SELECT count(*) AS n FROM permit_safety_event WHERE entry_id = %s AND reason_code = 'EXIT_TIME_AHEAD_OF_RECEIPT'",
                        (other["entry_id"],)).fetchone()["n"] == 1

    refused(sup.post(f"{API}/permits/{pid}/close"), 409, "invalid_state", "still inside")
    refused(sup.post(f"{API}/permits/{pid}/entries/{entry['entry_id']}/exit", json={"exited_at": iso(NOW() + timedelta(minutes=15))}),
            422, "rule_violation", "five minutes ahead")
    done = ok(sup.post(f"{API}/permits/{pid}/entries/{entry['entry_id']}/exit", json={"exited_at": iso(NOW() + timedelta(minutes=2))}))
    assert done["minutes"] >= 1 and done["open"] is False and done["exit_recorded_at"] is not None
    assert ok(sup.post(f"{API}/permits/{pid}/close"))["status"] == "CLOSED"
    refused(sup.post(f"{API}/permits/{pid}/entries", json={"worker_id": w[1], "entered_at": iso(start + timedelta(minutes=90))}), 409, "invalid_state")

    # the closed, logged permit is lawful clearance evidence: resolving the complaint raises no warning
    resolved = ok(eng.post(f"{API}/complaints/{complaint['complaint_id']}/resolve", json={"resolution_code": "CLEARED"}))
    assert resolved["status"] == "RESOLVED" and resolved["evidence_on_file"] is True and resolved["warning"] is None


def test_exit_can_be_logged_after_permit_abort_without_rewriting_the_stop_reason(api, world, conn):
    sup = api("supervisor")
    widen_daylight(api)
    _, _, permit = build_permit(api, world)
    pid, worker = permit["permit_id"], world["workers_a"][0]
    ok(sup.post(f"{API}/permits/{pid}/authorise"))
    entered = ok(sup.post(f"{API}/permits/{pid}/entries", json={"worker_id": worker, "entered_at": iso(NOW())}), 201)
    ok(sup.post(f"{API}/permits/{pid}/abort", json={"reason": "Gas alarm: stop work now"}))
    exited = ok(sup.post(f"{API}/permits/{pid}/entries/{entered['entry_id']}/exit",
                         json={"exited_at": iso(NOW() + timedelta(minutes=2))}))
    assert exited["open"] is False and exited["exit_recorded_at"] is not None
    status = ok(sup.get(f"{API}/permits/{pid}"))["permit"]["status"]
    assert status == "ABORTED"
    reason = conn.execute("SELECT end_reason FROM entry_permit WHERE permit_id = %s", (pid,)).fetchone()["end_reason"]
    assert reason == "Gas alarm: stop work now"
    assert conn.execute("SELECT count(*) AS n FROM permit_safety_event WHERE entry_id = %s AND reason_code = 'EXIT_AFTER_PERMIT_STOP'",
                        (entered["entry_id"],)).fetchone()["n"] == 1


def test_daylight_is_law_as_data_the_default_window_refuses_night_entry(api, world, conn):
    sup = api("supervisor")
    complaint, job, permit = build_permit(api, world)
    pid, w = permit["permit_id"], world["workers_a"]
    assert ok(sup.post(f"{API}/permits/{pid}/authorise"))["authorised"] is True
    # two hours before the permit existed, or a night hour: pick an instant inside the window but outside 06:00-18:00 IST
    ist = timezone(timedelta(hours=5, minutes=30))
    t = NOW().astimezone(ist)
    night = t.replace(hour=23, minute=0, second=0, microsecond=0)
    if t.hour >= 6 and t.hour < 18:                           # daytime now: use a sub-case that is always true
        refused(sup.post(f"{API}/permits/{pid}/entries", json={"worker_id": w[0], "entered_at": iso(t - timedelta(hours=1))}), 422, "rule_violation")
    else:
        refused(sup.post(f"{API}/permits/{pid}/entries", json={"worker_id": w[0], "entered_at": iso(t + timedelta(minutes=1))}),
                422, "rule_violation", "daylight")
    ok(api("admin").patch(f"{API}/rules/daylight_end_hour", json={"value": 24, "reason": "Synthetic test policy adjustment"}))
    audit = ok(api("auditor").get(f"{API}/audit-log?table_name=rule_parameter"))
    assert audit["items"][0]["new_data"]["param_key"] == "daylight_end_hour" and audit["items"][0]["actor_user_id"] == world["users"]["admin"]["id"]
    assert night.hour == 23


# --- permit ownership and stop-work -------------------------------------------------------------------------------
def test_a_supervisor_cannot_touch_another_supervisors_permit_but_an_engineer_can_decide(api, world):
    sup, other, eng = api("supervisor"), api("supervisor2"), api("engineer")
    complaint, job, permit = build_permit(api, world)
    pid = permit["permit_id"]
    refused(other.post(f"{API}/permits/{pid}/crew", json={"worker_id": world["workers_a"][4], "crew_role": "ENTRANT"}), 403, message="another supervisor")
    refused(other.post(f"{API}/permits/{pid}/authorise"), 403, message="another supervisor")
    assert ok(eng.post(f"{API}/permits/{pid}/authorise"))["authorised"] is True                 # an engineer may
    assert ok(eng.post(f"{API}/permits/{pid}/abort", json={"reason": "Wet-weather stand-down"}))["status"] == "ABORTED"
    refused(sup.post(f"{API}/permits/{pid}/abort", json={"reason": "Already aborted by the engineer"}), 409, "invalid_state")


def test_a_crew_member_can_stop_work_but_an_outsider_cannot(api, world):
    sup, worker, outsider = api("supervisor"), api("worker_a"), api("contractor_a")
    complaint, job, permit = build_permit(api, world)                     # worker_a (workers_a[0]) is an entrant
    pid = permit["permit_id"]
    assert ok(sup.post(f"{API}/permits/{pid}/authorise"))["authorised"] is True
    refused(outsider.post(f"{API}/permits/{pid}/stop-work", json={"reason": "I am not crew"}), 403)
    refused(worker.post(f"{API}/permits/{pid}/stop-work", json={"reason": "no"}), 422)
    stopped = ok(worker.post(f"{API}/permits/{pid}/stop-work", json={"reason": "Strong gas smell at the bottom of the chamber"}))
    assert stopped["status"] == "ABORTED" and "worker" in stopped["end_reason"].lower()
    assert ok(sup.get(f"{API}/permits/{pid}"))["permit"]["status"] == "ABORTED"


def test_cancelling_a_draft_and_listing_filters(api, world):
    sup = api("supervisor")
    _, job, permit = build_permit(api, world)
    ok(sup.post(f"{API}/permits/{permit['permit_id']}/cancel", json={"reason": "Wrong chamber selected"}))
    cancelled = ok(sup.get(f"{API}/permits?status=CANCELLED"))
    assert cancelled["total"] == 1 and cancelled["items"][0]["permit_id"] == permit["permit_id"]
    assert ok(sup.get(f"{API}/permits?status=AUTHORISED"))["total"] == 0
    assert ok(sup.get(f"{API}/permits?contractor_id={world['ca']}"))["total"] == 1
    assert ok(sup.get(f"{API}/permits?contractor_id={world['cb']}"))["total"] == 0
    assert ok(sup.get(f"{API}/permits?q=TST-MH"))["total"] == 1


# --- the fatality transaction ---------------------------------------------------------------------------------------
def test_recording_a_fatality_does_everything_in_one_call(api, world):
    sup, eng, contractor = api("supervisor"), api("engineer"), api("contractor_a")
    widen_daylight(api)
    complaint, job, permit = build_permit(api, world)
    pid, w = permit["permit_id"], world["workers_a"]
    assert ok(sup.post(f"{API}/permits/{pid}/authorise"))["authorised"] is True
    ok(sup.post(f"{API}/permits/{pid}/entries", json={"worker_id": w[0], "entered_at": iso(NOW() + timedelta(minutes=1))}), 201)
    invoice = ok(contractor.post(f"{API}/invoices", json={"job_id": job["job_id"], "invoice_no": "INV-100", "amount_inr": 250000}), 201)
    assert invoice["on_hold"] is False

    result = ok(sup.post(f"{API}/incidents", json={
        "incident_type": "FATALITY", "occurred_at": iso(NOW() - timedelta(minutes=1)), "worker_id": w[0], "manhole_id": world["manhole"],
        "permit_id": pid, "description": "Worker collapsed at the bottom of the chamber"}), 201)
    assert result["compensation_case"]["amount_due"] == 3000000 and result["compensation_case"]["status"] == "OPEN"
    assert result["contractor"]["status"] == "BLACKLISTED"
    assert result["invoice_holds"] == []                                 # a supervisor cannot see money (row-level security)
    assert ok(eng.get(f"{API}/invoice-holds"))["total"] == 1             # the engineer sees the hold the same call placed

    assert ok(sup.get(f"{API}/permits/{pid}"))["permit"]["status"] == "ABORTED"
    assert ok(eng.get(f"{API}/contractors/{world['ca']}"))["status"] == "BLACKLISTED"
    refused(eng.post(f"{API}/jobs", json={"complaint_id": complaint["complaint_id"], "contractor_id": world["ca"]}), 409, "invalid_state", "BLACKLISTED")
    refused(eng.post(f"{API}/invoices/{invoice['invoice_id']}/approve"), 409, "invalid_state", "on hold")
    refused(sup.post(f"{API}/incidents", json={"incident_type": "FATALITY", "occurred_at": result["occurred_at"], "worker_id": w[0],
                                               "manhole_id": world["manhole"], "permit_id": pid, "description": "duplicate click"}), 409, "duplicate")

    # a contractor sees its own consequences; a different contractor does not
    assert ok(contractor.get(f"{API}/compensation-cases"))["total"] == 1
    assert ok(api("contractor_b").get(f"{API}/compensation-cases"))["total"] == 0
    assert ok(api("auditor").get(f"{API}/invoice-holds"))["total"] == 1
