"""Every condition at once: what the database does in each situation, with the state before and after.

    python scripts/showcase.py            (or: python run.py showcase)
    python scripts/showcase.py --only 3,7,17

Starts its own throwaway embedded PostgreSQL 16 (never touches .pgdata, so `python run.py` can keep running), builds one
template from the SAME migrations and demo data the UI shows (CHN-ADY-010 draft permit, the five alerts, held invoices),
clones one private database per condition and runs ALL conditions at the same time, each in its own thread. It then
prints, per condition: the situation, the action tried, the database's reaction (result or SQLSTATE + its own sentence)
and the rows that changed. Exit code 1 if any reaction differs from the expected one, so this is also a self-check.
"""

import argparse
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import pgserver
import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
from db import alembic_config  # noqa: E402

from zeroentry.db import url_for  # noqa: E402
from zeroentry.seed import run_seed  # noqa: E402

APP_PASSWORD = "showcase_only_Aa1"     # throwaway cluster, deleted at exit
NOTE = "Showcase decision: reviewed against the machine log and the contractor's statement."


@dataclass
class Result:
    condition: str
    action: str
    reaction: str = ""
    state: list[tuple[str, object, object]] = field(default_factory=list)
    ok: bool = False
    seconds: float = 0.0


@dataclass
class Db:
    uri: str
    name: str

    def owner(self, autocommit: bool = True) -> psycopg.Connection:
        return psycopg.connect(make_conninfo(self.uri, dbname=self.name), autocommit=autocommit, row_factory=dict_row)

    def app(self) -> psycopg.Connection:
        return psycopg.connect(make_conninfo(self.uri, dbname=self.name, user="ze_app", password=APP_PASSWORD),
                               autocommit=True, row_factory=dict_row)


SCENARIOS: list[tuple[str, str, object]] = []


def scenario(group: str, title: str):
    def register(fn):
        SCENARIOS.append((group, title, fn))
        return fn
    return register


# --- helpers ---------------------------------------------------------------------------------------------------------
def one(c, sql: str, *params):
    row = c.execute(sql, params).fetchone()
    return None if row is None else next(iter(row.values()))


def attempt(c, sql: str, *params) -> tuple[str | None, str]:
    """Run a statement that may be refused; returns (None, '') or (SQLSTATE, the database's own message)."""
    try:
        c.execute(sql, params)
        return None, ""
    except psycopg.Error as exc:
        return exc.sqlstate, (exc.diag.message_primary or str(exc)).replace("\n", " ")


def refused(code: str | None, msg: str) -> str:
    return f"REFUSED, SQLSTATE {code}: {msg[:150]}" if code else "ACCEPTED"


class Ids:
    """The demo rows every condition starts from, looked up by their natural keys."""

    def __init__(self, c):
        q = lambda sql, *p: one(c, sql, *p)  # noqa: E731
        self.permit = q("SELECT max(permit_id) FROM entry_permit WHERE status = 'DRAFT'")
        self.supervisor = q("SELECT user_id FROM app_user WHERE email = 'supervisor@zeroentry.example'")
        self.engineer = q("SELECT user_id FROM app_user WHERE email = 'engineer@zeroentry.example'")
        self.detector = q("SELECT detector_id FROM gas_detector WHERE serial_no = 'GD-4G-0001'")
        self.expired_detector = q("SELECT detector_id FROM gas_detector WHERE serial_no = 'GD-4G-0002'")
        self.worker = lambda nam: q("SELECT worker_id FROM worker WHERE namaste_id = %s", nam)
        self.entrant = self.worker("NAM-TN-100001")
        self.standby = self.worker("NAM-TN-100003")
        self.alert = lambda code: q("SELECT a.alert_id FROM shadow_entry_alert a JOIN complaint c USING (complaint_id) "
                                    "JOIN manhole m USING (manhole_id) WHERE m.code = %s", code)


def manhole(c) -> int:                 # PostgreSQL does not accept a subquery as a CALL argument
    return one(c, "SELECT min(manhole_id) FROM manhole")


def status(c, permit: int) -> str:
    return one(c, "SELECT status FROM entry_permit WHERE permit_id = %s", permit)


def count(c, sql: str, *params) -> int:
    return one(c, f"SELECT count(*) FROM {sql}", *params)


def complete_evidence(c, s: Ids) -> None:
    """What the supervisor does in the UI: add a standby, issue the missing gear, log TOP/MID/BOTTOM readings."""
    c.execute("INSERT INTO permit_crew (permit_id, worker_id, crew_role) VALUES (%s, %s, 'STANDBY')", (s.permit, s.standby))
    c.execute("INSERT INTO gear_issue (permit_id, worker_id, gear_code, serial_no, issued_by) "
              "SELECT pc.permit_id, pc.worker_id, g.gear_code, 'SHOW-' || pc.worker_id || '-' || g.gear_code, %s "
              "FROM permit_crew pc CROSS JOIN gear_item g WHERE pc.permit_id = %s AND pc.crew_role = 'ENTRANT' AND g.statutory "
              "AND NOT EXISTS (SELECT 1 FROM gear_issue gi WHERE gi.permit_id = pc.permit_id "
              "                AND gi.worker_id = pc.worker_id AND gi.gear_code = g.gear_code)", (s.supervisor, s.permit))
    for depth in ("TOP", "MID", "BOTTOM"):
        c.execute("INSERT INTO gas_reading (permit_id, detector_id, depth_level, o2_pct, h2s_ppm, lel_pct, co_ppm, taken_at, "
                  "recorded_by) VALUES (%s, %s, %s, 20.9, 0, 0, 0, now(), %s)", (s.permit, s.detector, depth, s.supervisor))


def authorise(c, s: Ids) -> list[dict]:
    return c.execute("SELECT clause_code, passed, detail, permit_status FROM authorise_entry(%s, %s)",
                     (s.permit, s.supervisor)).fetchall()


def authorised_permit(c) -> Ids:
    s = Ids(c)
    complete_evidence(c, s)
    authorise(c, s)
    assert status(c, s.permit) == "AUTHORISED"
    return s


def open_entry(c, s: Ids, worker: int) -> int:
    return one(c, "INSERT INTO entry_log (permit_id, worker_id, period, recorded_by) "
                  "VALUES (%s, %s, tstzrange(clock_timestamp(), NULL, '[)'), %s) RETURNING entry_id", s.permit, worker, s.supervisor)


def in_background(db: Db, sql: str, *params) -> tuple[threading.Thread, dict]:
    """Run one statement from a SECOND session; returns while it is still running if it is waiting for a lock."""
    out: dict = {}

    def run():
        with db.owner() as other:
            out["code"], out["msg"] = attempt(other, sql, *params)
            out["done_at"] = time.perf_counter()
    thread = threading.Thread(target=run)
    thread.start()
    thread.join(timeout=1.0)
    return thread, out


# --- A. the entry gate -----------------------------------------------------------------------------------------------
@scenario("A. Entry gate (default deny)", "Incomplete permit asks for authorisation")
def gate_denied(db: Db) -> Result:
    with db.owner() as c:
        s = Ids(c)
        r = Result("DRAFT permit on CHN-ADY-010: no standby, entrant NAM-TN-100002 lacks breathing apparatus and harness, no gas readings",
                   "SELECT * FROM authorise_entry(permit, supervisor)")
        before = status(c, s.permit)
        rows = authorise(c, s)
        failed = [x["clause_code"] for x in rows if not x["passed"]]
        r.reaction = f"DENIED, {len(failed)} of {len(rows)} clauses fail: {', '.join(failed)}"
        r.state = [("permit status", before, status(c, s.permit))]
        r.ok = len(failed) == 5 and status(c, s.permit) == "DRAFT"
        return r


@scenario("A. Entry gate (default deny)", "Bypass attempt: raw UPDATE to AUTHORISED")
def gate_bypass(db: Db) -> Result:
    with db.owner() as c:
        s = Ids(c)
        r = Result("Same incomplete permit; someone skips the app and types SQL as the database OWNER",
                   "UPDATE entry_permit SET status = 'AUTHORISED' WHERE permit_id = <draft>")
        code, msg = attempt(c, "UPDATE entry_permit SET status = 'AUTHORISED', authorised_by = %s WHERE permit_id = %s",
                            s.supervisor, s.permit)
        r.reaction = refused(code, msg)
        r.state = [("permit status", "DRAFT", status(c, s.permit))]
        r.ok = code == "ZE001"
        return r


@scenario("A. Entry gate (default deny)", "Evidence completed, then authorised")
def gate_authorised(db: Db) -> Result:
    with db.owner() as c:
        s = Ids(c)
        r = Result("Supervisor adds a standby, issues the missing gear, logs fresh TOP/MID/BOTTOM readings (GD-4G-0001)",
                   "INSERT crew, gear, 3 readings; then authorise_entry()")
        counts = lambda: (count(c, "permit_crew WHERE permit_id = %s", s.permit), count(c, "gear_issue WHERE permit_id = %s", s.permit),  # noqa: E731
                          count(c, "gas_reading WHERE permit_id = %s", s.permit),
                          count(c, "permit_authorization_decision WHERE permit_id = %s", s.permit))
        before = counts()
        complete_evidence(c, s)
        rows = authorise(c, s)
        after = counts()
        digest = one(c, "SELECT snapshot_sha256 FROM permit_authorization_decision WHERE permit_id = %s", s.permit)
        r.reaction = f"AUTHORISED ({sum(x['passed'] for x in rows)}/{len(rows)} clauses pass); immutable snapshot saved, SHA-256 {str(digest)[:16]}..."
        r.state = [("permit status", "DRAFT", status(c, s.permit)), ("crew", before[0], after[0]), ("gear issued", before[1], after[1]),
                   ("gas readings", before[2], after[2]), ("decision snapshots", before[3], after[3])]
        r.ok = status(c, s.permit) == "AUTHORISED" and after[3] == 1
        return r


@scenario("A. Entry gate (default deny)", "Reading from an out-of-calibration detector")
def expired_detector(db: Db) -> Result:
    with db.owner() as c:
        s = Ids(c)
        r = Result("Detector GD-4G-0002's calibration expired on 2026-08-31", "INSERT INTO gas_reading (... GD-4G-0002 ...)")
        before = count(c, "gas_reading WHERE permit_id = %s", s.permit)
        code, msg = attempt(c, "INSERT INTO gas_reading (permit_id, detector_id, depth_level, o2_pct, h2s_ppm, lel_pct, co_ppm, "
                               "taken_at, recorded_by) VALUES (%s, %s, 'TOP', 20.9, 0, 0, 0, now(), %s)",
                            s.permit, s.expired_detector, s.supervisor)
        r.reaction = refused(code, msg)
        r.state = [("gas readings", before, count(c, "gas_reading WHERE permit_id = %s", s.permit))]
        r.ok = code == "ZE002"
        return r


@scenario("A. Entry gate (default deny)", "Crew changed after authorisation")
def crew_frozen(db: Db) -> Result:
    with db.owner() as c:
        s = authorised_permit(c)
        r = Result("Permit is AUTHORISED; someone adds an un-geared entrant (NAM-TN-100006) afterwards",
                   "INSERT INTO permit_crew (..., 'ENTRANT')")
        before = count(c, "permit_crew WHERE permit_id = %s", s.permit)
        code, msg = attempt(c, "INSERT INTO permit_crew (permit_id, worker_id, crew_role) VALUES (%s, %s, 'ENTRANT')",
                            s.permit, s.worker("NAM-TN-100006"))
        r.reaction = refused(code, msg)
        r.state = [("crew", before, count(c, "permit_crew WHERE permit_id = %s", s.permit))]
        r.ok = code == "ZE003"
        return r


# --- B. during the work ----------------------------------------------------------------------------------------------
@scenario("B. During the work", "Same worker logged into two overlapping entries")
def overlap(db: Db) -> Result:
    with db.owner() as c:
        s = authorised_permit(c)
        r = Result("Worker NAM-TN-100001 is already inside; a second open entry is logged for the same worker",
                   "INSERT INTO entry_log (... overlapping period ...)")
        open_entry(c, s, s.entrant)
        code, msg = attempt(c, "INSERT INTO entry_log (permit_id, worker_id, period, recorded_by) "
                               "VALUES (%s, %s, tstzrange(clock_timestamp(), NULL, '[)'), %s)", s.permit, s.entrant, s.supervisor)
        r.reaction = refused(code, msg) + "  (exclusion constraint, not code)"
        r.state = [("entries for this worker", 1, count(c, "entry_log WHERE worker_id = %s AND permit_id = %s", s.entrant, s.permit))]
        r.ok = code == "23P01"
        return r


@scenario("B. During the work", "Standby (top man) tries to go down")
def standby_enters(db: Db) -> Result:
    with db.owner() as c:
        s = authorised_permit(c)
        r = Result("The standby must stay outside to watch and rescue", "INSERT INTO entry_log (... standby worker ...)")
        code, msg = attempt(c, "INSERT INTO entry_log (permit_id, worker_id, period, recorded_by) "
                               "VALUES (%s, %s, tstzrange(clock_timestamp(), NULL, '[)'), %s)", s.permit, s.standby, s.supervisor)
        r.reaction = refused(code, msg)
        r.state = [("entries", 0, count(c, "entry_log WHERE permit_id = %s", s.permit))]
        r.ok = code == "ZE002"
        return r


@scenario("B. During the work", "Unsafe gas reading while a worker is inside")
def unsafe_gas(db: Db) -> Result:
    with db.owner() as c:
        s = authorised_permit(c)
        entry = open_entry(c, s, s.entrant)
        r = Result("Permit AUTHORISED, NAM-TN-100001 inside; a new BOTTOM reading shows O2 at 12 % (unsafe)",
                   "INSERT INTO gas_reading (... BOTTOM, o2_pct = 12 ...); then record the worker's exit")
        events_before = count(c, "permit_safety_event WHERE permit_id = %s", s.permit)
        c.execute("INSERT INTO gas_reading (permit_id, detector_id, depth_level, o2_pct, h2s_ppm, lel_pct, co_ppm, taken_at, "
                  "recorded_by) VALUES (%s, %s, 'BOTTOM', 12, 0, 0, 0, now(), %s)", (s.permit, s.detector, s.supervisor))
        after_stop = status(c, s.permit)
        events = [x["event_type"] for x in c.execute("SELECT event_type FROM permit_safety_event WHERE permit_id = %s ORDER BY event_id",
                                                     (s.permit,)).fetchall()]
        code, msg = attempt(c, "UPDATE entry_log SET period = tstzrange(lower(period), clock_timestamp(), '[)') WHERE entry_id = %s", entry)
        r.reaction = (f"reading stored; trigger STOPPED the permit ({', '.join(events)}); "
                      f"exit after the stop {'recorded' if code is None else refused(code, msg)}")
        r.state = [("permit status", "AUTHORISED", after_stop), ("safety events", events_before, len(events)),
                   ("workers still inside", 1, count(c, "entry_log WHERE permit_id = %s AND upper(period) IS NULL", s.permit))]
        r.ok = after_stop == "ABORTED" and len(events) > events_before and code is None
        return r


# --- C. detection by absence -----------------------------------------------------------------------------------------
@scenario("C. Detection by absence", "Absence scan run again")
def scan_again(db: Db) -> Result:
    with db.owner() as c:
        r = Result("The scan already ran at start-up and opened 5 alerts", "SELECT * FROM scan_shadow_entries(now())")
        before = count(c, "shadow_entry_alert")
        out = c.execute("SELECT * FROM scan_shadow_entries(now())").fetchone()
        r.reaction = f"idempotent: {out['opened']} opened, {out['moved_to_review']} moved to review, nothing duplicated or closed"
        r.state = [("alerts", before, count(c, "shadow_entry_alert"))]
        r.ok = out["opened"] == 0 and count(c, "shadow_entry_alert") == before
        return r


@scenario("C. Detection by absence", "Late evidence arrives for an open alert")
def late_evidence(db: Db) -> Result:
    with db.owner() as c:
        s = Ids(c)
        alert = s.alert("CHN-ADY-002")
        r = Result("CHN-ADY-002 was closed as 'cleared' with no evidence (alert OPEN, invoice held); a machine log turns up days later",
                   "INSERT INTO machine_deployment (... CLEARED ...); then scan_shadow_entries()")
        holds = lambda: count(c, "invoice_hold WHERE alert_id = %s AND released_at IS NULL", alert)  # noqa: E731
        before, holds_before = one(c, "SELECT status FROM shadow_entry_alert WHERE alert_id = %s", alert), holds()
        c.execute("INSERT INTO machine_deployment (job_id, machine_id, started_at, ended_at, outcome) "
                  "SELECT j.job_id, (SELECT machine_id FROM machine WHERE ulb_id = m.ulb_id ORDER BY machine_id LIMIT 1), "
                  "       now() - interval '2 hours', now() - interval '1 hour', 'CLEARED' "
                  "FROM job j JOIN complaint co USING (complaint_id) JOIN manhole m USING (manhole_id) "
                  "WHERE m.code = 'CHN-ADY-002' ORDER BY j.job_id LIMIT 1")
        c.execute("SELECT * FROM scan_shadow_entries(now())")
        after = one(c, "SELECT status FROM shadow_entry_alert WHERE alert_id = %s", alert)
        r.reaction = "alert sent to a HUMAN for review, never closed automatically; the invoice stays held until someone decides"
        r.state = [("alert status", before, after), ("active invoice holds", holds_before, holds())]
        r.ok = before == "OPEN" and after == "EVIDENCE_RECEIVED" and holds() == holds_before
        return r


@scenario("C. Detection by absence", "Engineer dismisses an alert")
def dismiss(db: Db) -> Result:
    with db.owner() as c:
        s = Ids(c)
        alert = s.alert("CHN-ADY-006")
        r = Result("Alert on CHN-ADY-006 (late paperwork, EVIDENCE_RECEIVED) holds its contractor's invoice",
                   "SELECT review_shadow_alert(alert, 'DISMISSED', note, engineer)")
        own = lambda: count(c, "invoice_hold WHERE alert_id = %s AND released_at IS NULL", alert)  # noqa: E731
        others = lambda: count(c, "invoice_hold WHERE alert_id IS DISTINCT FROM %s AND released_at IS NULL", alert)  # noqa: E731
        before, own_before, others_before = one(c, "SELECT status FROM shadow_entry_alert WHERE alert_id = %s", alert), own(), others()
        c.execute("SELECT review_shadow_alert(%s, 'DISMISSED', %s, %s)", (alert, NOTE, s.engineer))
        r.reaction = "decision recorded with the note; ONLY this alert's hold released"
        r.state = [("alert status", before, one(c, "SELECT status FROM shadow_entry_alert WHERE alert_id = %s", alert)),
                   ("this alert's active holds", own_before, own()), ("every other active hold", others_before, others())]
        r.ok = own() == 0 and own_before > 0 and others() == others_before
        return r


@scenario("C. Detection by absence", "Supervisor tries to decide an alert")
def wrong_role(db: Db) -> Result:
    with db.owner() as c:
        s = Ids(c)
        alert = s.alert("CHN-ADY-002")
        r = Result("Only an engineer (the sanitation authority) may confirm or dismiss", "SELECT review_shadow_alert(..., supervisor)")
        code, msg = attempt(c, "SELECT review_shadow_alert(%s, 'DISMISSED', %s, %s)", alert, NOTE, s.supervisor)
        r.reaction = refused(code, msg)
        r.state = [("alert status", "OPEN", one(c, "SELECT status FROM shadow_entry_alert WHERE alert_id = %s", alert))]
        r.ok = code == "ZE006"
        return r


# --- D. money and consequences ---------------------------------------------------------------------------------------
@scenario("D. Money and consequences", "Approve an invoice that is on hold")
def held_invoice(db: Db) -> Result:
    with db.owner() as c:
        s = Ids(c)
        inv = one(c, "SELECT i.invoice_id FROM invoice i JOIN invoice_hold h USING (invoice_id) "
                     "WHERE h.released_at IS NULL AND i.status = 'SUBMITTED' ORDER BY 1 LIMIT 1")
        r = Result("An invoice is held because of a shadow-entry alert", "UPDATE invoice SET status = 'APPROVED' ...")
        code, msg = attempt(c, "UPDATE invoice SET status = 'APPROVED', decided_by = %s WHERE invoice_id = %s", s.engineer, inv)
        r.reaction = refused(code, msg)
        r.state = [("invoice status", "SUBMITTED", one(c, "SELECT status FROM invoice WHERE invoice_id = %s", inv))]
        r.ok = code == "ZE003"
        return r


@scenario("D. Money and consequences", "A death is recorded (one atomic procedure)")
def fatality(db: Db) -> Result:
    with db.owner() as c:
        s = Ids(c)
        worker = s.worker("NAM-TN-100005")
        contractor = one(c, "SELECT contractor_id FROM worker WHERE worker_id = %s", worker)
        r = Result("A fatality involving a worker of Marina Sanitation Services (ACTIVE contractor with unpaid invoices)",
                   "CALL record_incident('FATALITY', ...)")
        snap = lambda: (count(c, "incident"), count(c, "compensation_case"),  # noqa: E731
                        one(c, "SELECT status FROM contractor WHERE contractor_id = %s", contractor))
        new_job = lambda: attempt(c, "INSERT INTO job (complaint_id, contractor_id) "  # noqa: E731 - rolled back below if accepted
                                     "VALUES ((SELECT min(complaint_id) FROM complaint WHERE status <> 'RESOLVED'), %s)", contractor)
        with c.transaction(force_rollback=True):
            before = (*snap(), "yes" if new_job()[0] is None else "no")
        c.execute("CALL record_incident('FATALITY', now() - interval '1 hour', %s, %s, "
                  "'Showcase: recorded in a throwaway database.', %s, NULL, NULL, NULL)", (worker, manhole(c), s.engineer))
        code, msg = new_job()
        after = (*snap(), "yes" if code is None else f"no ({code})")
        due = one(c, "SELECT amount_due FROM compensation_case ORDER BY case_id DESC LIMIT 1")
        r.reaction = (f"ONE transaction: incident + compensation case of INR {due:,.0f} with a deadline + contractor BLACKLISTED; "
                      f"afterwards a new job for them is {refused(code, msg)}")
        r.state = [("incidents", before[0], after[0]), ("compensation cases", before[1], after[1]),
                   ("contractor status", before[2], after[2]), ("can be given a new job", before[3], after[3])]
        r.ok = after[0] == before[0] + 1 and after[1] == before[1] + 1 and after[2] == "BLACKLISTED" and code == "ZE003"
        return r


@scenario("D. Money and consequences", "The same procedure fails half-way")
def fatality_rollback(db: Db) -> Result:
    with db.owner(autocommit=False) as c:
        s = Ids(c)
        snap = lambda: (count(c, "incident"), count(c, "compensation_case"),  # noqa: E731
                        count(c, "contractor WHERE status = 'BLACKLISTED'"))
        before = snap()
        c.rollback()
        r = Result("The compensation amount is mis-configured to 0, so the CHECK fails AFTER the incident row is written",
                   "UPDATE rule_parameter ... = 0; CALL record_incident(...)  in one transaction")
        c.execute("UPDATE rule_parameter SET value = 0 WHERE param_key = 'compensation_fatality_inr'")
        code, msg = attempt(c, "CALL record_incident('FATALITY', now() - interval '1 hour', %s, %s, "
                               "'Showcase: failing consequence.', %s, NULL, NULL, NULL)", s.worker("NAM-TN-100005"), manhole(c), s.engineer)
        c.rollback()
        after = snap()
        r.reaction = f"{refused(code, msg)}  -> whole transaction rolled back, nothing half-done"
        r.state = [("incidents", before[0], after[0]), ("compensation cases", before[1], after[1]), ("blacklisted contractors", before[2], after[2])]
        r.ok = code == "23514" and after == before
        return r


# --- E. concurrency --------------------------------------------------------------------------------------------------
@scenario("E. Concurrency (two sessions at the same instant)", "Crew removed WHILE the permit is being authorised")
def race_crew(db: Db) -> Result:
    with db.owner() as setup:
        s = Ids(setup)
        complete_evidence(setup, s)
    r = Result("Session 1 is inside authorise_entry() (not yet committed); session 2 deletes the standby at that moment",
               "S1: BEGIN; authorise_entry()   S2: DELETE FROM permit_crew ... STANDBY   S1: COMMIT")
    with db.owner(autocommit=False) as decider:
        authorise(decider, s)
        thread, out = in_background(db, "DELETE FROM permit_crew WHERE permit_id = %s AND crew_role = 'STANDBY'", s.permit)
        waiting = thread.is_alive()
        committed_at = time.perf_counter()
        decider.commit()
    thread.join(timeout=10)
    with db.owner() as c:
        r.reaction = (f"session 2 {'WAITED for the lock' if waiting else 'did not wait'}, re-read the committed permit, then "
                      f"{refused(out.get('code'), out.get('msg', ''))}")
        r.state = [("permit status", "DRAFT", status(c, s.permit)),
                   ("standby on the crew", 1, count(c, "permit_crew WHERE permit_id = %s AND crew_role = 'STANDBY'", s.permit))]
        r.ok = waiting and out.get("code") == "ZE003" and out.get("done_at", 0) >= committed_at
        return r


@scenario("E. Concurrency (two sessions at the same instant)", "Two clerks pay the same compensation at once")
def race_payment(db: Db) -> Result:
    with db.owner() as c:
        case, outstanding, before = c.execute("SELECT case_id, amount_due - amount_paid AS left, status FROM compensation_case "
                                      "WHERE amount_paid < amount_due ORDER BY case_id LIMIT 1").fetchone().values()
    r = Result(f"Compensation case #{case} has INR {outstanding:,.0f} outstanding; both clerks press 'pay in full'",
               "S1: BEGIN; record_compensation_payment(full)   S2: the same   S1: COMMIT")
    with db.owner(autocommit=False) as clerk1:
        clerk1.execute("SELECT record_compensation_payment(%s, %s)", (case, outstanding))
        thread, out = in_background(db, "SELECT record_compensation_payment(%s, %s)", case, outstanding)
        waiting = thread.is_alive()
        clerk1.commit()
    thread.join(timeout=10)
    with db.owner() as c:
        due, paid, st = c.execute("SELECT amount_due, amount_paid, status FROM compensation_case WHERE case_id = %s", (case,)).fetchone().values()
        r.reaction = (f"clerk 1 paid; clerk 2 {'WAITED on the row lock, then ' if waiting else ''}"
                      f"{refused(out.get('code'), out.get('msg', ''))}")
        r.state = [("amount paid", f"{due - outstanding:,.0f}", f"{paid:,.0f} of {due:,.0f}"), ("case status", before, st)]
        r.ok = out.get("code") == "ZE002" and paid == due
        return r


# --- F. security -----------------------------------------------------------------------------------------------------
@scenario("F. Security inside the database", "Who sees which permits (row-level security)")
def rls(db: Db) -> Result:
    with db.owner() as c:
        total = count(c, "entry_permit")
        users = {k: c.execute("SELECT user_id, contractor_id, worker_id FROM app_user WHERE email = %s",
                              (f"{k}@zeroentry.example",)).fetchone() for k in ("contractor", "worker", "engineer")}
    r = Result("The API connects as ze_app and sets the signed-in user per transaction", "SELECT count(*) FROM entry_permit, as each user")
    seen = {}
    with db.app() as app:
        seen["no user set"] = count(app, "entry_permit")
        for key, role in (("engineer", "ENGINEER"), ("contractor", "CONTRACTOR"), ("worker", "WORKER")):
            u = users[key]
            app.execute("SELECT set_config('app.user_id', %s, false), set_config('app.role', %s, false), "
                        "set_config('app.contractor_id', %s, false), set_config('app.worker_id', %s, false)",
                        (str(u["user_id"]), role, str(u["contractor_id"] or ""), str(u["worker_id"] or "")))
            seen[key] = count(app, "entry_permit")
    r.reaction = "same query, different rows: " + ", ".join(f"{k} sees {v}" for k, v in seen.items()) + f" (of {total})"
    r.state = [(f"visible to {k}", total, v) for k, v in seen.items()]
    r.ok = seen["no user set"] == 0 and seen["engineer"] == total and seen["contractor"] < total
    return r


@scenario("F. Security inside the database", "The app's own database role tries to rewrite history")
def least_privilege(db: Db) -> Result:
    r = Result("Even if the API had a bug, it connects as ze_app, which owns nothing",
               "as ze_app: UPDATE gas_reading ...; DROP TABLE complaint; INSERT INTO role ...")
    with db.app() as app:
        tries = {"edit a gas reading": attempt(app, "UPDATE gas_reading SET o2_pct = 20.9"),
                 "drop a table": attempt(app, "DROP TABLE complaint"),
                 "create a new role row": attempt(app, "INSERT INTO role (name) VALUES ('ROOT')")}
    r.reaction = "; ".join(f"{k}: {code or 'ACCEPTED'}" for k, (code, _) in tries.items())
    r.state = [("statements refused", 0, sum(code is not None for code, _ in tries.values()))]
    r.ok = all(code is not None for code, _ in tries.values())
    return r


# --- runner ----------------------------------------------------------------------------------------------------------
def build_template(uri: str) -> str:
    name = "showcase_template"
    with psycopg.connect(uri, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {name}")
    from alembic import command
    owner_url = url_for(uri, name)
    command.upgrade(alembic_config(owner_url), "head")
    with psycopg.connect(make_conninfo(uri, dbname=name), autocommit=True) as c:
        c.execute(f"ALTER ROLE ze_app LOGIN PASSWORD '{APP_PASSWORD}'")
    run_seed(owner_url, "Showcase-only-Aa1", bcrypt_rounds=4)
    with psycopg.connect(make_conninfo(uri, dbname=name), autocommit=True) as c:
        # Entries may only start in daylight (06:00-18:00 IST). Widen it in THIS throwaway copy so the demo runs at any
        # hour; the change goes through policy history with a reason, exactly like an admin's change in the UI.
        c.execute("SELECT set_config('app.rule_change_reason', 'Synthetic showcase: all-day window so entries can be shown at any hour', false)")
        c.execute("UPDATE rule_parameter SET value = 0 WHERE param_key = 'daylight_start_hour'")
        c.execute("UPDATE rule_parameter SET value = 24 WHERE param_key = 'daylight_end_hour'")
        c.execute("SELECT * FROM scan_shadow_entries(now())")
    return name


def run_one(item, db: Db) -> Result:
    started = time.perf_counter()
    try:
        r = item[2](db)
    except Exception as exc:  # noqa: BLE001 - a showcase must report, not crash
        r = Result("(setup failed)", item[1], reaction=f"UNEXPECTED {type(exc).__name__}: {exc}".replace("\n", " "))
    r.seconds = time.perf_counter() - started
    return r


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="comma-separated condition numbers, e.g. 1,3,17")
    args = parser.parse_args()
    chosen = [(i, s) for i, s in enumerate(SCENARIOS, 1) if not args.only or str(i) in args.only.split(",")]
    color = sys.stdout.isatty()
    paint = (lambda text, code: f"\033[{code}m{text}\033[0m") if color else (lambda text, code: text)

    print("Starting a throwaway PostgreSQL 16 and loading the demo data (about 20 seconds) ...", flush=True)
    with tempfile.TemporaryDirectory(prefix="zeroentry-showcase-") as tmp:
        server = pgserver.get_server(Path(tmp), cleanup_mode="stop")
        try:
            uri = server.get_uri()
            template = build_template(uri)
            dbs = {}
            with psycopg.connect(uri, autocommit=True) as admin:
                for i, _ in chosen:
                    admin.execute(f"CREATE DATABASE showcase_{i} TEMPLATE {template}")
                    dbs[i] = Db(uri, f"showcase_{i}")
            print(f"Running {len(chosen)} conditions AT THE SAME TIME, each in its own private copy of the database ...\n", flush=True)
            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=len(chosen)) as pool:
                futures = {i: pool.submit(run_one, s, dbs[i]) for i, s in chosen}
                results = {i: f.result() for i, f in futures.items()}
            wall = time.perf_counter() - started
        finally:
            server.cleanup()

    group = None
    for i, (g, title, _) in chosen:
        r = results[i]
        if g != group:
            group = g
            print(paint(f"\n=== {g} " + "=" * max(0, 100 - len(g)), "1"))
        print(f"\n[{i:02d}] {paint(title, '1')}   {paint('as expected', '32') if r.ok else paint('UNEXPECTED', '31')}   ({r.seconds:.1f} s)")
        print(f"     Situation : {r.condition}")
        print(f"     Action    : {r.action}")
        print(f"     Database  : {paint(r.reaction, '36')}")
        for label, before, after in r.state:
            change = "unchanged" if before == after else "changed"
            print(f"     State     : {label:<28} {str(before):>14}  ->  {str(after):<20} ({change})")

    print(paint("\n=== Summary " + "=" * 89, "1"))
    for i, (g, title, _) in chosen:
        r = results[i]
        print(f"  [{i:02d}] {'OK ' if r.ok else 'BAD'}  {title:<52} {r.reaction[:70]}")
    bad = [i for i, _ in chosen if not results[i].ok]
    print(f"\n{len(chosen) - len(bad)} of {len(chosen)} conditions behaved as expected; all ran concurrently in {wall:.1f} s "
          f"(sum of their individual times {sum(r.seconds for r in results.values()):.1f} s).")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
