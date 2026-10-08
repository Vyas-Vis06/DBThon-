"""A SQL presentation must not accidentally attach to another local demo cluster."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pgserver
import pytest


spec = importlib.util.spec_from_file_location("ze_run_sql", Path(__file__).resolve().parents[2] / "scripts/run_sql.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_missing_selected_cluster_is_not_implicitly_created(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Should not start another database")
    monkeypatch.setattr(pgserver, "get_server", forbidden)
    with pytest.raises(FileNotFoundError, match="initialized demo cluster"):
        runner.dsn_for_dev(tmp_path / "missing-rehearsal")


def test_sql_runner_uses_exact_selected_cluster_without_cleanup(tmp_path, monkeypatch):
    selected = tmp_path / "rehearsal"
    cluster = selected / "cluster"
    cluster.mkdir(parents=True)
    (cluster / "PG_VERSION").write_text("16")
    calls = []
    def server(path, cleanup_mode):
        calls.append((path, cleanup_mode))
        return SimpleNamespace(get_uri=lambda: "postgresql://localhost/synthetic")
    monkeypatch.setattr(pgserver, "get_server", server)
    assert "dbname=zeroentry" in runner.dsn_for_dev(selected)
    assert calls == [(cluster.resolve(), None)]
