"""Request plumbing shared by every router: the database session, authentication, CSRF, role guards, paging.

Authorisation is decided HERE, on the server, from the session row in the database. Nothing the client sends
(not a role claim, not a user id) is trusted. The same transaction also tells PostgreSQL who is asking
(`set_config(..., true)`, transaction-local) so row-level security and the audit trail see the real user.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import Depends, Query, Request
from sqlalchemy import func, inspect as sa_inspect, select
from sqlalchemy.orm import Session

from .errors import Forbidden, Unauthorized
from .models import AppUser, Role, UserSession
from .security import hash_token, tokens_equal

SESSION_COOKIE = "ze_session"
CSRF_HEADER = "x-csrf-token"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def get_db(request: Request) -> Iterator[Session]:
    """One transaction per request. It commits when the handler returns and rolls back on any exception.

    Registered with scope="function" so the commit runs BEFORE the response is sent: a failing commit becomes an
    error response instead of a 200 that never happened (tests/api/test_admin_and_validation.py guards this).
    """
    session: Session = request.app.state.sessionmaker()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


DB = Annotated[Session, Depends(get_db, scope="function")]


@dataclass(frozen=True)
class Principal:
    user_id: int
    role: str
    email: str
    full_name: str
    ulb_id: int | None
    contractor_id: int | None
    worker_id: int | None
    session_id: int
    csrf_token: str
    via_cookie: bool


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    return origin is None or urlparse(origin).netloc == request.url.netloc


def authenticate(request: Request, db: DB) -> Principal:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token, via_cookie = auth[7:].strip(), False
    elif request.cookies.get(SESSION_COOKIE):
        token, via_cookie = request.cookies[SESSION_COOKIE], True
    else:
        raise Unauthorized("Sign in required.")

    row = db.execute(
        select(UserSession, AppUser, Role.name)
        .join(AppUser, AppUser.user_id == UserSession.user_id)
        .join(Role, Role.role_id == AppUser.role_id)
        .where(UserSession.token_hash == hash_token(token), UserSession.revoked_at.is_(None),
               UserSession.expires_at > func.now(), AppUser.is_active.is_(True))
    ).first()
    if row is None:
        raise Unauthorized("Your session has expired or is invalid. Sign in again.")
    session_row, user, role_name = row

    # CSRF: a browser sends the cookie on cross-site requests, so cookie-authenticated writes must also carry the
    # per-session token (only same-origin script can read it) and come from our own origin. Bearer clients are exempt.
    if via_cookie and request.method in UNSAFE_METHODS:
        header = request.headers.get(CSRF_HEADER, "")
        if not _same_origin(request) or not tokens_equal(header, session_row.csrf_token):
            raise Forbidden("Missing or invalid CSRF token.", code="csrf")

    # Tell PostgreSQL who is asking, for this transaction only (cannot leak to another request on the pooled connection).
    db.execute(select(
        func.set_config("app.user_id", str(user.user_id), True),
        func.set_config("app.role", role_name, True),
        func.set_config("app.contractor_id", str(user.contractor_id or ""), True),
        func.set_config("app.worker_id", str(user.worker_id or ""), True),
        func.set_config("app.ulb_id", str(user.ulb_id or ""), True)))
    return Principal(user.user_id, role_name, user.email, user.full_name, user.ulb_id, user.contractor_id,
                     user.worker_id, session_row.session_id, session_row.csrf_token, via_cookie)


def require(*roles: str):
    """Dependency factory: authenticated AND holding one of `roles` (no roles = any signed-in user)."""

    def guard(principal: Annotated[Principal, Depends(authenticate)]) -> Principal:
        if roles and principal.role not in roles:
            raise Forbidden(f"The {principal.role} role may not perform this action.")
        return principal

    guard.roles = roles               # read by api_doc.py to document who may call each endpoint
    return guard


STAFF = ("ADMIN", "ENGINEER", "SUPERVISOR", "AUDITOR")          # may read operational data across contractors
WRITERS = ("ADMIN", "ENGINEER")                                  # municipal officers who maintain records


@dataclass(frozen=True)
class PageParams:
    limit: int
    offset: int


def page_params(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)) -> PageParams:
    return PageParams(limit, offset)


Paging = Annotated[PageParams, Depends(page_params)]


def to_dict(obj: Any, exclude: tuple[str, ...] = ()) -> dict[str, Any]:
    """Column values of an ORM row as a plain dict (secrets are excluded by name)."""
    return {c.key: getattr(obj, c.key) for c in sa_inspect(obj).mapper.column_attrs if c.key not in exclude}


def paged(db: Session, stmt, params: PageParams, convert=to_dict) -> dict[str, Any]:
    """Run a SELECT with LIMIT/OFFSET and a total count. `convert` maps one result row to a JSON-able dict."""
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = db.execute(stmt.limit(params.limit).offset(params.offset)).all()
    return {"items": [convert(r[0] if len(r) == 1 else r) for r in rows], "total": total,
            "limit": params.limit, "offset": params.offset}
