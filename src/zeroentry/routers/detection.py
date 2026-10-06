"""Shadow-entry detection by absence: candidates (what is suspected right now), alerts (the persisted, reviewable
result), the scan, and the human review. The detection logic itself lives in SQL (database/migrations/sql/0007)."""

from fastapi import APIRouter, Depends
from sqlalchemy import select, text, update

from ..deps import DB, Paging, Principal, paged, require, to_dict
from ..errors import NotFound
from ..models import (Complaint, Contractor, DetectionRule, Invoice, InvoiceHold, Manhole, ShadowEntryAlert,
                      ShadowEntryAlertEvent, Ulb)
from ..schemas import ReviewIn, RuleToggleIn
from ..views import v_suspected_shadow_entry as cand

router = APIRouter(prefix="/detections", tags=["detection by absence"])
READERS = ("ADMIN", "ENGINEER", "AUDITOR")       # contractors never see alerts about themselves (PROJECT_SPEC section 3)
DECIDERS = ("ADMIN", "ENGINEER")


@router.get("/candidates")
def candidates(db: DB, page: Paging, principal: Principal = Depends(require(*READERS)), rule_code: str | None = None,
               ulb_id: int | None = None, contractor_id: int | None = None, past_grace: bool | None = None,
               alerted: bool | None = None):
    """Every complaint/permit currently missing its expected evidence, including those still inside the grace window."""
    stmt = select(cand)
    for column, value in ((cand.c.rule_code, rule_code), (cand.c.ulb_id, ulb_id), (cand.c.contractor_id, contractor_id),
                          (cand.c.past_grace, past_grace)):
        if value is not None:
            stmt = stmt.where(column == value)
    if alerted is not None:
        stmt = stmt.where(cand.c.alert_id.is_not(None) if alerted else cand.c.alert_id.is_(None))
    return paged(db, stmt.order_by(cand.c.evidence_deadline), page, lambda r: dict(r._mapping))


@router.get("/alerts")
def list_alerts(db: DB, page: Paging, principal: Principal = Depends(require(*READERS)), status: str | None = None,
                rule_code: str | None = None, contractor_id: int | None = None, ulb_id: int | None = None):
    stmt = (select(ShadowEntryAlert, Manhole.code, Ulb.name, Contractor.name, DetectionRule.title)
            .join(Complaint, Complaint.complaint_id == ShadowEntryAlert.complaint_id)
            .join(Manhole, Manhole.manhole_id == Complaint.manhole_id).join(Ulb, Ulb.ulb_id == Manhole.ulb_id)
            .join(DetectionRule, DetectionRule.rule_code == ShadowEntryAlert.rule_code)
            .outerjoin(Contractor, Contractor.contractor_id == ShadowEntryAlert.contractor_id))
    for column, value in ((ShadowEntryAlert.status, status), (ShadowEntryAlert.rule_code, rule_code),
                          (ShadowEntryAlert.contractor_id, contractor_id), (Manhole.ulb_id, ulb_id)):
        if value is not None:
            stmt = stmt.where(column == value)
    return paged(db, stmt.order_by(ShadowEntryAlert.detected_at.desc(), ShadowEntryAlert.alert_id.desc()), page,
                 lambda r: {**to_dict(r[0]), "manhole_code": r[1], "ulb_name": r[2], "contractor_name": r[3], "rule_title": r[4]})


@router.get("/alerts/{alert_id}")
def alert_detail(alert_id: int, db: DB, principal: Principal = Depends(require(*READERS))):
    alert = db.get(ShadowEntryAlert, alert_id)
    if alert is None:
        raise NotFound("No such alert.")
    events = db.scalars(select(ShadowEntryAlertEvent).where(ShadowEntryAlertEvent.alert_id == alert_id)
                        .order_by(ShadowEntryAlertEvent.event_id)).all()
    holds = db.execute(select(InvoiceHold, Invoice.invoice_no, Invoice.amount_inr)
                       .join(Invoice, Invoice.invoice_id == InvoiceHold.invoice_id)
                       .where(InvoiceHold.alert_id == alert_id).order_by(InvoiceHold.hold_id)).all()
    return {**to_dict(alert), "events": [to_dict(e) for e in events],
            "holds": [{**to_dict(h), "invoice_no": no, "amount_inr": amount} for h, no, amount in holds]}


@router.post("/scan")
def run_scan(db: DB, principal: Principal = Depends(require(*DECIDERS))):
    """Idempotent: opens alerts whose evidence window has closed, sends changed ones to review, never closes anything."""
    return dict(db.execute(text("SELECT * FROM scan_shadow_entries(now())")).mappings().one())


@router.post("/alerts/{alert_id}/review")
def review_alert(alert_id: int, body: ReviewIn, db: DB, principal: Principal = Depends(require(*DECIDERS))):
    row = db.execute(text("SELECT * FROM review_shadow_alert(:id, :decision, :note, :by)"),
                     {"id": alert_id, "decision": body.decision, "note": body.note, "by": principal.user_id}).mappings().one()
    return dict(row)


@router.get("/rules")
def list_rules(db: DB, principal: Principal = Depends(require(*READERS))):
    return {"items": [to_dict(r) for r in db.scalars(select(DetectionRule).order_by(DetectionRule.rule_code))]}


@router.patch("/rules/{rule_code}")
def toggle_rule(rule_code: str, body: RuleToggleIn, db: DB, principal: Principal = Depends(require("ADMIN"))):
    result = db.execute(update(DetectionRule).where(DetectionRule.rule_code == rule_code).values(enabled=body.enabled))
    if result.rowcount == 0:
        raise NotFound("No such detection rule.")
    return to_dict(db.get(DetectionRule, rule_code))
