"""Administration: user accounts, the statutory rule parameters ("law as data") and the audit trail."""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, update

from ..deps import DB, Paging, Principal, STAFF, paged, require, to_dict
from ..errors import Forbidden, NotFound, Unprocessable
from ..models import AppUser, AuditLog, Role, RuleParameter, UserSession
from ..schemas import RuleValueIn, UserCreateIn, UserUpdateIn
from ..security import hash_password

router = APIRouter(tags=["administration"])
IST = timezone(timedelta(hours=5, minutes=30))
SECRET_COLUMNS = ("password_hash",)

# Fat-finger guard for the numbers that decide who may enter a sewer. Out-of-range values are refused; every accepted
# change is audited (who, when, old and new). Keys not listed accept any non-negative number up to 10**12.
BOUNDS: dict[str, tuple[float, float]] = {
    "gas_o2_min": (15, 21), "gas_o2_max": (19.5, 25), "gas_h2s_max_ppm": (0, 50), "gas_lel_max_pct": (0, 25),
    "gas_co_max_ppm": (0, 200), "gas_max_age_min": (1, 60), "min_crew_size": (2, 20), "max_continuous_minutes": (10, 240),
    "daylight_start_hour": (0, 12), "daylight_end_hour": (12, 24), "permit_valid_minutes": (30, 1440),
    "compensation_fatality_inr": (1, 100_000_000), "compensation_disability_inr": (1, 100_000_000),
    "compensation_due_days": (1, 365), "shadow_grace_hours": (1, 720),
}


def _user_row(user: AppUser, role: str) -> dict:
    out = {k: v for k, v in to_dict(user, exclude=SECRET_COLUMNS).items()}
    out["role"] = role
    return out


# --- users -----------------------------------------------------------------------------------------------------
@router.get("/admin/users")
def list_users(db: DB, page: Paging, principal: Principal = Depends(require("ADMIN")), role: str | None = None,
               is_active: bool | None = None, q: str | None = None):
    stmt = select(AppUser, Role.name).join(Role, Role.role_id == AppUser.role_id)
    if role:
        stmt = stmt.where(Role.name == role)
    if is_active is not None:
        stmt = stmt.where(AppUser.is_active == is_active)
    if q:
        stmt = stmt.where(AppUser.email.ilike(q.replace("%", r"\%").replace("_", r"\_") + "%", escape="\\"))
    return paged(db, stmt.order_by(AppUser.user_id), page, lambda r: _user_row(r[0], r[1]))


@router.post("/admin/users", status_code=201)
def create_user(body: UserCreateIn, request: Request, db: DB, principal: Principal = Depends(require("ADMIN"))):
    role_id = db.scalar(select(Role.role_id).where(Role.name == body.role))
    try:
        hashed = hash_password(body.password, request.app.state.settings.bcrypt_rounds)
    except ValueError as exc:
        raise Unprocessable(str(exc)) from exc
    user = AppUser(role_id=role_id, ulb_id=body.ulb_id, contractor_id=body.contractor_id, worker_id=body.worker_id,
                   email=body.email, full_name=body.full_name, password_hash=hashed)
    db.add(user)
    db.flush()                                   # the scope trigger checks contractor/worker links match the role
    return _user_row(user, body.role)


@router.patch("/admin/users/{user_id}")
def update_user(user_id: int, body: UserUpdateIn, request: Request, db: DB, principal: Principal = Depends(require("ADMIN"))):
    user = db.scalar(select(AppUser).where(AppUser.user_id == user_id).with_for_update())
    if user is None:
        raise NotFound("No such user.")
    changes = body.model_dump(exclude_unset=True, exclude={"unlock", "new_password", "role"})
    if user_id == principal.user_id and (body.role is not None or changes.get("is_active") is False):
        raise Forbidden("You cannot change your own role or deactivate yourself (you would lock the last administrator out).")
    for key, value in changes.items():
        setattr(user, key, value)
    if body.role is not None:
        user.role_id = db.scalar(select(Role.role_id).where(Role.name == body.role))
    if body.unlock:
        user.failed_logins, user.locked_until = 0, None
    if body.new_password is not None:
        try:
            user.password_hash = hash_password(body.new_password, request.app.state.settings.bcrypt_rounds)
        except ValueError as exc:
            raise Unprocessable(str(exc)) from exc
    if body.new_password is not None or changes.get("is_active") is False or body.role is not None:
        db.execute(update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
                   .values(revoked_at=datetime.now(timezone.utc)))               # sign the user out everywhere
    db.flush()
    return _user_row(user, db.scalar(select(Role.name).where(Role.role_id == user.role_id)))


# --- rule parameters ---------------------------------------------------------------------------------------------
@router.get("/rules")
def list_rules(db: DB, principal: Principal = Depends(require())):
    """The numbers the law is encoded as, with their legal references; assumptions are flagged."""
    return {"items": [to_dict(r) for r in db.scalars(select(RuleParameter).order_by(RuleParameter.param_key))]}


@router.patch("/rules/{param_key}")
def set_rule(param_key: str, body: RuleValueIn, db: DB, principal: Principal = Depends(require("ADMIN"))):
    row = db.scalar(select(RuleParameter).where(RuleParameter.param_key == param_key).with_for_update())
    if row is None:
        raise NotFound("No such rule parameter.")
    low, high = BOUNDS.get(param_key, (0, 10**12))
    if not Decimal(str(low)) <= body.value <= Decimal(str(high)):
        raise Unprocessable(f"{param_key} must be between {low} and {high}.")
    row.value, row.updated_by, row.updated_at = body.value, principal.user_id, datetime.now(timezone.utc)
    db.flush()
    return to_dict(row)


# --- audit trail -------------------------------------------------------------------------------------------------
@router.get("/audit-log")
def audit_log(db: DB, page: Paging, principal: Principal = Depends(require("ADMIN", "AUDITOR")), table_name: str | None = None,
              row_pk: str | None = None, actor_user_id: int | None = None, action: str | None = None,
              occurred_from: date | None = None, occurred_to: date | None = None):
    stmt = select(AuditLog)
    for column, value in ((AuditLog.table_name, table_name), (AuditLog.row_pk, row_pk), (AuditLog.actor_user_id, actor_user_id),
                          (AuditLog.action, action)):
        if value is not None:
            stmt = stmt.where(column == value)
    if occurred_from:
        stmt = stmt.where(AuditLog.occurred_at >= datetime.combine(occurred_from, time.min, tzinfo=IST))
    if occurred_to:
        stmt = stmt.where(AuditLog.occurred_at < datetime.combine(occurred_to, time.min, tzinfo=IST) + timedelta(days=1))
    return paged(db, stmt.order_by(AuditLog.log_id.desc()), page)
