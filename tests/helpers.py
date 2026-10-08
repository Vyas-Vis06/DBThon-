import re
from contextlib import contextmanager

import psycopg
import pytest


def act_as(conn, user_id: int, role: str, *, contractor_id: int | None = None, worker_id: int | None = None,
            ulb_id: int | None = None) -> None:
    """Set the request context exactly as the API does per request (session-level here: a test connection is long-lived)."""
    conn.execute("SELECT set_config('app.user_id', %s, false), set_config('app.role', %s, false), "
                 "set_config('app.contractor_id', %s, false), set_config('app.worker_id', %s, false), "
                 "set_config('app.ulb_id', %s, false)",
                 (str(user_id), role, str(contractor_id or ""), str(worker_id or ""), str(ulb_id or "")))


@contextmanager
def expect(sqlstate: str, match: str | None = None):
    """Assert the block raises a database error with this SQLSTATE (and, optionally, a message matching `match`).

    Business rules raise custom SQLSTATEs (ZE001..ZE006); constraints raise the standard ones (23xxx).
    """
    with pytest.raises(psycopg.Error) as info:
        yield
    err = info.value
    assert err.sqlstate == sqlstate, f"expected SQLSTATE {sqlstate}, got {err.sqlstate}: {err}"
    if match:
        text = err.diag.message_primary or str(err)
        assert re.search(match, text, re.S), f"{match!r} not found in: {text!r}"
