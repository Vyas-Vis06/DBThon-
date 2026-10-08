"""The incrementally maintained job projection must equal the complaint-anchored reference anti-join."""

from datetime import datetime, timedelta, timezone

from tests.factories import Factory


def _claim(conn, scenario, external_id):
    return conn.execute(
        "INSERT INTO completion_claim(source_ulb_id,source,external_id,external_job_ref,matched_job_id,claimed_status,claimed_at) "
        "VALUES(%s,'SYNTHETIC_TEST',%s,%s,%s,'COMPLETED',clock_timestamp()) RETURNING claim_id",
        (scenario["ulb"], external_id, f"external-{external_id}", scenario["job"]),
    ).fetchone()["claim_id"]


def _assert_projection_matches_reference(conn, job_id):
    row = conn.execute(
        "SELECT p.gap_codes,p.has_gap,COALESCE((SELECT jsonb_agg(jsonb_build_object('claim_id',r.claim_id,'gap_code',r.gap_code) "
        "ORDER BY r.claim_id) FROM v_completion_claim_reference r WHERE r.matched_job_id=p.job_id AND r.gap_code IS NOT NULL),'[]'::jsonb) AS reference "
        "FROM completion_projection p WHERE p.job_id=%s", (job_id,),
    ).fetchone()
    assert row is not None
    assert row["gap_codes"] == row["reference"]
    assert row["has_gap"] == bool(row["reference"])
    return row["gap_codes"]


def test_claim_and_evidence_changes_refresh_projection_to_reference(conn):
    f = Factory(conn)
    s = f.gate_scenario(datetime.now(timezone.utc) - timedelta(days=4))
    resolved_at = datetime.now(timezone.utc) - timedelta(days=2)
    conn.execute("UPDATE complaint SET status='RESOLVED',raised_at=%s,resolved_at=%s,resolution_code='CLEARED',resolved_by=%s WHERE complaint_id=%s",
                 (resolved_at-timedelta(days=1),resolved_at, s["engineer"], s["complaint"]))
    claim_id = _claim(conn, s, "projection-evidence")
    gaps = _assert_projection_matches_reference(conn, s["job"])
    assert gaps == [{"claim_id": claim_id, "gap_code": "COMPLETION_EVIDENCE_MISSING"}]
    projection_before = conn.execute("SELECT evidence_revision FROM completion_projection WHERE job_id=%s", (s["job"],)).fetchone()["evidence_revision"]

    # A finalized machine result arriving after the 24-hour deadline changes the derived gap to human review,
    # never to a clean closure. The source trigger must update only this job's projection.
    f.deployment(s["job"], s["machine"], "CLEARED", started_at=resolved_at + timedelta(hours=1))
    gaps = _assert_projection_matches_reference(conn, s["job"])
    assert gaps == [{"claim_id": claim_id, "gap_code": "LATE_EVIDENCE_HUMAN_REVIEW"}]
    assert conn.execute("SELECT evidence_revision FROM completion_projection WHERE job_id=%s", (s["job"],)).fetchone()["evidence_revision"] > projection_before


def test_time_sweep_recomputes_grace_without_a_source_row_mutation(conn):
    f = Factory(conn)
    s = f.gate_scenario(datetime.now(timezone.utc) - timedelta(hours=2))
    resolved_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    conn.execute("UPDATE rule_parameter SET value=1 WHERE param_key='shadow_grace_hours'")
    conn.execute("UPDATE complaint SET status='RESOLVED',raised_at=%s,resolved_at=%s,resolution_code='CLEARED',resolved_by=%s WHERE complaint_id=%s",
                 (resolved_at-timedelta(days=1),resolved_at, s["engineer"], s["complaint"]))
    _claim(conn, s, "projection-grace")
    assert _assert_projection_matches_reference(conn, s["job"])[0]["gap_code"] == "WITHIN_GRACE"

    # No claim/evidence row changed. A zero-hour policy means the current-time result is now overdue;
    # the bounded sweep is the required time-driven refresh path.
    conn.execute("UPDATE rule_parameter SET value=0 WHERE param_key='shadow_grace_hours'")
    sweep = conn.execute("SELECT * FROM sweep_completion_projections(0,500)").fetchone()
    assert sweep["processed_count"] >= 1 and sweep["has_more"] is False
    assert _assert_projection_matches_reference(conn, s["job"])[0]["gap_code"] == "COMPLETION_EVIDENCE_MISSING"


def test_projection_sweep_cursor_advances_in_bounded_job_order(conn):
    f = Factory(conn)
    scenarios = [f.gate_scenario(datetime.now(timezone.utc)-timedelta(days=3)) for _ in range(3)]
    for s in scenarios:
        conn.execute("UPDATE complaint SET status='RESOLVED',raised_at=clock_timestamp()-interval '3 days',resolved_at=clock_timestamp()-interval '2 days',"
                     "resolution_code='CLEARED',resolved_by=%s WHERE complaint_id=%s", (s["engineer"], s["complaint"]))
        _claim(conn, s, f"projection-cursor-{s['job']}")
    ids = sorted(s["job"] for s in scenarios)
    first = conn.execute("SELECT * FROM sweep_completion_projections(0,1)").fetchone()
    second = conn.execute("SELECT * FROM sweep_completion_projections(%s,1)", (first["next_after_job_id"],)).fetchone()
    assert first["processed_count"] == second["processed_count"] == 1
    assert first["has_more"] is True and second["next_after_job_id"] > first["next_after_job_id"]
    assert first["next_after_job_id"] in ids and second["next_after_job_id"] in ids
    for job_id in ids:
        _assert_projection_matches_reference(conn, job_id)
