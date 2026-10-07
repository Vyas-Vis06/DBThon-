"""Measure ZeroEntry against the conventional approach and write docs/EVALUATION_RESULTS.md.

    python scripts/evaluate.py                          # full run (about 10 minutes); rewrites docs/EVALUATION_RESULTS.md
    python scripts/evaluate.py --sizes 1000,10000       # smaller history volumes
    python scripts/evaluate.py --out -                  # print the report instead of writing the file

Starts its own throwaway embedded PostgreSQL 16 in a temporary directory (it never touches .pgdata or any other
database), migrates it through the normal Alembic path and runs three experiments (docs/EVALUATION.md explains them):

  E1  detection accuracy   scan_shadow_entries() vs the proposal's naive anti-join, on labelled synthetic complaints
  E2  enforcement          one invalid write per database-enforced rule, against ZeroEntry and against the same schema
                           with its rule triggers disabled (the rules living in application code)
  E3  performance          entry-decision latency and absence-scan cost as history grows, with and without the indexes

tests/db/test_evaluation.py runs E1-E3 at a tiny scale and asserts the counts (never the timings).
"""

import argparse
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tests.factories import Factory, ist  # noqa: E402  (row factories that go through every constraint and trigger)

EVAL_SQL = ROOT / "database" / "evaluation" / "evaluation.sql"
BASELINE_SQL = ROOT / "database" / "evaluation" / "rules_in_app_code.sql"
H, MIN = timedelta(hours=1), timedelta(minutes=1)
T0 = ist(2026, 9, 1, 10, 0)                       # labelled complaints are resolved here; any past daylight instant works
FIRST_SCAN, SCAN = T0 + 25 * H, T0 + 48 * H


def prepare(conn: psycopg.Connection) -> None:
    """Create the evaluation-only objects (naive baseline view, history generator) in a throwaway database."""
    conn.execute(EVAL_SQL.read_text(encoding="utf-8"))


# =====================================================================================================================
# E1 detection accuracy
# =====================================================================================================================
# (class, an alert is expected at SCAN, what the complaint looks like)
CLASSES = [
    ("machine_cleared", False, "machine deployment CLEARED, recorded before the resolution"),
    ("retried_then_cleared", False, "first job's machine FAILED, a second job's machine CLEARED"),
    ("evidence_synced_in_grace", False, "CLEARED deployment recorded 10 h after the resolution (grace is 24 h)"),
    ("lawful_manual_entry", False, "waiver, authorised permit, every entrant logged, permit closed"),
    ("exempt_resolution", False, "resolved NO_BLOCKAGE_FOUND / DUPLICATE / REFERRED_OUT / WITHDRAWN, no evidence"),
    ("still_in_grace", False, "resolved 2 h before the scan, evidence may still arrive"),
    ("no_evidence", True, "resolved CLEARED, a job exists, no machine log, no permit"),
    ("no_job_at_all", True, "resolved CLEARED with no job at all"),
    ("machine_failed_only", True, "the only machine deployment FAILED"),
    ("entrant_not_logged", True, "lawful permit closed, but one entrant has no entry log"),
]
EXEMPT = ["NO_BLOCKAGE_FOUND", "DUPLICATE_COMPLAINT", "REFERRED_OUT", "WITHDRAWN"]


def _lawful_permit(conn, f: Factory, log_both: bool) -> int:
    at = T0 - 20 * H                                               # the afternoon before (14:00 IST): daylight
    s = f.gate_scenario(at)
    conn.execute("SELECT * FROM authorise_entry(%s, %s, %s)", (s["permit"], s["supervisor"], at))
    for e in ("e1", "e2") if log_both else ("e1",):
        conn.execute("INSERT INTO entry_log (permit_id, worker_id, period, recorded_by, recorded_at) "
                     "VALUES (%s, %s, tstzrange(%s, %s), %s, %s)",
                     (s["permit"], s[e], at + 10 * MIN, at + 40 * MIN, s["supervisor"], at + 45 * MIN))
    conn.execute("UPDATE entry_permit SET status = 'CLOSED', ended_at = %s WHERE permit_id = %s", (at + H, s["permit"]))
    conn.execute("UPDATE complaint SET raised_at = %s, status = 'RESOLVED', resolved_at = %s, resolution_code = 'CLEARED' "
                 "WHERE complaint_id = %s", (at - 24 * H, T0, s["complaint"]))
    return s["complaint"]


def _build(conn, f: Factory, w: dict, cls: str, i: int) -> int:
    if cls == "lawful_manual_entry":
        return _lawful_permit(conn, f, log_both=True)
    if cls == "entrant_not_logged":
        return _lawful_permit(conn, f, log_both=False)
    if cls == "no_job_at_all":
        return f.resolved_complaint(w["manhole"], T0)
    if cls == "exempt_resolution":
        c = f.resolved_complaint(w["manhole"], T0, EXEMPT[i % len(EXEMPT)])
    elif cls == "still_in_grace":
        c = f.resolved_complaint(w["manhole"], SCAN - 2 * H)
    else:
        c = f.resolved_complaint(w["manhole"], T0)
    j = f.job(c, w["contractor"])
    if cls == "machine_cleared":
        f.deployment(j, w["machine"], "CLEARED", started_at=T0 - 3 * H, recorded_at=T0 - H)
    elif cls == "retried_then_cleared":
        f.deployment(j, w["machine"], "FAILED", started_at=T0 - 5 * H, recorded_at=T0 - 3 * H)
        f.deployment(f.job(c, w["contractor"]), w["machine"], "CLEARED", started_at=T0 - 3 * H, recorded_at=T0 - H)
    elif cls == "evidence_synced_in_grace":
        f.deployment(j, w["machine"], "CLEARED", started_at=T0 - 3 * H, recorded_at=T0 + 10 * H)
    elif cls == "machine_failed_only":
        f.deployment(j, w["machine"], "FAILED", started_at=T0 - 3 * H, recorded_at=T0 - H)
    return c


def _scores(truth: dict[int, bool], flagged: set[int]) -> dict:
    tp = sum(1 for c, pos in truth.items() if pos and c in flagged)
    fp = sum(1 for c, pos in truth.items() if not pos and c in flagged)
    fn = sum(1 for c, pos in truth.items() if pos and c not in flagged)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": len(truth) - tp - fp - fn,
            "precision": precision, "recall": recall, "f1": f1}


def detection_accuracy(conn: psycopg.Connection, per_class: int = 20) -> dict:
    """Labelled synthetic complaints; ZeroEntry's persisted alerts vs the naive view, both read at the same instant."""
    f = Factory(conn)
    ulb = f.ulb()
    w = {"manhole": f.manhole(ulb), "machine": f.machine(ulb), "contractor": f.contractor()}
    cls_of: dict[int, str] = {}
    for cls, _, _ in CLASSES:
        for i in range(per_class):
            cls_of[_build(conn, f, w, cls, i)] = cls
    late = []                                       # resolved with no evidence; a CLEARED log is recorded after scan 1
    for _ in range(per_class):
        c = f.resolved_complaint(w["manhole"], T0)
        late.append((c, f.job(c, w["contractor"])))

    naive = lambda: {r["complaint_id"] for r in conn.execute("SELECT complaint_id FROM eval_naive_shadow")}  # noqa: E731
    naive_first = naive()
    conn.execute("SELECT * FROM scan_shadow_entries(%s)", (FIRST_SCAN,))
    for _, j in late:
        f.deployment(j, w["machine"], "CLEARED", started_at=T0 - 3 * H, recorded_at=T0 + 30 * H)
    naive_now = naive()
    conn.execute("SELECT * FROM scan_shadow_entries(%s)", (SCAN,))
    alerts = {r["complaint_id"]: r["status"] for r in conn.execute("SELECT complaint_id, status FROM shadow_entry_alert")}

    expected = {cls: pos for cls, pos, _ in CLASSES}
    truth = {c: expected[cls] for c, cls in cls_of.items()}
    rows = []
    for cls, pos, what in CLASSES:
        ids = [c for c, k in cls_of.items() if k == cls]
        rows.append({"class": cls, "what": what, "n": len(ids), "expected": pos,
                     "zeroentry": sum(c in alerts for c in ids), "naive": sum(c in naive_now for c in ids)})
    late_ids = [c for c, _ in late]
    return {
        "classes": rows,
        "summary": {"ZeroEntry": _scores(truth, set(alerts)), "naive": _scores(truth, naive_now)},
        "late": {"n": len(late_ids),
                 "zeroentry_kept_for_review": sum(alerts.get(c) == "EVIDENCE_RECEIVED" for c in late_ids),
                 "naive_silently_cleared": sum(c in naive_first and c not in naive_now for c in late_ids)},
    }


# =====================================================================================================================
# E2 enforcement: one invalid write per rule the database enforces on writes
# =====================================================================================================================
def _authorise_raw(conn, s):
    """What any client could send: set the permit AUTHORISED directly, every column filled in consistently."""
    conn.execute("UPDATE entry_permit SET status = 'AUTHORISED', authorised_at = %(at)s, authorised_by = %(sup)s, "
                 "valid_until = %(at)s + interval '240 minutes' WHERE permit_id = %(p)s",
                 {"at": s["at"], "sup": s["supervisor"], "p": s["permit"]})


def _alert(conn, s) -> int:
    return conn.execute("INSERT INTO shadow_entry_alert (complaint_id, rule_code, status, reason, evidence_deadline) "
                        "VALUES (%s, 'SE1_NO_CLEARANCE_EVIDENCE', 'OPEN', 'Evaluation probe', %s) RETURNING alert_id",
                        (s["complaint"], s["at"])).fetchone()["alert_id"]


def _held_invoice(conn, f, s):
    s["invoice"] = f.invoice(s["job"])
    s["alert"] = _alert(conn, s)                  # ZeroEntry holds the invoice itself; the explicit row is for the baseline
    conn.execute("INSERT INTO invoice_hold (invoice_id, reason, alert_id) VALUES (%s, 'SHADOW_ENTRY', %s) "
                 "ON CONFLICT DO NOTHING", (s["invoice"], s["alert"]))


def _closed(conn, s):
    _authorise_raw(conn, s)
    conn.execute("UPDATE entry_permit SET status = 'CLOSED', ended_at = %s WHERE permit_id = %s", (s["at"] + H, s["permit"]))


def _noop(conn, f, s):
    pass


# (rule, the invalid write, setup(conn, f, s), attack(conn, f, s)). s is a fresh permit that passes every clause.
ATTACKS = [
    ("BR-01", "Draft a permit for a job that has no written mechanisation waiver", _noop,
     lambda c, f, s: f.permit(f.job(s["complaint"], s["contractor"]), s["supervisor"])),
    ("BR-02", "File a MACHINE_FAILED waiver when no machine has failed on the complaint", _noop,
     lambda c, f, s: f.waiver(f.job(f.complaint(s["manhole"]), s["contractor"]), s["engineer"], reason_code="MACHINE_FAILED")),
    ("BR-03", "Authorise a permit whose crew has no standby (raw UPDATE)",
     lambda c, f, s: c.execute("DELETE FROM permit_crew WHERE permit_id = %s AND worker_id = %s", (s["permit"], s["standby"])),
     lambda c, f, s: _authorise_raw(c, s)),
    ("BR-04", "Authorise with an entrant whose medical fitness has expired",
     lambda c, f, s: c.execute("UPDATE worker SET medical_fit_until = '2020-01-01' WHERE worker_id = %s", (s["e1"],)),
     lambda c, f, s: _authorise_raw(c, s)),
    ("BR-05", "Authorise a job whose contractor is blacklisted",
     lambda c, f, s: c.execute("UPDATE contractor SET status = 'BLACKLISTED' WHERE contractor_id = %s", (s["contractor"],)),
     lambda c, f, s: _authorise_raw(c, s)),
    ("BR-06", "Authorise when an entrant has no breathing apparatus",
     lambda c, f, s: c.execute("DELETE FROM gear_issue WHERE permit_id = %s AND worker_id = %s "
                               "AND gear_code = 'BREATHING_APPARATUS'", (s["permit"], s["e1"])),
     lambda c, f, s: _authorise_raw(c, s)),
    ("BR-07", "Authorise after the latest BOTTOM reading showed H2S at 25 ppm",
     lambda c, f, s: f.reading(s["permit"], s["detector"], "BOTTOM", s["at"] - MIN, s["supervisor"], h2s=25),
     lambda c, f, s: _authorise_raw(c, s)),
    ("BR-08", "Insert a permit that is born AUTHORISED", _noop,
     lambda c, f, s: c.execute("INSERT INTO entry_permit (job_id, supervisor_id, status, authorised_at, authorised_by, "
                               "valid_until) VALUES (%(j)s, %(u)s, 'AUTHORISED', %(at)s, %(u)s, %(at)s + interval '4 hours')",
                               {"j": s["job"], "u": s["supervisor"], "at": s["at"]})),
    ("BR-09", "Add an un-geared entrant to an authorised permit", lambda c, f, s: _authorise_raw(c, s),
     lambda c, f, s: f.crew(s["permit"], f.worker(s["contractor"]), "ENTRANT")),
    ("BR-10", "Log a 95-minute continuous entry", lambda c, f, s: _authorise_raw(c, s),
     lambda c, f, s: c.execute("INSERT INTO entry_log (permit_id, worker_id, period, recorded_by) "
                               "VALUES (%s, %s, tstzrange(%s, %s), %s)",
                               (s["permit"], s["e1"], s["at"] + 10 * MIN, s["at"] + 105 * MIN, s["supervisor"]))),
    ("BR-11", "Re-open a CLOSED permit", lambda c, f, s: _closed(c, s),
     lambda c, f, s: c.execute("UPDATE entry_permit SET status = 'AUTHORISED', ended_at = NULL WHERE permit_id = %s",
                               (s["permit"],))),
    ("BR-12", "Record a gas reading from a detector whose calibration had lapsed", _noop,
     lambda c, f, s: f.reading(s["permit"], f.detector(calibration_valid_until="2020-01-01"), "TOP", s["at"] - MIN,
                               s["supervisor"])),
    ("BR-22", "Give a new job to a blacklisted contractor",
     lambda c, f, s: c.execute("UPDATE contractor SET status = 'BLACKLISTED' WHERE contractor_id = %s", (s["contractor"],)),
     lambda c, f, s: f.job(s["complaint"], s["contractor"])),
    ("BR-23", "Approve an invoice that is on hold", lambda c, f, s: _held_invoice(c, f, s),
     lambda c, f, s: c.execute("UPDATE invoice SET status = 'APPROVED', decided_by = %s WHERE invoice_id = %s",
                               (s["engineer"], s["invoice"]))),
    ("BR-31", "A supervisor dismisses a shadow-entry alert (only an engineer may decide)",
     lambda c, f, s: s.update(alert=_alert(c, s)),
     lambda c, f, s: c.execute("UPDATE shadow_entry_alert SET status = 'DISMISSED', reviewed_by = %s, reviewed_at = now(), "
                               "review_note = 'Looked fine on the site visit' WHERE alert_id = %s",
                               (s["supervisor"], s["alert"]))),
    ("BR-34", "Raise a second alert for the same complaint and rule", lambda c, f, s: _alert(c, s),
     lambda c, f, s: _alert(c, s)),
    ("BR-36", "Rewrite an alert's lifecycle history",
     lambda c, f, s: s.update(event=c.execute(
         "INSERT INTO shadow_entry_alert_event (alert_id, to_status, note) VALUES (%s, 'OPEN', 'probe') RETURNING event_id",
         (_alert(c, s),)).fetchone()["event_id"]),
     lambda c, f, s: c.execute("UPDATE shadow_entry_alert_event SET note = 'nothing happened' WHERE event_id = %s",
                               (s["event"],))),
    ("BR-41", "Delete a row from the audit log",
     lambda c, f, s: s.update(log=c.execute("INSERT INTO audit_log (action, table_name, row_pk) "
                                            "VALUES ('INSERT', 'probe', '1') RETURNING log_id").fetchone()["log_id"]),
     lambda c, f, s: c.execute("DELETE FROM audit_log WHERE log_id = %s", (s["log"],))),
]


def _probe(conn, setup, attack) -> psycopg.Error | None:
    """Run one attack on a fresh compliant permit; everything is rolled back. Returns the refusal, or None if accepted."""
    with conn.transaction(force_rollback=True):
        f = Factory(conn)
        s = f.gate_scenario(T0)
        setup(conn, f, s)
        try:
            with conn.transaction():
                attack(conn, f, s)
        except psycopg.Error as err:
            return err
    return None


def _outcome(err: psycopg.Error | None) -> dict:
    if err is None:
        return {"refused": False, "sqlstate": None, "message": "accepted"}
    lines = (err.diag.message_primary or str(err)).splitlines()
    message = " ".join(lines[:2]) if lines[0].endswith(":") else lines[0]      # the gate names the failed clause next
    return {"refused": True, "sqlstate": err.sqlstate, "message": message[:140]}


def enforcement(conn: psycopg.Connection) -> list[dict]:
    """Every attack against ZeroEntry, then the same attacks after the rule triggers are disabled in this database."""
    rows = [{"rule": r, "write": w, "zeroentry": _outcome(_probe(conn, setup, attack))} for r, w, setup, attack in ATTACKS]
    conn.execute(BASELINE_SQL.read_text(encoding="utf-8"))
    for row, (_, _, setup, attack) in zip(rows, ATTACKS):
        row["baseline"] = _outcome(_probe(conn, setup, attack))
    return rows


# =====================================================================================================================
# E3 performance and scalability
# =====================================================================================================================
GATE_INDEXES = ["ix_reading_permit_depth", "ix_gear_issue_permit_worker"]
SCAN_INDEXES = ["ix_job_complaint", "ix_deployment_job_outcome", "ix_permit_job", "ix_entry_permit_worker",
                "ix_complaint_resolved"]


def _timed(conn, query, params, reps: int, warmup: int = 6) -> dict:
    """Median and p95 wall time (ms) of `query`, each repetition rolled back so every one does the same work.

    Six warm-up runs: PL/pgSQL plans its statements afresh for the first five calls of a session before it settles on a
    cached plan, so fewer warm-ups would compare whichever variant happened to run first, not the variants themselves."""
    samples = []
    for i in range(warmup + reps):
        with conn.transaction(force_rollback=True):
            start = time.perf_counter()
            conn.execute(query, params).fetchall()
            if i >= warmup:
                samples.append((time.perf_counter() - start) * 1000)
    q = statistics.quantiles(samples, n=20, method="inclusive") if len(samples) > 1 else samples * 19
    return {"median_ms": statistics.median(samples), "p95_ms": q[18]}


def _explain(conn, query: sql.Composable) -> dict:
    """Execution time and shared buffers touched (hit + read): the 'how much data did it process' measure."""
    with conn.transaction(force_rollback=True):
        plan = conn.execute(sql.SQL("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ") + query).fetchone()
    top = next(iter(plan.values()))[0]
    return {"ms": top["Execution Time"],
            "buffers": top["Plan"].get("Shared Hit Blocks", 0) + top["Plan"].get("Shared Read Blocks", 0)}


def _changed(conn, ddl: list[sql.Composable], measure, timeout_s: int) -> dict | None:
    """Run `measure` after `ddl` inside a transaction that is rolled back (DDL is transactional in PostgreSQL)."""
    try:
        with conn.transaction(force_rollback=True):
            for statement in ddl:
                conn.execute(statement)
            conn.execute(sql.SQL("SET LOCAL statement_timeout = {}").format(sql.Literal(f"{timeout_s}s")))
            return measure()
    except psycopg.errors.QueryCanceled:
        return None                                                        # reported as "timed out"


def _drop(indexes: list[str]) -> list[sql.Composable]:
    return [sql.SQL("DROP INDEX {}").format(sql.SQL(", ").join(map(sql.Identifier, indexes)))]


def _before_0011(conn) -> list[sql.Composable]:
    """The detection views as 0007 defined them: the grace CTE inlined, so rule_num() runs once per joined row."""
    ddl = []
    for view in ("v_shadow_se1", "v_shadow_se2"):
        body = conn.execute("SELECT pg_get_viewdef(%s::regclass) AS d", (view,)).fetchone()["d"]
        assert "WITH g AS MATERIALIZED (" in body, f"{view} no longer has the 0011 shape"
        ddl.append(sql.SQL("CREATE OR REPLACE VIEW {} WITH (security_invoker = true) AS ").format(sql.Identifier(view))
                   + sql.SQL(body.replace("WITH g AS MATERIALIZED (", "WITH g AS (", 1)))      # our own catalog text
    return ddl


def performance(conn: psycopg.Connection, sizes: list[int], reps: tuple[int, int] = (30, 8), timeout_s: int = 60,
                log=lambda msg: None) -> list[dict]:
    """Grow the history to each size in turn and measure the entry decision and the absence scan on it."""
    f = Factory(conn)
    s = f.gate_scenario(T0)                                    # the probe: a compliant DRAFT permit, never committed as authorised
    decide = ("SELECT * FROM authorise_entry(%s, %s, %s)", (s["permit"], s["supervisor"], s["at"]))
    check = sql.SQL("SELECT * FROM permit_clause_check({}, {})").format(sql.Literal(s["permit"]), sql.Literal(s["at"]))
    candidates = sql.SQL("SELECT count(*) FROM v_shadow_candidate")
    naive = sql.SQL("SELECT count(*) FROM eval_naive_shadow")
    scan = ("SELECT * FROM scan_shadow_entries(now())", None)
    old_views = _before_0011(conn)
    rows = []
    for size in sizes:
        have = conn.execute("SELECT count(*) AS n FROM complaint WHERE description LIKE 'Synthetic history%'").fetchone()["n"]
        log(f"  E3: growing history to {size:,} complaints ...")
        if size > have:
            conn.execute("SELECT eval_add_history(%s)", (size - have,))
        conn.execute("ANALYZE")
        count = lambda q: conn.execute(q).fetchone()["n"]  # noqa: E731
        row = {
            "complaints": count("SELECT count(*) AS n FROM complaint"),
            "permits": count("SELECT count(*) AS n FROM entry_permit"),
            "gas_readings": count("SELECT count(*) AS n FROM gas_reading"),
            "audit_rows": count("SELECT count(*) AS n FROM audit_log"),
            "naive_flagged": count("SELECT count(DISTINCT complaint_id) AS n FROM eval_naive_shadow"),
            "zeroentry_candidates": count("SELECT count(DISTINCT complaint_id) AS n FROM v_shadow_candidate "
                                          "WHERE evidence_deadline <= now()"),
        }
        log("     timing the entry decision and the scan ...")
        row["decision"] = _timed(conn, *decide, reps[0])
        row["check_plan"] = _explain(conn, check)
        row["decision_no_index"] = _changed(conn, _drop(GATE_INDEXES), lambda: _timed(conn, *decide, reps[0]), timeout_s)
        row["scan"] = _timed(conn, *scan, reps[1])
        row["scan_before_0011"] = _changed(conn, old_views, lambda: _timed(conn, *scan, reps[1]), timeout_s)
        row["detect_plan"] = _explain(conn, candidates)
        row["detect_plan_before_0011"] = _changed(conn, old_views, lambda: _explain(conn, candidates), timeout_s)
        row["detect_plan_no_index"] = _changed(conn, _drop(SCAN_INDEXES), lambda: _explain(conn, candidates), timeout_s)
        row["naive_plan"] = _explain(conn, naive)
        rows.append(row)
    return rows


# =====================================================================================================================
# Report
# =====================================================================================================================
def _pct(x: float) -> str:
    return f"{100 * x:.0f} %"


def _ms(d: dict | None, key: str = "median_ms") -> str:
    return "timed out" if d is None else f"{d[key]:,.1f}"


def _plan(d: dict | None) -> str:
    return "timed out" if d is None else f"{d['ms']:,.1f} / {d['buffers']:,}"


def render(results: dict, meta: dict) -> str:
    e1, e2, e3 = results["e1"], results["e2"], results["e3"]
    z, n = e1["summary"]["ZeroEntry"], e1["summary"]["naive"]
    out = [
        "# Evaluation results (generated)",
        "",
        "**Generated by `python scripts/evaluate.py`; do not edit by hand.** Method, baselines and limits: "
        "[EVALUATION.md](EVALUATION.md). Timings depend on the machine; counts do not.",
        "",
        "| Run | |", "|---|---|",
        *(f"| {k} | {v} |" for k, v in meta.items()),
        "",
        "## E1 Detection accuracy (labelled synthetic complaints)",
        "",
        "ZeroEntry = alerts persisted by `scan_shadow_entries()`; naive = the proposal's anti-join "
        "(`database/evaluation/evaluation.sql`). Both read the same data at the same instant.",
        "",
        "| Method | TP | FP | FN | TN | Precision | Recall | F1 |", "|---|---|---|---|---|---|---|---|",
        *(f"| {name} | {m['tp']} | {m['fp']} | {m['fn']} | {m['tn']} | {_pct(m['precision'])} | {_pct(m['recall'])} | "
          f"{m['f1']:.2f} |" for name, m in (("ZeroEntry", z), ("Naive anti-join", n))),
        "",
        "| Class | Complaint | n | Should alert | ZeroEntry alerted | Naive flagged |", "|---|---|---|---|---|---|",
        *(f"| `{r['class']}` | {r['what']} | {r['n']} | {'yes' if r['expected'] else 'no'} | {r['zeroentry']} | {r['naive']} |"
          for r in e1["classes"]),
        "",
        f"**Late paperwork** ({e1['late']['n']} complaints resolved with no evidence; a CLEARED machine log is recorded "
        f"30 h later, after the first scan): ZeroEntry kept **{e1['late']['zeroentry_kept_for_review']}** for human review "
        f"(`EVIDENCE_RECEIVED`, invoice still held); the naive query silently dropped "
        f"**{e1['late']['naive_silently_cleared']}** from its list.",
        "",
        "## E2 Enforcement (one invalid write per rule, any client)",
        "",
        "Baseline = the same schema and constraints with every rule trigger disabled "
        "(`database/evaluation/rules_in_app_code.sql`): the rules live in application code, so any other client "
        "(a script, a second app, a SQL console, a buggy endpoint) is unconstrained.",
        "",
        "| Rule | Invalid write | ZeroEntry | Baseline (rules in app code) |", "|---|---|---|---|",
        *(f"| {r['rule']} | {r['write']} | "
          + " | ".join(("refused, `{}`: {}".format(o["sqlstate"], o["message"].replace("|", "/")) if o["refused"]
                        else "**accepted**") for o in (r["zeroentry"], r["baseline"])) + " |" for r in e2),
        "",
        f"**Refused: ZeroEntry {sum(r['zeroentry']['refused'] for r in e2)}/{len(e2)}, baseline "
        f"{sum(r['baseline']['refused'] for r in e2)}/{len(e2)}.** SQLSTATE class `ZE` is a ZeroEntry rule (trigger or "
        "function); `23xxx` is a declarative constraint that both designs share.",
        "",
        "## E3 Performance and scalability (history grows)",
        "",
        "Every measurement is rolled back, so each repetition does the same work. Times in ms; buffers = shared blocks "
        "touched, from `EXPLAIN (ANALYZE, BUFFERS)` (the amount of data processed). \"Before 0011\" and \"without "
        "indexes\" are measured on the same data, inside a transaction that is rolled back.",
        "",
        "### E3a The entry decision (`authorise_entry()` on one compliant permit)",
        "",
        "| Complaints | Permits | Gas readings | Decision median | Decision p95 | Without gate indexes (median) "
        "| Clause check buffers |",
        "|---|---|---|---|---|---|---|",
        *(f"| {r['complaints']:,} | {r['permits']:,} | {r['gas_readings']:,} | {_ms(r['decision'])} | "
          f"{_ms(r['decision'], 'p95_ms')} | {_ms(r['decision_no_index'])} | {r['check_plan']['buffers']:,} |" for r in e3),
        "",
        "### E3b Detection by absence (`scan_shadow_entries()` and the candidate query)",
        "",
        "| Complaints | Scan median / p95 | Scan before 0011 (median) | Candidate query ms / buffers | Before 0011 "
        "| Without scan indexes | Naive query ms / buffers | Naive flagged | ZeroEntry candidates |",
        "|---|---|---|---|---|---|---|---|---|",
        *(f"| {r['complaints']:,} | {_ms(r['scan'])} / {_ms(r['scan'], 'p95_ms')} | {_ms(r['scan_before_0011'])} | "
          f"{_plan(r['detect_plan'])} | {_plan(r['detect_plan_before_0011'])} | {_plan(r['detect_plan_no_index'])} | "
          f"{_plan(r['naive_plan'])} | {r['naive_flagged']:,} | {r['zeroentry_candidates']:,} |" for r in e3),
        "",
    ]
    return "\n".join(out)


def _meta(conn, argv: list[str]) -> dict:
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                                check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    return {
        "Date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "Command": "`" + " ".join(["python scripts/evaluate.py", *argv]) + "`",
        "Commit": f"`{commit}` (plus uncommitted changes, if any)",
        "Machine": f"{platform.system()} {platform.release()}, {os.cpu_count()} logical CPUs, {platform.machine()}",
        "Python / PostgreSQL": f"{platform.python_version()} / "
                               f"{conn.execute('SHOW server_version').fetchone()['server_version']} (embedded, default settings)",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sizes", default="1000,10000,100000", help="history volumes (complaints), cumulative")
    parser.add_argument("--per-class", type=int, default=20, help="labelled complaints per E1 class")
    parser.add_argument("--timeout", type=int, default=60, help="seconds before a no-index query is reported as timed out")
    parser.add_argument("--out", default=str(ROOT / "docs" / "EVALUATION_RESULTS.md"), help="report path, or - for stdout")
    args = parser.parse_args()
    sizes = [int(x) for x in args.sizes.split(",")]

    try:
        import pgserver
    except ImportError:
        sys.exit("The embedded PostgreSQL (pgserver) is missing or has no wheel for this Python (3.9-3.12 only). "
                 "See docs/SETUP.md.")
    from alembic import command

    from zeroentry.db import url_for
    sys.path.insert(0, str(Path(__file__).parent))
    from db import alembic_config

    log = lambda msg: print(msg, file=sys.stderr, flush=True)  # noqa: E731
    log("Starting a throwaway embedded PostgreSQL 16 ...")
    server = pgserver.get_server(Path(tempfile.mkdtemp(prefix="ze_eval_")), cleanup_mode="delete")
    try:
        uri = server.get_uri()
        with psycopg.connect(uri, autocommit=True) as admin:
            admin.execute("CREATE DATABASE ze_eval_template")
        command.upgrade(alembic_config(url_for(uri, "ze_eval_template")), "head")

        def fresh(name: str) -> psycopg.Connection:
            with psycopg.connect(uri, autocommit=True) as admin:
                admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE ze_eval_template").format(sql.Identifier(name)))
            return psycopg.connect(make_conninfo(uri, dbname=name), autocommit=True, row_factory=dict_row)

        results = {}
        with fresh("ze_e1") as conn:
            log(f"E1 detection accuracy ({args.per_class} complaints per class) ...")
            prepare(conn)
            results["e1"] = detection_accuracy(conn, args.per_class)
        with fresh("ze_e2") as conn:
            log(f"E2 enforcement ({len(ATTACKS)} invalid writes, twice) ...")
            results["e2"] = enforcement(conn)
        with fresh("ze_e3") as conn:
            log("E3 performance ...")
            prepare(conn)
            results["e3"] = performance(conn, sizes, timeout_s=args.timeout, log=log)
            meta = _meta(conn, sys.argv[1:])
        report = render(results, meta)
    finally:
        server.cleanup()

    if args.out == "-":
        print(report)
    else:
        Path(args.out).write_text(report, encoding="utf-8")
        log(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
