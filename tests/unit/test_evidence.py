import json

from zeroentry.evidence import current_manifest, source_fingerprint


def test_manifest_rejects_source_changes_schema_changes_and_failed_runs(tmp_path):
    for directory in ("src", "tests", "scripts", "database"):
        (tmp_path / directory).mkdir()
    (tmp_path / "src/example.py").write_text("value = 1\n")
    for filename in ("pyproject.toml", "alembic.ini"):
        (tmp_path / filename).write_text("example\n")
    target = tmp_path / "docs/evidence/current.json"
    target.parent.mkdir(parents=True)
    manifest = {"source_sha256": source_fingerprint(tmp_path), "schema_revision": "0016",
                "summary": {"total": 1, "passed": 1, "failed": 0, "errors": 0, "skipped": 0, "browser_passed": 0},
                "run_id": "local-test", "measured_at": "test",
                "git_sha": "test", "dirty": True, "machine": "fixture", "python": "fixture",
                "labs": [], "limitations": []}
    target.write_text(json.dumps(manifest))
    assert current_manifest("0016", tmp_path) == manifest
    for invalid in ({}, {**manifest["summary"], "total": 0},
                    {**manifest["summary"], "passed": True}, {**manifest["summary"], "browser_passed": 2}):
        target.write_text(json.dumps({**manifest, "summary": invalid}))
        assert current_manifest("0016", tmp_path) is None
    target.write_text(json.dumps(manifest))
    assert current_manifest("0015", tmp_path) is None
    (tmp_path / "src/example.py").write_text("value = 2\n")
    assert current_manifest("0016", tmp_path) is None
    manifest["source_sha256"] = source_fingerprint(tmp_path)
    manifest["summary"]["failed"] = 1
    target.write_text(json.dumps(manifest))
    assert current_manifest("0016", tmp_path) is None


def test_missing_or_malformed_manifest_never_becomes_measured(tmp_path):
    assert current_manifest("0016", tmp_path) is None
    target = tmp_path / "docs/evidence/current.json"
    target.parent.mkdir(parents=True)
    for value in ("not JSON", "[]", "{}", '{"summary":[]}'):
        target.write_text(value)
        assert current_manifest("0016", tmp_path) is None
