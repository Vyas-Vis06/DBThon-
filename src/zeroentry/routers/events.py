"""Authenticated, bounded durable polling over the per-ULB outbox."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from ..deps import DB, Principal, require
from ..errors import NotFound

router = APIRouter(prefix="/events", tags=["events"])


def _check_scope(ulb_id: int, principal: Principal) -> None:
    if principal.role in {"ADMIN", "AUDITOR"}:
        return
    if principal.role in {"ENGINEER", "SUPERVISOR"}:
        if principal.ulb_id is None or principal.ulb_id != ulb_id:
            raise NotFound("No event stream is available for that scope.")


@router.get("")
def poll_events(
    db: DB,
    ulb_id: Annotated[int, Query(gt=0)],
    principal: Annotated[Principal, Depends(require("ADMIN", "ENGINEER", "SUPERVISOR", "AUDITOR"))],
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    _check_scope(ulb_id, principal)
    if not db.scalar(text("SELECT EXISTS (SELECT 1 FROM ulb WHERE ulb_id=:ulb)"), {"ulb": ulb_id}):
        raise NotFound("No event stream is available for that scope.")
    stmt = text(
        "SELECT ulb_id,event_seq,event_type,entity_type,entity_id,payload,occurred_at "
        "FROM outbox_event WHERE ulb_id=:ulb AND event_seq>:after "
        "ORDER BY event_seq LIMIT :fetch_limit"
    )
    rows = db.execute(stmt, {"ulb": ulb_id, "after": after, "fetch_limit": limit + 1}).mappings().all()
    has_more = len(rows) > limit
    page = rows[:limit]
    items = [dict(row) for row in page]
    next_after = items[-1]["event_seq"] if items else after
    return {"items": items, "next_after": next_after, "has_more": has_more, "reset_required": False}
