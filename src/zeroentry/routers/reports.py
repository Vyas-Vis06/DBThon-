"""Dashboards and reports. Aggregates (COUNT, SUM, AVG, MIN, MAX), views, and role-scoped counters."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text

from ..deps import DB, STAFF, Principal, require
from ..models import (CompensationCase, Complaint, Contractor, EntryPermit, Incident, InvoiceHold, Job, PermitCrew,
                      ShadowEntryAlert)
from ..views import (v_compensation_overdue as overdue, v_contractor_risk as risk, v_permit_compliance as readiness,
                     v_ulb_year_incidents as incidents, v_ulb_year_kpi as kpi)

router = APIRouter(prefix="/reports", tags=["reports"])
ANALYSTS = ("ADMIN", "ENGINEER", "AUDITOR")


def _rows(db, stmt) -> list[dict]:
    return [dict(r._mapping) for r in db.execute(stmt)]


def _by(db, column, *where):
    """{value: count} for one column, e.g. permits by status."""
    stmt = select(column, func.count()).group_by(column)
    for clause in where:
        stmt = stmt.where(clause)
    return {key: n for key, n in db.execute(stmt)}


@router.get("/dashboard")
def dashboard(db: DB, principal: Principal = Depends(require())):
    """Role-shaped counters. Contractors and workers only ever see numbers about their own records."""
    role = principal.role
    if role in STAFF:
        out = {"complaints": _by(db, Complaint.status), "permits": _by(db, EntryPermit.status),
               "contractors": _by(db, Contractor.status)}
        if role == "SUPERVISOR":
            out["draft_permits_not_ready"] = db.scalar(select(func.count()).where(readiness.c.ready_to_authorise.is_(False)))
            return out
        out["alerts"] = _by(db, ShadowEntryAlert.status)
        out["invoices_on_hold"] = db.scalar(select(func.count(func.distinct(InvoiceHold.invoice_id))).where(InvoiceHold.released_at.is_(None)))
        out["compensation_overdue"] = dict(db.execute(
            select(func.count().label("cases"), func.coalesce(func.sum(overdue.c.amount_outstanding), 0).label("outstanding"))).mappings().one())
        total, mech = db.execute(select(func.sum(kpi.c.jobs), func.sum(kpi.c.mechanised_jobs))).one()
        out["zero_entry_rate_pct"] = round(100 * mech / total, 1) if total else None
        return out
    if role == "CONTRACTOR":
        cid = principal.contractor_id
        mine = EntryPermit.job_id.in_(select(Job.job_id).where(Job.contractor_id == cid))
        return {"jobs": db.scalar(select(func.count()).select_from(Job).where(Job.contractor_id == cid)),
                "permits": _by(db, EntryPermit.status, mine),
                "invoices_on_hold": db.scalar(text("SELECT count(*) FROM v_invoice_status WHERE contractor_id = :c AND on_hold"), {"c": cid}),
                "incidents": db.scalar(select(func.count()).select_from(Incident).where(Incident.contractor_id == cid))}
    crewed = EntryPermit.permit_id.in_(select(PermitCrew.permit_id).where(PermitCrew.worker_id == principal.worker_id))
    return {"my_permits": _by(db, EntryPermit.status, crewed)}

@router.get("/summary")
def summary(db: DB, principal: Principal = Depends(require(*ANALYSTS))):
    """Aggregate demonstration: COUNT, SUM, AVG, MIN, MAX over complaints, gas readings and compensation."""
    complaints = db.execute(select(
        func.count().label("complaints"),
        func.count().filter(Complaint.status == "RESOLVED").label("resolved"),
        func.round(func.avg(func.extract("epoch", Complaint.resolved_at - Complaint.raised_at) / 3600), 1).label("avg_hours_to_resolve"),
        func.round(func.min(func.extract("epoch", Complaint.resolved_at - Complaint.raised_at) / 3600), 1).label("min_hours_to_resolve"),
        func.round(func.max(func.extract("epoch", Complaint.resolved_at - Complaint.raised_at) / 3600), 1).label("max_hours_to_resolve"),
    )).mappings().one()
    money = db.execute(select(
        func.count().label("cases"), func.coalesce(func.sum(CompensationCase.amount_due), 0).label("total_due"),
        func.coalesce(func.sum(CompensationCase.amount_paid), 0).label("total_paid"),
        func.coalesce(func.avg(CompensationCase.amount_due), 0).label("avg_case"),
        func.min(CompensationCase.due_by).label("earliest_deadline"), func.max(CompensationCase.due_by).label("latest_deadline"),
    )).mappings().one()
    return {"complaints": dict(complaints), "compensation": dict(money)}


@router.get("/ulb-kpis")
def ulb_kpis(db: DB, principal: Principal = Depends(require(*ANALYSTS)), year: int | None = None):
    k, i = select(kpi), select(incidents)
    if year:
        k, i = k.where(kpi.c.year == year), i.where(incidents.c.year == year)
    return {"zero_entry": _rows(db, k.order_by(kpi.c.year.desc(), kpi.c.ulb_name)),
            "incidents": _rows(db, i.order_by(incidents.c.year.desc(), incidents.c.ulb_name))}


@router.get("/contractor-risk")
def contractor_risk(db: DB, principal: Principal = Depends(require(*ANALYSTS))):
    return {"items": _rows(db, select(risk).order_by(risk.c.risk_score.desc(), risk.c.name))}


@router.get("/compensation-overdue")
def compensation_overdue(db: DB, principal: Principal = Depends(require(*ANALYSTS))):
    return {"items": _rows(db, select(overdue).order_by(overdue.c.days_overdue.desc()))}


@router.get("/shadow-summary")
def shadow_summary(db: DB, principal: Principal = Depends(require(*ANALYSTS))):
    """Alerts by rule and status, with the oldest still unresolved (GROUP BY + COUNT + MIN)."""
    rows = db.execute(select(ShadowEntryAlert.rule_code, ShadowEntryAlert.status, func.count().label("alerts"),
                             func.min(ShadowEntryAlert.detected_at).label("oldest"))
                      .group_by(ShadowEntryAlert.rule_code, ShadowEntryAlert.status)
                      .order_by(ShadowEntryAlert.rule_code, ShadowEntryAlert.status)).mappings().all()
    return {"items": [dict(r) for r in rows]}


@router.get("/permit-readiness")
def permit_readiness(db: DB, principal: Principal = Depends(require(*STAFF))):
    return {"items": _rows(db, select(readiness).order_by(readiness.c.permit_id))}
