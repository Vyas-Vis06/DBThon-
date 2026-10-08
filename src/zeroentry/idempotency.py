"""Transactional idempotency for commands that can create externally visible records.

The advisory transaction lock closes the missing-row race before the unique key is queried. The lock,
business write, stored response, and outbox events all share the request transaction and therefore commit
or roll back together.
"""

import hashlib
import json
from typing import Any
from uuid import UUID

from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from sqlalchemy.orm import Session

from .errors import Conflict, Unprocessable


def command_key(value: str | None) -> UUID:
    if not value:
        raise Unprocessable("This command requires an Idempotency-Key UUID.", code="idempotency_key_required")
    try:
        return UUID(value)
    except (ValueError, TypeError, AttributeError) as exc:
        raise Unprocessable("Idempotency-Key must be a UUID.", code="invalid_idempotency_key") from exc


def body_digest(payload: Any) -> str:
    """Hash a validated JSON-compatible body in stable key order."""
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def replay_or_lock(db: Session, actor_id: int, operation: str, key: UUID, digest: str) -> JSONResponse | None:
    lock_name = f"{actor_id}:{operation}:{key}"
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_name, 0))"), {"lock_name": lock_name})
    row = db.execute(text(
        "SELECT body_sha256, response_status, response_json FROM command_dedup "
        "WHERE actor_user_id=:actor AND operation=:operation AND idempotency_key=:key"
    ), {"actor": actor_id, "operation": operation, "key": key}).mappings().first()
    if row is None:
        return None
    if row["body_sha256"] != digest:
        raise Conflict("This Idempotency-Key was already used with a different command body.",
                       code="idempotency_mismatch")
    return JSONResponse(content=row["response_json"], status_code=row["response_status"])


def save_result(db: Session, actor_id: int, operation: str, key: UUID, digest: str,
                response_json: dict[str, Any], response_status: int) -> None:
    response_json = jsonable_encoder(response_json)
    db.execute(text(
        "INSERT INTO command_dedup "
        "(actor_user_id, operation, idempotency_key, body_sha256, response_status, response_json) "
        "VALUES (:actor, :operation, :key, :digest, :status, CAST(:response AS jsonb))"
    ), {"actor": actor_id, "operation": operation, "key": key, "digest": digest,
        "status": response_status, "response": json.dumps(response_json, ensure_ascii=False, separators=(",", ":"))})
