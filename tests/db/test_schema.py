"""Schema structure and declarative constraints (keys, CHECK, UNIQUE, FK, exclusion). No trigger logic here."""

import psycopg
import pytest

from tests.factories import Factory, utc

EXPECTED_TABLES = {
    "role", "app_user", "user_session", "ulb", "manhole", "resolution_type", "complaint", "contractor", "worker",
    "machine", "job", "machine_deployment", "mechanisation_waiver", "entry_permit", "permit_crew", "gear_item",
    "gear_issue", "gas_detector", "gas_reading", "entry_log", "incident", "compensation_case", "invoice",
    "invoice_hold", "detection_rule", "shadow_entry_alert", "shadow_entry_alert_event", "rule_parameter",
    "legal_clause", "audit_log", "permit_safety_event", "policy_source", "legal_clause_source",
    "rule_parameter_history", "permit_authorization_decision",
    "gear_asset", "permit_site_gear", "permit_readiness", "permit_resource_reservation",
    "permit_decision_receipt", "completion_claim", "completion_projection",
    "command_dedup", "outbox_scope_counter", "outbox_event", "incident_report",
    "incident_report_victim", "incident_assessment_case", "ulb_contractor_scope", "ulb_detector_scope",
}


def test_application_tables_exist(conn):
    names = {r["table_name"] for r in conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'")}
    assert names - {"alembic_version"} == EXPECTED_TABLES


def test_every_table_has_a_primary_key(conn):
    missing = conn.execute("""
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname <> 'alembic_version'
          AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conrelid = c.oid AND k.contype = 'p')""").fetchall()
    assert missing == []


def test_relationships_are_enforced_by_many_foreign_keys(conn):
    n = conn.execute("SELECT count(*) AS n FROM pg_constraint WHERE contype = 'f' AND connamespace = 'public'::regnamespace"
                     ).fetchone()["n"]
    assert n >= 40


def test_reference_data_is_loaded_by_migrations(conn):
    one = lambda sql: conn.execute(sql).fetchone()["n"]  # noqa: E731
    assert one("SELECT count(*) AS n FROM role") == 6
    assert one("SELECT count(*) AS n FROM legal_clause") == 19
    assert one("SELECT count(*) AS n FROM gear_item WHERE statutory") == 5
    assert one("SELECT count(*) AS n FROM detection_rule WHERE enabled") == 2
    assert one("SELECT count(*) AS n FROM rule_parameter WHERE is_assumption") >= 6
    assert one("SELECT count(*) AS n FROM resolution_type WHERE requires_evidence") == 1


def test_overlap_is_excluded_by_a_gist_exclusion_constraint(conn):
    row = conn.execute("SELECT pg_get_constraintdef(oid) AS d FROM pg_constraint WHERE conname = 'ex_entry_no_overlap'").fetchone()
    assert "EXCLUDE USING gist" in row["d"] and "period WITH &&" in row["d"]


@pytest.fixture
def world(conn):
    f = Factory(conn)
    ulb = f.ulb()
    contractor = f.contractor()
    manhole = f.manhole(ulb)
    return {"f": f, "ulb": ulb, "contractor": contractor, "manhole": manhole,
            "engineer": f.user("ENGINEER"), "complaint": f.complaint(manhole)}


def _insert_fails(conn, exc, sql, params=()):
    with pytest.raises(exc), conn.transaction():
        conn.execute(sql, params)


@pytest.mark.parametrize("sql,exc", [
    ("INSERT INTO manhole (ulb_id, code, kind, depth_m, lat, lng) SELECT min(ulb_id), 'BAD-1', 'SEWER', 0, 13, 80 FROM ulb",
     psycopg.errors.CheckViolation),
    ("INSERT INTO manhole (ulb_id, code, kind, depth_m, lat, lng) SELECT min(ulb_id), 'BAD-2', 'CAVE', 3, 13, 80 FROM ulb",
     psycopg.errors.CheckViolation),
    ("INSERT INTO manhole (ulb_id, code, kind, depth_m, lat, lng) SELECT min(ulb_id), 'BAD-3', 'SEWER', 3, 123, 80 FROM ulb",
     psycopg.errors.CheckViolation),
    ("INSERT INTO contractor (name, licence_no, licence_valid_until, status) VALUES ('x', 'L1', '2030-01-01', 'FINE')",
     psycopg.errors.CheckViolation),
    ("INSERT INTO role (name, description) VALUES ('lowercase', 'x')", psycopg.errors.CheckViolation),
])
def test_declarative_checks_reject_bad_rows(world, sql, exc):
    # these tests need at least one ULB for the SELECT min(ulb_id) form
    _insert_fails(world["f"].c, exc, sql)


def test_email_must_be_lowercase_and_unique(world):
    f = world["f"]
    _insert_fails(f.c, psycopg.errors.CheckViolation,
                  "INSERT INTO app_user (role_id, email, full_name, password_hash) VALUES (%s, 'Mixed@Case.example', 'x', 'h')",
                  (f.role_id("ADMIN"),))
    f.user("ADMIN", email="dup@zeroentry.example")
    _insert_fails(f.c, psycopg.errors.UniqueViolation,
                  "INSERT INTO app_user (role_id, email, full_name, password_hash) VALUES (%s, 'dup@zeroentry.example', 'x', 'h')",
                  (f.role_id("ADMIN"),))


def test_unique_namaste_id(world):
    f = world["f"]
    f.worker(world["contractor"], namaste_id="NAM-DUP-1")
    _insert_fails(f.c, psycopg.errors.UniqueViolation,
                  "INSERT INTO worker (contractor_id, full_name, namaste_id, medical_fit_until, trained_until) "
                  "VALUES (%s, 'x', 'NAM-DUP-1', '2030-01-01', '2030-01-01')", (world["contractor"],))


def test_resolved_complaint_must_carry_time_and_resolution(world):
    f = world["f"]
    _insert_fails(f.c, psycopg.errors.CheckViolation,
                  "INSERT INTO complaint (manhole_id, description, status) VALUES (%s, 'x', 'RESOLVED')", (world["manhole"],))
    _insert_fails(f.c, psycopg.errors.CheckViolation,
                  "INSERT INTO complaint (manhole_id, description, resolved_at) VALUES (%s, 'x', now())", (world["manhole"],))
    # resolved before it was raised
    _insert_fails(f.c, psycopg.errors.CheckViolation,
                  "INSERT INTO complaint (manhole_id, description, status, raised_at, resolved_at, resolution_code) "
                  "VALUES (%s, 'x', 'RESOLVED', '2026-01-02', '2026-01-01', 'CLEARED')", (world["manhole"],))


def test_deployment_outcome_must_match_its_end_time(world):
    f = world["f"]
    job = f.job(world["complaint"], world["contractor"])
    machine = f.machine(world["ulb"])
    _insert_fails(f.c, psycopg.errors.CheckViolation,
                  "INSERT INTO machine_deployment (job_id, machine_id, started_at, ended_at) VALUES (%s, %s, now(), now())",
                  (job, machine))
    _insert_fails(f.c, psycopg.errors.CheckViolation,
                  "INSERT INTO machine_deployment (job_id, machine_id, started_at, outcome) VALUES (%s, %s, now(), 'CLEARED')",
                  (job, machine))
    f.deployment(job, machine, None)  # in progress: no end, no outcome: legal


def test_waiver_justification_needs_fifty_characters(world):
    f = world["f"]
    job = f.job(world["complaint"], world["contractor"])
    _insert_fails(f.c, psycopg.errors.CheckViolation,
                  "INSERT INTO mechanisation_waiver (job_id, reason_code, justification, approved_by) VALUES (%s, 'OTHER', 'too short', %s)",
                  (job, world["engineer"]))


def test_foreign_keys_reject_orphans_and_restrict_deletes(world):
    f = world["f"]
    _insert_fails(f.c, psycopg.errors.ForeignKeyViolation,
                  "INSERT INTO job (complaint_id, contractor_id) VALUES (999999, %s)", (world["contractor"],))
    f.worker(world["contractor"])
    _insert_fails(f.c, psycopg.errors.ForeignKeyViolation,
                  "DELETE FROM contractor WHERE contractor_id = %s", (world["contractor"],))


def test_deleting_a_user_cascades_to_their_sessions_only(world):
    f = world["f"]
    uid = f.user("AUDITOR")
    f.insert("user_session", "session_id", user_id=uid, token_hash=b"\x01" * 32, csrf_token="t",
             expires_at=utc(2099, 1, 1))
    f.c.execute("DELETE FROM app_user WHERE user_id = %s", (uid,))
    assert f.scalar("SELECT count(*) FROM user_session") == 0


def test_alert_is_unique_per_complaint_and_rule_and_review_needs_a_note(world):
    f = world["f"]
    base = dict(complaint_id=world["complaint"], rule_code="SE1_NO_CLEARANCE_EVIDENCE", reason="r",
                evidence_deadline=utc(2026, 9, 2))
    f.insert("shadow_entry_alert", "alert_id", **base)
    _insert_fails(f.c, psycopg.errors.UniqueViolation,
                  "INSERT INTO shadow_entry_alert (complaint_id, rule_code, reason, evidence_deadline) VALUES (%s, %s, 'r', now())",
                  (world["complaint"], "SE1_NO_CLEARANCE_EVIDENCE"))
    # CONFIRMED without a reviewer is refused by the lifecycle trigger ...
    with pytest.raises(psycopg.Error) as err, f.c.transaction():
        f.c.execute("UPDATE shadow_entry_alert SET status = 'CONFIRMED' WHERE complaint_id = %s", (world["complaint"],))
    assert err.value.sqlstate == "ZE006"
    # ... and, independently, by the CHECK constraint (proved here with the trigger switched off, as a DBA could)
    f.c.execute("ALTER TABLE shadow_entry_alert DISABLE TRIGGER trg_alert_guard")
    _insert_fails(f.c, psycopg.errors.CheckViolation,
                  "UPDATE shadow_entry_alert SET status = 'CONFIRMED' WHERE complaint_id = %s", (world["complaint"],))


def test_hold_needs_exactly_one_source(world):
    f = world["f"]
    job = f.job(world["complaint"], world["contractor"])
    inv = f.insert("invoice", "invoice_id", job_id=job, invoice_no="INV-1", amount_inr=1000)
    _insert_fails(f.c, psycopg.errors.CheckViolation,
                  "INSERT INTO invoice_hold (invoice_id, reason) VALUES (%s, 'SHADOW_ENTRY')", (inv,))


def test_compensation_status_must_agree_with_payments(world):
    f = world["f"]
    worker = f.worker(world["contractor"])
    incident = f.insert("incident", "incident_id", incident_type="FATALITY", occurred_at=utc(2026, 9, 1), manhole_id=world["manhole"],
                        worker_id=worker, contractor_id=world["contractor"], description="d", recorded_by=world["engineer"])
    for status, paid in (("PAID", 0), ("OPEN", 500), ("PARTIAL", 3000000)):
        _insert_fails(f.c, psycopg.errors.CheckViolation,
                      "INSERT INTO compensation_case (incident_id, amount_due, amount_paid, due_by, status, paid_at) "
                      "VALUES (%s, 3000000, %s, '2026-10-01', %s, NULL)", (incident, paid, status))
    f.insert("compensation_case", "case_id", incident_id=incident, amount_due=3000000, due_by="2026-10-01")
    _insert_fails(f.c, psycopg.errors.UniqueViolation,
                  "INSERT INTO compensation_case (incident_id, amount_due, due_by) VALUES (%s, 1, '2026-10-01')", (incident,))
