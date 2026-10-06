"""A small generic CRUD router for plain reference tables (ULBs, manholes, machines, gear, detectors, contractors,
workers). Complex workflows (permits, detection, incidents) are written out explicitly in their own routers.

Every route still goes through `require()` (server-side role check), pydantic validation, and the ORM; deletes and
updates that break a business rule are refused by the database and surface as readable 409/422 errors.
"""

from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import DeclarativeBase

from .deps import DB, Paging, Principal, paged, require, to_dict
from .errors import NotFound, Unprocessable
from .schemas import In, partial


def coerce(column: Any, raw: str) -> Any:
    """Turn a query-string value into the column's Python type, or refuse with a 422 (never a database error)."""
    try:
        kind = column.type.python_type
        if kind is bool:
            return raw.lower() in ("1", "true", "yes")
        if kind in (date, datetime):
            return kind.fromisoformat(raw)
        return Decimal(raw) if kind is Decimal else kind(raw)
    except (ValueError, TypeError, ArithmeticError, NotImplementedError) as exc:
        raise Unprocessable(f"Invalid value for filter '{column.key}'.") from exc


def crud_router(
    prefix: str, tag: str, model: type[DeclarativeBase], create: type[In], *,
    read_roles: tuple[str, ...], write_roles: tuple[str, ...], delete_roles: tuple[str, ...] = ("ADMIN",),
    filters: tuple[str, ...] = (), search: tuple[str, ...] = (), order_by: str | None = None, pk_type: type = int,
    scope: Callable[[Any, Principal], Any] | None = None,
    guard: Callable[[Any, dict[str, Any], Principal], None] | None = None,
) -> APIRouter:
    """filters: columns accepted as `?column=value`. search: columns matched by `?q=` (case-insensitive prefix on any of them).
    scope(stmt, principal): narrow a SELECT for roles that may only see their own rows.
    guard(row, changes, principal): raise to veto an update."""
    router = APIRouter(prefix=prefix, tags=[tag])
    pk = model.__mapper__.primary_key[0]
    update_model = partial(create, f"{model.__name__}Patch")
    order = getattr(model, order_by) if order_by else pk

    def _scoped(stmt, principal):
        return scope(stmt, principal) if scope else stmt

    @router.get("")
    def list_(request: Request, db: DB, page: Paging, principal: Principal = Depends(require(*read_roles)), q: str | None = None):
        stmt = _scoped(select(model), principal)
        for name in filters:
            if name in request.query_params:
                stmt = stmt.where(getattr(model, name) == coerce(getattr(model, name), request.query_params[name]))
        if q and search:
            prefix = q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_") + "%"
            stmt = stmt.where(or_(*[getattr(model, c).ilike(prefix, escape="\\") for c in search]))
        return paged(db, stmt.order_by(order), page)

    @router.get("/{item_id}")
    def get_(item_id: pk_type, db: DB, principal: Principal = Depends(require(*read_roles))):
        row = db.scalar(_scoped(select(model), principal).where(pk == item_id))
        if row is None:
            raise NotFound(f"No such {tag}.")
        return to_dict(row)

    @router.post("", status_code=201)
    def create_(body: create, db: DB, principal: Principal = Depends(require(*write_roles))):  # type: ignore[valid-type]
        row = model(**body.model_dump())
        db.add(row)
        db.flush()
        return to_dict(row)

    @router.patch("/{item_id}")
    def update_(item_id: pk_type, body: update_model, db: DB,  # type: ignore[valid-type]
                principal: Principal = Depends(require(*write_roles))):
        row = db.scalar(select(model).where(pk == item_id).with_for_update())
        if row is None:
            raise NotFound(f"No such {tag}.")
        changes = body.model_dump(exclude_unset=True)
        if guard:
            guard(row, changes, principal)
        for key, value in changes.items():
            setattr(row, key, value)
        db.flush()
        return to_dict(row)

    @router.delete("/{item_id}")
    def delete_(item_id: pk_type, db: DB, principal: Principal = Depends(require(*delete_roles))):
        row = db.scalar(select(model).where(pk == item_id))
        if row is None:
            raise NotFound(f"No such {tag}.")
        db.delete(row)
        db.flush()                        # surface an FK refusal here, as a 409, not at commit time
        return {"deleted": item_id}

    return router
