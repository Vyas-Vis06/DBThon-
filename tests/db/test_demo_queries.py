"""Every documented query file runs against the seeded demo database and says what the docs claim it says."""

from pathlib import Path

import psycopg
import pytest
from psycopg.rows import tuple_row

from zeroentry.seed import run_seed
from tests.factories import Factory, yesterday_ist

QUERIES = sorted((Path(__file__).resolve().parents[2] / "database" / "queries").glob("*.sql"))


def run_script(conn, path: Path):
    """Execute a whole .sql file; return [(columns, rows)] for every result set and the list of NOTICE messages."""
    notices: list[str] = []
    conn.add_notice_handler(lambda n: notices.append(n.message_primary))
    cur = conn.cursor(row_factory=tuple_row)                                  # positional access: result sets have many shapes
    cur.execute(path.read_text(encoding="utf-8"))
    results = []
    while True:
        if cur.description:
            results.append(([c.name for c in cur.description], cur.fetchall()))
        if not cur.nextset():
            break
    return results, notices


@pytest.fixture
def demo(db, conn):
    run_seed(db.owner_url, "Demo-Password-77", bcrypt_rounds=4)
    conn.execute("SELECT * FROM scan_shadow_entries(now())")
    return conn


def q(demo, name):
    return run_script(demo, next(p for p in QUERIES if p.name.startswith(name)))


def test_there_is_a_documented_query_file_for_each_topic():
    assert [p.name[:2] for p in QUERIES] == ["01", "02", "03", "04", "05", "06", "07", "08"]


@pytest.mark.parametrize("path", QUERIES, ids=lambda p: p.name)
def test_every_query_file_runs_cleanly(demo, path):
    results, notices = run_script(demo, path)
    assert results or notices, "a query file should print a result set or a NOTICE"


def test_joins_show_the_dossier_the_missing_gear_and_the_evidence_picture(demo):
    results, _ = q(demo, "01")
    dossier, crew, gear, readings, evidence, consequences, holds = (rows for _, rows in results)
    assert [r[1] for r in dossier] == ["CLOSED", "DRAFT"] and len(crew) == 7
    assert sum(1 for r in gear if r[2] == "** MISSING **") == 2                       # the demo permit lacks harness + breathing apparatus
    assert len(readings) == 3                                                          # the lawful permit's TOP/MID/BOTTOM
    by_complaint = {r[0]: r for r in evidence}
    assert any(r[4] == 0 and r[5] == 1 and r[6] == 0 for r in evidence)                # machine FAILED, nothing else, yet "cleared"
    assert len(consequences) == 3 and {r[1] for r in consequences} == {"FATALITY", "DISABILITY", "NEAR_MISS"}
    assert len(holds) == 4 and by_complaint                                            # S1, S2, S4, S5 each hold an invoice


def test_aggregates_match_the_seeded_world(demo):
    results, _ = q(demo, "02")
    summary, by_zone, money, gas, invoices, kpi, incidents, risk, alerts = (rows for _, rows in results)
    assert summary[0][0] == 11 and summary[0][1] == 10
    assert money[0][0] == 2 and money[0][1] == 5_000_000 and money[0][2] == 1_000_000
    assert {r[0] for r in gas} == {"TOP", "MID", "BOTTOM"}
    assert risk[0][0] == "Adyar Hydro Services" and risk[0][-1] >= 12                  # the contractor with the death on record
    assert sum(r[2] for r in alerts) == 5


def test_search_queries_use_the_documented_filters(demo):
    results, _ = q(demo, "03")
    workers_by_id, workers_by_name, permits, complaints, alerts, lapsing, trail = (rows for _, rows in results)
    assert len(workers_by_id) == 10 and all(r[2].startswith("NAM-TN-1000") for r in workers_by_id)
    assert all(r[1].lower().startswith("a") for r in workers_by_name) and workers_by_name
    assert len(permits) == 1 and len(alerts) == 5 and len(lapsing) >= 3 and trail          # the synthetic EDU permit is outside city ULB filters


def test_division_and_anti_join_queries_find_exactly_what_the_story_promises(demo):
    results, _ = q(demo, "04")
    gear_division, depth_division, anti_join, set_algebra, se2, clauses, readiness, suspected = (rows for _, rows in results)
    assert [r[1] for r in gear_division] == ["NAM-TN-100002"]                          # the entrant short of two statutory items
    assert [r[1] for r in depth_division] == ["BOTTOM", "MID", "TOP"]                  # no readings logged at any depth
    assert len(anti_join) == 5 and [r[0] for r in anti_join] == [r[0] for r in set_algebra]   # two formulations, one answer
    assert se2 == []
    assert len(clauses) == 18 and sum(1 for r in clauses if not r[2]) == 11
    assert len(readiness) == 1 and readiness[0][5] is False
    assert len(suspected) == 6                                                         # 5 alerts + 1 pending inside the grace window


def test_catalogue_lists_the_routines_and_triggers(demo):
    results, _ = q(demo, "05")
    routines, triggers = results[-2][1], results[-1][1]
    names = {r[0] for r in routines}
    assert {"permit_clause_check", "authorise_entry", "scan_shadow_entries", "record_incident", "review_shadow_alert"} <= names
    assert any(r[1] == "procedure" for r in routines) and any(r[2] == "definer" for r in routines)
    assert len(triggers) >= 40


def test_the_transaction_demo_changes_nothing_in_the_end(demo):
    results, notices = q(demo, "06")
    moments = {r[0][0]: r[0] for _, r in results if r and r[0] and isinstance(r[0][0], str)}
    before, inside, after = moments["BEFORE"], moments["INSIDE TRANSACTION"], moments["AFTER ROLLBACK"]
    assert inside[1] == before[1] + 1 and inside[2] == before[2] + 1 and inside[3] == before[3] + 1       # all three effects together
    assert before[1:] == after[1:]                                                                            # ...and all gone after ROLLBACK
    assert inside[4] == 3_000_000
    assert any("failed as intended" in n for n in notices)
    assert moments["AFTER FAILED CALL"][1:] == (before[1], before[2])
    assert demo.execute("SELECT value FROM rule_parameter WHERE param_key = 'compensation_fatality_inr'").fetchone()["value"] == 3_000_000


def test_every_trigger_refusal_is_demonstrated_and_nothing_changes(demo):
    counts = lambda: demo.execute("SELECT (SELECT count(*) FROM audit_log) a, (SELECT count(*) FROM gas_reading) g, "  # noqa: E731
                                  "(SELECT count(*) FROM entry_permit WHERE status = 'AUTHORISED') p").fetchone()
    before = counts()
    _, notices = q(demo, "07")
    assert before == counts()
    assert len(notices) == 9 and all("refused" in n for n in notices), notices
    assert "Entry denied" in notices[0] and "calibration expired" in notices[1]


def test_cursor_rowtype_loop_and_assertion_trigger_lab_runs_without_persistent_changes(conn):
    Factory(conn).gate_scenario(yesterday_ist())
    before = conn.execute("SELECT count(*) AS n FROM entry_permit").fetchone()["n"]
    results, notices = q(conn, "08")
    assert sum("cursor visited" in n for n in notices) == before
    assert any(f"cursor loop completed with {before} permit rows" in n for n in notices)
    assert sum("assertion-style trigger refused" in n for n in notices) == 2
    assert results[0][1] == [("REFUSED_ACTIVATION", False, 0)]
    assert results[-1][1] == [("VALID_STATE_RETAINED", True, 1)]
    assert conn.execute("SELECT count(*) AS n FROM entry_permit").fetchone()["n"] == before
