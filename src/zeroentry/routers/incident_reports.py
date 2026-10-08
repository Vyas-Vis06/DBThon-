"""Standalone multi-victim intake, separate from permit-dependent legacy incident recording."""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy import text

from ..deps import DB, Paging, Principal, require
from ..errors import NotFound
from ..idempotency import body_digest, command_key, replay_or_lock, save_result
from ..schemas import IncidentReportIn

router = APIRouter(prefix="/incident-reports", tags=["incident reports"])
WRITE = ("ADMIN", "ENGINEER", "SUPERVISOR")
READ = ("ADMIN", "ENGINEER", "SUPERVISOR", "AUDITOR")


def _scope(ulb_id: int, principal: Principal) -> None:
    if principal.role in {"ADMIN", "AUDITOR"}:
        return
    if principal.ulb_id is None or principal.ulb_id != ulb_id:
        raise NotFound("No incident report is available in that scope.")


def _view(db, report_id: int) -> dict | None:
    row = db.execute(text("""
      SELECT r.report_id,r.ulb_id,r.job_id,r.permit_id,r.contractor_id,r.occurred_at,r.site_label,
             r.hazard_type,r.description,r.reported_sections,r.reported_by,r.classification_status,
             r.source_mode,r.created_at,
             COALESCE((SELECT jsonb_agg(jsonb_build_object(
               'victim_id',v.victim_id,'victim_key',v.victim_key,'worker_id',v.worker_id,
               'display_alias',v.display_alias,'outcome',v.outcome,
               'case',CASE WHEN c.assessment_case_id IS NULL THEN NULL ELSE jsonb_build_object(
                 'assessment_case_id',c.assessment_case_id,'status',c.status,
                 'reference_amount',c.reference_amount::text,'claimed_amount',c.claimed_amount::text,
                 'awarded_amount',c.awarded_amount::text,'paid_amount',c.paid_amount::text,
                 'review_due_at',c.review_due_at) END
             ) ORDER BY v.victim_id)
             FROM incident_report_victim v LEFT JOIN incident_assessment_case c USING (victim_id)
             WHERE v.report_id=r.report_id), '[]'::jsonb) AS victims
        FROM incident_report r WHERE r.report_id=:report_id
    """), {"report_id": report_id}).mappings().first()
    return dict(row) if row else None


@router.post("", status_code=201)
def create_incident_report(
    body: IncidentReportIn,
    db: DB,
    principal: Annotated[Principal, Depends(require(*WRITE))],
    idempotency_header: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    _scope(body.ulb_id, principal)
    key = command_key(idempotency_header)
    payload = body.model_dump(mode="json")
    digest = body_digest(payload)
    operation = "incident-reports:create"
    replay = replay_or_lock(db, principal.user_id, operation, key, digest)
    if replay is not None:
        return replay
    result = db.scalar(text("SELECT record_incident_report(CAST(:payload AS jsonb))"),
                       {"payload": json.dumps(payload, separators=(",", ":"), ensure_ascii=False)})
    save_result(db, principal.user_id, operation, key, digest, result, 201)
    return result


@router.get("")
def list_incident_reports(
    db: DB,
    page: Paging,
    principal: Annotated[Principal, Depends(require(*READ))],
    ulb_id: int | None = None,
):
    if principal.role == "AUDITOR" and ulb_id is None:
        raise NotFound("Choose a ULB to list incident reports.")
    if ulb_id is not None:
        _scope(ulb_id, principal)
    stmt = "SELECT report_id FROM incident_report"
    params: dict[str, int] = {}
    if ulb_id is not None:
        stmt += " WHERE ulb_id=:ulb"
        params["ulb"] = ulb_id
    total = db.scalar(text(f"SELECT count(*) FROM ({stmt}) visible_reports"), params) or 0
    ids = db.execute(text(stmt + " ORDER BY report_id DESC LIMIT :limit OFFSET :offset"),
                     {**params, "limit": page.limit, "offset": page.offset}).scalars().all()
    return {"items": [report for report_id in ids if (report := _view(db, report_id)) is not None],
            "total": total, "limit": page.limit, "offset": page.offset}


@router.get("/{report_id}")
def get_incident_report(report_id: int, db: DB, principal: Annotated[Principal, Depends(require(*READ))]):
    row = _view(db, report_id)
    if row is None:
        raise NotFound("No incident report is available.")
    _scope(row["ulb_id"], principal)
    return row
