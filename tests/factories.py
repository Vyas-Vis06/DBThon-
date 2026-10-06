"""Plain-SQL row factories for tests.

Everything goes through the real constraints and triggers (nothing is bypassed), so a factory that can
build a row proves the row is legal. Each method returns the new primary key. Defaults are legal and
unique; override only what the test is about.
"""

import itertools
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg

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
        return self.insert("ulb", "ulb_id", **{"name": f"Test ULB {n}", "district": "Chennai", "state": "Tamil Nadu", **kw})

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
        return self.insert("machine_deployment", "deploy_id", **values)

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

    def crew(self, permit_id: int, worker_id: int, role: str) -> None:
        self.c.execute("INSERT INTO permit_crew (permit_id, worker_id, crew_role) VALUES (%s, %s, %s)",
                       (permit_id, worker_id, role))

    def issue_gear(self, permit_id: int, worker_id: int, issued_by: int | None = None) -> None:
        """Issue every statutory item to the worker (each with a serial number)."""
        self.c.execute("INSERT INTO gear_issue (permit_id, worker_id, gear_code, serial_no, issued_by) "
                       "SELECT %s, %s, gear_code, 'SN-' || gear_code, %s FROM gear_item WHERE statutory",
                       (permit_id, worker_id, issued_by))

    def reading(self, permit_id: int, detector_id: int, level: str, taken_at: datetime, recorded_by: int,
                *, o2: float = 20.9, h2s: float = 0, lel: float = 0, co: float = 0) -> int:
        return self.insert("gas_reading", "reading_id", permit_id=permit_id, detector_id=detector_id, depth_level=level,
                           o2_pct=o2, h2s_ppm=h2s, lel_pct=lel, co_ppm=co, taken_at=taken_at, recorded_by=recorded_by)

    def gate_scenario(self, at: datetime, *, readings: dict[str, dict | None] | None = None) -> dict[str, Any]:
        """A DRAFT permit that satisfies every legal clause as of `at`, plus all the ids a test may want to break.

        `readings` overrides per depth level: None skips the level; a dict may carry age_min, o2, h2s, lel, co.
        Default is a fresh, in-limit reading at TOP, MID and BOTTOM five minutes before `at`.
        """
        s: dict[str, Any] = {"at": at}
        s["ulb"] = self.ulb()
        s["contractor"] = self.contractor()
        s["manhole"] = self.manhole(s["ulb"])
        s["engineer"] = self.user("ENGINEER")
        s["supervisor"] = self.user("SUPERVISOR")
        s["complaint"] = self.complaint(s["manhole"])
        s["job"] = self.job(s["complaint"], s["contractor"])
        s["machine"] = self.machine(s["ulb"])
        s["failed_deployment"] = self.deployment(s["job"], s["machine"], "FAILED", started_at=at - timedelta(days=1))
        s["waiver"] = self.waiver(s["job"], s["engineer"], reason_code="MACHINE_FAILED")
        s["permit"] = self.permit(s["job"], s["supervisor"])
        for name, role in (("e1", "ENTRANT"), ("e2", "ENTRANT"), ("standby", "STANDBY"), ("sup_worker", "SUPERVISOR")):
            s[name] = self.worker(s["contractor"])
            self.crew(s["permit"], s[name], role)
        for name in ("e1", "e2"):
            self.issue_gear(s["permit"], s[name], s["supervisor"])
        s["detector"] = self.detector()
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
