"""The zero-entry gate: every legal clause has a pass and a fail case, denial is explainable, and no client
(not even a raw UPDATE or INSERT) can reach AUTHORISED without the proof. PROJECT_SPEC BR-01 .. BR-08."""

from datetime import timedelta

import pytest

from tests.factories import Factory, ist, yesterday_ist
from tests.helpers import expect

ALL_CLAUSES = {"MECH_WAIVER", "CONTRACTOR_OK", "CREW_ENTRANT", "CREW_SUPERVISOR", "CREW_STANDBY", "CREW_SIZE",
               "CREW_FIT", "GEAR_ALL", "GAS_TOP", "GAS_MID", "GAS_BOTTOM"}


@pytest.fixture
def f(conn):
    return Factory(conn)


def authorise(conn, s, actor=None):
    return conn.execute("SELECT * FROM authorise_entry(%s, %s, %s)",
                        (s["permit"], actor or s["supervisor"], s["at"])).fetchall()


def failed(rows):
    return {r["clause_code"] for r in rows if not r["passed"]}


def status(conn, s):
    return conn.execute("SELECT status FROM entry_permit WHERE permit_id = %s", (s["permit"],)).fetchone()["status"]


# ----------------------------------------------------------------------------------------------------------
def test_a_fully_compliant_permit_is_authorised(conn, f):
    s = f.gate_scenario(yesterday_ist())
    rows = authorise(conn, s)
    assert {r["clause_code"] for r in rows} == ALL_CLAUSES
    assert failed(rows) == set()
    assert {r["permit_status"] for r in rows} == {"AUTHORISED"}
    p = conn.execute("SELECT * FROM entry_permit WHERE permit_id = %s", (s["permit"],)).fetchone()
    assert p["status"] == "AUTHORISED" and p["authorised_by"] == s["supervisor"]
    assert p["authorised_at"] == s["at"]
    assert p["valid_until"] == s["at"] + timedelta(minutes=240)       # permit_valid_minutes (assumption A-02)


def test_checklist_rows_carry_title_legal_reference_and_detail_in_order(conn, f):
    rows = authorise(conn, f.gate_scenario(yesterday_ist()))
    assert len(rows) == 11
    assert all(r["title"] and r["legal_ref"] and r["detail"] for r in rows)
    assert [r["clause_code"] for r in rows][:2] == ["MECH_WAIVER", "CONTRACTOR_OK"]
    assert [r["clause_code"] for r in rows][-3:] == ["GAS_TOP", "GAS_MID", "GAS_BOTTOM"]


# --- one failing clause at a time (relational division, anti-joins, rule parameters) --------------------
def _delete_crew(role):
    return lambda c, s: c.execute("DELETE FROM permit_crew WHERE permit_id = %s AND crew_role = %s", (s["permit"], role))


def _set(sql, *keys):
    return lambda c, s: c.execute(sql, tuple(s[k] for k in keys))


CLAUSE_CASES = {
    "no_standby":        (_delete_crew("STANDBY"),    {"CREW_STANDBY"},                "0 standby"),
    "no_supervisor":     (_delete_crew("SUPERVISOR"), {"CREW_SUPERVISOR"},             "0 supervisor"),
    "no_entrants":       (_delete_crew("ENTRANT"),    {"CREW_ENTRANT", "CREW_SIZE"},   "0 entrant"),
    "crew_below_minimum": (lambda c, s: c.execute("UPDATE rule_parameter SET value = 5 WHERE param_key = 'min_crew_size'"),
                           {"CREW_SIZE"}, "4 of the required 5"),
    "medical_expired":   (_set("UPDATE worker SET medical_fit_until = '2020-01-01' WHERE worker_id = %s", "e2"),
                          {"CREW_FIT"}, "medical fitness expired"),
    "training_expired":  (_set("UPDATE worker SET trained_until = '2020-01-01' WHERE worker_id = %s", "standby"),
                          {"CREW_FIT"}, "training expired"),
    "worker_inactive":   (_set("UPDATE worker SET is_active = false WHERE worker_id = %s", "sup_worker"),
                          {"CREW_FIT"}, "not active"),
    "contractor_blacklisted": (_set("UPDATE contractor SET status = 'BLACKLISTED' WHERE contractor_id = %s", "contractor"),
                               {"CONTRACTOR_OK"}, "BLACKLISTED"),
    "contractor_suspended": (_set("UPDATE contractor SET status = 'SUSPENDED' WHERE contractor_id = %s", "contractor"),
                             {"CONTRACTOR_OK"}, "SUSPENDED"),
    "licence_expired":   (_set("UPDATE contractor SET licence_valid_until = '2020-01-01' WHERE contractor_id = %s", "contractor"),
                          {"CONTRACTOR_OK"}, "licence expired"),
    "entrant_missing_one_item": (_set("DELETE FROM gear_issue WHERE worker_id = %s AND gear_code = 'SAFETY_HARNESS'", "e2"),
                                 {"GEAR_ALL"}, "Safety harness with lifeline"),
    "no_statutory_gear_defined": (lambda c, s: c.execute("UPDATE gear_item SET statutory = false"),
                                  {"GEAR_ALL"}, "No statutory gear item is defined"),
}


@pytest.mark.parametrize("name", CLAUSE_CASES)
def test_each_broken_clause_is_reported_and_only_that_clause(conn, f, name):
    mutate, expected, detail = CLAUSE_CASES[name]
    s = f.gate_scenario(yesterday_ist())
    mutate(conn, s)
    rows = authorise(conn, s)
    assert failed(rows) == expected
    assert detail in " ".join(r["detail"] for r in rows if not r["passed"])
    assert status(conn, s) == "DRAFT" and {r["permit_status"] for r in rows} == {"DRAFT"}


def test_gear_division_names_the_entrant_and_only_the_entrant_who_is_short(conn, f):
    s = f.gate_scenario(yesterday_ist())
    conn.execute("DELETE FROM gear_issue WHERE worker_id = %s AND gear_code IN ('SAFETY_HARNESS', 'HELMET_LAMP')", (s["e2"],))
    detail = next(r["detail"] for r in authorise(conn, s) if r["clause_code"] == "GEAR_ALL")
    e1 = conn.execute("SELECT namaste_id FROM worker WHERE worker_id = %s", (s["e1"],)).fetchone()["namaste_id"]
    e2 = conn.execute("SELECT namaste_id FROM worker WHERE worker_id = %s", (s["e2"],)).fetchone()["namaste_id"]
    assert e2 in detail and "Helmet with head lamp" in detail and "Safety harness with lifeline" in detail
    assert e1 not in detail


# --- gas: division over the three depth levels, latest reading governs ------------------------------------
GAS_CASES = {
    "bottom_never_tested":   ({"BOTTOM": None},                 {"GAS_BOTTOM"}, "No BOTTOM reading"),
    "bottom_22_min_old":     ({"BOTTOM": {"age_min": 22}},      {"GAS_BOTTOM"}, "22 min old"),
    "exactly_15_min_ok":     ({"MID": {"age_min": 15}},         set(),          None),
    "16_min_fails":          ({"MID": {"age_min": 16}},         {"GAS_MID"},    "16 min old"),
    "oxygen_too_low":        ({"MID": {"o2": 18.2}},            {"GAS_MID"},    r"O2 18\.2"),
    "oxygen_too_high":       ({"TOP": {"o2": 23.0}},            {"GAS_TOP"},    r"O2 23\.0"),
    "oxygen_at_lower_bound": ({"TOP": {"o2": 19.5}},            set(),          None),
    "h2s_at_limit_fails":    ({"BOTTOM": {"h2s": 10}},          {"GAS_BOTTOM"}, "H2S"),
    "h2s_just_below_ok":     ({"BOTTOM": {"h2s": 9.99}},        set(),          None),
    "combustibles_at_limit": ({"MID": {"lel": 10}},             {"GAS_MID"},    "LEL"),
    "carbon_monoxide":       ({"TOP": {"co": 35}},              {"GAS_TOP"},    "CO"),
    "two_levels_bad":        ({"TOP": {"o2": 15}, "BOTTOM": {"h2s": 50}}, {"GAS_TOP", "GAS_BOTTOM"}, None),
}


@pytest.mark.parametrize("name", GAS_CASES)
def test_gas_clauses(conn, f, name):
    readings, expected, detail = GAS_CASES[name]
    s = f.gate_scenario(yesterday_ist(), readings=readings)
    rows = authorise(conn, s)
    assert failed(rows) == expected
    if detail:
        import re
        assert re.search(detail, " ".join(r["detail"] for r in rows if not r["passed"]))


def test_a_newer_bad_reading_is_not_hidden_behind_an_older_good_one(conn, f):
    s = f.gate_scenario(yesterday_ist())
    f.reading(s["permit"], s["detector"], "TOP", s["at"] - timedelta(minutes=2), s["supervisor"], o2=15.0)
    assert failed(authorise(conn, s)) == {"GAS_TOP"}


def test_a_newer_good_reading_supersedes_an_older_bad_one(conn, f):
    s = f.gate_scenario(yesterday_ist(), readings={"TOP": {"age_min": 12, "o2": 15.0}})
    f.reading(s["permit"], s["detector"], "TOP", s["at"] - timedelta(minutes=3), s["supervisor"])
    assert failed(authorise(conn, s)) == set()


def test_readings_taken_after_the_authorisation_instant_do_not_count(conn, f):
    s = f.gate_scenario(yesterday_ist(), readings={"BOTTOM": None})
    f.reading(s["permit"], s["detector"], "BOTTOM", s["at"] + timedelta(minutes=10), s["supervisor"])
    assert failed(authorise(conn, s)) == {"GAS_BOTTOM"}


def test_gas_limits_are_rule_parameters_not_code(conn, f):
    s = f.gate_scenario(yesterday_ist(), readings={"TOP": {"h2s": 12}})
    assert failed(authorise(conn, s)) == {"GAS_TOP"}
    conn.execute("UPDATE rule_parameter SET value = 15 WHERE param_key = 'gas_h2s_max_ppm'")   # law is data
    assert failed(authorise(conn, s)) == set()


def test_a_missing_rule_parameter_is_an_error_not_a_silent_default(conn, f):
    # Parameters referenced by immutable history cannot be deleted. Missing keys still fail closed.
    with expect("ZE005", "missing_test_parameter"):
        conn.execute("SELECT rule_num('missing_test_parameter')")


# --- the demo: denied with exactly three legal reasons, then fixed and authorised -----------------------
def test_denial_with_three_reasons_then_fix_and_authorise(conn, f):
    s = f.gate_scenario(yesterday_ist(), readings={"BOTTOM": {"age_min": 22}})
    conn.execute("DELETE FROM permit_crew WHERE permit_id = %s AND crew_role = 'STANDBY'", (s["permit"],))
    conn.execute("DELETE FROM gear_issue WHERE worker_id = %s AND gear_code = 'BREATHING_APPARATUS'", (s["e1"],))
    rows = authorise(conn, s)
    assert failed(rows) == {"CREW_STANDBY", "GEAR_ALL", "GAS_BOTTOM"}
    assert status(conn, s) == "DRAFT"

    # the supervisor fixes each point: a distinct standby, the missing gear, a fresh BOTTOM reading
    standby = f.worker(s["contractor"])
    f.crew(s["permit"], standby, "STANDBY")
    conn.execute("INSERT INTO gear_issue (permit_id, worker_id, gear_code, serial_no) VALUES (%s, %s, 'BREATHING_APPARATUS', 'SN-NEW')",
                 (s["permit"], s["e1"]))
    f.reading(s["permit"], s["detector"], "BOTTOM", s["at"] - timedelta(minutes=1), s["supervisor"])
    rows = authorise(conn, s)
    assert failed(rows) == set() and status(conn, s) == "AUTHORISED"


def test_live_readiness_view_reports_failing_clauses_of_draft_permits(conn, f):
    ok = f.gate_scenario(yesterday_ist())                       # stale as of now(): readings are a day old
    row = conn.execute("SELECT * FROM v_permit_compliance WHERE permit_id = %s", (ok["permit"],)).fetchone()
    assert row["clauses_total"] == 11 and row["ready_to_authorise"] is False
    assert set(row["failing_clauses"].split(", ")) == {"GAS_BOTTOM", "GAS_MID", "GAS_TOP"}
    authorise(conn, ok)
    assert conn.execute("SELECT count(*) AS n FROM v_permit_compliance WHERE permit_id = %s", (ok["permit"],)).fetchone()["n"] == 0


# --- default deny: there is no side door -----------------------------------------------------------------
def test_raw_update_cannot_authorise_a_non_compliant_permit(conn, f):
    s = f.gate_scenario(yesterday_ist())
    conn.execute("DELETE FROM permit_crew WHERE permit_id = %s AND crew_role = 'STANDBY'", (s["permit"],))
    with expect("ZE001", r"Entry denied.*standby"):
        conn.execute("UPDATE entry_permit SET status = 'AUTHORISED', authorised_at = %s, authorised_by = %s WHERE permit_id = %s",
                     (s["at"], s["supervisor"], s["permit"]))
    assert status(conn, s) == "DRAFT"


def test_raw_update_with_the_proof_in_place_is_accepted_the_gate_is_data_driven(conn, f):
    s = f.gate_scenario(yesterday_ist())
    conn.execute("UPDATE entry_permit SET status = 'AUTHORISED', authorised_at = %s, authorised_by = %s WHERE permit_id = %s",
                 (s["at"], s["supervisor"], s["permit"]))
    assert status(conn, s) == "AUTHORISED"


def test_a_permit_cannot_be_inserted_already_authorised(conn, f):
    s = f.gate_scenario(yesterday_ist())
    with expect("ZE003", "created as DRAFT"):
        conn.execute("INSERT INTO entry_permit (job_id, supervisor_id, status, authorised_at, authorised_by, valid_until) "
                     "VALUES (%s, %s, 'AUTHORISED', %s, %s, %s)",
                     (s["job"], s["supervisor"], s["at"], s["supervisor"], s["at"] + timedelta(hours=4)))


def test_only_a_supervisor_or_engineer_may_authorise(conn, f):
    s = f.gate_scenario(yesterday_ist())
    worker_login = f.user("WORKER", worker_id=f.worker(s["contractor"]))
    with expect("ZE006", "SUPERVISOR or ENGINEER"):
        authorise(conn, s, actor=worker_login)
    with expect("ZE006"):                                        # no actor at all
        conn.execute("UPDATE entry_permit SET status = 'AUTHORISED', authorised_at = %s WHERE permit_id = %s",
                     (s["at"], s["permit"]))
    assert status(conn, s) == "DRAFT"
    assert failed(authorise(conn, s, actor=s["engineer"])) == set()   # an engineer may


def test_the_state_machine_forbids_illegal_transitions(conn, f):
    s = f.gate_scenario(yesterday_ist())
    with expect("ZE003", "DRAFT to CLOSED"):
        conn.execute("UPDATE entry_permit SET status = 'CLOSED' WHERE permit_id = %s", (s["permit"],))
    authorise(conn, s)
    with expect("ZE003", "AUTHORISED to DRAFT"):
        conn.execute("UPDATE entry_permit SET status = 'DRAFT' WHERE permit_id = %s", (s["permit"],))
    with expect("ZE003", "can no longer be authorised"):          # authorising twice
        authorise(conn, s)
    with expect("ZE003", "cannot be altered"):
        conn.execute("UPDATE entry_permit SET valid_until = valid_until + interval '3 hours' WHERE permit_id = %s", (s["permit"],))
    conn.execute("UPDATE entry_permit SET status = 'CLOSED' WHERE permit_id = %s", (s["permit"],))
    with expect("ZE003", "CLOSED to AUTHORISED"):
        conn.execute("UPDATE entry_permit SET status = 'AUTHORISED' WHERE permit_id = %s", (s["permit"],))


def test_the_permit_row_is_locked_while_authorising_so_stale_proofs_cannot_race(db, f):
    """A second session adding a crew member blocks until the authorising transaction ends (FOR UPDATE vs FOR KEY SHARE)."""
    import threading
    conn = f.c
    s = f.gate_scenario(yesterday_ist())
    other = db.connect()
    other.execute("SET lock_timeout = '300ms'")
    late = f.worker(s["contractor"])
    with conn.transaction():
        authorise(conn, s)                                        # holds the permit row lock until commit
        errors: list[Exception] = []

        def try_add():
            try:
                other.execute("INSERT INTO permit_crew (permit_id, worker_id, crew_role) VALUES (%s, %s, 'ENTRANT')",
                              (s["permit"], late))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        t = threading.Thread(target=try_add)
        t.start()
        t.join()
    assert errors and errors[0].sqlstate == "55P03", f"expected lock timeout, got {errors}"   # lock_not_available
    other.close()


def test_a_permit_needs_a_waiver_and_a_supervisor_role_to_exist_at_all(conn, f):
    s = f.gate_scenario(yesterday_ist())
    no_waiver_job = f.job(f.complaint(s["manhole"]), s["contractor"])
    with expect("ZE002", "written mechanisation waiver"):
        f.permit(no_waiver_job, s["supervisor"])
    with expect("ZE006", "SUPERVISOR role"):
        f.permit(s["job"], s["engineer"])
    f.c.execute("UPDATE job SET status = 'CANCELLED' WHERE job_id = %s", (s["job"],))
    with expect("ZE003", "CANCELLED"):
        f.permit(s["job"], s["supervisor"])
