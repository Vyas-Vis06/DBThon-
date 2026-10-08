"""E5: same-predicate application preview/write versus database revalidation.

Run only in the automatically created disposable cluster. No timing or field-safety claim.
The minimal application-only comparator checks the SAME configured SQL predicate, then
writes without rechecking; an injected evidence change models the read/write interleaving.
This does not compare against an application that also locks/rechecks correctly.
"""

import argparse
import hashlib
import json
import platform
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tests.factories import Factory, yesterday_ist


def _preview(conn, scenario):
    rows = conn.execute("SELECT * FROM permit_clause_check(%s,%s)",
                        (scenario["permit"], scenario["at"])).fetchall()
    return bool(rows) and all(row["passed"] is True for row in rows)


def compare(conn):
    outcomes = {}
    # Each trial is rolled back, including the narrowly disabled comparator triggers.
    # Real constraints/FKs and all other tables' guards remain enabled.
    for design in ("application_preview_write", "database_revalidation"):
        with conn.transaction(force_rollback=True):
            scenario = Factory(conn).gate_scenario(yesterday_ist())
            passing = _preview(conn, scenario)
            if not passing:
                raise AssertionError("The shared ordinary passing fixture does not pass every configured predicate")
            conn.execute("DELETE FROM gear_issue WHERE permit_id=%s AND worker_id=%s",
                         (scenario["permit"], scenario["e1"]))
            fresh = _preview(conn, scenario)
            if fresh:
                raise AssertionError("The changed fixture must fail the shared gear predicate")
            if design == "application_preview_write":
                # Implement the minimal application-side check-before-write behavior, not a
                # supposed industrial product. Owner-only ablation is confined to this trial.
                conn.execute("ALTER TABLE entry_permit DISABLE TRIGGER USER")
                if passing:
                    conn.execute("UPDATE entry_permit SET status='AUTHORISED',authorised_at=%s,authorised_by=%s, "
                                 "valid_until=%s+make_interval(mins=>rule_num('permit_valid_minutes')::int) "
                                 "WHERE permit_id=%s", (scenario["at"], scenario["supervisor"],
                                                         scenario["at"], scenario["permit"]))
                conn.execute("ALTER TABLE entry_permit ENABLE TRIGGER USER")
            else:
                conn.execute("SELECT * FROM authorise_entry(%s,%s,%s)",
                             (scenario["permit"], scenario["supervisor"], scenario["at"])).fetchall()
            status = conn.execute("SELECT status FROM entry_permit WHERE permit_id=%s",
                                  (scenario["permit"],)).fetchone()["status"]
            outcomes[design] = {"ordinary_pass": passing, "ordinary_deny": not fresh,
                                "after_interleaving_status": status,
                                "stale_authorization_accepted_in_trial": status == "AUTHORISED"}
    return outcomes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="-", help="JSON report path, or stdout")
    args = parser.parse_args()
    import pgserver
    from alembic import command
    from zeroentry.db import url_for
    sys.path.insert(0, str(ROOT / "scripts"))
    from db import alembic_config
    with tempfile.TemporaryDirectory(prefix="ze_preview_") as directory:
        server = pgserver.get_server(Path(directory) / "cluster", cleanup_mode="delete")
        try:
            uri = server.get_uri()
            with psycopg.connect(uri, autocommit=True) as admin:
                admin.execute("CREATE DATABASE ze_preview")
            command.upgrade(alembic_config(url_for(uri, "ze_preview")), "head")
            with psycopg.connect(make_conninfo(uri, dbname="ze_preview"), autocommit=True,
                                 row_factory=dict_row) as conn:
                result = compare(conn)
                version = conn.execute("SHOW server_version").fetchone()["server_version"]
        finally:
            server.cleanup()
    fingerprint = hashlib.sha256()
    for path in sorted((ROOT / "database/migrations/sql").glob("*.sql")):
        fingerprint.update(path.name.encode())
        fingerprint.update(path.read_bytes())
    report = {"experiment": "E5 controlled application-preview/write interleaving",
              "recorded_at": datetime.now(timezone.utc).isoformat(), "machine": platform.platform(),
              "python": platform.python_version(), "postgresql": version,
              "migration_sha256": fingerprint.hexdigest(), "results": result,
              "limits": "Synthetic single interleaving; identical predicate; no performance, production-product "
                        "or physical-safety claim. Correct application locking/revalidation can also close this race."}
    rendered = json.dumps(report, indent=2) + "\n"
    if args.out == "-":
        print(rendered, end="")
    else:
        destination = Path(args.out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
