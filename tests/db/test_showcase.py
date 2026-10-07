"""The judges' showcase (scripts/showcase.py) still shows what it claims: every condition reacts as expected.

It starts its own throwaway server, so it runs as a subprocess and never shares this session's cluster or ze_app password.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_every_showcase_condition_reacts_as_expected():
    run = subprocess.run([sys.executable, str(ROOT / "scripts" / "showcase.py")], cwd=ROOT,
                         capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stdout[-4000:] + run.stderr[-2000:]
    assert "19 of 19 conditions behaved as expected" in run.stdout
