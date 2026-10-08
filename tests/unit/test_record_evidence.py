"""Evidence publication must use a successful, source-bound multilayer test run."""

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/record_evidence.py"


@pytest.fixture
def recorder(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("ze_test_record_evidence", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    versions = tmp_path / "database/migrations/versions"
    versions.mkdir(parents=True)
    (versions / "0016_example.py").write_text("# controlled fixture\n")
    (tmp_path / "database/queries").mkdir()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "source_fingerprint", lambda: "current-source")
    report = tmp_path / "run.xml"
    report.with_suffix(".source.json").write_text(json.dumps({
        "source_sha256": "current-source", "pytest_exit_code": 0,
    }))
    return module, report


def test_manifest_uses_actual_counts_and_does_not_invent_lab_proofs(recorder):
    module, report = recorder
    report.write_text('''<testsuites><testsuite>
      <testcase classname="tests.db.test_schema" name="test_real_constraint"/>
      <testcase classname="tests.api.test_workflow" name="test_real_route"/>
      <testcase classname="tests.unit.test_config" name="test_real_config"/>
      <testcase classname="tests.browser.test_workflows" name="test_real_browser"/>
      <testcase classname="tests.unit.test_optional" name="test_unavailable"><skipped/></testcase>
    </testsuite></testsuites>''')
    manifest = module.build(report)
    assert manifest["summary"] == {"total": 5, "passed": 4, "failed": 0, "errors": 0,
                                    "skipped": 1, "browser_passed": 1}
    assert manifest["schema_revision"] == "0016"
    assert next(row for row in manifest["labs"] if row["id"] == "LAB1-DDL")["status"] == "TESTED"
    assert next(row for row in manifest["labs"] if row["id"] == "LAB6-PROC")["status"] == "NOT_YET_MEASURED"


@pytest.mark.parametrize("xml", [
    '<testsuites/>',
    '<testsuite><testcase classname="tests.db.only" name="test_one"/></testsuite>',
    '<testsuite><testcase classname="tests.db.only" name="test_bad"><failure/></testcase></testsuite>',
    '<testsuite><testcase classname="tests.db.only" name="test_bad"><error/></testcase></testsuite>',
])
def test_empty_partial_failed_or_error_runs_cannot_publish(recorder, xml):
    module, report = recorder
    report.write_text(xml)
    with pytest.raises(ValueError):
        module.build(report)


@pytest.mark.parametrize("binding", [
    {"source_sha256": "stale-source", "pytest_exit_code": 0},
    {"source_sha256": "current-source", "pytest_exit_code": 1},
])
def test_sources_changed_or_failed_process_cannot_publish(recorder, binding):
    module, report = recorder
    report.with_suffix(".source.json").write_text(json.dumps(binding))
    with pytest.raises(ValueError):
        module.build(report)
