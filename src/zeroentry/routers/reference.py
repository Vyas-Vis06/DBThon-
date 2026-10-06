"""Reference and master data: ULBs, manholes, machines, gear catalogue, gas detectors, contractors, workers.
Plain CRUD through the generic router; the database enforces uniqueness, keys and every business rule."""

from fastapi import APIRouter

from ..crud import crud_router
from ..deps import STAFF, Principal
from ..errors import Forbidden
from ..models import Contractor, GasDetector, GearItem, Machine, Manhole, Ulb, Worker
from ..schemas import ContractorIn, DetectorIn, GearItemIn, MachineIn, ManholeIn, UlbIn, WorkerIn

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
