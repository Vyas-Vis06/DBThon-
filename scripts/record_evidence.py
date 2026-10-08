"""Build current judge evidence from an actual successful pytest JUnit report.

    python scripts/verify_release.py

Run immediately after tests without changing code. Repository-level proof only; not a
signature, sensor certificate, field outcome measurement or remote CI claim.
"""

import argparse
import json
import platform
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from zeroentry.evidence import ROOT, source_fingerprint


def build(report: Path) -> dict:
    bound_source = json.loads(report.with_suffix(".source.json").read_text(encoding="utf-8"))
    if (bound_source.get("source_sha256") != source_fingerprint()
            or bound_source.get("pytest_exit_code") != 0):
        raise ValueError("JUnit evidence is not bound to this unchanged source tree; rerun verify_release.py")
    cases = list(ET.parse(report).getroot().iter("testcase"))
    if not cases:
        raise ValueError("JUnit report contains no test cases")
    failed = sum(case.find("failure") is not None for case in cases)
    errors = sum(case.find("error") is not None for case in cases)
    skipped = sum(case.find("skipped") is not None for case in cases)
    if failed or errors:
        raise ValueError("Refusing to publish a passing manifest from a failed JUnit run")
    passed_cases = [case for case in cases if case.find("skipped") is None]
    identities = [case.get("classname", "") + "." + case.get("name", "") for case in passed_cases]
    # Require the ordinary suite, not a single selected smoke test presented as the full run.
    if not all(any(name.startswith(prefix) for name in identities) for prefix in
               ("tests.db.", "tests.api.", "tests.unit.")):
        raise ValueError("Manifest requires database, API and unit test layers in the actual run")
    revision_files = sorted((ROOT / "database/migrations/versions").glob("[0-9]*.py"))
    revision = revision_files[-1].stem.split("_", 1)[0]
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                                capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, check=True,
                                    capture_output=True, text=True).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = "NOT_AVAILABLE", True
    measured_at = datetime.now(timezone.utc).isoformat()
    run_id = str(uuid4())
    specs = [
        ("LAB1-DDL", "DDL and DML", "database/migrations/sql/0002_core_schema.sql", "test_schema"),
        ("LAB1-DML", "DDL and DML", "database/seeds", "test_seed"),
        ("LAB2-PASS", "Constraints accepted", "tests/db/test_schema.py", "test_schema"),
        ("LAB2-REJECT", "Constraints rejected", "tests/db/test_schema.py", "test_schema"),
        ("LAB3-BOUNDARY", "Scalar time functions", "database/queries/05_views_functions_procedures.sql", "05_views_functions_procedures.sql"),
        ("LAB4-AGG", "Operators and aggregates", "database/queries/02_aggregates.sql", "02_aggregates.sql"),
        ("LAB5-JOIN", "Queries and joins", "database/queries/01_joins.sql", "01_joins.sql"),
        ("LAB5-ANTI", "Relational division and anti-join", "database/queries/04_division_and_anti_join.sql", "04_division_and_anti_join.sql"),
        ("LAB5-VIEW", "Views", "database/queries/05_views_functions_procedures.sql", "05_views_functions_procedures.sql"),
        ("LAB6-FN", "Database functions", "tests/db/test_entry_gate.py", "test_entry_gate"),
        ("LAB6-PROC", "Atomic procedures", "tests/db/test_consequences.py", "test_consequences"),
        ("LAB6-TRG", "Database triggers", "database/queries/07_trigger_refusals.sql", "07_trigger_refusals.sql"),
    ]
    # Select the actual executed cursor showcase rather than a proposed path.
    cursor_paths = [path for path in (ROOT / "database/queries").glob("*.sql")
                    if "OPEN " in path.read_text(encoding="utf-8").upper()
                    and "FETCH " in path.read_text(encoding="utf-8").upper()
                    and "CLOSE " in path.read_text(encoding="utf-8").upper()]
    if cursor_paths:
        cursor = sorted(cursor_paths)[0]
        specs.append(("LAB6-CURSOR", "Explicit cursor", cursor.relative_to(ROOT).as_posix(), cursor.name))
    labs = []
    for lab_id, title, artifact, needle in specs:
        matching = [name for name in identities if needle in name]
        labs.append({"id": lab_id, "title": title, "artifact_path": artifact,
                     "status": "TESTED" if matching else "NOT_YET_MEASURED", "url": None,
                     "run_id": run_id if matching else None, "git_sha": commit if matching else None,
                     "measured_at": measured_at if matching else None,
                     "summary": f"{len(matching)} passing test cases reference this proof" if matching else None})
    return {"run_id": run_id, "measured_at": measured_at, "git_sha": commit, "dirty": dirty,
            "schema_revision": revision, "source_sha256": source_fingerprint(),
            "machine": platform.platform(), "python": platform.python_version(),
            "junit_report": report.as_posix(), "verification": bound_source, "labs": labs,
            "summary": {"total": len(cases), "passed": len(passed_cases), "failed": failed,
                        "errors": errors, "skipped": skipped,
                        "browser_passed": sum(name.startswith("tests.browser.") for name in identities)},
            "limitations": ["Local synthetic PostgreSQL tests, not field deployment or remote CI results.",
                            "JUnit/build provenance is trusted locally; it is not external signed attestation."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", required=True, type=Path)
    args = parser.parse_args()
    manifest = build(args.junit)
    target = ROOT / "docs/evidence/current.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["summary"]))


if __name__ == "__main__":
    main()
