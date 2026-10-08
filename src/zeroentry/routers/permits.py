"""Entry permits: the zero-entry workflow. The router orchestrates; the database decides (clause gate, state machine,
freeze, gas and entry-log rules). A refusal from a trigger surfaces as a 409/422 with the database's own wording."""

import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.orm import Session

from ..deps import DB, STAFF, Paging, Principal, paged, require, to_dict
from ..errors import Conflict, Forbidden, NotFound
from ..idempotency import body_digest, command_key, replay_or_lock, save_result
from ..models import (AppUser, Complaint, Contractor, EntryLog, EntryPermit, GasDetector, GasReading, GearIssue, GearItem,
                      Job, Manhole, MechanisationWaiver, PermitCrew, Ulb, Worker)
from ..models import PermitSafetyEvent
from ..schemas import CrewIn, EntryIn, ExitIn, GearIssueIn, PermitIn, ReadinessIn, ReadingIn, ReasonIn, SiteGearIn

router = APIRouter(prefix="/permits", tags=["permits"])
IST = timezone(timedelta(hours=5, minutes=30))
OPERATE = ("SUPERVISOR",)                      # runs the permit: crew, gear, readings, entries
DECIDE = ("SUPERVISOR", "ENGINEER")            # may authorise, close, abort, cancel
VIEW = (*STAFF, "CONTRACTOR", "WORKER")


def _visible(stmt, principal: Principal):
    """Narrow a SELECT that already joins EntryPermit and Job to what this role may see."""
    if principal.role == "CONTRACTOR":
        return stmt.where(Job.contractor_id == principal.contractor_id)
    if principal.role == "WORKER":
        return stmt.where(EntryPermit.permit_id.in_(select(PermitCrew.permit_id).where(PermitCrew.worker_id == principal.worker_id)))
    return stmt


def _load(db: Session, permit_id: int, principal: Principal, *, lock: bool = False) -> EntryPermit:
    stmt = _visible(select(EntryPermit).join(Job, Job.job_id == EntryPermit.job_id).where(EntryPermit.permit_id == permit_id), principal)
    if lock:
        stmt = stmt.with_for_update(of=EntryPermit)
    permit = db.scalar(stmt)
    if permit is None:
        raise NotFound("No such permit.")
    return permit


def _operable(db: Session, permit_id: int, principal: Principal, *, lock: bool = False) -> EntryPermit:
    """A permit this user may change: a supervisor only their own; an engineer any."""
    permit = _load(db, permit_id, principal, lock=lock)
    if principal.role == "SUPERVISOR" and permit.supervisor_id != principal.user_id:
        raise Forbidden("This permit belongs to another supervisor.")
    return permit


def checklist(db: Session, permit_id: int) -> list[dict[str, Any]]:
    rows = db.execute(text(
        "SELECT c.clause_code, l.title, l.legal_ref, c.passed, c.detail "
        "FROM permit_clause_check(:pid, now()) c JOIN legal_clause l ON l.clause_code = c.clause_code ORDER BY l.sort_order"),
        {"pid": permit_id}).mappings().all()
    return [dict(r) for r in rows]


def _entry(e: EntryLog, name: str | None = None, namaste: str | None = None) -> dict[str, Any]:
    start, end = e.period.lower, e.period.upper
    return {"entry_id": e.entry_id, "permit_id": e.permit_id, "worker_id": e.worker_id, "worker_name": name, "namaste_id": namaste,
            "receipt_id": e.receipt_id,
            "entered_at": start, "exited_at": end, "open": end is None,
            "minutes": None if end is None else round((end - start).total_seconds() / 60),
            "entry_recorded_at": e.recorded_at, "exit_recorded_at": e.exit_recorded_at}


# --- list and dossier --------------------------------------------------------------------------------------------
@router.get("")
def list_permits(db: DB, page: Paging, principal: Principal = Depends(require(*VIEW)), status: str | None = None,
                 job_id: int | None = None, ulb_id: int | None = None, contractor_id: int | None = None,
                 supervisor_id: int | None = None, created_from: date | None = None, created_to: date | None = None,
                 q: str | None = None):
    stmt = (select(EntryPermit, Contractor.name, Manhole.code, Ulb.name)
            .join(Job, Job.job_id == EntryPermit.job_id)
            .outerjoin(Contractor, Contractor.contractor_id == Job.contractor_id)      # outer: RLS may hide the contractor from a worker
            .join(Complaint, Complaint.complaint_id == Job.complaint_id).join(Manhole, Manhole.manhole_id == Complaint.manhole_id)
            .join(Ulb, Ulb.ulb_id == Manhole.ulb_id))
    stmt = _visible(stmt, principal)
    for column, value in ((EntryPermit.status, status), (EntryPermit.job_id, job_id), (Manhole.ulb_id, ulb_id),
                          (Job.contractor_id, contractor_id), (EntryPermit.supervisor_id, supervisor_id)):
        if value is not None:
            stmt = stmt.where(column == value)
    if created_from:
        stmt = stmt.where(EntryPermit.created_at >= datetime.combine(created_from, time.min, tzinfo=IST))
    if created_to:
        stmt = stmt.where(EntryPermit.created_at < datetime.combine(created_to, time.min, tzinfo=IST) + timedelta(days=1))
    if q:
        like = q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_") + "%"
        stmt = stmt.where(Manhole.code.ilike(like, escape="\\"))
    return paged(db, stmt.order_by(EntryPermit.permit_id.desc()), page,
                 lambda r: {**to_dict(r[0]), "contractor_name": r[1], "manhole_code": r[2], "ulb_name": r[3]})


@router.get("/{permit_id}")
def permit_dossier(permit_id: int, db: DB, principal: Principal = Depends(require(*VIEW))):
    """Everything about one permit in one answer: permit ⋈ job ⋈ complaint ⋈ manhole ⋈ crew ⋈ worker ⋈ gear ⋈ readings ⋈ detector."""
    permit = _load(db, permit_id, principal)
    job = db.get(Job, permit.job_id)
    if job is None:
        # The permit was visible, but a related row may still be filtered by a narrower
        # legacy RLS policy. Never turn that situation into an AttributeError/500.
        raise NotFound("The permit's linked work order is not visible in this scope.")
    complaint = db.get(Complaint, job.complaint_id)
    if complaint is None:
        raise NotFound("The permit's linked complaint is not visible in this scope.")
    manhole = db.get(Manhole, complaint.manhole_id)
    if manhole is None:
        raise NotFound("The permit's linked manhole is not visible in this scope.")
    crew = db.execute(select(PermitCrew.crew_role, PermitCrew.acknowledged_at, PermitCrew.acknowledged_by, Worker)
                      .join(Worker, Worker.worker_id == PermitCrew.worker_id)
                      .where(PermitCrew.permit_id == permit_id).order_by(PermitCrew.crew_role, Worker.full_name)).all()
    gear = db.execute(select(GearIssue, GearItem.name, GearItem.statutory).join(GearItem, GearItem.gear_code == GearIssue.gear_code)
                      .where(GearIssue.permit_id == permit_id).order_by(GearIssue.worker_id, GearItem.name)).all()
    readings = db.execute(select(GasReading, GasDetector.serial_no, AppUser.full_name)
                          .join(GasDetector, GasDetector.detector_id == GasReading.detector_id)
                          .join(AppUser, AppUser.user_id == GasReading.recorded_by)
                          .where(GasReading.permit_id == permit_id).order_by(GasReading.taken_at.desc())).all()
    entries = db.execute(select(EntryLog, Worker.full_name, Worker.namaste_id).join(Worker, Worker.worker_id == EntryLog.worker_id)
                         .where(EntryLog.permit_id == permit_id).order_by(EntryLog.entry_id)).all()
    waiver = db.scalar(select(MechanisationWaiver).where(MechanisationWaiver.job_id == permit.job_id))
    readiness = db.execute(text("""
      SELECT DISTINCT ON (kind) readiness_id,permit_id,kind,passed,recorded_by,recorded_at,expires_at,details,source_mode
      FROM permit_readiness WHERE permit_id=:permit ORDER BY kind,recorded_at DESC,readiness_id DESC
    """), {"permit": permit_id}).mappings().all()
    site_gear = db.execute(text("""
      SELECT s.site_gear_id,s.permit_id,s.gear_asset_id,s.issued_by,s.issued_at,s.returned_at,
             a.gear_code,a.serial_no,a.status AS asset_status,a.inspection_valid_until
      FROM permit_site_gear s JOIN gear_asset a USING (gear_asset_id)
      WHERE s.permit_id=:permit ORDER BY s.issued_at DESC,s.site_gear_id DESC
    """), {"permit": permit_id}).mappings().all()
    current_receipt = db.execute(text(
        "SELECT receipt_id,decision,evidence_revision,evaluated_at,expires_at, "
        "(decision='AUTHORISED' AND evidence_revision=:revision AND :status='AUTHORISED' "
        " AND expires_at IS NOT NULL AND clock_timestamp()<expires_at) AS usable "
        "FROM permit_decision_receipt WHERE permit_id=:pid ORDER BY evaluated_at DESC,receipt_id DESC LIMIT 1"
    ), {"pid": permit_id, "revision": getattr(permit, "evidence_revision", 0), "status": permit.status}).mappings().first()
    return {
        "permit": to_dict(permit),
        "policy": db.execute(text("SELECT u.ulb_id, u.policy_mode, u.policy_mode = 'EDUCATIONAL' AS educational, "
                                  "'ULB policy setting stored in the application database; not an external legal citation.' AS policy_provenance "
                                  "FROM ulb u WHERE u.ulb_id=:ulb"), {"ulb": manhole.ulb_id}).mappings().one(),
        "evidence_revision": getattr(permit, "evidence_revision", 0),
        "current_receipt": dict(current_receipt) if current_receipt else None,
        "current_decision_usable": bool(current_receipt and current_receipt["usable"]),
        "job": {**to_dict(job), "contractor_name": db.scalar(select(Contractor.name).where(Contractor.contractor_id == job.contractor_id))},
        "complaint": {**to_dict(complaint), "manhole_code": manhole.code, "manhole_kind": manhole.kind, "depth_m": manhole.depth_m,
                      "ulb_name": db.scalar(select(Ulb.name).where(Ulb.ulb_id == manhole.ulb_id))},
        "waiver": to_dict(waiver) if waiver else None,
        "readiness": [dict(r) for r in readiness],
        "site_gear": [dict(r) for r in site_gear],
        "crew": [{"worker_id": w.worker_id, "full_name": w.full_name, "namaste_id": w.namaste_id, "crew_role": role,
                  "acknowledged_at": acknowledged_at, "acknowledged_by": acknowledged_by,
                  "medical_fit_until": w.medical_fit_until, "trained_until": w.trained_until, "is_active": w.is_active}
                 for role, acknowledged_at, acknowledged_by, w in crew],
        "gear": [{**to_dict(g), "gear_name": name, "statutory": statutory} for g, name, statutory in gear],
        "readings": [{**to_dict(r), "detector_serial": serial, "recorded_by_name": who} for r, serial, who in readings],
        "entries": [_entry(e, name, namaste) for e, name, namaste in entries],
        "receipts": [dict(r) for r in db.execute(text(
            "SELECT receipt_id,decision,evidence_revision,evaluated_at,expires_at,failures,snapshot_sha256, "
            "(decision='AUTHORISED' AND evidence_revision=:revision AND :status='AUTHORISED' "
            " AND expires_at IS NOT NULL AND clock_timestamp()<expires_at) AS usable "
            "FROM permit_decision_receipt WHERE permit_id=:pid ORDER BY evaluated_at DESC,receipt_id DESC LIMIT 5"
        ), {"pid": permit_id, "revision": getattr(permit, "evidence_revision", 0), "status": permit.status}).mappings().all()],
        "clauses": checklist(db, permit_id) if permit.status == "DRAFT" else None,
    }


@router.get("/{permit_id}/clauses")
def live_clauses(permit_id: int, db: DB, principal: Principal = Depends(require(*VIEW))):
    """The red/green checklist as of right now (read-only; nothing is authorised by looking)."""
    _load(db, permit_id, principal)
    clauses = checklist(db, permit_id)
    return {"ready_to_authorise": all(c["passed"] for c in clauses), "clauses": clauses}


# --- building the permit ----------------------------------------------------------------------------------------------
@router.post("", status_code=201)
def create_permit(body: PermitIn, db: DB, principal: Principal = Depends(require(*OPERATE))):
    permit = EntryPermit(job_id=body.job_id, supervisor_id=principal.user_id)
    db.add(permit)
    db.flush()                                   # refused unless the job has a waiver and is live
    return to_dict(permit)


@router.post("/{permit_id}/crew", status_code=201)
def add_crew(permit_id: int, body: CrewIn, db: DB, principal: Principal = Depends(require(*OPERATE))):
    permit = _operable(db, permit_id, principal)
    row = PermitCrew(permit_id=permit_id, worker_id=body.worker_id, crew_role=body.crew_role)
    db.add(row)
    db.flush()
    return to_dict(row)


@router.delete("/{permit_id}/crew/{worker_id}")
def remove_crew(permit_id: int, worker_id: int, db: DB, principal: Principal = Depends(require(*OPERATE))):
    _operable(db, permit_id, principal)
    row = db.get(PermitCrew, (permit_id, worker_id))
    if row is None:
        raise NotFound("That worker is not on this crew.")
    db.delete(row)
    db.flush()
    return {"removed": worker_id}


@router.post("/{permit_id}/gear", status_code=201)
def issue_gear(permit_id: int, body: GearIssueIn, db: DB, principal: Principal = Depends(require(*OPERATE)),
               idempotency_header: str | None = Header(default=None, alias="Idempotency-Key")):
    permit = _operable(db, permit_id, principal)
    key = command_key(idempotency_header or str(uuid4()))
    payload = body.model_dump(mode="json")
    digest = body_digest(payload)
    operation = f"permit:gear:{permit_id}"
    replay = replay_or_lock(db, principal.user_id, operation, key, digest)
    if replay is not None:
        return replay
    if body.gear_asset_id is not None:
        asset = db.execute(text(
            "SELECT a.gear_code,a.serial_no,a.ulb_id FROM gear_asset a "
            "JOIN job j ON j.job_id=:job JOIN complaint c ON c.complaint_id=j.complaint_id "
            "JOIN manhole m ON m.manhole_id=c.manhole_id "
            "WHERE a.gear_asset_id=:asset AND a.ulb_id=m.ulb_id"
        ), {"job": permit.job_id, "asset": body.gear_asset_id}).mappings().first()
        if asset is None:
            raise NotFound("No serial asset is available in this permit's ULB.")
        if asset["gear_code"] != body.gear_code or asset["serial_no"] != body.serial_no:
            raise Conflict("The selected asset does not match the supplied gear code and serial.", code="gear_asset_mismatch")
    row = GearIssue(permit_id=permit_id, worker_id=body.worker_id, gear_code=body.gear_code, serial_no=body.serial_no,
                    gear_asset_id=body.gear_asset_id, issued_by=principal.user_id)
    db.add(row)
    db.flush()
    result = to_dict(row)
    save_result(db, principal.user_id, operation, key, digest, result, 201)
    return result


@router.post("/{permit_id}/acknowledge")
def acknowledge_crew(
    permit_id: int,
    db: DB,
    principal: Principal = Depends(require("WORKER")),
    idempotency_header: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """A worker acknowledges only their own stored crew assignment."""
    _load(db, permit_id, principal)
    if principal.worker_id is None:
        raise Forbidden("This account is not linked to a worker record.")
    key = command_key(idempotency_header)
    body = {"permit_id": permit_id, "worker_id": principal.worker_id}
    digest = body_digest(body)
    operation = f"permit:acknowledge:{permit_id}"
    replay = replay_or_lock(db, principal.user_id, operation, key, digest)
    if replay is not None:
        return replay
    row = db.execute(text(
        "UPDATE permit_crew SET acknowledged_at=clock_timestamp(), acknowledged_by=:actor "
        "WHERE permit_id=:permit AND worker_id=:worker AND acknowledged_at IS NULL "
        "RETURNING permit_id,worker_id,acknowledged_at,acknowledged_by"
    ), {"actor": principal.user_id, "permit": permit_id, "worker": principal.worker_id}).mappings().first()
    if row is None:
        row = db.execute(text(
            "SELECT permit_id,worker_id,acknowledged_at,acknowledged_by FROM permit_crew "
            "WHERE permit_id=:permit AND worker_id=:worker"
        ), {"permit": permit_id, "worker": principal.worker_id}).mappings().first()
    if row is None:
        raise NotFound("You are not assigned to this permit.")
    if row["acknowledged_by"] != principal.user_id:
        raise Forbidden("This assignment was acknowledged by another account.")
    result = dict(row)
    save_result(db, principal.user_id, operation, key, digest, result, 200)
    return result


@router.post("/{permit_id}/readiness", status_code=201)
def record_readiness(
    permit_id: int,
    body: ReadinessIn,
    db: DB,
    principal: Principal = Depends(require(*OPERATE)),
    idempotency_header: str | None = Header(default=None, alias="Idempotency-Key"),
):
    _operable(db, permit_id, principal)
    key = command_key(idempotency_header)
    payload = body.model_dump(mode="json")
    digest = body_digest(payload)
    operation = f"permit:readiness:{permit_id}"
    replay = replay_or_lock(db, principal.user_id, operation, key, digest)
    if replay is not None:
        return replay
    row = db.execute(text(
        "INSERT INTO permit_readiness (permit_id,kind,passed,recorded_by,expires_at,details,source_mode) "
        "VALUES (:permit,:kind,:passed,:actor,:expires,CAST(:details AS jsonb),'TYPED') "
        "RETURNING readiness_id,permit_id,kind,passed,recorded_at,expires_at,details,source_mode"
    ), {"permit": permit_id, "kind": body.kind, "passed": body.passed, "actor": principal.user_id,
        "expires": body.expires_at, "details": json.dumps(body.details, separators=(",", ":"), ensure_ascii=False)}).mappings().one()
    result = dict(row)
    save_result(db, principal.user_id, operation, key, digest, result, 201)
    return result


@router.post("/{permit_id}/site-gear", status_code=201)
def issue_site_gear(
    permit_id: int,
    body: SiteGearIn,
    db: DB,
    principal: Principal = Depends(require(*OPERATE)),
    idempotency_header: str | None = Header(default=None, alias="Idempotency-Key"),
):
    _operable(db, permit_id, principal)
    key = command_key(idempotency_header)
    payload = body.model_dump(mode="json")
    digest = body_digest(payload)
    operation = f"permit:site-gear:{permit_id}"
    replay = replay_or_lock(db, principal.user_id, operation, key, digest)
    if replay is not None:
        return replay
    row = db.execute(text(
        "INSERT INTO permit_site_gear (permit_id,gear_asset_id,issued_by) "
        "VALUES (:permit,:asset,:actor) "
        "RETURNING site_gear_id,permit_id,gear_asset_id,issued_by,issued_at,returned_at"
    ), {"permit": permit_id, "asset": body.gear_asset_id, "actor": principal.user_id}).mappings().one()
    result = dict(row)
    save_result(db, principal.user_id, operation, key, digest, result, 201)
    return result


@router.get("/{permit_id}/receipts")
def permit_receipts(permit_id: int, db: DB, page: Paging, principal: Principal = Depends(require(*VIEW))):
    permit = _load(db, permit_id, principal)
    rows = db.execute(text(
        "SELECT receipt_id,permit_id,evidence_revision,decision,evaluated_at,expires_at,failures,snapshot_sha256, "
        "(decision='AUTHORISED' AND evidence_revision=:revision AND :status='AUTHORISED' "
        " AND expires_at IS NOT NULL AND clock_timestamp()<expires_at) AS usable "
        "FROM permit_decision_receipt WHERE permit_id=:permit ORDER BY evaluated_at DESC,receipt_id DESC "
        "LIMIT :limit OFFSET :offset"
    ), {"permit": permit_id, "revision": getattr(permit, "evidence_revision", 0), "status": permit.status,
        "limit": page.limit, "offset": page.offset}).mappings().all()
    total = db.scalar(text("SELECT count(*) FROM permit_decision_receipt WHERE permit_id=:permit"), {"permit": permit_id})
    return {"items": [dict(row) for row in rows], "total": total, "limit": page.limit, "offset": page.offset}


@router.delete("/{permit_id}/gear/{issue_id}")
def withdraw_gear(permit_id: int, issue_id: int, db: DB, principal: Principal = Depends(require(*OPERATE))):
    _operable(db, permit_id, principal)
    row = db.scalar(select(GearIssue).where(GearIssue.issue_id == issue_id, GearIssue.permit_id == permit_id))
    if row is None:
        raise NotFound("No such gear issue on this permit.")
    db.delete(row)
    db.flush()
    return {"removed": issue_id}


@router.post("/{permit_id}/readings", status_code=201)
def log_reading(permit_id: int, body: ReadingIn, db: DB, principal: Principal = Depends(require(*DECIDE)),
                idempotency_header: str | None = Header(default=None, alias="Idempotency-Key")):
    """Supervisor's digital sign-off: the reading is bound to a detector serial, the recorder and the server clock."""
    _operable(db, permit_id, principal)
    key = command_key(idempotency_header or str(uuid4()))
    payload = body.model_dump(mode="json")
    digest = body_digest(payload)
    operation = f"permit:readings:{permit_id}"
    replay = replay_or_lock(db, principal.user_id, operation, key, digest)
    if replay is not None:
        return replay
    row = GasReading(permit_id=permit_id, detector_id=body.detector_id, depth_level=body.depth_level, o2_pct=body.o2_pct,
                     h2s_ppm=body.h2s_ppm, lel_pct=body.lel_pct, co_ppm=body.co_ppm,
                     source_mode=body.source_mode, taken_at=body.taken_at or datetime.now(timezone.utc), recorded_by=principal.user_id)
    db.add(row)
    db.flush()
    result = to_dict(row)
    save_result(db, principal.user_id, operation, key, digest, result, 201)
    return result


# --- the gate ----------------------------------------------------------------------------------------------------------
@router.post("/{permit_id}/authorise")
def authorise(permit_id: int, db: DB, principal: Principal = Depends(require(*DECIDE)),
              idempotency_header: str | None = Header(default=None, alias="Idempotency-Key")):
    """Ask the database to authorise entry. A denial is a normal 200 answer carrying every clause and the reason it failed."""
    permit = _operable(db, permit_id, principal)
    key = command_key(idempotency_header or str(uuid4()))
    digest = body_digest({"permit_id": permit_id})
    operation = f"permit:authorise:{permit_id}"
    replay = replay_or_lock(db, principal.user_id, operation, key, digest)
    if replay is not None:
        return replay
    rows = db.execute(text("SELECT * FROM authorise_entry(:pid, :actor, now())"),
                      {"pid": permit_id, "actor": principal.user_id}).mappings().all()
    clauses = [{k: r[k] for k in ("clause_code", "title", "legal_ref", "passed", "detail")} for r in rows]
    receipt = db.execute(text(
        "SELECT receipt_id,decision,evidence_revision,evaluated_at,expires_at,failures,snapshot_sha256, "
        "(decision='AUTHORISED' AND evidence_revision=:revision AND :status='AUTHORISED' "
        " AND expires_at IS NOT NULL AND clock_timestamp()<expires_at) AS usable "
        "FROM permit_decision_receipt WHERE permit_id=:pid ORDER BY evaluated_at DESC,receipt_id DESC LIMIT 1"
    ), {"pid": permit_id, "revision": getattr(permit, "evidence_revision", 0), "status": rows[0]["permit_status"]}).mappings().first()
    result = {"authorised": rows[0]["permit_status"] == "AUTHORISED", "permit_status": rows[0]["permit_status"],
              "failed": [c["clause_code"] for c in clauses if not c["passed"]], "clauses": clauses,
              "receipt": dict(receipt) if receipt else None,
              "receipt_id": receipt["receipt_id"] if receipt else None,
              "evidence_revision": receipt["evidence_revision"] if receipt else getattr(permit, "evidence_revision", 0),
              "expires_at": receipt["expires_at"] if receipt else None,
              "current_decision_usable": bool(receipt and receipt["usable"])}
    save_result(db, principal.user_id, operation, key, digest, result, 200)
    return result


# --- entries -----------------------------------------------------------------------------------------------------------
@router.post("/{permit_id}/entries", status_code=201)
def log_entry(permit_id: int, body: EntryIn, db: DB, principal: Principal = Depends(require(*OPERATE)),
              idempotency_header: str | None = Header(default=None, alias="Idempotency-Key")):
    permit = _operable(db, permit_id, principal)
    key = command_key(idempotency_header or str(uuid4()))
    payload = body.model_dump(mode="json")
    digest = body_digest(payload)
    operation = f"permit:entries:{permit_id}"
    replay = replay_or_lock(db, principal.user_id, operation, key, digest)
    if replay is not None:
        return replay
    receipt = db.execute(text(
        "SELECT receipt_id,decision,evidence_revision,expires_at "
        "FROM permit_decision_receipt WHERE permit_id=:permit "
        "ORDER BY evaluated_at DESC,receipt_id DESC LIMIT 1"
    ), {"permit": permit_id}).mappings().first()
    current_revision = getattr(permit, "evidence_revision", 0)
    if (receipt is None or receipt["decision"] != "AUTHORISED" or receipt["evidence_revision"] != current_revision
            or permit.status != "AUTHORISED" or receipt["expires_at"] is None
            or receipt["expires_at"] <= datetime.now(timezone.utc)):
        raise Conflict("Evidence changed or the decision expired; request a fresh authorization receipt.",
                       code="receipt_stale")
    if body.receipt_id is not None and body.receipt_id != receipt["receipt_id"]:
        raise Conflict("The supplied authorization receipt is no longer current.", code="receipt_stale")
    receipt_id = receipt["receipt_id"]
    # Always pass through the database's open-entry admission gate first. Suppressed rows represent
    # a durable automatic safety stop, so return normally (rather than raising and rolling it back).
    entry_id = db.execute(text(
        "INSERT INTO entry_log (permit_id, worker_id, period, recorded_by, receipt_id) "
        "VALUES (:pid, :wid, tstzrange(:entered, NULL, '[)'), :actor, :receipt) RETURNING entry_id"),
        {"pid": permit_id, "wid": body.worker_id, "entered": body.entered_at, "actor": principal.user_id,
         "receipt": receipt_id}).scalar_one_or_none()
    if entry_id is None:
        state = db.execute(text("SELECT status, end_reason FROM entry_permit WHERE permit_id = :pid"),
                           {"pid": permit_id}).mappings().one()
        result = {"error": {"code": "safety_stopped",
            "message": state["end_reason"] or "The permit was stopped because current safety conditions no longer pass.",
            "details": {"permit_status": state["status"]}}}
        save_result(db, principal.user_id, operation, key, digest, result, 409)
        return JSONResponse(status_code=409, content=result)
    row = db.get(EntryLog, entry_id)
    assert row is not None
    if body.exited_at is not None:
        row.period = Range(body.entered_at, body.exited_at, bounds="[)")
        db.flush()                               # exit is retained with server receipt and violation evidence
    result = _entry(row)
    save_result(db, principal.user_id, operation, key, digest, result, 201)
    return result


@router.post("/{permit_id}/entries/{entry_id}/exit")
def log_exit(permit_id: int, entry_id: int, body: ExitIn, db: DB, principal: Principal = Depends(require(*OPERATE)),
             idempotency_header: str | None = Header(default=None, alias="Idempotency-Key")):
    _operable(db, permit_id, principal)
    key = command_key(idempotency_header or str(uuid4()))
    payload = body.model_dump(mode="json")
    digest = body_digest(payload)
    operation = f"permit:entries:{permit_id}:{entry_id}:exit"
    replay = replay_or_lock(db, principal.user_id, operation, key, digest)
    if replay is not None:
        return replay
    row = db.scalar(select(EntryLog).where(EntryLog.entry_id == entry_id, EntryLog.permit_id == permit_id).with_for_update())
    if row is None:
        raise NotFound("No such entry on this permit.")
    row.period = Range(row.period.lower, body.exited_at, bounds="[)")
    db.flush()
    db.refresh(row)
    result = _entry(row)
    save_result(db, principal.user_id, operation, key, digest, result, 200)
    return result


# --- ending a permit ---------------------------------------------------------------------------------------------------
def _end(db: Session, permit_id: int, principal: Principal, status: str, reason: str | None) -> dict[str, Any]:
    permit = _operable(db, permit_id, principal, lock=True)
    permit.status = status
    if reason:
        permit.end_reason = reason
    db.flush()
    return to_dict(permit)


@router.post("/{permit_id}/close")
def close_permit(permit_id: int, db: DB, principal: Principal = Depends(require(*DECIDE))):
    return _end(db, permit_id, principal, "CLOSED", None)


@router.post("/{permit_id}/abort")
def abort_permit(permit_id: int, body: ReasonIn, db: DB, principal: Principal = Depends(require(*DECIDE))):
    return _end(db, permit_id, principal, "ABORTED", body.reason)


@router.post("/{permit_id}/cancel")
def cancel_permit(permit_id: int, body: ReasonIn, db: DB, principal: Principal = Depends(require(*DECIDE))):
    return _end(db, permit_id, principal, "CANCELLED", body.reason)


@router.post("/{permit_id}/stop-work")
def stop_work(permit_id: int, body: ReasonIn, db: DB, principal: Principal = Depends(require("WORKER", *DECIDE))):
    """A crew member's right to refuse. Goes through a SECURITY DEFINER function that checks crew membership itself,
    because a WORKER has no UPDATE right on permits (row-level security), only this one narrow door."""
    _load(db, permit_id, principal)
    row = db.execute(text("SELECT * FROM stop_work(:pid, :reason)"), {"pid": permit_id, "reason": body.reason}).mappings().one()
    return {k: row[k] for k in ("permit_id", "status", "end_reason", "ended_at")}


@router.get("/{permit_id}/decision")
def authorization_decision(permit_id: int, db: DB, principal: Principal = Depends(require(*VIEW))):
    """Original successful gate explanation. Hash the exact canonical_snapshot UTF-8 bytes to verify its digest."""
    _load(db, permit_id, principal)
    row = db.execute(text("SELECT d.*, snapshot::text AS canonical_snapshot, "
                          "snapshot_sha256 = encode(sha256(convert_to(snapshot::text, 'UTF8')), 'hex') AS digest_verified "
                          "FROM permit_authorization_decision d WHERE permit_id=:pid"), {"pid": permit_id}).mappings().first()
    if row is None:
        raise NotFound("No saved authorization decision for this permit (draft or pre-migration history).")
    return dict(row)


@router.get("/{permit_id}/safety-events")
def safety_events(permit_id: int, db: DB, page: Paging, principal: Principal = Depends(require(*VIEW))):
    """Scoped immutable stop and violation history; records survive a permit ending."""
    _load(db, permit_id, principal)
    return paged(db, select(PermitSafetyEvent).where(PermitSafetyEvent.permit_id == permit_id)
                 .order_by(PermitSafetyEvent.event_id.desc()), page)
