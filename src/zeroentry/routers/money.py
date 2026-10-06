"""Consequences and payments: incidents (the atomic fatality transaction), compensation cases, invoices and holds."""

from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, text

from ..deps import DB, STAFF, WRITERS, Paging, Principal, paged, require, to_dict
from ..errors import Forbidden, NotFound
from ..models import CompensationCase, Contractor, Incident, Invoice, InvoiceHold, Job, Manhole, Ulb, Worker
from ..schemas import IncidentIn, InvoiceIn, NoteIn, PaymentIn
from ..views import v_invoice_status as vinv

router = APIRouter(tags=["incidents, compensation, invoices"])
IST = timezone(timedelta(hours=5, minutes=30))
VIEW = (*STAFF, "CONTRACTOR")


def _own(stmt, column, principal: Principal):
    return stmt.where(column == principal.contractor_id) if principal.role == "CONTRACTOR" else stmt


# --- incidents ---------------------------------------------------------------------------------------------------
@router.post("/incidents", status_code=201)
def record_incident(body: IncidentIn, db: DB, principal: Principal = Depends(require("ADMIN", "ENGINEER", "SUPERVISOR"))):
    """ONE call, ONE transaction: incident + compensation case + contractor sanction + stop-work + invoice holds.
    If any step fails nothing is written (PROJECT_SPEC BR-20)."""
    new_id = db.execute(
        text("CALL record_incident(:t, :occ, :worker, :manhole, :descr, :by, :permit, :job, NULL::bigint)"),
        {"t": body.incident_type, "occ": body.occurred_at, "worker": body.worker_id, "manhole": body.manhole_id,
         "descr": body.description, "by": principal.user_id, "permit": body.permit_id, "job": body.job_id}
    ).mappings().one()["p_incident_id"]
    return _incident_detail(db, new_id)


def _incident_detail(db, incident_id: int) -> dict:
    inc = db.get(Incident, incident_id)
    case = db.scalar(select(CompensationCase).where(CompensationCase.incident_id == incident_id))
    contractor = db.get(Contractor, inc.contractor_id)
    holds = db.scalars(select(InvoiceHold).where(InvoiceHold.incident_id == incident_id)).all()
    return {**to_dict(inc), "compensation_case": to_dict(case) if case else None,
            "contractor": {"contractor_id": contractor.contractor_id, "name": contractor.name, "status": contractor.status},
            "invoice_holds": [to_dict(h) for h in holds]}


@router.get("/incidents")
def list_incidents(db: DB, page: Paging, principal: Principal = Depends(require(*VIEW)), incident_type: str | None = None,
                   contractor_id: int | None = None, ulb_id: int | None = None, occurred_from: date | None = None,
                   occurred_to: date | None = None):
    stmt = (select(Incident, Worker.full_name, Contractor.name, Manhole.code, Ulb.name)
            .outerjoin(Worker, Worker.worker_id == Incident.worker_id).join(Contractor, Contractor.contractor_id == Incident.contractor_id)
            .join(Manhole, Manhole.manhole_id == Incident.manhole_id).join(Ulb, Ulb.ulb_id == Manhole.ulb_id))
    stmt = _own(stmt, Incident.contractor_id, principal)
    for column, value in ((Incident.incident_type, incident_type), (Incident.contractor_id, contractor_id), (Manhole.ulb_id, ulb_id)):
        if value is not None:
            stmt = stmt.where(column == value)
    if occurred_from:
        stmt = stmt.where(Incident.occurred_at >= datetime.combine(occurred_from, time.min, tzinfo=IST))
    if occurred_to:
        stmt = stmt.where(Incident.occurred_at < datetime.combine(occurred_to, time.min, tzinfo=IST) + timedelta(days=1))
    return paged(db, stmt.order_by(Incident.occurred_at.desc()), page,
                 lambda r: {**to_dict(r[0]), "worker_name": r[1], "contractor_name": r[2], "manhole_code": r[3], "ulb_name": r[4]})


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: int, db: DB, principal: Principal = Depends(require(*VIEW))):
    inc = db.scalar(_own(select(Incident).where(Incident.incident_id == incident_id), Incident.contractor_id, principal))
    if inc is None:
        raise NotFound("No such incident.")
    return _incident_detail(db, incident_id)


# --- compensation ------------------------------------------------------------------------------------------------
@router.get("/compensation-cases")
def list_cases(db: DB, page: Paging, principal: Principal = Depends(require(*VIEW)), status: str | None = None,
               contractor_id: int | None = None, overdue: bool | None = None):
    stmt = (select(CompensationCase, Incident.incident_type, Incident.occurred_at, Incident.contractor_id, Contractor.name)
            .join(Incident, Incident.incident_id == CompensationCase.incident_id)
            .join(Contractor, Contractor.contractor_id == Incident.contractor_id))
    stmt = _own(stmt, Incident.contractor_id, principal)
    if status:
        stmt = stmt.where(CompensationCase.status == status)
    if contractor_id:
        stmt = stmt.where(Incident.contractor_id == contractor_id)
    if overdue:
        stmt = stmt.where(CompensationCase.status != "PAID", CompensationCase.due_by < datetime.now(IST).date())
    return paged(db, stmt.order_by(CompensationCase.due_by), page,
                 lambda r: {**to_dict(r[0]), "incident_type": r[1], "occurred_at": r[2], "contractor_id": r[3],
                            "contractor_name": r[4]})


@router.post("/compensation-cases/{case_id}/payments")
def pay_compensation(case_id: int, body: PaymentIn, db: DB, principal: Principal = Depends(require(*WRITERS))):
    row = db.execute(text("SELECT * FROM record_compensation_payment(:id, :amount, now())"),
                     {"id": case_id, "amount": body.amount}).mappings().one()
    return dict(row)


# --- invoices and holds ----------------------------------------------------------------------------------------
@router.get("/invoices")
def list_invoices(db: DB, page: Paging, principal: Principal = Depends(require(*VIEW)), job_id: int | None = None,
                  status: str | None = None, on_hold: bool | None = None, contractor_id: int | None = None):
    stmt = select(vinv)
    stmt = _own(stmt, vinv.c.contractor_id, principal)
    for column, value in ((vinv.c.job_id, job_id), (vinv.c.status, status), (vinv.c.on_hold, on_hold), (vinv.c.contractor_id, contractor_id)):
        if value is not None:
            stmt = stmt.where(column == value)
    return paged(db, stmt.order_by(vinv.c.invoice_id.desc()), page, lambda r: dict(r._mapping))


@router.post("/invoices", status_code=201)
def submit_invoice(body: InvoiceIn, db: DB, principal: Principal = Depends(require(*WRITERS, "CONTRACTOR"))):
    job = db.get(Job, body.job_id)
    if job is None:
        raise NotFound("No such job.")
    if principal.role == "CONTRACTOR" and job.contractor_id != principal.contractor_id:
        raise Forbidden("A contractor can only invoice its own jobs.")
    row = Invoice(job_id=body.job_id, invoice_no=body.invoice_no, amount_inr=body.amount_inr)
    db.add(row)
    db.flush()
    held = db.scalar(select(vinv.c.on_hold).where(vinv.c.invoice_id == row.invoice_id))
    return {**to_dict(row), "on_hold": bool(held)}


def _decide(db, invoice_id: int, principal: Principal, status: str) -> dict:
    row = db.scalar(select(Invoice).where(Invoice.invoice_id == invoice_id).with_for_update())
    if row is None:
        raise NotFound("No such invoice.")
    row.status = status
    if status in ("APPROVED", "REJECTED"):
        row.decided_by = principal.user_id
    db.flush()                                   # an unreleased hold refuses APPROVED / PAID here (409)
    return to_dict(row)


@router.post("/invoices/{invoice_id}/approve")
def approve_invoice(invoice_id: int, db: DB, principal: Principal = Depends(require(*WRITERS))):
    return _decide(db, invoice_id, principal, "APPROVED")


@router.post("/invoices/{invoice_id}/reject")
def reject_invoice(invoice_id: int, db: DB, principal: Principal = Depends(require(*WRITERS))):
    return _decide(db, invoice_id, principal, "REJECTED")


@router.post("/invoices/{invoice_id}/pay")
def pay_invoice(invoice_id: int, db: DB, principal: Principal = Depends(require(*WRITERS))):
    return _decide(db, invoice_id, principal, "PAID")


@router.get("/invoice-holds")
def list_holds(db: DB, page: Paging, principal: Principal = Depends(require(*WRITERS, "AUDITOR")), active: bool = True,
               reason: str | None = None):
    stmt = (select(InvoiceHold, Invoice.invoice_no, Invoice.amount_inr, Job.contractor_id)
            .join(Invoice, Invoice.invoice_id == InvoiceHold.invoice_id).join(Job, Job.job_id == Invoice.job_id))
    if active:
        stmt = stmt.where(InvoiceHold.released_at.is_(None))
    if reason:
        stmt = stmt.where(InvoiceHold.reason == reason)
    return paged(db, stmt.order_by(InvoiceHold.hold_id.desc()), page,
                 lambda r: {**to_dict(r[0]), "invoice_no": r[1], "amount_inr": r[2], "contractor_id": r[3]})


@router.post("/invoice-holds/{hold_id}/release")
def release_hold(hold_id: int, body: NoteIn, db: DB, principal: Principal = Depends(require(*WRITERS))):
    db.execute(text("SELECT release_invoice_hold(:id, :actor, :note)"),
               {"id": hold_id, "actor": principal.user_id, "note": body.note})
    return to_dict(db.get(InvoiceHold, hold_id))
