"""The runtime role (ze_app) can do its job and nothing more. Even a compromised application cannot rewrite history."""

import psycopg
import pytest

from tests.factories import Factory, utc, yesterday_ist
from tests.helpers import act_as

DENIED = psycopg.errors.InsufficientPrivilege


@pytest.fixture
def app(db):
    """A connection as the runtime role, no request context set (so no RLS passes; privileges are what is tested)."""
    with db.connect(user="ze_app") as c:
        yield c


@pytest.fixture
def seeded(conn):
    f = Factory(conn)
    s = f.gate_scenario(yesterday_ist())
    conn.execute("SELECT * FROM authorise_entry(%s, %s, %s)", (s["permit"], s["supervisor"], s["at"]))
    s["worker_login"] = f.user("WORKER", worker_id=f.worker(s["contractor"]))
    return s


@pytest.mark.parametrize("sql", [
    "UPDATE audit_log SET row_pk = 'x'",
    "DELETE FROM audit_log",
    "TRUNCATE audit_log",
    "UPDATE gas_reading SET o2_pct = 20.9",
    "DELETE FROM gas_reading",
    "UPDATE mechanisation_waiver SET reason_code = 'OTHER'",
    "DELETE FROM mechanisation_waiver",
    "UPDATE incident SET description = 'x'",
    "DELETE FROM incident",
    "UPDATE shadow_entry_alert_event SET note = 'x'",
    "DELETE FROM shadow_entry_alert_event",
    "DELETE FROM entry_log",
    "UPDATE entry_log SET worker_id = worker_id",
    "DELETE FROM compensation_case",
    "UPDATE compensation_case SET amount_due = 1",
    "DELETE FROM shadow_entry_alert",
    "UPDATE shadow_entry_alert SET rule_code = rule_code",
    "DELETE FROM invoice_hold",
    "UPDATE invoice_hold SET alert_id = NULL",
    "INSERT INTO role (name, description) VALUES ('ROGUE', 'x')",
    "UPDATE role SET description = 'x'",
    "DELETE FROM legal_clause",
    "UPDATE legal_clause SET title = 'x'",
    "INSERT INTO resolution_type (code, description, requires_evidence) VALUES ('X', 'x', false)",
    "INSERT INTO rule_parameter (param_key, value, unit, description, legal_ref) VALUES ('new_key', 1, 'u', 'd', 'l')",
    "DELETE FROM rule_parameter",
    "UPDATE rule_parameter SET legal_ref = 'rewritten history'",
    "INSERT INTO detection_rule (rule_code, title, description) VALUES ('SE9_X', 't', 'd')",
    "UPDATE detection_rule SET title = 'x'",
    "CREATE TABLE sneaky (id int)",
    "DROP TABLE audit_log",
])
def test_the_runtime_role_cannot_rewrite_history_or_the_law(app, seeded, sql):
    with pytest.raises(DENIED):
        app.execute(sql)


def test_the_runtime_role_can_still_do_the_narrow_things_the_workflow_needs(app, seeded, conn):
    s = seeded
    admin = Factory(conn).user("ADMIN")
    act_as(app, admin, "ADMIN")                                    # row-level security: no identity, no rows
    app.execute("UPDATE rule_parameter SET value = 12, updated_by = %s, updated_at = now() WHERE param_key = 'gas_h2s_max_ppm'",
                (admin,))
    app.execute("UPDATE detection_rule SET enabled = false WHERE rule_code = 'SE2_ENTRANT_NOT_LOGGED'")
    app.execute("SELECT * FROM scan_shadow_entries(now())")                                    # needs INSERT + limited UPDATE on alerts
    assert app.execute("SELECT count(*) AS n FROM audit_log").fetchone()["n"] > 0           # may read the trail
    assert app.execute("SELECT value FROM rule_parameter WHERE param_key = 'gas_h2s_max_ppm'").fetchone()["value"] == 12


def test_gate_and_incident_machinery_work_under_the_runtime_role(app, conn):
    """authorise_entry and record_incident are SECURITY INVOKER: they must succeed with only ze_app's privileges."""
    f = Factory(conn)
    s = f.gate_scenario(yesterday_ist())
    act_as(app, s["supervisor"], "SUPERVISOR")
    rows = app.execute("SELECT * FROM authorise_entry(%s, %s, %s)", (s["permit"], s["supervisor"], s["at"])).fetchall()
    assert all(r["passed"] for r in rows) and rows[0]["permit_status"] == "AUTHORISED"
    act_as(app, s["engineer"], "ENGINEER")
    iid = app.execute("CALL record_incident('FATALITY', %s, %s, %s, 'Collapsed in the chamber', %s, %s, NULL, NULL::bigint)",
                      (s["at"] + (utc(2026, 1, 1, 0, 30) - utc(2026, 1, 1)), s["e1"], s["manhole"], s["engineer"], s["permit"])
                      ).fetchone()["p_incident_id"]
    assert iid and app.execute("SELECT status FROM entry_permit WHERE permit_id = %s", (s["permit"],)).fetchone()["status"] == "ABORTED"
    assert app.execute("SELECT status FROM contractor WHERE contractor_id = %s", (s["contractor"],)).fetchone()["status"] == "BLACKLISTED"
