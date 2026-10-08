"""Plain-SQL row factories for tests.

Everything goes through the real constraints and triggers (nothing is bypassed), so a factory that can
build a row proves the row is legal. Each method returns the new primary key. Defaults are legal and
unique; override only what the test is about.
"""

import itertools
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

_seq = itertools.count(1)


def utc(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


def ist(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    """A wall-clock time in India as an absolute instant (fixed UTC+05:30)."""
    return datetime(y, mo, d, h, mi, tzinfo=timezone(timedelta(hours=5, minutes=30)))


class Factory:
    def __init__(self, conn: psycopg.Connection) -> None:
        self.c = conn

    # -- generic -----------------------------------------------------------------------------------
    def insert(self, table: str, returning: str, **values: Any) -> int:
        cols = ", ".join(values)
        marks = ", ".join(f"%({k})s" for k in values)
        row = self.c.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks}) RETURNING {returning} AS id",  # noqa: S608
                             values).fetchone()
        return row["id"]

    def scalar(self, sql: str, *params: Any) -> Any:
        row = self.c.execute(sql, params).fetchone()
        return None if row is None else next(iter(row.values()))

    # -- reference lookups ---------------------------------------------------------------------------
    def role_id(self, name: str) -> int:
        return self.scalar("SELECT role_id FROM role WHERE name = %s", name)

    # -- people and organisations --------------------------------------------------------------------
    def ulb(self, **kw: Any) -> int:
        n = next(_seq)
        # Test factories create an explicitly educational scope. Production/new scopes use the migration's
        # REVIEW_REQUIRED default; this convenience never changes real seeded municipalities.
        values = {"name": f"EDU test ULB {n}", "district": "Chennai", "state": "Tamil Nadu", **kw}
        # Migration-backfill tests deliberately construct databases at pre-0015 revisions.
        has_policy_mode = self.scalar("SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                                      "WHERE table_schema=current_schema() AND table_name='ulb' AND column_name='policy_mode')")
        if has_policy_mode:
            values.setdefault("policy_mode", "EDUCATIONAL")
        return self.insert("ulb", "ulb_id", **values)

    def contractor(self, **kw: Any) -> int:
        n = next(_seq)
        return self.insert("contractor", "contractor_id", **{
            "name": f"Contractor {n}", "licence_no": f"TST-{n:05d}", "licence_valid_until": "2099-12-31", **kw})

    def worker(self, contractor_id: int, **kw: Any) -> int:
        n = next(_seq)
        return self.insert("worker", "worker_id", **{
            "contractor_id": contractor_id, "full_name": f"Worker {n}", "namaste_id": f"NAM-T-{n:05d}",
            "medical_fit_until": "2099-12-31", "trained_until": "2099-12-31", **kw})

    def user(self, role: str, **kw: Any) -> int:
        n = next(_seq)
        return self.insert("app_user", "user_id", **{
            "role_id": self.role_id(role), "email": f"{role.lower()}{n}@zeroentry.example",
            "full_name": f"{role.title()} {n}", "password_hash": "not-a-real-hash", **kw})

    # -- assets, complaints, jobs ------------------------------------------------------------------
    def manhole(self, ulb_id: int, **kw: Any) -> int:
        n = next(_seq)
        return self.insert("manhole", "manhole_id", **{
            "ulb_id": ulb_id, "code": f"TST-MH-{n:05d}", "kind": "SEWER", "depth_m": 4.0, "lat": 13.05, "lng": 80.25, **kw})

    def complaint(self, manhole_id: int, **kw: Any) -> int:
        return self.insert("complaint", "complaint_id", **{
            "manhole_id": manhole_id, "description": "Overflowing manhole, foul smell", **kw})

    def resolved_complaint(self, manhole_id: int, resolved_at: datetime, code: str = "CLEARED", **kw: Any) -> int:
        """A complaint resolved at an explicit instant (raised one day earlier)."""
        return self.complaint(manhole_id, status="RESOLVED", resolved_at=resolved_at, resolution_code=code,
                              raised_at=resolved_at - timedelta(days=1), **kw)

    def machine(self, ulb_id: int, **kw: Any) -> int:
        n = next(_seq)
        return self.insert("machine", "machine_id", **{"ulb_id": ulb_id, "code": f"TST-MC-{n:05d}", "kind": "JETTING", **kw})

    def job(self, complaint_id: int, contractor_id: int, **kw: Any) -> int:
        return self.insert("job", "job_id", **{"complaint_id": complaint_id, "contractor_id": contractor_id, **kw})

    def deployment(self, job_id: int, machine_id: int, outcome: str | None, *, started_at: datetime | None = None,
                   recorded_at: datetime | None = None, **kw: Any) -> int:
        started_at = started_at or utc(2026, 9, 1, 4)
        values: dict[str, Any] = {"job_id": job_id, "machine_id": machine_id, "started_at": started_at,
                                  "ended_at": None if outcome is None else started_at + timedelta(hours=1),
                                  "outcome": outcome, **kw}
        if recorded_at is not None:
            values["recorded_at"] = recorded_at
        deploy_id = self.insert("machine_deployment", "deploy_id", **values)
        if outcome is not None and recorded_at is not None:
            # Tests that model a historical receipt explicitly backfill only the new server-owned timestamp.
            # Disable this one trigger inside a throwaway owner transaction; live inserts/finalizations always
            # use clock_timestamp(), including inserts made by the database owner.
            with self.c.transaction():
                self.c.execute("ALTER TABLE machine_deployment DISABLE TRIGGER trg_machine_deployment_outcome_guard")
                self.c.execute("UPDATE machine_deployment SET outcome_recorded_at = %s WHERE deploy_id = %s",
                               (recorded_at, deploy_id))
                self.c.execute("ALTER TABLE machine_deployment ENABLE TRIGGER trg_machine_deployment_outcome_guard")
        return deploy_id

    def waiver(self, job_id: int, approver_id: int, **kw: Any) -> int:
        return self.insert("mechanisation_waiver", "waiver_id", **{
            "job_id": job_id, "approved_by": approver_id, "reason_code": "NO_MACHINE_ACCESS",
            "justification": "Narrow chamber with no vehicle access; jetting and suction units cannot reach it.", **kw})

    def invoice(self, job_id: int, *, status: str = "SUBMITTED", approver: int | None = None, amount: int = 1000) -> int:
        iid = self.insert("invoice", "invoice_id", job_id=job_id, invoice_no=f"INV-T-{next(_seq):05d}", amount_inr=amount)
        if status in ("APPROVED", "PAID"):
            self.c.execute("UPDATE invoice SET status = 'APPROVED', decided_by = %s WHERE invoice_id = %s", (approver, iid))
        if status == "PAID":
            self.c.execute("UPDATE invoice SET status = 'PAID' WHERE invoice_id = %s", (iid,))
        return iid

    # -- permits ---------------------------------------------------------------------------------------
    def detector(self, **kw: Any) -> int:
        n = next(_seq)
        return self.insert("gas_detector", "detector_id", **{
            "serial_no": f"GD-T-{n:05d}", "model": "Test 4-gas", "calibration_valid_until": "2099-12-31", **kw})

    def permit(self, job_id: int, supervisor_id: int) -> int:
        return self.insert("entry_permit", "permit_id", job_id=job_id, supervisor_id=supervisor_id)

    def crew(self, permit_id: int, worker_id: int, role: str, *, acknowledged: bool = True,
             acknowledged_at: datetime | None = None) -> int | None:
        self.c.execute("INSERT INTO permit_crew (permit_id, worker_id, crew_role) VALUES (%s, %s, %s)",
                       (permit_id, worker_id, role))
        if not acknowledged:
            return None
        actor = self.c.execute("SELECT user_id FROM app_user WHERE worker_id = %s", (worker_id,)).fetchone()
        user_id = actor["user_id"] if actor else self.user("WORKER", worker_id=worker_id)
        self.c.execute("UPDATE permit_crew SET acknowledged_by=%s, acknowledged_at=%s WHERE permit_id=%s AND worker_id=%s",
                       (user_id, acknowledged_at or datetime.now(timezone.utc), permit_id, worker_id))
        return user_id

    def issue_gear(self, permit_id: int, worker_id: int, issued_by: int | None = None) -> None:
        """Issue every statutory item to the worker (each with a serial number)."""
        items = self.c.execute("SELECT gear_code FROM gear_item WHERE statutory AND requirement_scope='ENTRANT' ORDER BY gear_code").fetchall()
        for item in items:
            self.issue_gear_item(permit_id, worker_id, item["gear_code"], issued_by)

    def issue_gear_item(self, permit_id: int, worker_id: int, gear_code: str, issued_by: int | None = None) -> int:
        """Create an explicitly inspected synthetic serial asset and issue it in this test fixture."""
        ulb_id = self.scalar("SELECT m.ulb_id FROM entry_permit p JOIN job j USING (job_id) "
                             "JOIN complaint c USING (complaint_id) JOIN manhole m USING (manhole_id) WHERE p.permit_id=%s", permit_id)
        n = next(_seq)
        asset = self.insert("gear_asset", "gear_asset_id", ulb_id=ulb_id, gear_code=gear_code,
                            serial_no=f"EDU-SN-{n:06d}", status="USABLE", inspection_valid_until="2099-12-31")
        self.insert("gear_issue", "issue_id", permit_id=permit_id, worker_id=worker_id, gear_code=gear_code,
                    serial_no=f"EDU-SN-{n:06d}", gear_asset_id=asset, issued_by=issued_by)
        return asset

    def site_gear(self, permit_id: int, gear_code: str = "FIRST_AID_KIT", issued_by: int | None = None) -> int:
        ulb_id = self.scalar("SELECT m.ulb_id FROM entry_permit p JOIN job j USING (job_id) "
                             "JOIN complaint c USING (complaint_id) JOIN manhole m USING (manhole_id) WHERE p.permit_id=%s", permit_id)
        n = next(_seq)
        asset = self.insert("gear_asset", "gear_asset_id", ulb_id=ulb_id, gear_code=gear_code,
                            serial_no=f"EDU-SITE-{n:06d}", status="USABLE", inspection_valid_until="2099-12-31")
        self.insert("permit_site_gear", "site_gear_id", permit_id=permit_id, gear_asset_id=asset, issued_by=issued_by)
        return asset

    def readiness(self, permit_id: int, recorded_by: int, at: datetime | None = None, *, failed: str | None = None) -> None:
        ref = "EDU-FIXTURE-REFERENCE"
        details_by_kind = {
            "STRUCTURE": {"inspection_ref": ref, "qualified_person_ref": ref},
            "ISOLATION": {"isolation_ref": ref},
            "VENTILATION": {"opened_at": (at or datetime.now(timezone.utc)).isoformat(), "method_ref": ref},
            "RESCUE": {"plan_ref": ref, "retrieval_asset_ref": ref},
            "COMMUNICATION": {"method_ref": ref, "test_ref": ref},
            "TRAFFIC": {"barrier_ref": ref},
            "MEDICAL": {"contact_ref": ref, "first_aid_ref": ref},
        }
        for kind in ("STRUCTURE", "ISOLATION", "VENTILATION", "RESCUE", "COMMUNICATION", "TRAFFIC", "MEDICAL"):
            recorded = at or datetime.now(timezone.utc)
            self.insert("permit_readiness", "readiness_id", permit_id=permit_id, kind=kind,
                        passed=(kind != failed), recorded_by=recorded_by, recorded_at=recorded,
                        expires_at=recorded + timedelta(days=2), details=Jsonb({**details_by_kind[kind],
                        "fixture": "explicit synthetic educational test attestation; references are illustrative, not physical verification"}),
                        source_mode="SIMULATED")

    def reading(self, permit_id: int, detector_id: int, level: str, taken_at: datetime, recorded_by: int,
                *, o2: float = 20.9, h2s: float = 0, lel: float = 0, co: float = 0) -> int:
        return self.insert("gas_reading", "reading_id", permit_id=permit_id, detector_id=detector_id, depth_level=level,
                           o2_pct=o2, h2s_ppm=h2s, lel_pct=lel, co_ppm=co, taken_at=taken_at, recorded_by=recorded_by)

    def gate_scenario(self, at: datetime, *, readings: dict[str, dict | None] | None = None,
                      include_new_evidence: bool = True) -> dict[str, Any]:
        """A DRAFT permit that satisfies every legal clause as of `at`, plus all the ids a test may want to break.

        `readings` overrides per depth level: None skips the level; a dict may carry age_min, o2, h2s, lel, co.
        Default is a fresh, in-limit reading at TOP, MID and BOTTOM five minutes before `at`.
        """
        s: dict[str, Any] = {"at": at}
        s["ulb"] = self.ulb(policy_mode="EDUCATIONAL")
        s["contractor"] = self.contractor()
        s["manhole"] = self.manhole(s["ulb"])
        s["engineer"] = self.user("ENGINEER", ulb_id=s["ulb"])
        s["supervisor"] = self.user("SUPERVISOR", ulb_id=s["ulb"])
        self.insert("ulb_contractor_scope", "contractor_id", ulb_id=s["ulb"], contractor_id=s["contractor"],
                    assigned_by=s["engineer"], assignment_reason="Explicit synthetic test-scope contractor assignment")
        s["complaint"] = self.complaint(s["manhole"])
        s["job"] = self.job(s["complaint"], s["contractor"])
        s["machine"] = self.machine(s["ulb"])
        s["failed_deployment"] = self.deployment(s["job"], s["machine"], "FAILED", started_at=at - timedelta(days=1))
        s["waiver"] = self.waiver(s["job"], s["engineer"], reason_code="MACHINE_FAILED")
        s["permit"] = self.permit(s["job"], s["supervisor"])
        for name, role in (("e1", "ENTRANT"), ("e2", "ENTRANT"), ("standby", "STANDBY"), ("sup_worker", "SUPERVISOR")):
            s[name] = self.worker(s["contractor"])
            s[f"worker_user_{name}"] = self.crew(s["permit"], s[name], role, acknowledged_at=at - timedelta(minutes=2))
        for name in ("e1", "e2"):
            self.issue_gear(s["permit"], s[name], s["supervisor"])
        if include_new_evidence:
            s["site_asset"] = self.site_gear(s["permit"], issued_by=s["supervisor"])
            self.readiness(s["permit"], s["supervisor"], at - timedelta(minutes=2))
        s["detector"] = self.detector()
        self.insert("ulb_detector_scope", "detector_id", ulb_id=s["ulb"], detector_id=s["detector"],
                    assigned_by=s["engineer"], assignment_reason="Explicit synthetic test-scope detector assignment")
        spec = {"TOP": {}, "MID": {}, "BOTTOM": {}}
        spec.update(readings or {})
        for level, opts in spec.items():
            if opts is None:
                continue
            opts = dict(opts)
            age = opts.pop("age_min", 5)
            self.reading(s["permit"], s["detector"], level, at - timedelta(minutes=age), s["supervisor"], **opts)
        return s


IST = timezone(timedelta(hours=5, minutes=30))


def yesterday_ist(hour: int = 10, minute: int = 0) -> datetime:
    """Yesterday at hour:minute India time: always in the past, so 'no future readings' never trips,
    and inside the default 06:00-18:00 daylight window whatever the wall clock says now."""
    day = (datetime.now(IST) - timedelta(days=1)).date()
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST)
