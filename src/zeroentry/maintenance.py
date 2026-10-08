"""Periodic DB decisions, including changes caused by time passing without a row write.

The API service is a trusted user of ze_app, as in deps.authenticate. Maintenance has system
context (no fabricated human actor). PostgreSQL owns every safety/detection decision. Advisory
transaction locks suppress overlapping runs across API processes; later ticks retry failures.
Durable database events survive process restarts. This module does not deliver SMS or sensor data.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import Engine, text

log = logging.getLogger("zeroentry.maintenance")


def run_maintenance(engine: Engine, completion_after_job_id: int = 0) -> dict:
    result = {}
    completion_cursor = completion_after_job_id
    # Commit safety independently: a detection scan failure must not roll back a stop decision.
    for key, query, lock_key in (
        ("safety", "SELECT sweep_permit_safety() AS stopped", 920260701),
        ("detection", "SELECT * FROM scan_shadow_entries(now())", 920260702),
        ("completion", "SELECT * FROM sweep_completion_projections(:after_job_id, 500)", 920260703),
    ):
        try:
            with engine.begin() as conn:
                conn.execute(text("SET LOCAL lock_timeout = '2s'"))
                conn.execute(text("SET LOCAL statement_timeout = '20s'"))
                if not conn.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": lock_key}):
                    result[key] = {"skipped": "another maintenance process is running"}
                    continue
                conn.execute(text("SELECT set_config('app.role', 'ADMIN', true)"))
                params = {"after_job_id": completion_after_job_id} if key == "completion" else {}
                result[key] = dict(conn.execute(text(query), params).mappings().one())
                if key == "completion":
                    completion_cursor = result[key]["next_after_job_id"] if result[key]["has_more"] else 0
        except Exception:
            log.exception("%s maintenance failed; next tick will retry", key)
            result[key] = {"error": "database maintenance failed"}
    result["completion_cursor"] = completion_cursor
    result["checked_at"] = datetime.now(timezone.utc).isoformat()
    return result


async def maintain(engine: Engine, interval: int, stop: asyncio.Event, status: dict) -> None:
    while not stop.is_set():
        status.update(await asyncio.to_thread(
            run_maintenance, engine, int(status.get("completion_cursor", 0))
        ))
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass
