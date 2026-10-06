import pytest

from zeroentry.seed import run_seed

PASSWORD = "Demo-Password-77"


def _seed(db, **kw):
    return run_seed(db.owner_url, PASSWORD, bcrypt_rounds=4, **kw)


def test_seed_creates_the_documented_demo_world(db, conn):
    counts = _seed(db)
    assert counts == {"ulb": 3, "manhole": 60, "contractor": 5, "worker": 40, "machine": 4, "gas_detector": 2, "app_user": 6}
    q = lambda sql: conn.execute(sql).fetchone()["n"]  # noqa: E731
    assert q("SELECT count(*) AS n FROM gas_detector WHERE calibration_valid_until < '2026-10-01'") == 1
    assert q("SELECT count(*) AS n FROM manhole WHERE kind = 'SEPTIC'") == 12
    assert q("SELECT count(DISTINCT contractor_id) AS n FROM worker") == 5
    assert q("SELECT count(*) AS n FROM worker WHERE medical_fit_until < '2026-10-01'") == 2   # demo: CREW_FIT failures
    assert q("SELECT count(*) AS n FROM worker WHERE trained_until < '2026-10-01'") == 1


def test_seed_is_idempotent(db):
    first = _seed(db)
    assert _seed(db) == first


def test_demo_users_are_scoped_hashed_and_cover_all_six_roles(db, conn):
    _seed(db)
    rows = conn.execute("""SELECT r.name AS role, u.email, u.password_hash, u.contractor_id, u.worker_id
                           FROM app_user u JOIN role r USING (role_id) ORDER BY r.name""").fetchall()
    assert [r["role"] for r in rows] == ["ADMIN", "AUDITOR", "CONTRACTOR", "ENGINEER", "SUPERVISOR", "WORKER"]
    assert all(r["email"].endswith("@zeroentry.example") for r in rows)
    assert all(r["password_hash"].startswith("$2") and PASSWORD not in r["password_hash"] for r in rows)
    by_role = {r["role"]: r for r in rows}
    assert by_role["CONTRACTOR"]["contractor_id"] is not None and by_role["WORKER"]["worker_id"] is not None
    assert by_role["ADMIN"]["contractor_id"] is None


def test_the_demo_scenarios_produce_exactly_the_detections_the_story_promises(db, conn):
    _seed(db)
    assert conn.execute("SELECT count(*) AS n FROM complaint").fetchone()["n"] == 11
    scan = conn.execute("SELECT * FROM scan_shadow_entries(now())").fetchone()
    assert scan == {"opened": 5, "moved_to_review": 0, "pending_in_grace": 1}          # S1-S4 open, S5 late evidence; S7 pending
    by_status = {r["status"]: r["n"] for r in conn.execute("SELECT status, count(*) AS n FROM shadow_entry_alert GROUP BY status")}
    assert by_status == {"OPEN": 4, "EVIDENCE_RECEIVED": 1}
    assert conn.execute("SELECT count(DISTINCT invoice_id) AS n FROM invoice_hold WHERE reason = 'SHADOW_ENTRY' AND released_at IS NULL").fetchone()["n"] == 4
    # nothing that should be silent was flagged: the normal job, the exempt resolutions, the lawful manual clearance, the demo draft
    flagged = {r["description"].removeprefix("[seed] ") for r in conn.execute(
        "SELECT c.description FROM shadow_entry_alert a JOIN complaint c USING (complaint_id)")}
    assert flagged == {                                                             # exactly these five, and nothing that should be silent
        "Foul smell and slow flow near the school gate", "Manhole cover surcharging after rain", "Blockage in the lane behind the temple",
        "Septic tank overflowing into the street drain", "Overflow at the market junction"}
    assert conn.execute("SELECT count(*) AS n FROM shadow_entry_alert WHERE rule_code = 'SE2_ENTRANT_NOT_LOGGED'").fetchone()["n"] == 0
    assert conn.execute("SELECT * FROM scan_shadow_entries(now())").fetchone()["opened"] == 0         # idempotent


def test_the_demo_world_has_a_lawful_permit_a_denied_draft_and_consequences_on_record(db, conn):
    _seed(db)
    permits = {r["status"]: r["n"] for r in conn.execute("SELECT status, count(*) AS n FROM entry_permit GROUP BY status")}
    assert permits == {"CLOSED": 1, "DRAFT": 1}                                        # the closed one went through the real gate
    draft = conn.execute("SELECT * FROM v_permit_compliance").fetchone()
    assert draft["ready_to_authorise"] is False
    assert set(draft["failing_clauses"].split(", ")) == {"CREW_STANDBY", "GEAR_ALL", "GAS_TOP", "GAS_MID", "GAS_BOTTOM"}
    status = {r["licence_no"]: r["status"] for r in conn.execute("SELECT licence_no, status FROM contractor")}
    assert status["TN-SAN-2026-004"] == "BLACKLISTED" and status["TN-SAN-2026-005"] == "SUSPENDED" and status["TN-SAN-2026-001"] == "ACTIVE"
    overdue = conn.execute("SELECT count(*) AS n, sum(amount_outstanding) AS owed FROM v_compensation_overdue").fetchone()
    assert overdue["n"] == 2 and overdue["owed"] == 2_000_000 + 3_000_000 - 1_000_000        # part-paid death + unpaid disability
    assert conn.execute("SELECT count(*) AS n FROM incident WHERE incident_type = 'NEAR_MISS'").fetchone()["n"] == 1


def test_seed_refuses_production_placeholders_and_weak_passwords(db):
    with pytest.raises(RuntimeError, match="production"):
        _seed(db, app_env="production")
    with pytest.raises(ValueError, match="CHANGE_ME"):
        run_seed(db.owner_url, "CHANGE_ME-Placeholder-1", bcrypt_rounds=4)
    with pytest.raises(ValueError, match="at least 12"):
        run_seed(db.owner_url, "Weak1", bcrypt_rounds=4)
