"""Rules that act after authorisation or around it: freeze, gas-reading integrity, entry log (daylight, 90 minutes,
overlap), waivers, job guards, audit trail, account scoping. PROJECT_SPEC BR-01..BR-12, BR-22, BR-41."""

from datetime import timedelta

import pytest
from psycopg.types.range import Range

from tests.factories import Factory, yesterday_ist
from tests.helpers import expect


@pytest.fixture
def f(conn):
    return Factory(conn)


def authorise(conn, s):
    rows = conn.execute("SELECT * FROM authorise_entry(%s, %s, %s)", (s["permit"], s["supervisor"], s["at"])).fetchall()
    assert all(r["passed"] for r in rows), [r for r in rows if not r["passed"]]


@pytest.fixture
def live(conn, f):
    """An AUTHORISED permit (10:00 IST yesterday, valid 4 h) with two entrants."""
    s = f.gate_scenario(yesterday_ist(10, 0))
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
    s = f.gate_scenario(yesterday_ist(), readings={"TOP": None, "MID": None, "BOTTOM": None})
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


def test_future_dated_readings_and_unauthorised_recorders_are_refused(conn, f):
    s = f.gate_scenario(yesterday_ist(), readings={"TOP": None})
    from datetime import datetime, timezone
    with expect("ZE002", "future"):
        f.reading(s["permit"], s["detector"], "TOP", datetime.now(timezone.utc) + timedelta(hours=1), s["supervisor"])
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


def test_ninety_minutes_is_the_longest_entry_and_ninety_five_is_refused_by_the_trigger(conn, live):
    assert enter(conn, live, "e1", 10, 100)                                      # exactly 90 min
    with expect("ZE002", r"(?s)95 minutes.*90 minute"):                           # the demo case
        enter(conn, live, "e2", 10, 105)
    with expect("ZE002", "exceeds"):
        enter(conn, live, "e2", 10, 101)


def test_one_worker_cannot_be_in_two_entries_at_once_but_others_can(conn, live):
    enter(conn, live, "e1", 10, 60)
    with expect("23P01"):                                                         # exclusion constraint
        enter(conn, live, "e1", 30, 80)
    assert enter(conn, live, "e1", 60, 100)                                       # touching, not overlapping
    assert enter(conn, live, "e2", 10, 60)                                        # different worker, same time


def test_an_open_entry_blocks_overlaps_and_only_its_exit_can_be_recorded(conn, live):
    eid = enter(conn, live, "e1", 10, None)
    with expect("23P01"):
        enter(conn, live, "e1", 120, 150)
    lower = live["at"] + timedelta(minutes=10)
    conn.execute("UPDATE entry_log SET period = tstzrange(%s, %s) WHERE entry_id = %s", (lower, lower + timedelta(minutes=45), eid))
    with expect("ZE003", "already closed"):
        conn.execute("UPDATE entry_log SET period = tstzrange(%s, %s) WHERE entry_id = %s", (lower, lower + timedelta(minutes=30), eid))
    eid2 = enter(conn, live, "e2", 10, None)
    with expect("ZE003", "exit time"):                                            # moving the start is not allowed
        conn.execute("UPDATE entry_log SET period = tstzrange(%s, %s) WHERE entry_id = %s",
                     (lower - timedelta(minutes=5), lower + timedelta(minutes=30), eid2))
    with expect("ZE002", "exceeds"):                                              # the exit cannot certify a 95 min stay
        conn.execute("UPDATE entry_log SET period = tstzrange(%s, %s) WHERE entry_id = %s", (lower, lower + timedelta(minutes=95), eid2))


def test_only_entrants_may_enter_and_only_inside_the_permit_window(conn, live):
    with expect("ZE002", "ENTRANT"):
        enter(conn, live, "standby", 10, 40)
    with expect("ZE002", "validity window"):
        enter(conn, live, "e1", -20, 10)                                          # before authorisation
    with expect("ZE002", "validity window"):
        enter(conn, live, "e1", 235, 245)                                         # past valid_until (4 h)
    assert enter(conn, live, "e1", 200, 240)                                      # ends exactly at valid_until


def test_entries_need_an_authorised_permit(conn, f):
    s = f.gate_scenario(yesterday_ist())                                          # still DRAFT
    with expect("ZE003", "AUTHORISED permit"):
        enter(conn, s, "e1", 10, 40)


def test_entries_are_daylight_only_and_both_ends_count(conn, f):
    s = f.gate_scenario(yesterday_ist(17, 30))                                    # authorised 17:30, valid to 21:30
    authorise(conn, s)
    with expect("ZE002", "daylight"):
        enter(conn, s, "e1", 60, 100)                                             # 18:30 - 19:10 is night
    with expect("ZE002", "daylight"):
        enter(conn, s, "e1", 15, 55)                                              # starts 17:45, ends 18:25: crosses dusk
    assert enter(conn, s, "e1", 0, 30)                                            # 17:30 - 18:00 ends exactly at the limit


def test_daylight_hours_are_law_as_data_and_the_change_is_audited(conn, f):
    s = f.gate_scenario(yesterday_ist(17, 30))
    authorise(conn, s)
    with expect("ZE002", "daylight"):
        enter(conn, s, "e1", 60, 100)
    conn.execute("UPDATE rule_parameter SET value = 24 WHERE param_key = 'daylight_end_hour'")
    assert enter(conn, s, "e1", 60, 100)
    row = conn.execute("SELECT old_data, new_data FROM audit_log WHERE table_name = 'rule_parameter' AND action = 'UPDATE'").fetchone()
    assert float(row["old_data"]["value"]) == 18 and float(row["new_data"]["value"]) == 24


def test_entries_cannot_be_deleted(conn, live):
    eid = enter(conn, live, "e1", 10, 40)
    with expect("ZE003", "no_delete|append-only|not allowed"):
        conn.execute("DELETE FROM entry_log WHERE entry_id = %s", (eid,))


def test_a_permit_cannot_close_while_someone_is_inside(conn, live):
    eid = enter(conn, live, "e1", 10, None)
    with expect("ZE003", "still inside"):
        conn.execute("UPDATE entry_permit SET status = 'CLOSED' WHERE permit_id = %s", (live["permit"],))
    lower = live["at"] + timedelta(minutes=10)
    conn.execute("UPDATE entry_log SET period = tstzrange(%s, %s) WHERE entry_id = %s", (lower, lower + timedelta(minutes=50), eid))
    conn.execute("UPDATE entry_permit SET status = 'CLOSED' WHERE permit_id = %s", (live["permit"],))
    p = conn.execute("SELECT status, ended_at FROM entry_permit WHERE permit_id = %s", (live["permit"],)).fetchone()
    assert p["status"] == "CLOSED" and p["ended_at"] is not None
    with expect("ZE003", "CLOSED"):
        enter(conn, live, "e2", 70, 90)


def test_stop_work_aborts_an_authorised_permit_even_with_a_worker_inside(conn, live):
    enter(conn, live, "e1", 10, None)
    conn.execute("UPDATE entry_permit SET status = 'ABORTED', end_reason = 'Worker refused entry' WHERE permit_id = %s", (live["permit"],))
    assert conn.execute("SELECT status FROM entry_permit WHERE permit_id = %s", (live["permit"],)).fetchone()["status"] == "ABORTED"


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
