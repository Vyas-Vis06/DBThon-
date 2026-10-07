"""Shadow-entry detection by absence: the six required scenarios plus idempotency, provenance of holds, SE2.
PROJECT_SPEC BR-30 .. BR-36.  All scans use an explicit clock (`scan(conn, at)`), so results never depend on today."""

from datetime import datetime, timedelta, timezone

import pytest

from tests.factories import Factory, utc, yesterday_ist
from tests.helpers import expect

T0 = utc(2026, 9, 1, 6)          # a complaint is resolved
H = timedelta(hours=1)
SE1, SE2 = "SE1_NO_CLEARANCE_EVIDENCE", "SE2_ENTRANT_NOT_LOGGED"


@pytest.fixture
def f(conn):
    return Factory(conn)


@pytest.fixture
def w(f):
    ulb = f.ulb()
    return {"ulb": ulb, "contractor": f.contractor(), "engineer": f.user("ENGINEER"), "supervisor": f.user("SUPERVISOR"),
            "manhole": f.manhole(ulb), "machine": f.machine(ulb)}


def scan(conn, at):
    return conn.execute("SELECT * FROM scan_shadow_entries(%s)", (at,)).fetchone()


def alerts(conn, complaint=None):
    sql = "SELECT * FROM shadow_entry_alert" + (" WHERE complaint_id = %s" if complaint else "") + " ORDER BY alert_id"
    return conn.execute(sql, (complaint,) if complaint else ()).fetchall()


def holds(conn, invoice):
    return conn.execute("SELECT * FROM invoice_hold WHERE invoice_id = %s ORDER BY hold_id", (invoice,)).fetchall()


def resolved_with_job(f, w, at=T0, code="CLEARED"):
    c = f.resolved_complaint(w["manhole"], at, code)
    return c, f.job(c, w["contractor"])


# ===== 1. normal: nothing to see ==========================================================================
def test_a_machine_cleared_complaint_with_timely_evidence_is_never_flagged(conn, f, w):
    c, j = resolved_with_job(f, w)
    f.deployment(j, w["machine"], "CLEARED", recorded_at=T0 - H)
    assert scan(conn, T0 + 48 * H) == {"opened": 0, "moved_to_review": 0, "pending_in_grace": 0}
    assert conn.execute("SELECT count(*) AS n FROM v_shadow_candidate").fetchone()["n"] == 0


def test_a_lawful_manual_clearance_is_evidence_too(conn, f):
    """Waiver -> authorised permit -> logged entry -> closed, all before the complaint was resolved."""
    s = f.gate_scenario(yesterday_ist(10, 0))
    conn.execute("SELECT * FROM authorise_entry(%s, %s, %s)", (s["permit"], s["supervisor"], s["at"]))
    conn.execute("INSERT INTO entry_log (permit_id, worker_id, period, recorded_by) VALUES (%s, %s, tstzrange(%s, %s), %s)",
                 (s["permit"], s["e1"], s["at"] + 10 * H / 60, s["at"] + 40 * H / 60, s["supervisor"]))
    conn.execute("UPDATE entry_permit SET status = 'CLOSED' WHERE permit_id = %s", (s["permit"],))
    now = datetime.now(timezone.utc)
    conn.execute("UPDATE complaint SET status = 'RESOLVED', resolved_at = %s, resolution_code = 'CLEARED' WHERE complaint_id = %s",
                 (now, s["complaint"]))
    # SE1 is satisfied by the closed, logged permit. SE2 notices that entrant e2 never logged an entry.
    result = scan(conn, now + 48 * H)
    assert result["opened"] == 1
    assert [a["rule_code"] for a in alerts(conn)] == [SE2]


# ===== 2. genuinely missing =============================================================================
def test_resolved_with_no_evidence_is_pending_inside_the_grace_window_then_an_alert(conn, f, w):
    c, j = resolved_with_job(f, w)
    inv = f.invoice(j)
    assert scan(conn, T0 + 23 * H) == {"opened": 0, "moved_to_review": 0, "pending_in_grace": 1}
    assert alerts(conn) == []

    assert scan(conn, T0 + 25 * H)["opened"] == 1
    (a,) = alerts(conn)
    assert (a["complaint_id"], a["rule_code"], a["status"], a["contractor_id"]) == (c, SE1, "OPEN", w["contractor"])
    assert "no clearance evidence" in a["reason"] and "Jobs: 1." in a["reason"] and a["evidence_deadline"] == T0 + 24 * H
    (h,) = holds(conn, inv)                                                            # BR-35: the invoice is held
    assert (h["reason"], h["alert_id"], h["released_at"]) == ("SHADOW_ENTRY", a["alert_id"], None)
    assert [e["to_status"] for e in conn.execute("SELECT * FROM shadow_entry_alert_event ORDER BY event_id")] == ["OPEN"]


def test_rescanning_is_idempotent_no_duplicate_alerts_or_holds(conn, f, w):
    c, j = resolved_with_job(f, w)
    inv = f.invoice(j)
    first = scan(conn, T0 + 25 * H)
    for hours in (26, 30, 100, 500):
        again = scan(conn, T0 + hours * H)
        assert (again["opened"], again["moved_to_review"]) == (0, 0)
    assert first["opened"] == 1 and len(alerts(conn)) == 1 and len(holds(conn, inv)) == 1
    assert conn.execute("SELECT count(*) AS n FROM shadow_entry_alert_event").fetchone()["n"] == 1


def test_an_invoice_submitted_after_the_alert_is_held_on_arrival(conn, f, w):
    c, j = resolved_with_job(f, w)
    scan(conn, T0 + 25 * H)
    late_invoice = f.invoice(j)
    assert [h["reason"] for h in holds(conn, late_invoice)] == ["SHADOW_ENTRY"]
    with expect("ZE003", "on hold"):
        conn.execute("UPDATE invoice SET status = 'APPROVED', decided_by = %s WHERE invoice_id = %s", (w["engineer"], late_invoice))


def test_a_complaint_resolved_with_no_job_at_all_is_caught(conn, f, w):
    """The proposal's inner join on job would have missed this, the purest shadow entry."""
    c = f.resolved_complaint(w["manhole"], T0)
    assert scan(conn, T0 + 25 * H)["opened"] == 1
    (a,) = alerts(conn)
    assert a["complaint_id"] == c and a["contractor_id"] is None and "Jobs: 0" in a["reason"]


def test_evidence_on_any_job_of_the_complaint_counts(conn, f, w):
    c = f.resolved_complaint(w["manhole"], T0)
    first = f.job(c, w["contractor"])
    f.deployment(first, w["machine"], "FAILED", recorded_at=T0 - 3 * H)
    second = f.job(c, f.contractor())                                                  # retried with another contractor
    f.deployment(second, w["machine"], "CLEARED", recorded_at=T0 - H)
    assert scan(conn, T0 + 48 * H)["opened"] == 0                                      # no false positive on the failed first job


# ===== 3. a record that arrives late ====================================================================
def test_evidence_recorded_inside_the_grace_window_prevents_the_alert(conn, f, w):
    c, j = resolved_with_job(f, w)
    f.deployment(j, w["machine"], "CLEARED", recorded_at=T0 + 10 * H)                  # field tablet synced late, but in time
    assert scan(conn, T0 + 48 * H)["opened"] == 0


def test_late_evidence_never_closes_an_alert_it_sends_it_to_a_human(conn, f, w):
    c, j = resolved_with_job(f, w)
    inv = f.invoice(j)
    scan(conn, T0 + 25 * H)
    f.deployment(j, w["machine"], "CLEARED", recorded_at=T0 + 30 * H)                  # backdated-looking paperwork, after the fact
    result = scan(conn, T0 + 31 * H)
    assert result["moved_to_review"] == 1
    (a,) = alerts(conn)
    assert a["status"] == "EVIDENCE_RECEIVED" and a["reviewed_by"] is None             # NOT closed
    assert [h["released_at"] for h in holds(conn, inv)] == [None]                      # the invoice stays held

    assert scan(conn, T0 + 32 * H)["moved_to_review"] == 0                             # and the scan is idempotent about it

    # a person inspects the log and decides: this was late paperwork for real work -> dismiss
    conn.execute("SELECT * FROM review_shadow_alert(%s, 'DISMISSED', 'Machine log verified against the GPS trace.', %s)",
                 (a["alert_id"], w["engineer"]))
    (a,) = alerts(conn)
    assert (a["status"], a["reviewed_by"]) == ("DISMISSED", w["engineer"]) and a["reviewed_at"] is not None
    (h,) = holds(conn, inv)
    assert h["released_at"] is not None and h["released_by"] == w["engineer"] and "dismissed" in h["release_note"]
    history = conn.execute("SELECT from_status, to_status, actor_id FROM shadow_entry_alert_event ORDER BY event_id").fetchall()
    assert [(e["from_status"], e["to_status"]) for e in history] == [
        (None, "OPEN"), ("OPEN", "EVIDENCE_RECEIVED"), ("EVIDENCE_RECEIVED", "DISMISSED")]
    assert history[-1]["actor_id"] == w["engineer"]


def test_evidence_that_arrives_after_the_deadline_but_before_any_scan_is_still_late(conn, f, w):
    c, j = resolved_with_job(f, w)
    f.deployment(j, w["machine"], "CLEARED", recorded_at=T0 + 30 * H)
    assert scan(conn, T0 + 40 * H)["opened"] == 1
    assert alerts(conn)[0]["status"] == "EVIDENCE_RECEIVED"                            # detection does not depend on scan timing


def test_a_dismissed_alert_is_final_and_never_reopened_by_the_scan(conn, f, w):
    c, j = resolved_with_job(f, w)
    scan(conn, T0 + 25 * H)
    (a,) = alerts(conn)
    conn.execute("SELECT * FROM review_shadow_alert(%s, 'DISMISSED', 'Inspection confirmed the repair by the ULB crew.', %s)",
                 (a["alert_id"], w["engineer"]))
    assert scan(conn, T0 + 500 * H) == {"opened": 0, "moved_to_review": 0, "pending_in_grace": 0}
    assert alerts(conn)[0]["status"] == "DISMISSED"
    with expect("ZE003", "final"):
        conn.execute("SELECT * FROM review_shadow_alert(%s, 'CONFIRMED', 'Changing my mind after the fact here.', %s)",
                     (a["alert_id"], w["engineer"]))


# ===== 4. duplicate and conflicting records ==============================================================
def test_a_machine_that_reported_failure_contradicts_a_cleared_resolution(conn, f, w):
    c, j = resolved_with_job(f, w)
    f.deployment(j, w["machine"], "FAILED", recorded_at=T0 - 2 * H)
    scan(conn, T0 + 25 * H)
    (a,) = alerts(conn)
    assert "0 cleared, 1 failed" in a["reason"]


def test_duplicate_evidence_rows_do_not_duplicate_detection_results(conn, f, w):
    c, j = resolved_with_job(f, w)
    f.deployment(j, w["machine"], "CLEARED", recorded_at=T0 - 2 * H)
    f.deployment(j, w["machine"], "CLEARED", recorded_at=T0 - H)
    assert scan(conn, T0 + 48 * H)["opened"] == 0
    c2, j2 = resolved_with_job(f, w)                                                   # no evidence at all
    scan(conn, T0 + 48 * H)
    scan(conn, T0 + 49 * H)
    assert len(alerts(conn, c2)) == 1
    assert conn.execute("SELECT count(*) AS n FROM v_shadow_candidate WHERE complaint_id = %s", (c2,)).fetchone()["n"] == 1


def test_two_rules_can_flag_the_same_complaint_once_each(conn, f):
    """A permit closed with no entry logged at all: SE1 (no logged permit) and SE2 (no entrant logged)."""
    s = f.gate_scenario(yesterday_ist(10, 0))
    conn.execute("SELECT * FROM authorise_entry(%s, %s, %s)", (s["permit"], s["supervisor"], s["at"]))
    closed_at = s["at"] + 2 * H
    conn.execute("UPDATE entry_permit SET status = 'CLOSED', ended_at = %s WHERE permit_id = %s", (closed_at, s["permit"]))
    conn.execute("UPDATE complaint SET status = 'RESOLVED', raised_at = %s, resolved_at = %s, resolution_code = 'CLEARED' "
                 "WHERE complaint_id = %s", (closed_at - 48 * H, closed_at + H, s["complaint"]))
    result = scan(conn, closed_at + 40 * H)
    assert result["opened"] == 2
    assert sorted(a["rule_code"] for a in alerts(conn)) == [SE1, SE2]
    se2 = next(a for a in alerts(conn) if a["rule_code"] == SE2)
    assert "entrant(s)" in se2["reason"]


# ===== 5. intentionally absent ===========================================================================
@pytest.mark.parametrize("code", ["NO_BLOCKAGE_FOUND", "DUPLICATE_COMPLAINT", "REFERRED_OUT", "WITHDRAWN"])
def test_resolutions_that_need_no_evidence_are_never_flagged(conn, f, w, code):
    f.resolved_complaint(w["manhole"], T0, code)
    assert scan(conn, T0 + 5000 * H) == {"opened": 0, "moved_to_review": 0, "pending_in_grace": 0}


def test_open_and_in_progress_complaints_are_not_in_the_expected_population(conn, f, w):
    f.complaint(w["manhole"])
    f.complaint(w["manhole"], status="IN_PROGRESS")
    assert scan(conn, utc(2030, 1, 1))["opened"] == 0


def test_whether_a_resolution_needs_evidence_is_data_not_code(conn, f, w):
    f.resolved_complaint(w["manhole"], T0, "WITHDRAWN")
    conn.execute("UPDATE resolution_type SET requires_evidence = true WHERE code = 'WITHDRAWN'")
    assert scan(conn, T0 + 25 * H)["opened"] == 1


def test_a_disabled_rule_is_skipped_and_picked_up_when_enabled(conn, f, w):
    resolved_with_job(f, w)
    conn.execute("UPDATE detection_rule SET enabled = false WHERE rule_code = %s", (SE1,))
    assert scan(conn, T0 + 25 * H)["opened"] == 0
    conn.execute("UPDATE detection_rule SET enabled = true WHERE rule_code = %s", (SE1,))
    assert scan(conn, T0 + 25 * H)["opened"] == 1


def test_a_changed_premise_sends_an_open_alert_back_for_human_review(conn, f, w):
    c, j = resolved_with_job(f, w)
    scan(conn, T0 + 25 * H)
    conn.execute("UPDATE complaint SET resolution_code = 'DUPLICATE_COMPLAINT' WHERE complaint_id = %s", (c,))   # reclassified later
    assert scan(conn, T0 + 26 * H)["moved_to_review"] == 1
    assert alerts(conn)[0]["status"] == "EVIDENCE_RECEIVED"


# ===== 6. detected, then resolved by a person ============================================================
def test_confirming_keeps_the_hold_and_counts_against_the_contractor(conn, f, w):
    c, j = resolved_with_job(f, w)
    inv = f.invoice(j)
    scan(conn, T0 + 25 * H)
    (a,) = alerts(conn)
    conn.execute("SELECT * FROM review_shadow_alert(%s, 'CONFIRMED', 'Crew admitted entering without a permit.', %s)",
                 (a["alert_id"], w["engineer"]))
    assert alerts(conn)[0]["status"] == "CONFIRMED"
    assert [h["released_at"] for h in holds(conn, inv)] == [None]
    risk = conn.execute("SELECT confirmed_alerts, open_alerts, risk_score FROM v_contractor_risk WHERE contractor_id = %s",
                        (w["contractor"],)).fetchone()
    assert risk == {"confirmed_alerts": 1, "open_alerts": 0, "risk_score": 3}


def test_only_an_engineer_or_admin_may_decide_and_a_written_note_is_required(conn, f, w):
    resolved_with_job(f, w)
    scan(conn, T0 + 25 * H)
    (a,) = alerts(conn)
    aid = a["alert_id"]
    with expect("ZE006", "ENGINEER or ADMIN"):
        conn.execute("SELECT * FROM review_shadow_alert(%s, 'DISMISSED', 'A supervisor should not decide this.', %s)", (aid, w["supervisor"]))
    with expect("ZE006"):
        conn.execute("SELECT * FROM review_shadow_alert(%s, 'DISMISSED', 'A contractor should not decide this.', %s)",
                     (aid, f.user("CONTRACTOR", contractor_id=w["contractor"])))
    with expect("ZE002", "written note"):
        conn.execute("SELECT * FROM review_shadow_alert(%s, 'DISMISSED', 'ok', %s)", (aid, w["engineer"]))
    with expect("ZE002", "CONFIRMED or DISMISSED"):
        conn.execute("SELECT * FROM review_shadow_alert(%s, 'IGNORED', 'long enough note here', %s)", (aid, w["engineer"]))
    with expect("ZE004"):
        conn.execute("SELECT * FROM review_shadow_alert(987654, 'DISMISSED', 'long enough note here', %s)", (w["engineer"],))
    conn.execute("UPDATE shadow_entry_alert SET status = 'EVIDENCE_RECEIVED' WHERE alert_id = %s", (aid,))   # legal move
    with expect("ZE003", "cannot change from EVIDENCE_RECEIVED to OPEN"):                                    # no way back
        conn.execute("UPDATE shadow_entry_alert SET status = 'OPEN' WHERE alert_id = %s", (aid,))
    with expect("ZE003", "append-only"):
        conn.execute("UPDATE shadow_entry_alert_event SET note = 'tampered'")
    with expect("ZE003", "not allowed"):
        conn.execute("DELETE FROM shadow_entry_alert WHERE alert_id = %s", (aid,))
    assert alerts(conn)[0]["status"] == "EVIDENCE_RECEIVED"


def test_dismissing_an_alert_releases_only_its_own_hold_never_a_fatalitys(conn, f, w):
    """Advisor trap (e): a hold placed by a death must survive the dismissal of an unrelated alert."""
    c, j = resolved_with_job(f, w)
    inv = f.invoice(j)
    scan(conn, T0 + 25 * H)
    (a,) = alerts(conn)
    worker = f.worker(w["contractor"])
    conn.execute("CALL record_incident('FATALITY', %s, %s, %s, 'Collapsed in the chamber', %s, NULL, %s, NULL::bigint)",
                 (T0 + 30 * H, worker, w["manhole"], w["engineer"], j))
    assert sorted(h["reason"] for h in holds(conn, inv)) == ["INCIDENT", "SHADOW_ENTRY"]
    conn.execute("SELECT * FROM review_shadow_alert(%s, 'DISMISSED', 'Alert was a recording gap, not an entry.', %s)",
                 (a["alert_id"], w["engineer"]))
    still = [h for h in holds(conn, inv) if h["released_at"] is None]
    assert [h["reason"] for h in still] == ["INCIDENT"]
    with expect("ZE003", "on hold"):
        conn.execute("UPDATE invoice SET status = 'APPROVED', decided_by = %s WHERE invoice_id = %s", (w["engineer"], inv))
    shadow_hold = next(h for h in holds(conn, inv) if h["reason"] == "SHADOW_ENTRY")
    with expect("ZE003", "already released"):
        conn.execute("SELECT release_invoice_hold(%s, %s, 'Trying to release a released hold.')", (shadow_hold["hold_id"], w["engineer"]))


def test_a_shadow_entry_hold_cannot_be_released_by_hand(conn, f, w):
    c, j = resolved_with_job(f, w)
    inv = f.invoice(j)
    scan(conn, T0 + 25 * H)
    with expect("ZE003", "dismissing its alert"):
        conn.execute("SELECT release_invoice_hold(%s, %s, 'Releasing without reviewing the alert.')", (holds(conn, inv)[0]["hold_id"], w["engineer"]))


# ===== SE2 and the public view ===========================================================================
def _closed_permit_with_entries(conn, f, logged, *, log_recorded_at=None, resolved=True):
    s = f.gate_scenario(yesterday_ist(10, 0))
    conn.execute("SELECT * FROM authorise_entry(%s, %s, %s)", (s["permit"], s["supervisor"], s["at"]))
    for i, who in enumerate(logged):
        entry_id = conn.execute("INSERT INTO entry_log (permit_id, worker_id, period, recorded_by) "
                                "VALUES (%s, %s, tstzrange(%s, %s), %s) RETURNING entry_id",
                                (s["permit"], s[who], s["at"] + (10 + 60 * i) * H / 60,
                                 s["at"] + (40 + 60 * i) * H / 60, s["supervisor"])).fetchone()["entry_id"]
        # Model an imported historical receipt only inside this owner-only test fixture. Live inserts always
        # stamp `recorded_at` at the database clock; a client cannot backdate timely evidence.
        with conn.transaction():
            conn.execute("ALTER TABLE entry_log DISABLE TRIGGER trg_entry_log_guard")
            conn.execute("UPDATE entry_log SET recorded_at = %s WHERE entry_id = %s",
                         (log_recorded_at or s["at"] + H, entry_id))
            conn.execute("ALTER TABLE entry_log ENABLE TRIGGER trg_entry_log_guard")
    s["closed_at"] = s["at"] + 3 * H
    conn.execute("UPDATE entry_permit SET status = 'CLOSED', ended_at = %s WHERE permit_id = %s", (s["closed_at"], s["permit"]))
    if resolved:   # resolved with the permit as evidence, so only SE2 is in play
        conn.execute("UPDATE complaint SET status = 'RESOLVED', raised_at = %s, resolved_at = %s, resolution_code = 'CLEARED' "
                     "WHERE complaint_id = %s", (s["closed_at"] - 48 * H, s["closed_at"] + H, s["complaint"]))
    return s


def test_se2_flags_an_entrant_with_no_entry_log_and_names_them(conn, f):
    s = _closed_permit_with_entries(conn, f, ["e1"])
    scan(conn, s["closed_at"] + 23 * H)
    assert alerts(conn) == []                                                           # still inside the grace window
    scan(conn, s["closed_at"] + 25 * H)
    (a,) = alerts(conn)
    e2 = conn.execute("SELECT namaste_id FROM worker WHERE worker_id = %s", (s["e2"],)).fetchone()["namaste_id"]
    e1 = conn.execute("SELECT namaste_id FROM worker WHERE worker_id = %s", (s["e1"],)).fetchone()["namaste_id"]
    assert a["rule_code"] == SE2 and e2 in a["reason"] and e1 not in a["reason"]


def test_se2_is_silent_when_every_entrant_logged_in_time(conn, f):
    s = _closed_permit_with_entries(conn, f, ["e1", "e2"])
    assert scan(conn, s["closed_at"] + 100 * H)["opened"] == 0


def test_se2_late_log_goes_to_review_not_to_silence(conn, f):
    """The application cannot log an entry on a CLOSED permit (the guard refuses), so late SE2 evidence can only
    come from a DBA backfill. The detector must still send that to review rather than quietly clearing the alert."""
    s = _closed_permit_with_entries(conn, f, ["e1"])
    scan(conn, s["closed_at"] + 25 * H)
    with expect("ZE003", "CLOSED"):
        conn.execute("INSERT INTO entry_log (permit_id, worker_id, period, recorded_by) VALUES (%s, %s, tstzrange(%s, %s), %s)",
                     (s["permit"], s["e2"], s["at"] + 130 * H / 60, s["at"] + 160 * H / 60, s["supervisor"]))
    conn.execute("ALTER TABLE entry_log DISABLE TRIGGER trg_entry_log_guard")            # simulate the backfill
    conn.execute("INSERT INTO entry_log (permit_id, worker_id, period, recorded_by, recorded_at) "
                 "VALUES (%s, %s, tstzrange(%s, %s), %s, %s)",
                 (s["permit"], s["e2"], s["at"] + 130 * H / 60, s["at"] + 160 * H / 60, s["supervisor"], s["closed_at"] + 30 * H))
    conn.execute("ALTER TABLE entry_log ENABLE TRIGGER trg_entry_log_guard")
    assert scan(conn, s["closed_at"] + 31 * H)["moved_to_review"] == 1
    assert alerts(conn)[0]["status"] == "EVIDENCE_RECEIVED"


def test_the_public_view_shows_suspicion_grace_state_and_the_persisted_alert(conn, f, w):
    now = datetime.now(timezone.utc)
    fresh = f.resolved_complaint(w["manhole"], now)                                    # inside its grace window
    stale = f.resolved_complaint(w["manhole"], now - timedelta(days=3))                # past it
    scan(conn, now)
    rows = {r["complaint_id"]: r for r in conn.execute("SELECT * FROM v_suspected_shadow_entry")}
    assert rows[fresh]["past_grace"] is False and rows[fresh]["alert_id"] is None
    assert rows[stale]["past_grace"] is True and rows[stale]["alert_status"] == "OPEN"
    assert rows[stale]["rule_title"] == "Resolved without clearance evidence"
