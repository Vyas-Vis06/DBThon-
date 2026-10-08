"""Row-level security, tested as the real runtime role (ze_app) with the same per-request settings the API uses.
Two competing contractors (A, B), a worker on A's crew, an auditor, supervisors and engineers. PROJECT_SPEC BR-42."""

import psycopg
import pytest

from tests.factories import Factory, yesterday_ist
from tests.helpers import act_as, expect

RLS_TABLES = ["contractor", "worker", "job", "complaint", "machine_deployment", "mechanisation_waiver", "entry_permit",
              "permit_crew", "gear_issue", "gas_reading", "entry_log", "incident", "compensation_case", "invoice",
              "invoice_hold", "shadow_entry_alert", "shadow_entry_alert_event", "audit_log"]


@pytest.fixture
def world(conn):
    """Two contractors, each with an authorised permit, a worked entry, an invoice. A has an alert; B had a fatality."""
    f = Factory(conn)
    w = {"f": f}
    for tag in ("a", "b"):
        s = f.gate_scenario(yesterday_ist(10, 0))
        conn.execute("SELECT * FROM authorise_entry(%s, %s, %s)", (s["permit"], s["supervisor"], s["at"]))
        conn.execute("INSERT INTO entry_log (permit_id, worker_id, period, recorded_by) VALUES (%s, %s, tstzrange(%s, %s), %s)",
                     (s["permit"], s["e1"], s["at"] + (yesterday_ist(10, 10) - yesterday_ist(10, 0)),
                      s["at"] + (yesterday_ist(10, 40) - yesterday_ist(10, 0)), s["supervisor"]))
        s["invoice"] = f.invoice(s["job"])
        s["contractor_user"] = f.user("CONTRACTOR", contractor_id=s["contractor"])
        s["worker_user"] = s["worker_user_e1"]
        w[tag] = s
    a, b = w["a"], w["b"]
    f.insert("shadow_entry_alert", "alert_id", complaint_id=a["complaint"], rule_code="SE1_NO_CLEARANCE_EVIDENCE",
             contractor_id=a["contractor"], reason="r", evidence_deadline=a["at"])
    conn.execute("CALL record_incident('FATALITY', %s, %s, %s, 'Collapsed in the chamber', %s, NULL, %s, NULL::bigint)",
                 (b["at"], b["e2"], b["manhole"], b["engineer"], b["job"]))
    w["auditor"] = f.user("AUDITOR")
    w["admin"] = f.user("ADMIN")
    return w


@pytest.fixture
def app(db):
    with db.connect(user="ze_app") as c:
        yield c


def count(app, table):
    return app.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]  # noqa: S608 - fixed names


def owner_count(conn, table):
    return conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]  # noqa: S608


# --- default deny ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("table", RLS_TABLES)
def test_with_no_request_context_the_runtime_role_sees_nothing(world, conn, app, table):
    assert owner_count(conn, table) > 0, f"fixture has no rows in {table}"
    assert count(app, table) == 0


def test_with_no_context_nothing_can_be_written_either(world, app):
    with expect("42501"):
        app.execute("INSERT INTO complaint (manhole_id, description) VALUES (1, 'x')")
    assert app.execute("UPDATE contractor SET name = 'hijacked'").rowcount == 0
    assert app.execute("DELETE FROM worker").rowcount == 0


def test_a_worker_can_ack_only_their_own_assignment_and_cannot_forge_the_actor(db, conn):
    s = Factory(conn).gate_scenario(yesterday_ist())
    f = Factory(conn)
    worker_user = s["worker_user_e1"]
    forged_worker = f.worker(s["contractor"])
    with db.connect(user="ze_app") as app:
        act_as(app,s["supervisor"],"SUPERVISOR")
        with expect("ZE006","cannot insert a worker acknowledgement"):
            app.execute("INSERT INTO permit_crew(permit_id,worker_id,crew_role,acknowledged_at,acknowledged_by) "
                        "VALUES(%s,%s,'ENTRANT',clock_timestamp(),%s)",(s["permit"],forged_worker,s["supervisor"]))
    conn.execute("UPDATE permit_crew SET acknowledged_at=NULL,acknowledged_by=NULL WHERE permit_id=%s AND worker_id=%s",
                 (s["permit"],s["e1"]))
    with db.connect(user="ze_app") as app:
        act_as(app,worker_user,"WORKER",worker_id=s["e1"])
        with expect("ZE006","assigned worker"):
            app.execute("UPDATE permit_crew SET acknowledged_at=clock_timestamp(),acknowledged_by=%s "
                        "WHERE permit_id=%s AND worker_id=%s",(s["supervisor"],s["permit"],s["e1"]))
        assert app.execute("UPDATE permit_crew SET acknowledged_at=clock_timestamp(),acknowledged_by=%s "
                           "WHERE permit_id=%s AND worker_id=%s",(worker_user,s["permit"],s["e1"])).rowcount==1
        assert app.execute("UPDATE permit_crew SET acknowledged_at=clock_timestamp(),acknowledged_by=%s "
                           "WHERE permit_id=%s AND worker_id=%s",(worker_user,s["permit"],s["e2"])).rowcount==0
    row=conn.execute("SELECT acknowledged_by FROM permit_crew WHERE permit_id=%s AND worker_id=%s",
                     (s["permit"],s["e1"])).fetchone()
    assert row["acknowledged_by"]==worker_user


def test_engineer_cannot_authorize_a_permit_outside_their_stored_scope(db, conn):
    f = Factory(conn)
    own = f.gate_scenario(yesterday_ist())
    foreign = f.gate_scenario(yesterday_ist())
    with db.connect(user="ze_app") as app:
        act_as(app, own["engineer"], "ENGINEER", ulb_id=own["ulb"])
        with expect("ZE006", "cannot authorize"):
            app.execute("SELECT * FROM authorise_entry(%s,%s,%s)",
                        (foreign["permit"], own["engineer"], foreign["at"]))


# --- a contractor sees and touches only its own rows ----------------------------------------------------------
def test_a_contractor_sees_only_its_own_rows(world, conn, app):
    a, b = world["a"], world["b"]
    act_as(app, a["contractor_user"], "CONTRACTOR", contractor_id=a["contractor"])
    assert [r["contractor_id"] for r in app.execute("SELECT contractor_id FROM contractor")] == [a["contractor"]]
    assert count(app, "worker") == 4                                           # A's crew only
    assert {r["contractor_id"] for r in app.execute("SELECT contractor_id FROM worker")} == {a["contractor"]}
    assert [r["job_id"] for r in app.execute("SELECT job_id FROM job")] == [a["job"]]
    assert [r["permit_id"] for r in app.execute("SELECT permit_id FROM entry_permit")] == [a["permit"]]
    assert count(app, "permit_crew") == 4 and count(app, "gas_reading") == 3 and count(app, "entry_log") == 1
    assert [r["invoice_id"] for r in app.execute("SELECT invoice_id FROM invoice")] == [a["invoice"]]
    assert count(app, "complaint") == 1 and count(app, "mechanisation_waiver") == 1 and count(app, "machine_deployment") == 1
    assert count(app, "incident") == 0                                         # the fatality was B's
    # B's records are invisible, even by key
    assert app.execute("SELECT 1 FROM job WHERE job_id = %s", (b["job"],)).fetchone() is None
    assert app.execute("SELECT 1 FROM entry_permit WHERE permit_id = %s", (b["permit"],)).fetchone() is None


def test_a_contractor_cannot_see_alerts_audit_or_other_contractors_money(world, conn, app):
    a, b = world["a"], world["b"]
    act_as(app, a["contractor_user"], "CONTRACTOR", contractor_id=a["contractor"])
    for table in ("shadow_entry_alert", "shadow_entry_alert_event", "audit_log", "compensation_case"):
        assert count(app, table) == 0, table
    assert [r["invoice_id"] for r in app.execute("SELECT invoice_id FROM v_invoice_status")] == [a["invoice"]]     # views obey RLS
    assert [r["contractor_id"] for r in app.execute("SELECT contractor_id FROM v_contractor_risk")] == [a["contractor"]]
    # B (whose worker died) sees its own case and holds
    act_as(app, b["contractor_user"], "CONTRACTOR", contractor_id=b["contractor"])
    assert count(app, "compensation_case") == 1 and count(app, "incident") == 1 and count(app, "invoice_hold") >= 1


def test_a_contractor_can_change_nothing_except_invoice_its_own_jobs(world, conn, app):
    a, b = world["a"], world["b"]
    act_as(app, a["contractor_user"], "CONTRACTOR", contractor_id=a["contractor"])
    assert app.execute("UPDATE job SET status = 'COMPLETED'").rowcount == 0
    assert app.execute("UPDATE worker SET full_name = 'x'").rowcount == 0
    assert app.execute("UPDATE invoice SET status = 'APPROVED'").rowcount == 0           # cannot approve its own invoice
    assert app.execute("UPDATE contractor SET status = 'ACTIVE'").rowcount == 0
    with expect("42501"):
        app.execute("INSERT INTO incident (incident_type, occurred_at, manhole_id, worker_id, contractor_id, description, recorded_by) "
                    "VALUES ('NEAR_MISS', now(), %s, %s, %s, 'x', %s)", (a["manhole"], a["e1"], a["contractor"], a["supervisor"]))
    with expect("ZE006"):                                                                # B's job; serialized invoice guard denies scope
        app.execute("INSERT INTO invoice (job_id, invoice_no, amount_inr) VALUES (%s, 'STEAL-1', 1)", (b["job"],))
    app.execute("INSERT INTO invoice (job_id, invoice_no, amount_inr) VALUES (%s, 'MINE-1', 500)", (a["job"],))   # own job: allowed
    assert owner_count(conn, "invoice") == 3


def test_an_invoice_a_contractor_submits_after_an_alert_is_held_even_though_it_cannot_see_the_alert(world, conn, app):
    a = world["a"]
    act_as(app, a["contractor_user"], "CONTRACTOR", contractor_id=a["contractor"])
    app.execute("INSERT INTO invoice (job_id, invoice_no, amount_inr) VALUES (%s, 'LATE-1', 500)", (a["job"],))   # trigger runs as definer
    held = conn.execute("SELECT on_hold, hold_reasons FROM v_invoice_status WHERE invoice_no = 'LATE-1'").fetchone()
    assert held == {"on_hold": True, "hold_reasons": "SHADOW_ENTRY"}
    audited = conn.execute("SELECT actor_user_id FROM audit_log WHERE table_name = 'invoice' AND action = 'INSERT' "
                           "ORDER BY log_id DESC LIMIT 1").fetchone()
    assert audited["actor_user_id"] == a["contractor_user"]                          # audit written by trigger, with the real actor


# --- a worker sees only the permits they are crewed on, and has one narrow door ---------------------------------
def test_a_worker_sees_only_their_own_permit_and_nothing_else(world, conn, app):
    a = world["a"]
    act_as(app, a["worker_user"], "WORKER", worker_id=a["e1"])
    assert [r["permit_id"] for r in app.execute("SELECT permit_id FROM entry_permit")] == [a["permit"]]
    assert count(app, "permit_crew") == 4 and count(app, "gear_issue") == 10 and count(app, "gas_reading") == 3
    assert sorted(r["worker_id"] for r in app.execute("SELECT worker_id FROM worker")) == sorted(
        [a["e1"], a["e2"], a["standby"], a["sup_worker"]])                                              # themself + the crew they share a permit with
    assert count(app, "job") == 1 and count(app, "complaint") == 1
    for table in ("contractor", "invoice", "incident", "compensation_case", "shadow_entry_alert", "audit_log"):
        assert count(app, table) == 0, table


def test_a_worker_cannot_edit_a_permit_but_can_stop_work_on_their_own(world, conn, app):
    a, b = world["a"], world["b"]
    act_as(app, a["worker_user"], "WORKER", worker_id=a["e1"])
    assert app.execute("UPDATE entry_permit SET status = 'CLOSED'").rowcount == 0
    with expect("ZE006", "not on the crew|does not exist"):                         # B's permit: invisible / not theirs
        app.execute("SELECT * FROM stop_work(%s, 'Gas smell at the bottom')", (b["permit"],))
    with expect("ZE002", "reason"):
        app.execute("SELECT * FROM stop_work(%s, 'no')", (a["permit"],))
    row = app.execute("SELECT * FROM stop_work(%s, 'Strong gas smell at the bottom')", (a["permit"],)).fetchone()
    assert row["status"] == "ABORTED" and "worker" in row["end_reason"].lower()
    assert conn.execute("SELECT status FROM entry_permit WHERE permit_id = %s", (a["permit"],)).fetchone()["status"] == "ABORTED"
    with expect("ZE003", "already"):
        app.execute("SELECT * FROM stop_work(%s, 'Trying again after it is aborted')", (a["permit"],))


def test_other_roles_cannot_use_the_stop_work_door(world, app):
    a = world["a"]
    act_as(app, a["contractor_user"], "CONTRACTOR", contractor_id=a["contractor"])
    with expect("ZE006", "cannot stop work"):
        app.execute("SELECT * FROM stop_work(%s, 'A contractor office should not do this')", (a["permit"],))
    act_as(app, world["auditor"], "AUDITOR")
    with expect("ZE006", "cannot stop work"):
        app.execute("SELECT * FROM stop_work(%s, 'An auditor should not do this either')", (a["permit"],))


# --- the auditor reads everything and writes nothing ----------------------------------------------------------------
def test_an_auditor_reads_alerts_and_audit_but_cannot_write_anything(world, conn, app):
    a = world["a"]
    act_as(app, world["auditor"], "AUDITOR")
    assert count(app, "shadow_entry_alert") == 1 and count(app, "audit_log") > 0 and count(app, "entry_permit") == 2
    assert count(app, "incident") == 1 and count(app, "compensation_case") == 1
    for sql in ("UPDATE complaint SET description = 'x'", "UPDATE job SET status = 'FAILED'", "UPDATE invoice SET status = 'PAID'",
                "UPDATE entry_permit SET status = 'CLOSED'", "UPDATE shadow_entry_alert SET status = 'DISMISSED'",
                "UPDATE rule_parameter SET value = 1", "UPDATE contractor SET status = 'ACTIVE'", "DELETE FROM worker"):
        assert app.execute(sql).rowcount == 0, sql
    with expect("42501"):
        app.execute("INSERT INTO complaint (manhole_id, description) VALUES (%s, 'x')", (a["manhole"],))
    with expect("ZE004"):                      # RLS hides the alert from a role that cannot update it
        app.execute("SELECT * FROM review_shadow_alert((SELECT min(alert_id) FROM shadow_entry_alert), 'DISMISSED', 'Auditors must not decide.', %s)",
                    (world["auditor"],))


# --- supervisors: staff for reading, own permits for writing -----------------------------------------------------------
def test_a_supervisor_writes_only_their_own_permits_and_cannot_see_alerts(world, conn, app):
    f, a, b = world["f"], world["a"], world["b"]
    draft_b = f.permit(b["job"], b["supervisor"])                    # B's supervisor starts a new draft permit
    act_as(app, a["supervisor"], "SUPERVISOR", ulb_id=a["ulb"])
    assert count(app, "entry_permit") == 1 and count(app, "shadow_entry_alert") == 0       # own stored ULB only; no alerts
    assert app.execute("UPDATE entry_permit SET end_reason = 'meddling' WHERE permit_id = %s", (draft_b,)).rowcount == 0
    with expect("42501"):                                                                 # crew on someone else's draft
        app.execute("INSERT INTO permit_crew (permit_id, worker_id, crew_role) VALUES (%s, %s, 'ENTRANT')", (draft_b, b["e1"]))
    act_as(app, b["supervisor"], "SUPERVISOR", ulb_id=b["ulb"])                            # its owner may
    app.execute("INSERT INTO permit_crew (permit_id, worker_id, crew_role) VALUES (%s, %s, 'ENTRANT')", (draft_b, f.worker(b["contractor"])))


def test_a_supervisor_can_create_a_permit_only_as_themselves(world, conn, app):
    """Regression: the insert policy must check the new row's own supervisor_id, not look the (nonexistent) row up."""
    a, b = world["a"], world["b"]
    act_as(app, a["supervisor"], "SUPERVISOR", ulb_id=a["ulb"])
    assert app.execute("INSERT INTO entry_permit (job_id, supervisor_id) VALUES (%s, %s) RETURNING permit_id", (a["job"], a["supervisor"])).fetchone()
    with expect("42501"):
        app.execute("INSERT INTO entry_permit (job_id, supervisor_id) VALUES (%s, %s)", (a["job"], b["supervisor"]))   # on someone's behalf
    act_as(app, a["engineer"], "ENGINEER", ulb_id=a["ulb"])
    with expect("42501"):
        app.execute("INSERT INTO entry_permit (job_id, supervisor_id) VALUES (%s, %s)", (a["job"], a["supervisor"]))   # engineers do not draft

def test_a_fatality_recorded_by_a_supervisor_still_runs_in_full(world, conn, app):
    """A supervisor has no right to blacklist, yet recording a death must - so the procedure runs with definer rights."""
    a = world["a"]
    act_as(app, a["supervisor"], "SUPERVISOR", ulb_id=a["ulb"])
    assert app.execute("UPDATE contractor SET status = 'BLACKLISTED'").rowcount == 0                      # directly: refused
    iid = app.execute("CALL record_incident('FATALITY', %s, %s, %s, 'Collapsed in the chamber', %s, %s, NULL, NULL::bigint)",
                      (a["at"] + (yesterday_ist(10, 30) - yesterday_ist(10, 0)), a["e1"], a["manhole"], a["supervisor"], a["permit"])
                      ).fetchone()["p_incident_id"]
    assert iid
    assert conn.execute("SELECT status FROM contractor WHERE contractor_id = %s", (a["contractor"],)).fetchone()["status"] == "BLACKLISTED"
    assert conn.execute("SELECT status FROM entry_permit WHERE permit_id = %s", (a["permit"],)).fetchone()["status"] == "ABORTED"
    assert owner_count(conn, "compensation_case") == 2
    with expect("ZE006"):                                                                                 # a worker may not record one
        act_as(app, a["worker_user"], "WORKER", worker_id=a["e1"])
        app.execute("CALL record_incident('NEAR_MISS', now(), %s, %s, 'x', %s, NULL, NULL, NULL::bigint)",
                    (a["e1"], a["manhole"], a["worker_user"]))


# --- engineers and administrators ---------------------------------------------------------------------------------------
def test_the_detection_workflow_runs_under_an_engineer_context(world, conn, app):
    a = world["a"]
    act_as(app, a["engineer"], "ENGINEER", ulb_id=a["ulb"])
    app.execute("SELECT * FROM scan_shadow_entries(now())")
    (alert,) = [r["alert_id"] for r in app.execute("SELECT alert_id FROM shadow_entry_alert")]
    row = app.execute("SELECT * FROM review_shadow_alert(%s, 'CONFIRMED', 'Crew admitted entering unpermitted.', %s)",
                      (alert, a["engineer"])).fetchone()
    assert row["status"] == "CONFIRMED"
    assert app.execute("UPDATE rule_parameter SET value = 1 WHERE param_key = 'min_crew_size'").rowcount == 0   # engineers cannot edit law


def test_only_an_admin_can_change_the_law_and_the_catalogues(world, conn, app):
    a = world["a"]
    act_as(app, world["admin"], "ADMIN")
    app.execute("SELECT set_config('app.rule_change_reason', 'Synthetic RLS policy verification', false)")
    assert app.execute("UPDATE rule_parameter SET value = 4 WHERE param_key = 'min_crew_size'").rowcount == 1
    assert app.execute("UPDATE gear_item SET statutory = false WHERE gear_code = 'GUMBOOTS'").rowcount == 1
    act_as(app, a["engineer"], "ENGINEER", ulb_id=a["ulb"])
    assert app.execute("UPDATE gear_item SET statutory = false WHERE gear_code = 'SAFETY_HARNESS'").rowcount == 0
    assert app.execute("UPDATE gas_detector SET calibration_valid_until = '2099-01-01'").rowcount == 0
    with expect("42501"):
        app.execute("INSERT INTO gear_item (gear_code, name, statutory) VALUES ('ROGUE_ITEM', 'x', false)")


def test_the_application_role_cannot_forge_an_audit_row(world, app):
    act_as(app, world["admin"], "ADMIN")
    with expect("42501"):
        app.execute("INSERT INTO audit_log (action, table_name, row_pk) VALUES ('INSERT', 'contractor', '1')")


def test_helper_functions_answer_false_without_identity(world, app):
    a = world["a"]
    assert app.execute("SELECT worker_on_permit(%s) AS x, contractor_owns_permit(%s) AS y, permit_writer(%s) AS z, app_is_staff() AS s",
                       (a["permit"], a["permit"], a["permit"])).fetchone() == {"x": False, "y": False, "z": False, "s": False}
