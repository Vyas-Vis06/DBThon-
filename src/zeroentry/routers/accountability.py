"""Imported completion claims remain separate from internally verified job completion."""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import text

from ..deps import DB, Principal, require
from ..errors import NotFound, Unprocessable
from ..idempotency import body_digest, command_key, replay_or_lock, save_result
from ..schemas import CompletionClaimIn, CompletionClaimReviewIn

router = APIRouter(tags=["accountability"])


def _scope(ulb_id: int, principal: Principal) -> None:
    if principal.role in {"ADMIN", "AUDITOR"}:
        return
    if principal.ulb_id is None or principal.ulb_id != ulb_id:
        raise NotFound("No completion reconciliation is available in that scope.")


@router.post("/completion-claims", status_code=201)
def create_completion_claim(
    body: CompletionClaimIn,
    db: DB,
    principal: Annotated[Principal, Depends(require("ADMIN", "ENGINEER"))],
    idempotency_header: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    ulb_id = body.ulb_id if principal.role == "ADMIN" else principal.ulb_id
    if ulb_id is None:
        raise Unprocessable("Choose a ULB for this completion claim.", code="ulb_required")
    _scope(ulb_id, principal)
    payload = body.model_dump(mode="json")
    payload["ulb_id"] = ulb_id
    key = command_key(idempotency_header)
    digest = body_digest(payload)
    operation = "completion-claims:create"
    replay = replay_or_lock(db, principal.user_id, operation, key, digest)
    if replay is not None:
        return replay
    result = db.scalar(text("SELECT record_completion_claim(CAST(:payload AS jsonb))"),
                       {"payload": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))})
    save_result(db, principal.user_id, operation, key, digest, result, 201)
    return result


@router.get("/completion-reconciliation")
def completion_reconciliation(
    db: DB,
    principal: Annotated[Principal, Depends(require("ADMIN", "ENGINEER", "SUPERVISOR", "AUDITOR"))],
    ulb_id: Annotated[int, Query(gt=0)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    _scope(ulb_id, principal)
    rows = db.execute(text("""
      SELECT v.claim_id,v.source_ulb_id,v.source,v.external_id,v.external_job_ref,v.matched_job_id,
             v.claimed_status,v.claimed_at,v.match_status,v.gap_code,v.complaint_id,v.complaint_status,
             v.resolution_code,v.resolved_at,v.evidence_deadline,v.timely_machine_evidence,v.timely_permit_evidence,
             v.late_evidence_exists,v.invoice_hold_refs,
             p.evidence_revision AS projection_evidence_revision,p.gap_codes AS projection_gap_codes,
             p.has_gap AS projection_has_gap,p.disposition AS projection_disposition,p.computed_at AS projection_computed_at,
             CASE WHEN v.matched_job_id IS NULL THEN NULL
                  WHEN v.gap_code IS NULL THEN p.job_id IS NOT NULL AND NOT p.has_gap
                  ELSE COALESCE(EXISTS(SELECT 1 FROM jsonb_array_elements(p.gap_codes) AS g
                       WHERE g->>'claim_id'=v.claim_id::text AND g->>'gap_code'=v.gap_code),false) END AS projection_consistent
      FROM v_completion_claim_reference v LEFT JOIN completion_projection p ON p.job_id=v.matched_job_id
      WHERE v.source_ulb_id=:ulb
      ORDER BY v.claimed_at DESC,v.claim_id DESC LIMIT :limit OFFSET :offset
    """), {"ulb": ulb_id, "limit": limit, "offset": offset}).mappings().all()
    total = db.scalar(text("SELECT count(*) FROM completion_claim WHERE source_ulb_id=:ulb"), {"ulb": ulb_id}) or 0
    candidates = db.execute(text("""
      SELECT j.job_id,j.status,j.complaint_id,m.code AS manhole_code,c.description,
             contractor.name AS contractor_name
      FROM job j JOIN complaint c USING (complaint_id) JOIN manhole m USING (manhole_id)
      LEFT JOIN contractor ON contractor.contractor_id=j.contractor_id
      WHERE m.ulb_id=:ulb ORDER BY j.created_at DESC,j.job_id DESC LIMIT 201
    """), {"ulb": ulb_id}).mappings().all()
    return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset, "ulb_id": ulb_id,
            "job_candidates": [dict(row) for row in candidates[:200]],
            "job_candidates_has_more": len(candidates) > 200,
            "semantics": "External completion claims are not internal evidence. Unmatched claims remain reviewable; missing evidence is not proof of no work."}


@router.post("/completion-claims/{claim_id}/match")
def review_completion_claim(
    claim_id: int,
    body: CompletionClaimReviewIn,
    db: DB,
    principal: Annotated[Principal, Depends(require("ADMIN", "ENGINEER"))],
    idempotency_header: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    key = command_key(idempotency_header)
    payload = {"claim_id": claim_id, **body.model_dump(mode="json")}
    digest = body_digest(payload)
    operation = f"completion-claims:{claim_id}:match"
    replay = replay_or_lock(db, principal.user_id, operation, key, digest)
    if replay is not None:
        return replay
    result = db.scalar(text(
        "SELECT review_completion_claim(:claim,:job,:decision,:reason)"
    ), {"claim": claim_id, "job": body.job_id, "decision": body.decision, "reason": body.reason})
    save_result(db, principal.user_id, operation, key, digest, result, 200)
    return result
