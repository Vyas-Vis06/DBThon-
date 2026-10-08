"""Login, logout, current user, change password. Sessions are opaque random tokens kept (hashed) in the database."""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import delete, func, select, text, update

from ..deps import DB, SESSION_COOKIE, Principal, authenticate
from ..errors import AppError, Unauthorized, Unprocessable
from ..models import AppUser, Role, UserSession
from ..schemas import ChangePasswordIn, LoginIn
from ..security import dummy_verify, hash_password, hash_token, new_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# One message for every way a login can fail: wrong password, unknown e-mail, locked, disabled (no enumeration).
_REFUSED = "Invalid email or password, or the account is temporarily locked."


def _user_view(user: AppUser, role: str, db=None) -> dict:
    policy_mode = (db.scalar(text("SELECT policy_mode FROM ulb WHERE ulb_id=:ulb"), {"ulb": user.ulb_id})
                   if db is not None and user.ulb_id is not None else None)
    return {"user_id": user.user_id, "email": user.email, "full_name": user.full_name, "role": role,
            "ulb_id": user.ulb_id, "policy_mode": policy_mode,
            "educational": policy_mode == "EDUCATIONAL" if policy_mode is not None else None,
            "policy_provenance": "ULB policy setting stored in the application database; not an external legal citation." if policy_mode is not None else None,
            "contractor_id": user.contractor_id, "worker_id": user.worker_id}


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: DB):
    settings = request.app.state.settings
    ip = request.client.host if request.client else "unknown"
    if not request.app.state.login_limiter.allow(ip):
        raise AppError("Too many sign-in attempts from this address. Wait a minute and try again.",
                       status_code=429, code="rate_limited")

    user = db.scalar(select(AppUser).where(AppUser.email == body.email.strip().lower()))
    now = datetime.now(timezone.utc)
    if user is None or not user.is_active:
        dummy_verify(body.password, settings.bcrypt_rounds)       # same cost as a real check: no timing oracle
        raise Unauthorized(_REFUSED)
    if user.locked_until is not None and user.locked_until > now:
        raise Unauthorized(_REFUSED)
    if not verify_password(body.password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= settings.login_max_failures:
            user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
            user.failed_logins = 0
        db.commit()                                               # the failure must persist even though we now raise
        raise Unauthorized(_REFUSED)

    user.failed_logins, user.locked_until = 0, None
    token, csrf = new_token(), new_token()
    expires = now + timedelta(minutes=settings.session_ttl_minutes)
    db.add(UserSession(user_id=user.user_id, token_hash=hash_token(token), csrf_token=csrf, expires_at=expires))
    db.execute(delete(UserSession).where(UserSession.expires_at < now - timedelta(days=1)))   # housekeeping
    role = db.scalar(select(Role.name).where(Role.role_id == user.role_id))
    # LOGIN has no session dependency yet; set a transaction-local context from the verified stored user
    # so the ULB's RLS-filtered policy_mode can be read by the same trusted transaction.
    db.execute(select(
        func.set_config("app.user_id", str(user.user_id), True),
        func.set_config("app.role", role, True),
        func.set_config("app.contractor_id", str(user.contractor_id or ""), True),
        func.set_config("app.worker_id", str(user.worker_id or ""), True),
        func.set_config("app.ulb_id", str(user.ulb_id or ""), True)))
    response.set_cookie(SESSION_COOKIE, token, max_age=settings.session_ttl_minutes * 60, httponly=True,
                        samesite="strict", secure=settings.cookie_secure, path="/")
    # session_token is for non-browser clients (Authorization: Bearer ...); the browser UI uses the HttpOnly cookie only.
    return {"user": _user_view(user, role, db), "csrf_token": csrf, "session_token": token, "expires_at": expires}


@router.post("/logout")
def logout(principal: Annotated[Principal, Depends(authenticate)], response: Response, db: DB):
    db.execute(update(UserSession).where(UserSession.session_id == principal.session_id)
               .values(revoked_at=datetime.now(timezone.utc)))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(principal: Annotated[Principal, Depends(authenticate)], db: DB):
    policy_mode = (db.scalar(text("SELECT policy_mode FROM ulb WHERE ulb_id=:ulb"), {"ulb": principal.ulb_id})
                   if principal.ulb_id is not None else None)
    return {"user": {"user_id": principal.user_id, "email": principal.email, "full_name": principal.full_name,
                     "role": principal.role, "ulb_id": principal.ulb_id, "policy_mode": policy_mode,
                     "educational": policy_mode == "EDUCATIONAL" if policy_mode is not None else None,
                     "policy_provenance": "ULB policy setting stored in the application database; not an external legal citation." if policy_mode is not None else None,
                     "contractor_id": principal.contractor_id,
                     "worker_id": principal.worker_id},
            "csrf_token": principal.csrf_token}


@router.post("/change-password")
def change_password(body: ChangePasswordIn, request: Request, principal: Annotated[Principal, Depends(authenticate)], db: DB):
    user = db.get(AppUser, principal.user_id)
    if not verify_password(body.current_password, user.password_hash):
        raise Unprocessable("The current password is wrong.")
    try:
        user.password_hash = hash_password(body.new_password, request.app.state.settings.bcrypt_rounds)
    except ValueError as exc:
        raise Unprocessable(str(exc)) from exc
    db.execute(update(UserSession).where(UserSession.user_id == user.user_id, UserSession.session_id != principal.session_id,
                                         UserSession.revoked_at.is_(None)).values(revoked_at=datetime.now(timezone.utc)))
    return {"ok": True, "other_sessions_revoked": True}
