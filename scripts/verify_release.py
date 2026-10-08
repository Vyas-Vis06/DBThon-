"""Run the whole suite and bind actual JUnit results to an unchanged source tree.

Creates only local test reports and a judge manifest. Does not publish, commit or reset a database.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from zeroentry.evidence import ROOT, source_fingerprint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if not 0 <= args.workers <= 8:
        parser.error("Use zero through eight workers to keep local PostgreSQL resources bounded")
    report = ROOT / ".reports/integration.xml"
    report.parent.mkdir(parents=True, exist_ok=True)
    before = source_fingerprint()
    started = datetime.now(timezone.utc).isoformat()
    command = [sys.executable, "-m", "pytest", "-n", str(args.workers), "-q", f"--junitxml={report}"]
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode:
        raise SystemExit(result.returncode)
    after = source_fingerprint()
    if before != after:
        raise SystemExit("Sources changed during verification; no passing manifest was published. Rerun after edits stop.")
    binding = {"source_sha256": after, "pytest_exit_code": result.returncode,
               "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
               "command": ["python", "-m", "pytest", "-n", str(args.workers), "-q", "--junitxml=.reports/integration.xml"]}
    report.with_suffix(".source.json").write_text(json.dumps(binding, indent=2) + "\n", encoding="utf-8")
    sys.path.insert(0, str(Path(__file__).parent))
    from record_evidence import build
    manifest = build(report)
    target = ROOT / "docs/evidence/current.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Published current local evidence:", json.dumps(manifest["summary"]))


if __name__ == "__main__":
    main()
