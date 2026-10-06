"""Pure unit tests: configuration validation, secret masking, database-error mapping."""

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError

from zeroentry.config import Settings
from zeroentry.errors import map_db_error
from zeroentry.log import mask_url


def test_production_requires_secure_cookies():
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(app_env="production", database_url="postgresql+psycopg://u:p@h/db", cookie_secure=False)


def test_production_rejects_placeholder_database_url():
    with pytest.raises(ValidationError, match="CHANGE_ME"):
        Settings(app_env="production", cookie_secure=True,
                 database_url="postgresql+psycopg://ze_app:CHANGE_ME@h/db")


def test_development_defaults_are_safe_and_owner_url_falls_back():
    s = Settings(database_url="postgresql+psycopg://u:p@h/db")
    assert s.app_env == "development" and s.cookie_secure is False
    assert s.owner_database_url == s.database_url
    s2 = Settings(database_url="postgresql+psycopg://u:p@h/db", migration_database_url="postgresql+psycopg://o:q@h/db")
    assert s2.owner_database_url.startswith("postgresql+psycopg://o:")


def test_mask_url_hides_the_password():
    masked = mask_url("postgresql+psycopg://ze_app:s3cret-value@localhost:5432/zeroentry")
    assert "s3cret-value" not in masked and "***" in masked


class _FakeDiag:
    def __init__(self, msg, constraint=None):
        self.message_primary, self.constraint_name = msg, constraint


class _FakePgError(Exception):
    def __init__(self, sqlstate, msg, constraint=None):
        super().__init__(msg)
        self.sqlstate, self.diag = sqlstate, _FakeDiag(msg, constraint)


def _wrap(sqlstate, msg="boom", constraint=None) -> DBAPIError:
    return DBAPIError("SELECT 1", {}, _FakePgError(sqlstate, msg, constraint))


def test_gate_denial_passes_the_database_message_through():
    err = map_db_error(_wrap("ZE001", "Entry denied: BOTTOM reading is 22 min old"))
    assert (err.status_code, err.code) == (422, "legal_clause_failed")
    assert err.message == "Entry denied: BOTTOM reading is 22 min old"


@pytest.mark.parametrize("state,status,code", [
    ("ZE003", 409, "invalid_state"), ("ZE006", 403, "not_permitted"), ("23505", 409, "duplicate"),
    ("23P01", 409, "overlap"), ("23514", 422, "check_failed"), ("42501", 403, "forbidden"),
])
def test_known_sqlstates_map_to_http(state, status, code):
    err = map_db_error(_wrap(state, "internal wording that must not leak" if state[:2] == "23" else "x"))
    assert (err.status_code, err.code) == (status, code)
    if state.startswith("23") or state == "42501":
        assert "internal wording" not in err.message  # constraint errors get a friendly message


def test_unknown_sqlstate_is_not_mapped():
    assert map_db_error(_wrap("XX000")) is None


def test_a_value_the_driver_refuses_client_side_is_a_422_not_a_500():
    import psycopg
    err = map_db_error(DBAPIError("SELECT 1", {}, psycopg.DataError("PostgreSQL text fields cannot contain NUL (0x00) bytes")))
    assert (err.status_code, err.code) == (422, "bad_value")
