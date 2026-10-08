"""Read a locally generated test-evidence manifest only when it matches current sources.

This is build/test provenance, not cryptographic attestation. Missing repository sources
or a stale manifest yield NOT_YET_MEASURED rather than carrying historical numbers forward.
"""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def source_fingerprint(root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    paths = []
    for directory in ("src", "tests", "scripts", "database"):
        base = root / directory
        if not base.is_dir():
            raise FileNotFoundError(f"Evidence source directory missing: {directory}")
        paths.extend(path for path in base.rglob("*") if path.is_file()
                     and path.suffix in {".py", ".sql", ".js", ".css", ".html"}
                     and "__pycache__" not in path.parts)
    paths.extend(root / name for name in ("pyproject.toml", "alembic.ini"))
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def current_manifest(schema_revision: str, root: Path = ROOT) -> dict | None:
    try:
        manifest = json.loads((root / "docs/evidence/current.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or not isinstance(manifest.get("summary"), dict):
            return None
        required = {"run_id", "measured_at", "git_sha", "dirty", "schema_revision", "source_sha256",
                    "summary", "machine", "python", "labs", "limitations"}
        if (not required <= manifest.keys() or not isinstance(manifest["labs"], list)
                or not isinstance(manifest["limitations"], list)):
            return None
        summary = manifest["summary"]
        counts = ("total", "passed", "failed", "errors", "skipped", "browser_passed")
        if any(type(summary.get(key)) is not int or summary[key] < 0 for key in counts):
            return None
        if (summary["total"] == 0 or summary["passed"] == 0
                or summary["total"] != sum(summary[key] for key in ("passed", "failed", "errors", "skipped"))
                or summary["browser_passed"] > summary["passed"]):
            return None
        if (manifest.get("source_sha256") != source_fingerprint(root)
                or manifest.get("schema_revision") != schema_revision
                or manifest.get("summary", {}).get("failed", 1) != 0
                or manifest.get("summary", {}).get("errors", 1) != 0):
            return None
        return manifest
    except (OSError, ValueError, TypeError):
        return None
