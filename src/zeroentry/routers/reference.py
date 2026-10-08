"""Reference and master data: ULBs, manholes, machines, gear catalogue, gas detectors, contractors, workers.
Plain CRUD through the generic router; the database enforces uniqueness, keys and every business rule."""

import os

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import text

from ..crud import crud_router
from ..deps import DB, STAFF, Principal, require
from ..errors import Conflict, Forbidden, NotFound, Unprocessable
from ..evidence import current_manifest
from ..idempotency import body_digest, command_key, replay_or_lock, save_result
from ..models import Contractor, GasDetector, GearItem, Machine, Manhole, Ulb, Worker
from ..schemas import (ContractorIn, DetectorIn, GearAssetIn, GearItemIn, MachineIn, ManholeIn, ScopeAssignmentIn,
                       UlbIn, WorkerIn)

router = APIRouter()
OFFICERS = ("ADMIN", "ENGINEER")

router.include_router(crud_router(
    "/ulbs", "ulb", Ulb, UlbIn, read_roles=STAFF, write_roles=("ADMIN",), search=("name",), order_by="name"))

router.include_router(crud_router(
    "/manholes", "manhole", Manhole, ManholeIn, read_roles=STAFF, write_roles=OFFICERS,
    filters=("ulb_id", "kind"), search=("code",), order_by="code"))

router.include_router(crud_router(
    "/machines", "machine", Machine, MachineIn, read_roles=STAFF, write_roles=OFFICERS,
    filters=("ulb_id", "kind", "status"), order_by="code"))

router.include_router(crud_router(
    "/gear-items", "gear item", GearItem, GearItemIn, read_roles=STAFF, write_roles=("ADMIN",),
    filters=("statutory",), pk_type=str, order_by="gear_code"))

router.include_router(crud_router(
    "/detectors", "gas detector", GasDetector, DetectorIn, read_roles=STAFF, write_roles=("ADMIN",),
    search=("serial_no",), order_by="serial_no"))


def _contractor_scope(stmt, principal: Principal):
    return stmt.where(Contractor.contractor_id == principal.contractor_id) if principal.role == "CONTRACTOR" else stmt


def _contractor_guard(row: Contractor, changes: dict, principal: Principal) -> None:
    """Blacklisting, and any way back from it, is an administrator's decision (BR-22); engineers may suspend/reinstate."""
    new = changes.get("status")
    if new is not None and principal.role != "ADMIN" and (new == "BLACKLISTED" or row.status == "BLACKLISTED"):
        raise Forbidden("Only an ADMIN may blacklist a contractor or lift a blacklisting.")


router.include_router(crud_router(
    "/contractors", "contractor", Contractor, ContractorIn, read_roles=(*STAFF, "CONTRACTOR"),
    write_roles=OFFICERS, filters=("status",), search=("name", "licence_no"), order_by="name",
    scope=_contractor_scope, guard=_contractor_guard))


def _worker_scope(stmt, principal: Principal):
    if principal.role == "CONTRACTOR":
        return stmt.where(Worker.contractor_id == principal.contractor_id)
    if principal.role == "WORKER":
        return stmt.where(Worker.worker_id == principal.worker_id)
    return stmt


router.include_router(crud_router(
    "/workers", "worker", Worker, WorkerIn, read_roles=(*STAFF, "CONTRACTOR", "WORKER"), write_roles=OFFICERS,
    filters=("contractor_id", "is_active"), search=("namaste_id", "full_name"), order_by="full_name",
    scope=_worker_scope))


@router.get("/ulbs/{ulb_id}/contractor-scopes")
def list_contractor_scopes(ulb_id: int, db: DB, principal: Principal = Depends(require(*STAFF))):
    if principal.role not in {"ADMIN", "AUDITOR"} and principal.ulb_id != ulb_id:
        raise NotFound("No contractor assignments are available in that scope.")
    rows = db.execute(text("""
      SELECT s.ulb_id,s.contractor_id,c.name,c.licence_no,c.status,s.assigned_by,s.assigned_at,s.assignment_reason
      FROM ulb_contractor_scope s JOIN contractor c USING(contractor_id)
      WHERE s.ulb_id=:ulb ORDER BY c.name,c.contractor_id
    """), {"ulb": ulb_id}).mappings().all()
    return {"items": [dict(row) for row in rows], "ulb_id": ulb_id}


@router.post("/ulbs/{ulb_id}/contractors/{contractor_id}/scope", status_code=201)
def assign_contractor_scope(ulb_id: int, contractor_id: int, body: ScopeAssignmentIn, db: DB,
                            principal: Principal = Depends(require("ADMIN", "ENGINEER")),
                            idempotency_header: str | None = Header(default=None, alias="Idempotency-Key")):
    if principal.role == "ENGINEER" and (principal.ulb_id is None or principal.ulb_id != ulb_id):
        raise NotFound("No contractor assignments are available in that scope.")
    key = command_key(idempotency_header)
    payload = {"ulb_id": ulb_id, "contractor_id": contractor_id, **body.model_dump(mode="json")}
    digest = body_digest(payload)
    operation = f"ulb:{ulb_id}:contractor:{contractor_id}:assign"
    replay = replay_or_lock(db, principal.user_id, operation, key, digest)
    if replay is not None:
        return replay
    result = db.scalar(text("SELECT assign_ulb_contractor(:ulb,:contractor,:reason)"),
                       {"ulb": ulb_id, "contractor": contractor_id, "reason": body.reason})
    save_result(db, principal.user_id, operation, key, digest, result, 201)
    return result


@router.get("/ulbs/{ulb_id}/detector-scopes")
def list_detector_scopes(ulb_id: int, db: DB, principal: Principal = Depends(require(*STAFF))):
    if principal.role not in {"ADMIN", "AUDITOR"} and principal.ulb_id != ulb_id:
        raise NotFound("No detector assignments are available in that scope.")
    rows = db.execute(text("""
      SELECT s.ulb_id,s.detector_id,d.serial_no,d.calibration_valid_until,d.calibration_standard,s.assigned_by,s.assigned_at,s.assignment_reason
      FROM ulb_detector_scope s JOIN gas_detector d USING(detector_id)
      WHERE s.ulb_id=:ulb ORDER BY d.serial_no,d.detector_id
    """), {"ulb": ulb_id}).mappings().all()
    return {"items": [dict(row) for row in rows], "ulb_id": ulb_id}


@router.post("/ulbs/{ulb_id}/detectors/{detector_id}/scope", status_code=201)
def assign_detector_scope(ulb_id: int, detector_id: int, body: ScopeAssignmentIn, db: DB,
                          principal: Principal = Depends(require("ADMIN")),
                          idempotency_header: str | None = Header(default=None, alias="Idempotency-Key")):
    key = command_key(idempotency_header)
    payload = {"ulb_id": ulb_id, "detector_id": detector_id, **body.model_dump(mode="json")}
    digest = body_digest(payload)
    operation = f"ulb:{ulb_id}:detector:{detector_id}:assign"
    replay = replay_or_lock(db, principal.user_id, operation, key, digest)
    if replay is not None:
        return replay
    result = db.scalar(text("SELECT assign_ulb_detector(:ulb,:detector,:reason)"),
                       {"ulb": ulb_id, "detector": detector_id, "reason": body.reason})
    save_result(db, principal.user_id, operation, key, digest, result, 201)
    return result


@router.get("/reference/gear-assets")
def gear_assets(db: DB, principal: Principal = Depends(require(*STAFF)), ulb_id: int | None = Query(default=None, gt=0),
                limit: int = Query(default=100, ge=1, le=200), offset: int = Query(default=0, ge=0)):
    """Serialised site assets and current availability; staff visibility never widens a scoped account."""
    scope = ulb_id if principal.role in {"ADMIN", "AUDITOR"} else principal.ulb_id
    if principal.role not in {"ADMIN", "AUDITOR"} and (principal.ulb_id is None or (ulb_id is not None and ulb_id != principal.ulb_id)):
        raise NotFound("No gear assets are available in that scope.")
    if scope is None:
        raise NotFound("Choose a ULB to list gear assets.")
    rows = db.execute(text("""
      SELECT a.gear_asset_id,a.ulb_id,a.gear_code,g.name AS gear_name,a.serial_no,a.status,a.inspection_valid_until,a.created_at,
        COALESCE((a.status='USABLE' AND a.inspection_valid_until>=local_date(now())
          AND NOT EXISTS(SELECT 1 FROM permit_resource_reservation r WHERE r.gear_asset_id=a.gear_asset_id AND r.released_at IS NULL)
          AND NOT EXISTS(SELECT 1 FROM permit_site_gear s WHERE s.gear_asset_id=a.gear_asset_id AND s.returned_at IS NULL)),false) AS available
      FROM gear_asset a JOIN gear_item g USING (gear_code) WHERE a.ulb_id=:ulb
      ORDER BY a.gear_code,a.serial_no LIMIT :limit OFFSET :offset
    """), {"ulb": scope, "limit": limit, "offset": offset}).mappings().all()
    total = db.scalar(text("SELECT count(*) FROM gear_asset WHERE ulb_id=:ulb"), {"ulb": scope}) or 0
    return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset, "ulb_id": scope}


@router.post("/reference/gear-assets", status_code=201)
def register_gear_asset(body: GearAssetIn, db: DB, principal: Principal = Depends(require("ADMIN", "ENGINEER")),
                        idempotency_header: str | None = Header(default=None, alias="Idempotency-Key")):
    if principal.role != "ADMIN" and (principal.ulb_id is None or principal.ulb_id != body.ulb_id):
        raise NotFound("No gear assets are available in that scope.")
    if not db.scalar(text("SELECT EXISTS(SELECT 1 FROM ulb WHERE ulb_id=:ulb)"), {"ulb": body.ulb_id}):
        raise NotFound("No such ULB.")
    if not db.scalar(text("SELECT EXISTS(SELECT 1 FROM gear_item WHERE gear_code=:code)"), {"code": body.gear_code}):
        raise NotFound("No such gear catalogue item.")
    key = command_key(idempotency_header)
    payload = body.model_dump(mode="json")
    digest = body_digest(payload)
    operation = "reference:gear-assets:create"
    replay = replay_or_lock(db, principal.user_id, operation, key, digest)
    if replay is not None:
        return replay
    row = db.execute(text("""
      INSERT INTO gear_asset(ulb_id,gear_code,serial_no,status,inspection_valid_until)
      VALUES (:ulb,:code,:serial,:status,:inspection)
      RETURNING gear_asset_id,ulb_id,gear_code,serial_no,status,inspection_valid_until,created_at
    """), {"ulb": body.ulb_id, "code": body.gear_code, "serial": body.serial_no, "status": body.status,
           "inspection": body.inspection_valid_until}).mappings().one()
    result = dict(row)
    save_result(db, principal.user_id, operation, key, digest, result, 201)
    return result


@router.get("/judge/evidence")
def judge_evidence(db: DB, principal: Principal = Depends(require(*STAFF))):
    """Evidence inventory is live DB data; generated experiment results are never inferred or copied stale."""
    sources = db.execute(text(
        "SELECT source_code,source_type,title,source_url,source_version,citation_clause,applicability "
        "FROM policy_source ORDER BY source_code")).mappings().all()
    revision = db.scalar(text("SELECT version_num FROM alembic_version"))
    server_version = db.scalar(text("SHOW server_version"))
    commit = os.getenv("ZEROENTRY_GIT_SHA") or "NOT_AVAILABLE"
    run_id = os.getenv("ZEROENTRY_RUN_ID") or None
    manifest = current_manifest(revision)
    if manifest:
        commit = os.getenv("ZEROENTRY_GIT_SHA") or manifest["git_sha"]
        run_id = os.getenv("ZEROENTRY_RUN_ID") or manifest["run_id"]
    labs = manifest["labs"] if manifest else []
    measurements = ({"status": "TESTED", "runs": [{k: manifest[k] for k in
        ("run_id", "measured_at", "git_sha", "dirty", "schema_revision", "source_sha256", "summary", "machine", "python")}],
        "limitations": manifest["limitations"]} if manifest else
        {"status": "NOT_YET_MEASURED", "runs": [], "limitations": [
            "No source-matching test manifest is available. Run scripts/verify_release.py; historical numbers are not current proof."]})
    return {"sources": [dict(row) for row in sources], "labs": labs,
            "measurements": measurements,
            "runtime": {"commit": commit, "run_id": run_id, "source_mode": "TYPED", "schema_revision": revision,
                        "database_version": server_version}}
