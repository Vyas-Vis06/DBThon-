"""Identical ordinary policy, explicit minimal comparator, no timing assertions."""

import importlib.util
from tests.conftest import ROOT

spec = importlib.util.spec_from_file_location("evaluate_preview", ROOT / "scripts/evaluate_preview.py")
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)


def test_same_predicate_parity_and_stale_preview_interleaving(conn):
    outcomes = preview.compare(conn)
    assert all(row["ordinary_pass"] and row["ordinary_deny"] for row in outcomes.values())
    assert outcomes["application_preview_write"]["after_interleaving_status"] == "AUTHORISED"
    assert outcomes["database_revalidation"]["after_interleaving_status"] == "DRAFT"
    assert not outcomes["database_revalidation"]["stale_authorization_accepted_in_trial"]
    assert conn.execute("SELECT count(*) AS n FROM entry_permit").fetchone()["n"] == 0
    assert conn.execute("SELECT bool_and(tgenabled='O') AS restored FROM pg_trigger "
                        "WHERE tgrelid='entry_permit'::regclass AND NOT tgisinternal").fetchone()["restored"]
