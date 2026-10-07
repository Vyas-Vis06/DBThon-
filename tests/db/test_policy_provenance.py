"""Policy source classification, append-only revisions, and permit decision snapshots."""

import hashlib
import json
import threading
from datetime import timedelta

from tests.factories import Factory, yesterday_ist
from tests.helpers import act_as, expect


def test_threshold_sources_distinguish_law_guidance_and_product_policy(conn):
    rows = conn.execute(
        "SELECT rp.param_key, rp.value, rp.is_assumption, rp.revision, ps.source_type, ps.source_url, "
        "ps.citation_clause, ps.applicability "
        "FROM rule_parameter rp JOIN policy_source ps USING (source_code)"
    ).fetchall()
    params = {row["param_key"]: row for row in rows}

    assert params["min_crew_size"]["source_type"] == "LAW"
    assert "6(3)(a)" in params["min_crew_size"]["citation_clause"]
    assert params["gas_o2_min"]["source_type"] == "LAW"
    assert params["gas_o2_max"]["source_type"] == "GUIDANCE"
    assert "CPHEEO" in params["gas_o2_max"]["applicability"]
    assert "ambiguous" in params["gas_o2_min"]["applicability"]
    assert params["gas_h2s_max_ppm"]["source_type"] == "GUIDANCE"
    assert params["gas_lel_max_pct"]["source_type"] == "GUIDANCE"
    assert params["gas_co_max_ppm"]["source_type"] == "PRODUCT_POLICY"
    assert "spot-reading" in params["gas_co_max_ppm"]["applicability"]
    assert params["gas_max_age_min"]["source_type"] == "PRODUCT_POLICY"
    assert params["gas_max_age_min"]["is_assumption"] is True
    assert params["gas_max_age_min"]["value"] == 15
    assert "15-minute" in params["gas_max_age_min"]["applicability"]
    assert params["mandatory_rest_minutes"]["source_type"] == "LAW"
    assert params["mandatory_rest_minutes"]["value"] == 30
    assert "6(3)(k)(ii)" in params["mandatory_rest_minutes"]["citation_clause"]

    gas_sources = conn.execute(
        "SELECT DISTINCT ps.source_type FROM legal_clause_source lcs "
        "JOIN policy_source ps USING (source_code) WHERE lcs.clause_code = 'GAS_TOP'"
    ).fetchall()
    assert {row["source_type"] for row in gas_sources} == {"LAW", "GUIDANCE", "PRODUCT_POLICY"}

    waiver = conn.execute(
        "SELECT ps.source_type, ps.applicability FROM legal_clause_source lcs "
        "JOIN policy_source ps USING (source_code) WHERE lcs.clause_code = 'MECH_WAIVER'"
    ).fetchone()
    assert waiver["source_type"] == "PRODUCT_POLICY"
    assert "stricter product workflow" in waiver["applicability"]


def test_rule_parameter_edits_require_reason_and_append_revision(db, conn):
    admin_id = Factory(conn).user("ADMIN")
    with db.connect(user="ze_app") as app:
        act_as(app, admin_id, "ADMIN")
        with expect("ZE002", "10 characters"):
            app.execute(
                "UPDATE rule_parameter SET value = 11 "
                "WHERE param_key = 'gas_h2s_max_ppm'",
            )

        app.execute(
            "SELECT set_config('app.rule_change_reason', %s, false)",
            ("Updated after reviewed field calibration guidance",),
        )
        app.execute(
            "UPDATE rule_parameter SET value = 11 "
            "WHERE param_key = 'gas_h2s_max_ppm'",
        )
        history = app.execute(
            "SELECT revision, value, source_code, actor_user_id, change_reason, effective_at "
            "FROM rule_parameter_history WHERE param_key = 'gas_h2s_max_ppm' ORDER BY revision"
        ).fetchall()
        assert [row["revision"] for row in history] == [1, 2]
        assert history[0]["change_reason"].startswith("Initial provenance baseline")
        assert history[1]["value"] == 11
        assert history[1]["source_code"] == "GUIDANCE_GAS_THRESHOLDS"
        assert history[1]["actor_user_id"] == admin_id
        assert history[1]["change_reason"] == "Updated after reviewed field calibration guidance"
        assert history[1]["effective_at"] is not None

        with expect("42501"):
            app.execute(
                "UPDATE rule_parameter SET updated_by = %s WHERE param_key = 'gas_h2s_max_ppm'",
                (admin_id,),
            )
        with expect("42501"):
            app.execute(
                "UPDATE rule_parameter SET updated_at = now() WHERE param_key = 'gas_h2s_max_ppm'"
            )

        with expect("42501"):
            app.execute(
                "UPDATE rule_parameter_history SET change_reason = 'rewritten history' "
                "WHERE param_key = 'gas_h2s_max_ppm'"
            )


def test_successful_authorisation_stores_hashable_immutable_evidence_snapshot(conn):
    f = Factory(conn)
    s = f.gate_scenario(yesterday_ist())
    result = conn.execute(
        "SELECT * FROM authorise_entry(%s, %s, %s)",
        (s["permit"], s["supervisor"], s["at"]),
    ).fetchall()
    assert result and all(row["passed"] for row in result)

    decision = conn.execute(
        "SELECT permit_id, actor_user_id, decision_at, snapshot, snapshot::text AS snapshot_text, snapshot_sha256 "
        "FROM permit_authorization_decision WHERE permit_id = %s",
        (s["permit"],),
    ).fetchone()
    snapshot = decision["snapshot"]
    assert decision["actor_user_id"] == s["supervisor"]
    assert decision["decision_at"] == s["at"]
    assert decision["snapshot_sha256"] == hashlib.sha256(decision["snapshot_text"].encode("utf-8")).hexdigest()
    assert snapshot["format"] == "zeroentry.permit-authorization-decision.v1"
    assert {clause["clause_code"] for clause in snapshot["gate"]} == {
        "MECH_WAIVER", "CONTRACTOR_OK", "CREW_ENTRANT", "CREW_SUPERVISOR", "CREW_STANDBY",
        "CREW_SIZE", "CREW_FIT", "GEAR_ALL", "GAS_TOP", "GAS_MID", "GAS_BOTTOM",
    }
    assert all(clause["passed"] and clause["detail"] for clause in snapshot["gate"])
    assert all(clause["sources"] for clause in snapshot["gate"])

    evidence = snapshot["evidence"]
    assert evidence["waiver"]["waiver_id"] == s["waiver"]
    assert evidence["contractor"]["contractor_id"] == s["contractor"]
    assert {member["crew_role"] for member in evidence["crew"]} == {"ENTRANT", "SUPERVISOR", "STANDBY"}
    assert all(member["gear_issues"] for member in evidence["crew"] if member["crew_role"] == "ENTRANT")
    readings = {row["depth_level"]: row for row in evidence["latest_gas_readings_by_depth"]}
    assert set(readings) == {"TOP", "MID", "BOTTOM"}
    assert all(readings[level]["reading_id"] for level in readings)
    params = {row["param_key"]: row for row in snapshot["policy_parameters"]}
    assert params["gas_max_age_min"]["value"] == 15
    assert params["gas_max_age_min"]["is_assumption"] is True
    assert params["mandatory_rest_minutes"]["value"] == 30

    old_text, old_hash = decision["snapshot_text"], decision["snapshot_sha256"]
    # Later policy and evidence changes do not rewrite the authorization explanation already made.
    conn.execute("UPDATE rule_parameter SET value = 9 WHERE param_key = 'gas_h2s_max_ppm'")
    f.reading(
        s["permit"], s["detector"], "TOP", s["at"] + timedelta(minutes=10),
        s["supervisor"], h2s=1,
    )
    same = conn.execute(
        "SELECT snapshot::text AS snapshot_text, snapshot_sha256 FROM permit_authorization_decision WHERE permit_id = %s",
        (s["permit"],),
    ).fetchone()
    assert (same["snapshot_text"], same["snapshot_sha256"]) == (old_text, old_hash)
    assert json.loads(same["snapshot_text"])["evidence"]["latest_gas_readings_by_depth"] == evidence["latest_gas_readings_by_depth"]

    with expect("ZE003", "append-only"):
        conn.execute("UPDATE permit_authorization_decision SET snapshot_sha256 = '0' WHERE permit_id = %s", (s["permit"],))
    with expect("ZE003", "append-only"):
        conn.execute("DELETE FROM permit_authorization_decision WHERE permit_id = %s", (s["permit"],))


def test_gate_denial_does_not_create_success_authorization_artifact(conn):
    s = Factory(conn).gate_scenario(yesterday_ist(), readings={"BOTTOM": None})
    result = conn.execute(
        "SELECT * FROM authorise_entry(%s, %s, %s)",
        (s["permit"], s["supervisor"], s["at"]),
    ).fetchall()
    assert any(not row["passed"] for row in result)
    assert conn.execute(
        "SELECT count(*) AS n FROM permit_authorization_decision WHERE permit_id = %s",
        (s["permit"],),
    ).fetchone()["n"] == 0


def test_runtime_raw_authorization_cannot_backdate_its_gate_timestamp(db, conn):
    s = Factory(conn).gate_scenario(yesterday_ist())
    with db.connect(user="ze_app") as app:
        act_as(app, s["supervisor"], "SUPERVISOR")
        with expect("ZE001"):
            app.execute(
                "UPDATE entry_permit SET status = 'AUTHORISED', authorised_at = %s, authorised_by = %s "
                "WHERE permit_id = %s",
                (s["at"], s["supervisor"], s["permit"]),
            )

    assert conn.execute(
        "SELECT status FROM entry_permit WHERE permit_id = %s", (s["permit"],)
    ).fetchone()["status"] == "DRAFT"
    assert conn.execute(
        "SELECT count(*) AS n FROM permit_authorization_decision WHERE permit_id = %s", (s["permit"],)
    ).fetchone()["n"] == 0


def test_policy_change_waits_for_authorization_snapshot(db):
    with db.connect() as setup:
        s = Factory(setup).gate_scenario(yesterday_ist())
    with db.connect(autocommit=False) as decider:
        decider.execute("SELECT * FROM authorise_entry(%s, %s, %s)", (s["permit"], s["supervisor"], s["at"]))
        started = threading.Event()
        outcome = {}

        def update_policy():
            try:
                with db.connect() as updater:
                    started.set()
                    updater.execute("UPDATE rule_parameter SET value = 11 WHERE param_key = 'gas_h2s_max_ppm'")
                outcome["ok"] = True
            except Exception as exc:  # report a background-thread failure in the main test thread
                outcome["error"] = exc

        thread = threading.Thread(target=update_policy)
        thread.start()
        assert started.wait(timeout=5)
        thread.join(timeout=0.5)
        assert thread.is_alive() and not outcome  # the authorization holds a share lock on active thresholds
        decider.commit()

    thread.join(timeout=10)
    assert not thread.is_alive() and outcome == {"ok": True}
    with db.connect() as check:
        decision = check.execute(
            "SELECT snapshot FROM permit_authorization_decision WHERE permit_id = %s", (s["permit"],)
        ).fetchone()
        snapshot_params = {row["param_key"]: row for row in decision["snapshot"]["policy_parameters"]}
        assert snapshot_params["gas_h2s_max_ppm"]["value"] == 10
        assert check.execute(
            "SELECT value FROM rule_parameter WHERE param_key = 'gas_h2s_max_ppm'"
        ).fetchone()["value"] == 11
