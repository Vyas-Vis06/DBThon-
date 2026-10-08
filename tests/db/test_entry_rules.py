"""Rules that act after authorisation or around it: freeze, gas-reading integrity, entry admission and exit evidence,
waivers, job guards, audit trail, account scoping. PROJECT_SPEC BR-01..BR-12, BR-22, BR-41."""

from datetime import datetime, timedelta, timezone

import pytest
from psycopg.types.range import Range

from tests.factories import Factory, IST, yesterday_ist
from tests.helpers import expect


@pytest.fixture
def f(conn):
    return Factory(conn)


def authorise(conn, s):
    rows = conn.execute("SELECT * FROM authorise_entry(%s, %s, %s)", (s["permit"], s["supervisor"], s["at"])).fetchall()
    assert all(r["passed"] for r in rows), [r for r in rows if not r["passed"]]


@pytest.fixture
def live(conn, f):
    """An AUTHORISED permit (10:00 IST yesterday, valid 4 h) for historical record tests."""
    s = f.gate_scenario(yesterday_ist(10, 0))
    authorise(conn, s)
    return s


@pytest.fixture
def live_current(conn, f):
    """A current AUTHORISED permit with an all-day synthetic daylight window for live-admission tests."""
    conn.execute("UPDATE rule_parameter SET value = 0 WHERE param_key = 'daylight_start_hour'")
    conn.execute("UPDATE rule_parameter SET value = 24 WHERE param_key = 'daylight_end_hour'")
    s = f.gate_scenario(datetime.now(IST))
    authorise(conn, s)
    return s


def enter(conn, s, who, start_min, end_min):
    """Log an entry [at+start, at+end) for crew member s[who]; end_min=None leaves the entry open."""
    period = Range(s["at"] + timedelta(minutes=start_min), None if end_min is None else s["at"] + timedelta(minutes=end_min), "[)")
    return conn.execute("INSERT INTO entry_log (permit_id, worker_id, period, recorded_by) VALUES (%s, %s, %s, %s) "
                        "RETURNING entry_id", (s["permit"], s[who], period, s["supervisor"])).fetchone()["entry_id"]


# --- BR-09: freeze ----------------------------------------------------------------------------------------
def test_crew_and_gear_are_frozen_once_authorised(conn, f, live):
    late = f.worker(live["contractor"])
    with expect("ZE003", "frozen"):
        f.crew(live["permit"], late, "ENTRANT")
    with expect("ZE003", "frozen"):
        conn.execute("DELETE FROM permit_crew WHERE permit_id = %s AND worker_id = %s", (live["permit"], live["standby"]))
    with expect("ZE003", "frozen"):
        conn.execute("UPDATE permit_crew SET crew_role = 'ENTRANT' WHERE permit_id = %s AND worker_id = %s",
                     (live["permit"], live["standby"]))
    with expect("ZE003", "frozen"):
        conn.execute("DELETE FROM gear_issue WHERE permit_id = %s AND worker_id = %s", (live["permit"], live["e1"]))
    with expect("ZE003", "frozen"):
        conn.execute("INSERT INTO gear_issue (permit_id, worker_id, gear_code, serial_no) VALUES (%s, %s, 'GUMBOOTS', 'X')",
                     (live["permit"], live["e1"]))


def test_a_worker_has_one_role_per_permit_so_a_standby_can_never_also_enter(conn, f):
    s = f.gate_scenario(yesterday_ist())                      # DRAFT: crew may still change, but only once per worker
    with expect("23505"):                                     # PK (permit_id, worker_id)
        f.crew(s["permit"], s["standby"], "ENTRANT")


def test_only_unused_drafts_can_be_deleted_and_they_take_crew_and_gear_with_them(conn, f):
    s = f.gate_scenario(yesterday_ist(), readings={"TOP": None, "MID": None, "BOTTOM": None}, include_new_evidence=False)
    conn.execute("DELETE FROM entry_permit WHERE permit_id = %s", (s["permit"],))          # cascades
    assert conn.execute("SELECT count(*) AS n FROM permit_crew WHERE permit_id = %s", (s["permit"],)).fetchone()["n"] == 0
    s2 = f.gate_scenario(yesterday_ist())                                                   # has readings
    with expect("23503"):
        conn.execute("DELETE FROM entry_permit WHERE permit_id = %s", (s2["permit"],))
    authorise(conn, s2)
    with expect("ZE003", "evidence"):
        conn.execute("DELETE FROM entry_permit WHERE permit_id = %s", (s2["permit"],))


# --- gas readings -----------------------------------------------------------------------------------------
def test_gas_readings_are_append_only(conn, live):
    rid = conn.execute("SELECT min(reading_id) AS r FROM gas_reading").fetchone()["r"]
    with expect("ZE003", "append-only"):
        conn.execute("UPDATE gas_reading SET o2_pct = 20.9 WHERE reading_id = %s", (rid,))
    with expect("ZE003", "append-only"):
        conn.execute("DELETE FROM gas_reading WHERE reading_id = %s", (rid,))


def test_a_reading_from_a_detector_out_of_calibration_that_day_is_refused(conn, f):
    s = f.gate_scenario(yesterday_ist(), readings={"TOP": None})
    day = conn.execute("SELECT local_date(%s) AS d", (s["at"],)).fetchone()["d"]
    lapsed = f.detector(calibration_valid_until=day - timedelta(days=1))
    with expect("ZE002", "calibration expired"):
        f.reading(s["permit"], lapsed, "TOP", s["at"] - timedelta(minutes=5), s["supervisor"])
    on_last_day = f.detector(calibration_valid_until=day)                 # valid THROUGH the stated day
    f.reading(s["permit"], on_last_day, "TOP", s["at"] - timedelta(minutes=5), s["supervisor"])


def test_future_dated_readings_are_retained_but_fail_latest_and_unauthorised_recorders_are_refused(conn, f):
    s = f.gate_scenario(yesterday_ist(), readings={"TOP": None})
    from datetime import datetime, timezone
    future_at = datetime.now(timezone.utc) + timedelta(hours=1)
    reading_id = f.reading(s["permit"], s["detector"], "TOP", future_at, s["supervisor"])
    assert conn.execute("SELECT taken_at FROM gas_reading WHERE reading_id=%s", (reading_id,)).fetchone()["taken_at"] == future_at
    from tests.db.test_entry_gate import authorise, failed
    assert {"GAS_TOP", "GAS_COMPLETE_SOURCE"} <= failed(authorise(conn, s))
    worker_login = f.user("WORKER", worker_id=f.worker(s["contractor"]))
    with expect("ZE006", "sign off"):
        f.reading(s["permit"], s["detector"], "TOP", s["at"] - timedelta(minutes=5), worker_login)


def test_readings_cannot_be_added_to_a_closed_permit(conn, live, f):
    conn.execute("UPDATE entry_permit SET status = 'CLOSED' WHERE permit_id = %s", (live["permit"],))
    with expect("ZE003", "CLOSED permit"):
        f.reading(live["permit"], live["detector"], "TOP", live["at"], live["supervisor"])


# --- entry log --------------------------------------------------------------------------------------------
def test_a_normal_entry_is_recorded(conn, live):
    assert enter(conn, live, "e1", 10, 60)


def test_historical_duration_overrun_is_kept_with_immutable_evidence(conn, live):
    eid_90 = enter(conn, live, "e1", 10, 100)                                    # exactly 90 min
    eid_95 = enter(conn, live, "e2", 110, 205)                                   # the 95-minute demonstration case
    event = conn.execute("SELECT reason_code, detail FROM permit_safety_event WHERE entry_id = %s AND reason_code = 'DURATION_OVERRUN'",
                         (eid_95,)).fetchone()
    assert event["detail"]["reported_minutes"] == 95 and event["detail"]["limit_minutes"] == 90
    eid_91 = enter(conn, live, "e1", 210, 301)
    assert conn.execute("SELECT count(*) AS n FROM permit_safety_event WHERE entry_id IN (%s, %s)", (eid_95, eid_91)).fetchone()["n"] == 5
    assert conn.execute("SELECT count(*) AS n FROM permit_safety_event WHERE entry_id = %s AND reason_code = 'DURATION_OVERRUN'",
                        (eid_90,)).fetchone()["n"] == 0
    with expect("ZE003", "append-only"):
        conn.execute("UPDATE permit_safety_event SET reason_code = 'OK' WHERE entry_id = %s", (eid_95,))


def test_one_worker_cannot_be_in_two_entries_at_once_but_others_can(conn, live):
    enter(conn, live, "e1", 10, 60)
    with expect("23P01"):                                                         # exclusion constraint
        enter(conn, live, "e1", 30, 80)
    assert enter(conn, live, "e1", 60, 100)                                       # touching, not overlapping
    assert enter(conn, live, "e2", 10, 60)                                        # different worker, same time


def test_an_open_entry_blocks_overlaps_and_its_long_exit_is_retained(conn, live_current):
    live = live_current
    eid = enter(conn, live, "e1", 0, None)
    with expect("23P01"):
        enter(conn, live, "e1", 2, None)
    lower = live["at"]
    conn.execute("UPDATE entry_log SET period = tstzrange(%s, %s) WHERE entry_id = %s", (lower, lower + timedelta(minutes=2), eid))
    with expect("ZE003", "already closed"):
        conn.execute("UPDATE entry_log SET period = tstzrange(%s, %s) WHERE entry_id = %s", (lower, lower + timedelta(minutes=30), eid))
    eid2 = enter(conn, live, "e2", 0, None)
    with expect("ZE003", "exit time"):                                            # moving the start is not allowed
        conn.execute("UPDATE entry_log SET period = tstzrange(%s, %s) WHERE entry_id = %s",
                     (lower - timedelta(minutes=5), lower + timedelta(minutes=30), eid2))
    with expect("ZE002", "five minutes ahead"):
        conn.execute("UPDATE entry_log SET period = tstzrange(%s, %s, '[)') WHERE entry_id = %s",
                     (lower, lower + timedelta(minutes=95), eid2))
    conn.execute("UPDATE entry_log SET period = tstzrange(%s, %s, '[)') WHERE entry_id = %s",
                 (lower, lower + timedelta(minutes=2), eid2))
    event = conn.execute("SELECT reason_code FROM permit_safety_event WHERE entry_id = %s AND reason_code = 'EXIT_TIME_AHEAD_OF_RECEIPT'",
                         (eid2,)).fetchone()
    assert event["reason_code"] == "EXIT_TIME_AHEAD_OF_RECEIPT"


def test_only_entrants_may_enter_and_historical_window_overruns_are_preserved(conn, live):
    with expect("ZE002", "ENTRANT"):
        enter(conn, live, "standby", 10, 40)
    before = enter(conn, live, "e1", -20, 10)                                     # reported before authorisation
    after = enter(conn, live, "e2", 235, 245)                                     # exit after valid_until (4 h)
    assert enter(conn, live, "e1", 200, 230)                                      # inside validity window
    assert conn.execute("SELECT count(*) AS n FROM permit_safety_event WHERE reason_code = 'PERMIT_WINDOW_OVERRUN' AND entry_id IN (%s, %s)",
                        (before, after)).fetchone()["n"] == 2


def test_backdated_open_entry_cannot_bypass_current_server_clock_admission(conn, live_current):
    with expect("ZE002", "server clock"):
        enter(conn, live_current, "e1", -1440, None)


def test_adverse_serial_asset_change_commits_stop_and_preserves_open_entry_until_truthful_exit(conn, live_current):
    s=live_current
    entry_id=enter(conn,s,"e1",0,None)
    old_revision=conn.execute("SELECT evidence_revision FROM entry_permit WHERE permit_id=%s",(s["permit"],)).fetchone()["evidence_revision"]
    conn.execute("UPDATE gear_asset SET status='OUT_OF_SERVICE' WHERE gear_asset_id=%s",(s["site_asset"],))
    permit=conn.execute("SELECT status,evidence_revision FROM entry_permit WHERE permit_id=%s",(s["permit"],)).fetchone()
    assert permit["status"]=="ABORTED" and permit["evidence_revision"]>old_revision
    assert conn.execute("SELECT count(*) FROM permit_safety_event WHERE permit_id=%s AND reason_code='CURRENT_CLAUSE_FAILED'",
                        (s["permit"],)).fetchone()["count"]>=1
    assert conn.execute("SELECT upper_inf(period) AS is_open FROM entry_log WHERE entry_id=%s",(entry_id,)).fetchone()["is_open"] is True
    assert conn.execute("SELECT count(*) AS n FROM permit_resource_reservation WHERE permit_id=%s AND released_at IS NULL",
                        (s["permit"],)).fetchone()["n"]>0
    with expect("ZE003"):
        enter(conn,s,"e2",0,None)
    conn.execute("UPDATE entry_log SET period=tstzrange(lower(period),clock_timestamp(),'[)') WHERE entry_id=%s",(entry_id,))
    assert conn.execute("SELECT exit_recorded_at IS NOT NULL AS exited FROM entry_log WHERE entry_id=%s",(entry_id,)).fetchone()["exited"] is True
    assert conn.execute("SELECT count(*) AS n FROM permit_resource_reservation WHERE permit_id=%s AND released_at IS NULL",
                        (s["permit"],)).fetchone()["n"]==0


def test_safe_asset_revision_reissues_receipt_and_rejects_the_old_receipt_id(conn, live_current):
    s=live_current
    old=conn.execute("SELECT receipt_id FROM permit_decision_receipt WHERE permit_id=%s AND decision='AUTHORISED' "
                     "ORDER BY receipt_id DESC LIMIT 1",(s["permit"],)).fetchone()["receipt_id"]
    conn.execute("UPDATE gear_asset SET inspection_valid_until='2098-12-31' WHERE gear_asset_id=%s",(s["site_asset"],))
    current=conn.execute("SELECT receipt_id,evidence_revision FROM permit_decision_receipt WHERE permit_id=%s AND decision='AUTHORISED' "
                         "ORDER BY receipt_id DESC LIMIT 1",(s["permit"],)).fetchone()
    assert current["receipt_id"]!=old
    assert current["evidence_revision"]==conn.execute("SELECT evidence_revision FROM entry_permit WHERE permit_id=%s",
                                                       (s["permit"],)).fetchone()["evidence_revision"]
    period=Range(datetime.now(IST),None,"[)")
    with expect("ZE001","current decision receipt"):
        conn.execute("INSERT INTO entry_log(permit_id,worker_id,period,recorded_by,receipt_id) VALUES(%s,%s,%s,%s,%s)",
                     (s["permit"],s["e1"],period,s["supervisor"],old))
    entry=conn.execute("INSERT INTO entry_log(permit_id,worker_id,period,recorded_by,receipt_id) VALUES(%s,%s,%s,%s,%s) RETURNING entry_id",
                       (s["permit"],s["e1"],period,s["supervisor"],current["receipt_id"])).fetchone()
    assert entry["entry_id"]


def test_adverse_gas_reading_commits_stop_and_retains_open_entry(conn, f, live_current):
    s=live_current
    entry_id=enter(conn,s,"e1",0,None)
    old_receipt=conn.execute("SELECT receipt_id FROM permit_decision_receipt WHERE permit_id=%s AND decision='AUTHORISED' "
                             "ORDER BY receipt_id DESC LIMIT 1",(s["permit"],)).fetchone()["receipt_id"]
    # A recent real adverse observation must commit together with the stop; no trigger-order
    # failure may roll either the reading or the terminal safety state back.
    reading_id=f.reading(s["permit"],s["detector"],"TOP",datetime.now(timezone.utc)-timedelta(seconds=1),
                         s["supervisor"],o2=15.0)
    assert conn.execute("SELECT o2_pct FROM gas_reading WHERE reading_id=%s",(reading_id,)).fetchone()["o2_pct"]==15.0
    permit=conn.execute("SELECT status,evidence_revision FROM entry_permit WHERE permit_id=%s",(s["permit"],)).fetchone()
    assert permit["status"]=="ABORTED"
    assert conn.execute("SELECT count(*) AS n FROM permit_safety_event WHERE permit_id=%s AND reason_code='CURRENT_CLAUSE_FAILED'",
                        (s["permit"],)).fetchone()["n"]>=1
    assert conn.execute("SELECT upper_inf(period) AS is_open FROM entry_log WHERE entry_id=%s",(entry_id,)).fetchone()["is_open"] is True
    assert conn.execute("SELECT count(*) AS n FROM permit_decision_receipt WHERE receipt_id=%s",(old_receipt,)).fetchone()["n"]==1
    with expect("ZE003"):
        enter(conn,s,"e2",0,None)
    conn.execute("UPDATE entry_log SET period=tstzrange(lower(period),clock_timestamp(),'[)') WHERE entry_id=%s",(entry_id,))
    assert conn.execute("SELECT exit_recorded_at IS NOT NULL AS exited FROM entry_log WHERE entry_id=%s",
                        (entry_id,)).fetchone()["exited"] is True


def test_a_full_ninety_minute_stretch_requires_the_configured_thirty_minute_rest(conn, live_current):
    live = live_current
    start, end = live["at"] - timedelta(minutes=120), live["at"] - timedelta(minutes=30)
    conn.execute("INSERT INTO entry_log (permit_id, worker_id, period, recorded_by) "
                 "VALUES (%s, %s, tstzrange(%s, %s, '[)'), %s)",
                 (live["permit"], live["e1"], start, end, live["supervisor"]))
    receipt = conn.execute("SELECT exit_recorded_at FROM entry_log WHERE permit_id = %s AND worker_id = %s",
                           (live["permit"], live["e1"])).fetchone()["exit_recorded_at"]
    assert receipt is not None
    with expect("ZE002", "must rest for 30 minutes"):
        enter(conn, live, "e1", 0, None)


def test_entries_need_an_authorised_permit(conn, f):
    s = f.gate_scenario(yesterday_ist())                                          # still DRAFT
    with expect("ZE003", "AUTHORISED permit"):
        enter(conn, s, "e1", 10, 40)


def test_historical_daylight_overruns_are_kept_as_evidence(conn, f):
    s = f.gate_scenario(yesterday_ist(17, 30))                                    # authorised 17:30, valid to 21:30
    authorise(conn, s)
    after_dusk = enter(conn, s, "e1", 60, 100)                                    # 18:30 - 19:10 is night
    crosses_dusk = enter(conn, s, "e2", 15, 55)                                   # starts 17:45, ends 18:25: crosses dusk
    exactly_at_limit = enter(conn, s, "e1", 0, 30)                               # 17:30 - 18:00 ends exactly at the limit
    assert conn.execute("SELECT count(*) AS n FROM permit_safety_event WHERE reason_code = 'DAYLIGHT_OVERRUN' AND entry_id IN (%s, %s)",
                        (after_dusk, crosses_dusk)).fetchone()["n"] == 2
    assert conn.execute("SELECT count(*) AS n FROM permit_safety_event WHERE entry_id = %s", (exactly_at_limit,)).fetchone()["n"] == 0


def test_daylight_hours_are_law_as_data_and_the_change_is_audited(conn, f):
    s = f.gate_scenario(yesterday_ist(17, 30))
    authorise(conn, s)
    eid = enter(conn, s, "e1", 60, 100)
    assert conn.execute("SELECT count(*) AS n FROM permit_safety_event WHERE entry_id = %s AND reason_code = 'DAYLIGHT_OVERRUN'", (eid,)).fetchone()["n"] == 1
    conn.execute("UPDATE rule_parameter SET value = 24 WHERE param_key = 'daylight_end_hour'")
    next_id = enter(conn, s, "e1", 110, 150)
    assert conn.execute("SELECT count(*) AS n FROM permit_safety_event WHERE entry_id = %s AND reason_code = 'DAYLIGHT_OVERRUN'", (next_id,)).fetchone()["n"] == 0
    row = conn.execute("SELECT old_data, new_data FROM audit_log WHERE table_name = 'rule_parameter' AND action = 'UPDATE' "
                        "AND new_data ->> 'param_key' = 'daylight_end_hour' ORDER BY log_id DESC LIMIT 1").fetchone()
    assert float(row["old_data"]["value"]) == 18 and float(row["new_data"]["value"]) == 24


def test_entries_cannot_be_deleted(conn, live):
    eid = enter(conn, live, "e1", 10, 40)
    with expect("ZE003", "no_delete|append-only|not allowed"):
        conn.execute("DELETE FROM entry_log WHERE entry_id = %s", (eid,))


def test_a_permit_cannot_close_while_someone_is_inside(conn, live_current):
    live = live_current
    eid = enter(conn, live, "e1", 0, None)
    with expect("ZE003", "still inside"):
        conn.execute("UPDATE entry_permit SET status = 'CLOSED' WHERE permit_id = %s", (live["permit"],))
    lower = live["at"]
    conn.execute("UPDATE entry_log SET period = tstzrange(%s, %s) WHERE entry_id = %s", (lower, lower + timedelta(minutes=3), eid))
    conn.execute("UPDATE entry_permit SET status = 'CLOSED' WHERE permit_id = %s", (live["permit"],))
    p = conn.execute("SELECT status, ended_at FROM entry_permit WHERE permit_id = %s", (live["permit"],)).fetchone()
    assert p["status"] == "CLOSED" and p["ended_at"] is not None
    with expect("ZE003", "CLOSED"):
        enter(conn, live, "e2", 70, 90)


def test_stop_work_aborts_an_authorised_permit_and_exit_remains_recordable(conn, live_current):
    live = live_current
    eid = enter(conn, live, "e1", 0, None)
    conn.execute("UPDATE entry_permit SET status = 'ABORTED', end_reason = 'Worker refused entry' WHERE permit_id = %s", (live["permit"],))
    end = live["at"] + timedelta(minutes=3)
    conn.execute("UPDATE entry_log SET period = tstzrange(%s, %s, '[)') WHERE entry_id = %s", (live["at"], end, eid))
    p = conn.execute("SELECT status, end_reason FROM entry_permit WHERE permit_id = %s", (live["permit"],)).fetchone()
    entry = conn.execute("SELECT upper(period) AS exited_at, exit_recorded_at FROM entry_log WHERE entry_id = %s", (eid,)).fetchone()
    assert p == {"status": "ABORTED", "end_reason": "Worker refused entry"}
    assert entry["exited_at"] == end and entry["exit_recorded_at"] is not None
    assert conn.execute("SELECT count(*) AS n FROM permit_safety_event WHERE entry_id = %s AND reason_code = 'EXIT_AFTER_PERMIT_STOP'",
                        (eid,)).fetchone()["n"] == 1


@pytest.mark.parametrize("final", ["CLOSED", "ABORTED", "CANCELLED"])
def test_a_finished_permit_is_evidence_and_cannot_be_rewritten(conn, f, final):
    """Regression: an ABORTED permit used to accept 'ABORTED' again and overwrite the original stop-work reason."""
    s = f.gate_scenario(yesterday_ist(10, 0))
    if final != "CANCELLED":
        authorise(conn, s)
    conn.execute("UPDATE entry_permit SET status = %s, end_reason = 'The original recorded reason' WHERE permit_id = %s", (final, s["permit"]))
    with expect("ZE003", "cannot be altered"):
        conn.execute("UPDATE entry_permit SET status = %s, end_reason = 'Rewritten after the fact' WHERE permit_id = %s", (final, s["permit"]))
    with expect("ZE003", "cannot be altered"):
        conn.execute("UPDATE entry_permit SET end_reason = 'Rewritten after the fact' WHERE permit_id = %s", (s["permit"],))
    assert conn.execute("SELECT end_reason FROM entry_permit WHERE permit_id = %s", (s["permit"],)).fetchone()["end_reason"] == "The original recorded reason"


# --- waivers and jobs -------------------------------------------------------------------------------------
@pytest.fixture
def small(conn, f):
    s = {"ulb": f.ulb(), "contractor": f.contractor(), "engineer": f.user("ENGINEER"), "supervisor": f.user("SUPERVISOR")}
    s["manhole"] = f.manhole(s["ulb"])
    s["complaint"] = f.complaint(s["manhole"])
    s["job"] = f.job(s["complaint"], s["contractor"])
    s["machine"] = f.machine(s["ulb"])
    return s


def test_only_an_engineer_may_approve_a_waiver(f, small):
    with expect("ZE006", "Responsible Sanitation Authority"):
        f.waiver(small["job"], small["supervisor"])


def test_machine_failed_needs_a_failed_deployment_and_a_cleared_one_does_not_count(f, conn, small):
    with expect("ZE002", "FAILED machine deployment"):
        f.waiver(small["job"], small["engineer"], reason_code="MACHINE_FAILED")
    f.deployment(small["job"], small["machine"], "CLEARED")
    with expect("ZE002", "FAILED machine deployment"):
        f.waiver(small["job"], small["engineer"], reason_code="MACHINE_FAILED")
    f.deployment(small["job"], small["machine"], "FAILED", started_at=yesterday_ist())
    f.waiver(small["job"], small["engineer"], reason_code="MACHINE_FAILED")
    assert conn.execute("SELECT method FROM job WHERE job_id = %s", (small["job"],)).fetchone()["method"] == "MANUAL_EXCEPTION"


def test_one_waiver_per_job_and_waivers_are_immutable(f, conn, small):
    wid = f.waiver(small["job"], small["engineer"])
    with expect("23505"):
        f.waiver(small["job"], small["engineer"])
    with expect("ZE003", "append-only"):
        conn.execute("UPDATE mechanisation_waiver SET justification = repeat('x', 60) WHERE waiver_id = %s", (wid,))
    with expect("ZE003", "append-only"):
        conn.execute("DELETE FROM mechanisation_waiver WHERE waiver_id = %s", (wid,))


def test_a_job_becomes_manual_only_through_a_waiver_and_never_goes_back(f, conn, small):
    with expect("ZE003", "only through a written waiver"):
        conn.execute("UPDATE job SET method = 'MANUAL_EXCEPTION' WHERE job_id = %s", (small["job"],))
    f.waiver(small["job"], small["engineer"])
    with expect("ZE003", "cannot revert"):
        conn.execute("UPDATE job SET method = 'MECHANISED' WHERE job_id = %s", (small["job"],))
    with expect("ZE003", "starts MECHANISED"):
        f.job(small["complaint"], small["contractor"], method="MANUAL_EXCEPTION")


@pytest.mark.parametrize("sql,match", [
    ("UPDATE contractor SET status = 'BLACKLISTED' WHERE contractor_id = %s", "BLACKLISTED"),
    ("UPDATE contractor SET status = 'SUSPENDED' WHERE contractor_id = %s", "SUSPENDED"),
    ("UPDATE contractor SET licence_valid_until = '2020-01-01' WHERE contractor_id = %s", "licence expired"),
])
def test_contractors_who_are_not_in_good_standing_get_no_new_jobs(f, conn, small, sql, match):
    conn.execute(sql, (small["contractor"],))
    with expect("ZE003", match):
        f.job(small["complaint"], small["contractor"])


# --- audit trail and accounts -----------------------------------------------------------------------------
def test_authorisation_is_audited_with_the_actor(conn, f):
    s = f.gate_scenario(yesterday_ist())
    conn.execute("SELECT set_config('app.user_id', %s, false)", (str(s["supervisor"]),))      # what the API does per request
    authorise(conn, s)
    row = conn.execute("SELECT actor_user_id, new_data ->> 'status' AS status FROM audit_log "
                       "WHERE table_name = 'entry_permit' AND action = 'UPDATE' ORDER BY log_id DESC LIMIT 1").fetchone()
    assert row == {"actor_user_id": s["supervisor"], "status": "AUTHORISED"}


def test_the_audit_log_is_append_only_even_for_the_owner(conn, f):
    f.ulb()
    f.contractor()
    assert conn.execute("SELECT count(*) AS n FROM audit_log").fetchone()["n"] >= 1
    with expect("ZE003", "append-only"):
        conn.execute("UPDATE audit_log SET row_pk = 'forged'")
    with expect("ZE003", "append-only"):
        conn.execute("DELETE FROM audit_log")


def test_password_hashes_never_reach_the_audit_log_but_a_change_is_visible(conn, f):
    uid = f.user("ADMIN", password_hash="$2b$04$originalhashoriginalhashoriginalhashoriginalhashorigina")
    conn.execute("UPDATE app_user SET failed_logins = 3 WHERE user_id = %s", (uid,))             # not an audit event
    conn.execute("UPDATE app_user SET password_hash = '$2b$04$brandnewhashbrandnewhashbrandnewhashbrandnewhashbrandne' "
                 "WHERE user_id = %s", (uid,))
    rows = conn.execute("SELECT action, old_data, new_data FROM audit_log WHERE table_name = 'app_user' ORDER BY log_id").fetchall()
    assert [r["action"] for r in rows] == ["INSERT", "UPDATE"]
    dump = str(rows)
    assert "originalhash" not in dump and "brandnewhash" not in dump
    assert rows[1]["new_data"]["password_hash"] == "[changed]"


@pytest.mark.parametrize("role,kw,ok", [
    ("CONTRACTOR", {}, False), ("CONTRACTOR", {"contractor": True}, True),
    ("WORKER", {}, False), ("WORKER", {"worker": True}, True),
    ("ADMIN", {"contractor": True}, False), ("AUDITOR", {"worker": True}, False), ("ADMIN", {}, True),
])
def test_user_scope_links_must_match_the_role(f, role, kw, ok):
    contractor = f.contractor()
    links = {}
    if kw.get("contractor"):
        links["contractor_id"] = contractor
    if kw.get("worker"):
        links["worker_id"] = f.worker(contractor)
    if ok:
        assert f.user(role, **links)
    else:
        with expect("ZE002"):
            f.user(role, **links)
