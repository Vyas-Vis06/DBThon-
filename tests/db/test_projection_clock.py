"""Natural wall-clock passage, without evidence/policy writes, needs reconciliation."""

from tests.factories import Factory, yesterday_ist


def test_grace_expires_by_time_alone_and_sweep_restores_projection_equality(conn):
    scenario = Factory(conn).gate_scenario(yesterday_ist())
    conn.execute("UPDATE rule_parameter SET value=1 WHERE param_key='shadow_grace_hours'")
    conn.execute("UPDATE complaint SET status='RESOLVED', raised_at=clock_timestamp()-interval '2 days', "
                 "resolved_at=clock_timestamp()-interval '1 hour'+interval '1 second', "
                 "resolution_code='CLEARED',resolved_by=%s WHERE complaint_id=%s",
                 (scenario["engineer"], scenario["complaint"]))
    claim = conn.execute("INSERT INTO completion_claim(source_ulb_id,source,external_id,external_job_ref,matched_job_id,"
                         "claimed_status,claimed_at,match_status,payload) "
                         "VALUES(%s,'EDU_CLOCK','natural-expiry','explicit synthetic job link',%s,'COMPLETED',clock_timestamp(),'MATCHED','{}') "
                         "RETURNING claim_id", (scenario["ulb"], scenario["job"])).fetchone()["claim_id"]
    before = conn.execute("SELECT gap_codes,evidence_revision FROM completion_projection WHERE job_id=%s",
                          (scenario["job"],)).fetchone()
    assert before["gap_codes"] == [{"claim_id": claim, "gap_code": "WITHIN_GRACE"}]
    # The database's own clock passes the deadline; no source or parameter is changed here.
    conn.execute("SELECT pg_sleep(1.2)")
    assert conn.execute("SELECT gap_code FROM v_completion_claim_reference WHERE claim_id=%s",
                        (claim,)).fetchone()["gap_code"] == "COMPLETION_EVIDENCE_MISSING"
    assert conn.execute("SELECT gap_codes FROM completion_projection WHERE job_id=%s",
                        (scenario["job"],)).fetchone()["gap_codes"] == before["gap_codes"]
    conn.execute("SELECT * FROM sweep_completion_projections(0,500)")
    after = conn.execute("SELECT gap_codes,evidence_revision FROM completion_projection WHERE job_id=%s",
                         (scenario["job"],)).fetchone()
    assert after["gap_codes"] == [{"claim_id": claim, "gap_code": "COMPLETION_EVIDENCE_MISSING"}]
    assert after["evidence_revision"] > before["evidence_revision"]
