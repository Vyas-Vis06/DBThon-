"""scripts/evaluate.py stays runnable and its claims hold, at a tiny scale. Only counts are asserted: timings vary by machine."""

import importlib.util

from tests.conftest import ROOT

spec = importlib.util.spec_from_file_location("evaluate", ROOT / "scripts" / "evaluate.py")
evaluate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluate)


def test_zeroentry_detection_is_exact_on_every_labelled_class_and_the_naive_anti_join_is_not(conn):
    evaluate.prepare(conn)
    result = evaluate.detection_accuracy(conn, per_class=2)
    for row in result["classes"]:
        assert row["zeroentry"] == (row["n"] if row["expected"] else 0), row
    zero, naive = result["summary"]["ZeroEntry"], result["summary"]["naive"]
    assert (zero["tp"], zero["fp"], zero["fn"]) == (8, 0, 0)
    # The naive query flags retried, exempt and in-grace complaints and misses the no-job and unlogged-entrant ones.
    assert (naive["tp"], naive["fp"], naive["fn"]) == (4, 6, 4)
    assert result["late"] == {"n": 2, "zeroentry_kept_for_review": 2, "naive_silently_cleared": 2}


def test_every_invalid_write_is_refused_by_zeroentry_and_only_the_unique_constraint_stops_the_baseline(conn):
    rows = evaluate.enforcement(conn)
    assert len(rows) == len(evaluate.ATTACKS) == 18
    assert [r["rule"] for r in rows if not r["zeroentry"]["refused"]] == []
    assert [r["rule"] for r in rows if r["baseline"]["refused"]] == ["BR-34"]
    assert all(r["zeroentry"]["sqlstate"].startswith("ZE") for r in rows if r["rule"] != "BR-34")
    rest = next(r for r in rows if r["rule"] == "BR-10")
    assert "rest for 30 minutes" in rest["zeroentry"]["message"]
    assert rest["baseline"] == {"refused": False, "sqlstate": None, "message": "accepted"}


def test_detection_reads_the_grace_parameter_once_per_statement_not_once_per_row(conn):
    """Migration 0011: a materialised CTE, not rule_num() inlined into the anti-join filters (12x slower scan at 100k complaints)."""
    plan = "\n".join(r["QUERY PLAN"] for r in conn.execute("EXPLAIN SELECT count(*) FROM v_shadow_candidate"))
    assert plan.count("CTE Scan on g") == 2                     # SE1 and SE2; before 0011 the CTE was inlined (no CTE Scan)


def test_the_history_generator_goes_through_the_real_gate_and_the_measurements_run(conn):
    evaluate.prepare(conn)
    rows = evaluate.performance(conn, [200, 400], reps=(2, 2), timeout_s=30)
    last = rows[-1]
    n = lambda q: conn.execute(q).fetchone()["n"]  # noqa: E731
    assert n("SELECT count(*) AS n FROM entry_permit WHERE status = 'CLOSED'") == 20          # 5 % of 400, all authorised
    assert n("SELECT count(*) AS n FROM entry_log") == 40                                   # two logged entrants each
    assert n("""SELECT count(*) AS n FROM machine_deployment d JOIN job j USING (job_id)
                 JOIN complaint c USING (complaint_id) WHERE c.description = 'Synthetic history'
                   AND d.outcome_recorded_at IS DISTINCT FROM d.recorded_at""") == 0
    assert n("""SELECT count(*) AS n FROM entry_log e JOIN entry_permit p USING (permit_id)
                 JOIN job j USING (job_id) JOIN complaint c USING (complaint_id)
                WHERE c.description = 'Synthetic history (manual)'
                  AND (e.recorded_at IS DISTINCT FROM upper(e.period) + interval '5 minutes'
                    OR e.exit_recorded_at IS DISTINCT FROM upper(e.period) + interval '5 minutes')""") == 0
    assert last["complaints"] == 401 and last["permits"] == 21                              # plus the probe permit
    assert last["naive_flagged"] > last["zeroentry_candidates"] > 0                          # exempt resolutions inflate naive
    assert last["decision"]["median_ms"] > 0 and last["detect_plan"]["buffers"] > 0
