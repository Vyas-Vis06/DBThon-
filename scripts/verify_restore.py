"""Demonstrate logical backup/restore in a private disposable PostgreSQL cluster.

No connection argument is accepted: this command cannot target a teammate database.
It compares every application table's rows and sequence state after pg_dump/pg_restore.
This is logical restore evidence, not a crash-recovery/WAL algorithm demonstration.
"""

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pgserver
import psycopg
from alembic import command
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from zeroentry.db import url_for
from zeroentry.evidence import ROOT, source_fingerprint

sys.path.insert(0, str(ROOT))
from tests.factories import Factory, yesterday_ist


def snapshot(conn):
    tables = [row["tablename"] for row in conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename<>'alembic_version' ORDER BY tablename")]
    results = {}
    for table in tables:
        row = conn.execute(sql.SQL("SELECT count(*) AS n, md5(COALESCE(string_agg(row_to_json(t)::text,'' "
                                  "ORDER BY row_to_json(t)::text),'')) AS checksum FROM {} t").format(
                                      sql.Identifier(table))).fetchone()
        results[table] = dict(row)
    sequences = [dict(row) for row in conn.execute(
        "SELECT sequencename,last_value FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename")]
    foreign_keys = conn.execute("SELECT count(*) AS n FROM pg_constraint WHERE contype='f' "
                                "AND connamespace='public'::regnamespace").fetchone()["n"]
    gaps = [dict(row) for row in conn.execute("SELECT claim_id,gap_code FROM v_completion_claim_gaps ORDER BY claim_id")]
    return {"tables": results, "sequences": sequences, "foreign_keys": foreign_keys, "claim_gaps": gaps}


def verify():
    extension = ".exe" if sys.platform == "win32" else ""
    binaries = Path(pgserver.__file__).resolve().parent / "pginstall/bin"
    dump, restore = binaries / ("pg_dump" + extension), binaries / ("pg_restore" + extension)
    if not dump.is_file() or not restore.is_file():
        raise RuntimeError("Embedded pg_dump/pg_restore unavailable; install the development PostgreSQL runtime")
    sys.path.insert(0, str(ROOT / "scripts"))
    from db import alembic_config
    with tempfile.TemporaryDirectory(prefix="ze_restore_") as directory:
        server = pgserver.get_server(Path(directory) / "cluster", cleanup_mode="delete")
        try:
            uri = server.get_uri()
            with psycopg.connect(uri, autocommit=True) as admin:
                admin.execute("CREATE DATABASE ze_restore_source")
                admin.execute("CREATE DATABASE ze_restore_target")
            command.upgrade(alembic_config(url_for(uri, "ze_restore_source")), "head")
            source_dsn = make_conninfo(uri, dbname="ze_restore_source")
            target_dsn = make_conninfo(uri, dbname="ze_restore_target")
            with psycopg.connect(source_dsn, autocommit=True, row_factory=dict_row) as conn:
                factory = Factory(conn)
                scenario = factory.gate_scenario(yesterday_ist())
                conn.execute("SELECT * FROM authorise_entry(%s,%s,%s)",
                             (scenario["permit"], scenario["supervisor"], scenario["at"])).fetchall()
                receipt = conn.execute("SELECT receipt_id FROM permit_decision_receipt WHERE permit_id=%s "
                                       "AND decision='AUTHORISED' ORDER BY receipt_id DESC LIMIT 1",
                                       (scenario["permit"],)).fetchone()
                if receipt is None:
                    raise AssertionError("Restore fixture did not produce a real educational authorization receipt")
                conn.execute("INSERT INTO entry_log(permit_id,worker_id,period,receipt_id,recorded_by) "
                             "VALUES(%s,%s,tstzrange(%s,%s,'[)'),%s,%s)",
                             (scenario["permit"], scenario["e1"], scenario["at"] + timedelta(minutes=1),
                              scenario["at"] + timedelta(minutes=11), receipt["receipt_id"], scenario["supervisor"]))
                factory.invoice(scenario["job"])
                denied = factory.gate_scenario(yesterday_ist())
                conn.execute("DELETE FROM gear_issue WHERE permit_id=%s AND worker_id=%s",
                             (denied["permit"], denied["e1"]))
                conn.execute("SELECT * FROM authorise_entry(%s,%s,%s)",
                             (denied["permit"], denied["supervisor"], denied["at"])).fetchall()
                conn.execute("INSERT INTO completion_claim(source_ulb_id,source,external_id,external_job_ref,"
                             "matched_job_id,claimed_status,claimed_at,match_status,payload) "
                             "VALUES(%s,'EDU_RESTORE','restore-1','explicit-owner-fixture',%s,'COMPLETED',now(),'MATCHED',"
                             "'{\"fixture\":\"synthetic explicit linkage\"}'::jsonb)",
                             (scenario["ulb"], scenario["job"]))
                actor = factory.user("ADMIN")
                with conn.transaction():
                    conn.execute("SELECT set_config('app.role','ADMIN',true),set_config('app.user_id',%s,true)", (str(actor),))
                    payload = {"ulb_id": scenario["ulb"], "occurred_at": datetime.now(timezone.utc).isoformat(),
                               "site_label": "Synthetic unregistered shaft", "hazard_type": "REPORTED_HAZARD",
                               "description": "Two synthetic victims; pending assessment only.",
                               "victims": [{"victim_key": "a", "display_alias": "Person A", "outcome": "FATAL"},
                                           {"victim_key": "b", "display_alias": "Person B", "outcome": "INJURY"}]}
                    conn.execute("SELECT record_incident_report(%s::jsonb)", (json.dumps(payload),))
                    payload.update(job_id=scenario["job"], permit_id=scenario["permit"],
                                   site_label="Synthetic linked educational work")
                    conn.execute("SELECT record_incident_report(%s::jsonb)", (json.dumps(payload),))
                before = snapshot(conn)
                version = conn.execute("SHOW server_version").fetchone()["server_version"]
            archive = Path(directory) / "private.dump"
            subprocess.run([str(dump), "--no-password", "--dbname", source_dsn, "--format=custom", "--file", str(archive)],
                           check=True, capture_output=True, text=True)
            subprocess.run([str(restore), "--no-password", "--dbname", target_dsn, "--no-owner", "--exit-on-error", str(archive)],
                           check=True, capture_output=True, text=True)
            with psycopg.connect(target_dsn, autocommit=True, row_factory=dict_row) as conn:
                after = snapshot(conn)
            if before != after:
                raise AssertionError("Logical restore differs in table rows, sequences, FKs or reference claim gaps")
            return {"recorded_at": datetime.now(timezone.utc).isoformat(), "source_sha256": source_fingerprint(),
                    "postgresql": version, "machine": platform.platform(), "outcome": "MATCHED",
                    "table_count": len(before["tables"]), "foreign_keys": before["foreign_keys"],
                    "rows": {name: result["n"] for name, result in before["tables"].items()},
                    "snapshot_sha256": hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
                    "limits": "Synthetic logical pg_dump/pg_restore in one private cluster; not crash recovery or production backup certification."}
        finally:
            server.cleanup()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="-")
    args = parser.parse_args()
    report = json.dumps(verify(), indent=2) + "\n"
    if args.out == "-":
        print(report, end="")
    else:
        destination = Path(args.out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
