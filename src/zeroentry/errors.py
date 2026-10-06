"""One error vocabulary for the whole API.

Business-rule failures raised inside PostgreSQL carry a custom SQLSTATE (class `ZE`); the database is
the author of those messages, so the API passes them through verbatim as readable legal messages:

  ZE001  entry gate denied: a statutory clause is not satisfied
  ZE002  a recorded value breaks a rule (calibration, 90-minute limit, daylight, ...)
  ZE003  not allowed in the current state (state machine, frozen crew, append-only table)
  ZE004  referenced record not found
  ZE005  rule parameter missing (misconfiguration)
  ZE006  actor's role may not perform this action
"""

import logging
from typing import Any

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("zeroentry.errors")


class AppError(Exception):
    status_code = 400
    code = "error"

    def __init__(self, message: str, *, details: Any = None, status_code: int | None = None,
                 code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code


class Unauthorized(AppError):
    status_code, code = 401, "unauthorized"


class Forbidden(AppError):
    status_code, code = 403, "forbidden"


class NotFound(AppError):
    status_code, code = 404, "not_found"


class Conflict(AppError):
    status_code, code = 409, "conflict"


class Unprocessable(AppError):
    status_code, code = 422, "unprocessable"


# SQLSTATE -> (HTTP status, error code, friendly message or None to pass the database message through)
_DB_MAP: dict[str, tuple[int, str, str | None]] = {
    "ZE001": (422, "legal_clause_failed", None),
    "ZE002": (422, "rule_violation", None),
    "ZE003": (409, "invalid_state", None),
    "ZE004": (404, "not_found", None),
    "ZE005": (500, "misconfigured", "A required rule parameter is missing; contact an administrator."),
    "ZE006": (403, "not_permitted", None),
    "23505": (409, "duplicate", "A record with the same unique value already exists."),
    "23503": (409, "reference_conflict", "The record refers to, or is still used by, another record."),
    "23514": (422, "check_failed", "The values violate a business rule enforced by the database."),
    "23502": (422, "missing_value", "A required value is missing."),
    "23P01": (409, "overlap", "This overlaps an existing record (a worker cannot be in two entries at once)."),
    "22P02": (422, "bad_value", "A value has an invalid format."),
    "22003": (422, "bad_value", "A numeric value is out of range."),
    "42501": (403, "forbidden", "You do not have permission to perform this action."),
}


def map_db_error(exc: DBAPIError) -> AppError | None:
    """Translate a database error into an AppError, or None when it is not a known business error."""
    orig = exc.orig
    state = getattr(orig, "sqlstate", None)
    if state is None and isinstance(orig, psycopg.DataError):
        # The driver itself refused the value before it reached the server (for example a NUL byte): client input.
        return AppError("A value contains characters that cannot be stored.", status_code=422, code="bad_value")
    if state not in _DB_MAP:
        return None
    status, code, friendly = _DB_MAP[state]
    diag = getattr(orig, "diag", None)
    message = friendly or (getattr(diag, "message_primary", None) or str(orig))
    details = {"constraint": getattr(diag, "constraint_name", None)} if state.startswith("23") else None
    return AppError(message, status_code=status, code=code, details=details)


def _body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(_body(exc.code, exc.message, exc.details), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [{"field": ".".join(str(p) for p in e["loc"] if p not in ("body", "query", "path")) or "(body)",
                    "message": e["msg"]} for e in exc.errors()]
        return JSONResponse(_body("validation_error", "The request is invalid: " + "; ".join(
            f"{d['field']}: {d['message']}" for d in details[:5]), details), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {404: "not_found", 405: "method_not_allowed"}
        return JSONResponse(_body(codes.get(exc.status_code, "http_error"), str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(DBAPIError)
    async def _db_error(_: Request, exc: DBAPIError) -> JSONResponse:
        mapped = map_db_error(exc)
        if mapped is None:
            log.exception("unmapped database error")  # details stay in the server log only
            return JSONResponse(_body("internal_error", "Internal server error."), status_code=500)
        return JSONResponse(_body(mapped.code, mapped.message, mapped.details), status_code=mapped.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error")
        return JSONResponse(_body("internal_error", "Internal server error."), status_code=500)
