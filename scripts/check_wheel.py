"""Run with the Python of a separately installed wheel environment, from any directory.

    python -m pip wheel --no-deps . -w dist
    python -m venv --system-site-packages wheel-check
    wheel-check/bin/python -m pip install --no-deps dist/zeroentry-*.whl
    wheel-check/bin/python scripts/check_wheel.py

Dependencies may come from the parent environment; zeroentry itself must come from the wheel.
No database is opened: the static page and asset routes are the distribution contract.
Migrations/seed commands intentionally require a source checkout (docs/SETUP.md).
"""

from pathlib import Path

from fastapi.testclient import TestClient

import zeroentry
from zeroentry.config import Settings
from zeroentry.main import create_app


def main() -> None:
    source = Path(__file__).resolve().parents[1] / "src"
    installed = Path(zeroentry.__file__).resolve()
    assert not installed.is_relative_to(source), f"Expected installed wheel, got source: {installed}"
    app = create_app(Settings(app_env="test", database_url="postgresql+psycopg://unused@localhost/unused",
                              safety_sweep_interval_seconds=0))
    with TestClient(app) as client:
        for path, fragment in (("/app/login", "<!doctype html>"), ("/static/app.js", "export"),
                               ("/static/style.css", "{"),
                               ("/static/pages/incident_reports.js", "export"),
                               ("/static/pages/completion_review.js", "export"),
                               ("/static/pages/judge_evidence.js", "export")):
            response = client.get(path)
            assert response.status_code == 200, (path, response.status_code, response.text[:300])
            assert fragment in response.text, path
    print("Installed-wheel HTML, JS and CSS smoke checks passed.")


if __name__ == "__main__":
    main()
