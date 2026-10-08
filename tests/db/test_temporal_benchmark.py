"""Temporal benchmark must measure real scoped rows, not empty RLS-filtered output."""

import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "ze_temporal_benchmark", Path(__file__).resolve().parents[2] / "scripts/evaluate_temporal.py")
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def test_temporal_benchmark_has_explicit_stored_engineer_scope_and_expected_cases(conn, db):
    engineer, ulb, labels = benchmark.fixture(conn, 12)
    assert conn.execute("SELECT ulb_id FROM app_user WHERE user_id=%s", (engineer,)).fetchone()["ulb_id"] == ulb
    with db.connect(user="ze_app") as runtime:
        runtime.execute("SELECT set_config('app.role','ENGINEER',false), set_config('app.user_id',%s,false), "
                        "set_config('app.ulb_id',%s,false)", (str(engineer), str(ulb)))
        assert runtime.execute("SELECT count(*) AS n FROM complaint").fetchone()["n"] == 12
        predicted = {row["complaint_id"] for row in runtime.execute(benchmark.ADVANCED)}
        confusion = benchmark.confusion(labels, predicted)
        assert (confusion["tp"], confusion["fp"], confusion["tn"], confusion["fn"]) == (6, 0, 6, 0)
        first = runtime.execute("SELECT * FROM scan_shadow_entries(now())").fetchone()
        again = runtime.execute("SELECT * FROM scan_shadow_entries(now())").fetchone()
        assert first["opened"] == 6 and again["opened"] == 0
