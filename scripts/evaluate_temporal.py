"""Reproducible synthetic accuracy/scale evaluation. Never connects to an existing database.

    python scripts/evaluate_temporal.py --sizes 1000 10000 100000 --repeats 7

Creates its own embedded PostgreSQL, applies real migrations, imports labeled historical
fixtures, measures as ze_app/ENGINEER, writes raw results/plans and cleans up the cluster.
Historical receipts are fixture data: only the owner temporarily disables the outcome
timestamp trigger during import. Live late finalization uses the real server-assigned guard.
The simple baseline ignores grace, resolution exemptions and final-outcome receipt time.
Synthetic accuracy is not field accuracy; speed comparisons change query semantics.
"""

import argparse
import hashlib
import json
import math
import platform
import statistics
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import pgserver
import psycopg
from alembic import command
from alembic.config import Config
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.factories import Factory  # noqa: E402 - deterministic synthetic fixtures shared with tests
from zeroentry.db import url_for  # noqa: E402
from zeroentry.evidence import source_fingerprint  # noqa: E402

BASELINE = """
SELECT c.complaint_id FROM complaint c
WHERE c.status = 'RESOLVED'
AND NOT EXISTS (SELECT 1 FROM job j JOIN machine_deployment d ON d.job_id = j.job_id
                WHERE j.complaint_id = c.complaint_id AND d.outcome = 'CLEARED')
AND NOT EXISTS (SELECT 1 FROM job j JOIN entry_permit p ON p.job_id = j.job_id
                JOIN entry_log e ON e.permit_id = p.permit_id
                WHERE j.complaint_id = c.complaint_id AND p.status = 'CLOSED')
"""
ADVANCED = """
SELECT DISTINCT complaint_id FROM v_shadow_candidate
WHERE rule_code = 'SE1_NO_CLEARANCE_EVIDENCE' AND evidence_deadline <= now()
"""
LABELS = {0: "timely_machine", 1: "missing_evidence", 2: "exempt_resolution", 3: "late_machine",
          4: "unfinished_then_finalized_late", 5: "inside_grace"}


def fixture(conn, size):
    f = Factory(conn)
    ulb = f.ulb(name=f"Synthetic scale {size}")
    mh, contractor, engineer = f.manhole(ulb), f.contractor(), f.user("ENGINEER", ulb_id=ulb)
    machine = f.machine(ulb)
    with conn.transaction():
        conn.execute("""INSERT INTO complaint (manhole_id, description, status, raised_at, resolved_at, resolution_code)
            SELECT %s, 'Synthetic case ' || n, 'RESOLVED', now() - interval '4 days',
                   CASE WHEN n %% 6 = 5 THEN now() ELSE now() - interval '3 days' END,
                   CASE WHEN n %% 6 = 2 THEN 'NO_BLOCKAGE_FOUND' ELSE 'CLEARED' END
            FROM generate_series(1, %s) AS n""", (mh, size))
        conn.execute("CREATE TEMP TABLE benchmark_labels (complaint_id bigint PRIMARY KEY, category integer, expected boolean)")
        conn.execute("""INSERT INTO benchmark_labels
            SELECT complaint_id, substring(description FROM 'Synthetic case ([0-9]+)')::integer % 6,
                   substring(description FROM 'Synthetic case ([0-9]+)')::integer % 6 IN (1,3,4) FROM complaint""")
        conn.execute("INSERT INTO job (complaint_id, contractor_id) SELECT complaint_id, %s FROM complaint", (contractor,))
        # Trusted historical synthetic import, not an application permission or timestamp override.
        conn.execute("ALTER TABLE machine_deployment DISABLE TRIGGER trg_machine_deployment_outcome_guard")
        conn.execute("""INSERT INTO machine_deployment
            (job_id, machine_id, started_at, ended_at, outcome, recorded_at, outcome_recorded_at)
            SELECT j.job_id, %s, now() - interval '4 days', now() - interval '3 days', 'CLEARED',
                   CASE WHEN b.category = 0 THEN now() - interval '3 days' ELSE now() END,
                   CASE WHEN b.category = 0 THEN now() - interval '3 days' ELSE now() END
            FROM job j JOIN benchmark_labels b USING (complaint_id) WHERE b.category IN (0,3)""", (machine,))
        conn.execute("ALTER TABLE machine_deployment ENABLE TRIGGER trg_machine_deployment_outcome_guard")
        conn.execute("""INSERT INTO machine_deployment (job_id, machine_id, started_at, recorded_at)
            SELECT j.job_id, %s, now() - interval '4 days', now() - interval '3 days'
            FROM job j JOIN benchmark_labels b USING (complaint_id) WHERE b.category = 4""", (machine,))
        # This is the audited counterexample: old insertion, normal finalization received now.
        conn.execute("""UPDATE machine_deployment SET outcome='CLEARED', ended_at=now() - interval '3 days'
            WHERE outcome IS NULL""")
    conn.execute("ANALYZE")
    labels = conn.execute("SELECT * FROM benchmark_labels ORDER BY complaint_id").fetchall()
    return engineer, ulb, labels


def confusion(labels, predicted):
    counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    categories = {}
    for row in labels:
        positive = row["complaint_id"] in predicted
        counts["tp" if row["expected"] and positive else "fn" if row["expected"] else "fp" if positive else "tn"] += 1
        label = LABELS[row["category"]]
        group = categories.setdefault(label, {"total": 0, "predicted": 0, "expected": row["expected"]})
        group["total"] += 1
        group["predicted"] += int(positive)
    counts["precision"] = counts["tp"] / (counts["tp"] + counts["fp"]) if counts["tp"] + counts["fp"] else None
    counts["recall"] = counts["tp"] / (counts["tp"] + counts["fn"]) if counts["tp"] + counts["fn"] else None
    return {**counts, "by_category": categories}


def measure(conn, query, repeats):
    conn.execute(query).fetchall()  # one documented warm-up; no cache-flushing claims
    durations, predicted = [], set()
    for _ in range(repeats):
        start = perf_counter()
        rows = conn.execute(query).fetchall()
        durations.append((perf_counter() - start) * 1000)
        predicted = {r["complaint_id"] for r in rows}
    plan = conn.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query).fetchone()["QUERY PLAN"]
    return {"samples_ms": durations, "p50_ms": statistics.median(durations),
            "p95_ms": sorted(durations)[max(0, math.ceil(.95 * len(durations)) - 1)],
            "rows": len(predicted), "plan": plan}, predicted


def run_size(server, size, repeats):
    name = f"ze_benchmark_{size}"
    with psycopg.connect(server.get_uri(), autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}" TEMPLATE ze_eval_template')
    with psycopg.connect(make_conninfo(server.get_uri(), dbname=name), autocommit=True, row_factory=dict_row) as owner:
        start = perf_counter()
        engineer, ulb, labels = fixture(owner, size)
        load_ms = (perf_counter() - start) * 1000
    with psycopg.connect(make_conninfo(server.get_uri(), dbname=name, user="ze_app", password="synthetic_eval_only"),
                        autocommit=True, row_factory=dict_row) as conn:
        conn.execute("SELECT set_config('app.role', 'ENGINEER', false), set_config('app.user_id', %s, false), "
                     "set_config('app.ulb_id', %s, false)", (str(engineer), str(ulb)))
        results = {}
        for key, query in (("untimed_baseline", BASELINE), ("zeroentry_se1", ADVANCED)):
            timing, predicted = measure(conn, query, repeats)
            results[key] = {**timing, "accuracy": confusion(labels, predicted)}
        a = results["zeroentry_se1"]["accuracy"]
        assert a["fp"] == a["fn"] == 0, a
        start = perf_counter()
        first = dict(conn.execute("SELECT * FROM scan_shadow_entries(now())").fetchone())
        first_ms = (perf_counter() - start) * 1000
        start = perf_counter()
        again = dict(conn.execute("SELECT * FROM scan_shadow_entries(now())").fetchone())
        again_ms = (perf_counter() - start) * 1000
        assert first["opened"] == a["tp"] and again["opened"] == 0, (first, again, a)
        results["persistent_scan"] = {"first_ms": first_ms, "first_result": first,
                                     "repeat_ms": again_ms, "repeat_result": again}
    # Owner inventory counts physical rows; ENGINEER's RLS intentionally hides the audit_log.
    with psycopg.connect(make_conninfo(server.get_uri(), dbname=name), row_factory=dict_row) as owner:
        counts = {table: owner.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]
                  for table in ("complaint", "job", "machine_deployment", "shadow_entry_alert", "audit_log")}
    return {"size": size, "load_ms": load_ms, "row_counts": counts, **results}


def markdown(report):
    lines = ["# Synthetic evidence evaluation", "", f"Measured {report['measured_at']} on {report['platform']}; "
             f"Python {report['python']}, PostgreSQL {report['postgres']}, commit {report['commit']} "
             f"(dirty={report['dirty']}, schema={report['schema_revision']}). Source fingerprint: "
             f"`{report['source_fingerprint']}`.", "", "All data is synthetic. Six evenly interleaved categories: timely, missing, exempt, late, "
             "unfinished-finalized-late and pending. Metrics classify evidence gaps, not physical human entries. "
             "The baseline lacks temporal/applicability semantics; timing differences do not prove equal-task speedup. "
             "Warm-cache local single-client measurements; no network or field workload.", "",
             "| Complaints | Baseline precision / recall | SE1 precision / recall | Baseline p50 / p95 ms | SE1 p50 / p95 ms | First / repeat scan ms |",
             "|---:|---:|---:|---:|---:|---:|"]
    for row in report["results"]:
        b, z, s = row["untimed_baseline"], row["zeroentry_se1"], row["persistent_scan"]
        def acc(x): return f"{x['accuracy']['precision']:.1%} / {x['accuracy']['recall']:.1%}"
        lines.append(f"| {row['size']:,} | {acc(b)} | {acc(z)} | {b['p50_ms']:.2f} / {b['p95_ms']:.2f} | "
                     f"{z['p50_ms']:.2f} / {z['p95_ms']:.2f} | {s['first_ms']:.2f} / {s['repeat_ms']:.2f} |")
    lines += ["", "Raw confusion matrices, per-category results, each sample, row counts and EXPLAIN plans "
              "are in results.json. Reproduce from a Python 3.11/3.12 source checkout:", "",
              "```sh", report["command"], "```", "",
              "SE2 division, concurrency and authorization correctness are covered separately by the real-PG regression suite. "
              "This experiment evaluates SE1 only; it does not benchmark an incremental cache or authenticated instruments.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=[1000, 10000, 100000])
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "evaluation")
    args = parser.parse_args()
    if any(n < 6 or n > 1000000 for n in args.sizes) or args.repeats < 2:
        parser.error("sizes must be 6..1000000 and repeats >=2")
    report = {"measured_at": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
              "python": platform.python_version(), "commit": subprocess.check_output(
                  ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "repeats": args.repeats, "queries": {"untimed_baseline": BASELINE, "zeroentry_se1": ADVANCED}, "results": []}
    report["dirty"] = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())
    report["source_fingerprint"] = source_fingerprint()
    report["schema_revision"] = sorted((ROOT / "database/migrations/versions").glob("[0-9]*.py"))[-1].stem.split("_", 1)[0]
    report["command"] = "python scripts/evaluate_temporal.py --sizes " + " ".join(map(str, args.sizes)) + f" --repeats {args.repeats}"
    report["source_sha256"] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in [Path(__file__).resolve(), *sorted((ROOT / "database/migrations/sql").glob("*.sql"))]}
    with tempfile.TemporaryDirectory(prefix="ze_evaluation_") as tmp:
        server = pgserver.get_server(Path(tmp) / "cluster", cleanup_mode="delete")
        try:
            with psycopg.connect(server.get_uri(), autocommit=True) as admin:
                admin.execute("CREATE DATABASE ze_eval_template")
                report["postgres"] = admin.execute("SHOW server_version").fetchone()[0]
            cfg = Config(str(ROOT / "alembic.ini"))
            cfg.set_main_option("script_location", str(ROOT / "database" / "migrations"))
            cfg.set_main_option("sqlalchemy.url", url_for(server.get_uri(), "ze_eval_template").replace("%", "%%"))
            command.upgrade(cfg, "head")
            with psycopg.connect(server.get_uri(), autocommit=True) as admin:
                admin.execute("ALTER ROLE ze_app LOGIN PASSWORD 'synthetic_eval_only'")
            for size in args.sizes:
                print(f"Measuring {size:,} complaints...", flush=True)
                report["results"].append(run_size(server, size, args.repeats))
        finally:
            server.cleanup()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "results.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    (args.output / "RESULTS.md").write_text(markdown(report))
    print(f"Wrote {args.output / 'RESULTS.md'} and raw results.json")


if __name__ == "__main__":
    main()
