"""Complaints, jobs, machine deployments, mechanisation waivers: the mechanised-first workflow."""

from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select, text

from ..deps import DB, STAFF, WRITERS, Paging, Principal, paged, require, to_dict
from ..errors import Conflict, NotFound
from ..models import (Complaint, Contractor, EntryPermit, Job, Machine, MachineDeployment, Manhole,
                      MechanisationWaiver, ShadowEntryAlert, Ulb)
from ..schemas import (ComplaintIn, ComplaintPatch, DeploymentFinishIn, DeploymentIn, JobIn, JobPatch, ResolveIn,
                       WaiverIn)

router = APIRouter(tags=["complaints and jobs"])
IST = timezone(timedelta(hours=5, minutes=30))


def _day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=IST)


# --- complaints ------------------------------------------------------------------------------------------------
@router.get("/complaints")
def list_complaints(db: DB, page: Paging, principal: Principal = Depends(require(*STAFF)), status: str | None = None,
                    ulb_id: int | None = None, manhole_id: int | None = None, resolution_code: str | None = None,
                    raised_from: date | None = None, raised_to: date | None = None, q: str | None = None):
    stmt = (select(Complaint, Manhole.code, Manhole.ulb_id, Ulb.name)
            .join(Manhole, Manhole.manhole_id == Complaint.manhole_id).join(Ulb, Ulb.ulb_id == Manhole.ulb_id))
    if status:
        stmt = stmt.where(Complaint.status == status)
    if ulb_id:
        stmt = stmt.where(Manhole.ulb_id == ulb_id)
    if manhole_id:
        stmt = stmt.where(Complaint.manhole_id == manhole_id)
    if resolution_code:
        stmt = stmt.where(Complaint.resolution_code == resolution_code)
    if raised_from:
        stmt = stmt.where(Complaint.raised_at >= _day_start(raised_from))
    if raised_to:
        stmt = stmt.where(Complaint.raised_at < _day_start(raised_to) + timedelta(days=1))
    if q:
        like = q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        stmt = stmt.where(or_(Manhole.code.ilike(like + "%", escape="\\"), Complaint.description.ilike("%" + like + "%", escape="\\")))
    return paged(db, stmt.order_by(Complaint.raised_at.desc(), Complaint.complaint_id.desc()), page,
                 lambda r: {**to_dict(r[0]), "manhole_code": r[1], "ulb_id": r[2], "ulb_name": r[3]})


@router.post("/complaints", status_code=201)
def create_complaint(body: ComplaintIn, db: DB, principal: Principal = Depends(require(*WRITERS))):
    row = Complaint(manhole_id=body.manhole_id, description=body.description)
    db.add(row)
    db.flush()
    return to_dict(row)


@router.get("/complaints/{complaint_id}")
def complaint_detail(complaint_id: int, db: DB, principal: Principal = Depends(require(*STAFF))):
    c = db.get(Complaint, complaint_id)
    if c is None:
        raise NotFound("No such complaint.")
    jobs = db.execute(select(Job, Contractor.name).join(Contractor, Contractor.contractor_id == Job.contractor_id)
                      .where(Job.complaint_id == complaint_id).order_by(Job.job_id)).all()
    job_ids = [j.job_id for j, _ in jobs]
    deployments = db.execute(select(MachineDeployment, Machine.code, Machine.kind).join(Machine, Machine.machine_id == MachineDeployment.machine_id)
                             .where(MachineDeployment.job_id.in_(job_ids)).order_by(MachineDeployment.deploy_id)).all() if job_ids else []
    waivers = db.scalars(select(MechanisationWaiver).where(MechanisationWaiver.job_id.in_(job_ids))).all() if job_ids else []
    permits = db.scalars(select(EntryPermit).where(EntryPermit.job_id.in_(job_ids)).order_by(EntryPermit.permit_id)).all() if job_ids else []
    manhole = db.get(Manhole, c.manhole_id)
    return {
        **to_dict(c),
        "manhole": {**to_dict(manhole), "ulb_name": db.scalar(select(Ulb.name).where(Ulb.ulb_id == manhole.ulb_id))},
        "jobs": [{**to_dict(j), "contractor_name": name} for j, name in jobs],
        "deployments": [{**to_dict(d), "machine_code": code, "machine_kind": kind} for d, code, kind in deployments],
        "waivers": [to_dict(w) for w in waivers],
        "permits": [to_dict(p) for p in permits],
        "alerts": [to_dict(a) for a in db.scalars(select(ShadowEntryAlert).where(ShadowEntryAlert.complaint_id == complaint_id))],
    }


@router.patch("/complaints/{complaint_id}")
def edit_complaint(complaint_id: int, body: ComplaintPatch, db: DB, principal: Principal = Depends(require(*WRITERS))):
    c = db.get(Complaint, complaint_id)
    if c is None:
        raise NotFound("No such complaint.")
    c.description = body.description
    db.flush()
    return to_dict(c)


@router.post("/complaints/{complaint_id}/resolve")
def resolve_complaint(complaint_id: int, body: ResolveIn, db: DB, principal: Principal = Depends(require(*WRITERS))):
    """Record the resolution. Deliberately NOT blocked when no clearance evidence exists: the complaint system is the
    ULB's own record, and the gap is exactly what the absence scan exists to find (PROJECT_SPEC Q2)."""
    c = db.scalar(select(Complaint).where(Complaint.complaint_id == complaint_id).with_for_update())
    if c is None:
        raise NotFound("No such complaint.")
    if c.status == "RESOLVED":
        raise Conflict("This complaint is already resolved.")
    c.status, c.resolution_code, c.resolved_by = "RESOLVED", body.resolution_code, principal.user_id
    c.resolved_at = datetime.now(timezone.utc)
    db.flush()
    evidence = db.scalar(text(
        "SELECT EXISTS (SELECT 1 FROM job j JOIN machine_deployment d ON d.job_id = j.job_id "
        "WHERE j.complaint_id = :c AND d.outcome = 'CLEARED') OR EXISTS (SELECT 1 FROM job j JOIN entry_permit p ON p.job_id = j.job_id "
        "WHERE j.complaint_id = :c AND p.status = 'CLOSED' AND p.authorised_at IS NOT NULL)"), {"c": complaint_id})
    needs = db.scalar(text("SELECT requires_evidence FROM resolution_type WHERE code = :code"), {"code": body.resolution_code})
    return {**to_dict(c), "evidence_on_file": bool(evidence),
            "warning": None if (evidence or not needs) else
            "No clearance evidence is on file yet. If none is recorded within the grace window the absence scan will raise an alert."}


# --- jobs ------------------------------------------------------------------------------------------------------
@router.get("/jobs")
def list_jobs(db: DB, page: Paging, principal: Principal = Depends(require(*STAFF, "CONTRACTOR")), complaint_id: int | None = None,
              contractor_id: int | None = None, status: str | None = None, method: str | None = None):
    stmt = (select(Job, Contractor.name, Manhole.code).join(Contractor, Contractor.contractor_id == Job.contractor_id)
            .join(Complaint, Complaint.complaint_id == Job.complaint_id).join(Manhole, Manhole.manhole_id == Complaint.manhole_id))
    if principal.role == "CONTRACTOR":
        stmt = stmt.where(Job.contractor_id == principal.contractor_id)
    for column, value in ((Job.complaint_id, complaint_id), (Job.contractor_id, contractor_id), (Job.status, status), (Job.method, method)):
        if value is not None:
            stmt = stmt.where(column == value)
    return paged(db, stmt.order_by(Job.job_id.desc()), page,
                 lambda r: {**to_dict(r[0]), "contractor_name": r[1], "manhole_code": r[2]})


@router.post("/jobs", status_code=201)
def create_job(body: JobIn, db: DB, principal: Principal = Depends(require(*WRITERS))):
    job = Job(complaint_id=body.complaint_id, contractor_id=body.contractor_id, created_by=principal.user_id)
    db.add(job)
    db.flush()                                   # the guard trigger refuses blacklisted/suspended/unlicensed contractors
    return to_dict(job)


@router.get("/jobs/{job_id}")
def job_detail(job_id: int, db: DB, principal: Principal = Depends(require(*STAFF, "CONTRACTOR"))):
    stmt = select(Job).where(Job.job_id == job_id)
    if principal.role == "CONTRACTOR":
        stmt = stmt.where(Job.contractor_id == principal.contractor_id)
    job = db.scalar(stmt)
    if job is None:
        raise NotFound("No such job.")
    deployments = db.execute(select(MachineDeployment, Machine.code).join(Machine, Machine.machine_id == MachineDeployment.machine_id)
                             .where(MachineDeployment.job_id == job_id).order_by(MachineDeployment.deploy_id)).all()
    waiver = db.scalar(select(MechanisationWaiver).where(MechanisationWaiver.job_id == job_id))
    permits = db.scalars(select(EntryPermit).where(EntryPermit.job_id == job_id).order_by(EntryPermit.permit_id)).all()
    return {**to_dict(job), "deployments": [{**to_dict(d), "machine_code": code} for d, code in deployments],
            "waiver": to_dict(waiver) if waiver else None, "permits": [to_dict(p) for p in permits]}


@router.patch("/jobs/{job_id}")
def update_job(job_id: int, body: JobPatch, db: DB, principal: Principal = Depends(require(*WRITERS))):
    job = db.scalar(select(Job).where(Job.job_id == job_id).with_for_update())
    if job is None:
        raise NotFound("No such job.")
    job.status = body.status
    db.flush()
    return to_dict(job)


# --- machine deployments (clearance evidence) ----------------------------------------------------------------------
@router.post("/jobs/{job_id}/deployments", status_code=201)
def deploy_machine(job_id: int, body: DeploymentIn, db: DB, principal: Principal = Depends(require(*WRITERS))):
    if db.get(Job, job_id) is None:
        raise NotFound("No such job.")
    row = MachineDeployment(job_id=job_id, machine_id=body.machine_id, started_at=body.started_at,
                            ended_at=body.ended_at, outcome=body.outcome, recorded_by=principal.user_id)
    db.add(row)
    db.flush()
    db.refresh(row)                              # include the DB-assigned outcome receipt when finalized at creation
    return to_dict(row)


@router.post("/deployments/{deploy_id}/finish")
def finish_deployment(deploy_id: int, body: DeploymentFinishIn, db: DB, principal: Principal = Depends(require(*WRITERS))):
    d = db.scalar(select(MachineDeployment).where(MachineDeployment.deploy_id == deploy_id).with_for_update())
    if d is None:
        raise NotFound("No such deployment.")
    if d.outcome is not None:
        raise Conflict("This deployment already has an outcome.")
    d.ended_at, d.outcome = body.ended_at, body.outcome
    db.flush()
    db.refresh(d)                                # the finalization instant is assigned by the database trigger
    if body.outcome == "CLEARED":                # a cleared blockage completes the job
        job = db.get(Job, d.job_id)
        if job.status in ("PLANNED", "IN_PROGRESS"):
            job.status = "COMPLETED"
    return to_dict(d)


# --- waivers ---------------------------------------------------------------------------------------------------
@router.post("/jobs/{job_id}/waiver", status_code=201)
def file_waiver(job_id: int, body: WaiverIn, db: DB, principal: Principal = Depends(require("ENGINEER"))):
    """Only the Responsible Sanitation Authority (ENGINEER) may record why a machine cannot do the job (BR-01)."""
    if db.get(Job, job_id) is None:
        raise NotFound("No such job.")
    w = MechanisationWaiver(job_id=job_id, reason_code=body.reason_code, justification=body.justification,
                            approved_by=principal.user_id)
    db.add(w)
    db.flush()
    db.refresh(db.get(Job, job_id))              # the trigger flipped job.method to MANUAL_EXCEPTION
    return to_dict(w)
