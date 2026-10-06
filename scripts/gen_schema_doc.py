"""Regenerate docs/SCHEMA_REFERENCE.md from a freshly migrated, throwaway embedded PostgreSQL.

    python scripts/gen_schema_doc.py

Run it after any change under database/migrations/. The test suite fails if the committed file is out of date.
"""

import tempfile
from pathlib import Path

import pgserver
import psycopg
from alembic import command

from zeroentry.schema_doc import generate

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    from db import alembic_config  # noqa: PLC0415 - sibling script
    with tempfile.TemporaryDirectory(prefix="ze_schema_doc_") as tmp:
        server = pgserver.get_server(Path(tmp) / "cluster", cleanup_mode="delete")
        try:
            info = psycopg.conninfo.conninfo_to_dict(server.get_uri())
            with psycopg.connect(server.get_uri(), autocommit=True) as admin:
                admin.execute("CREATE DATABASE schema_doc")
            url = f"postgresql+psycopg://postgres@{info['host']}:{info['port']}/schema_doc"
            command.upgrade(alembic_config(url), "head")
            with psycopg.connect(url.replace("+psycopg", "")) as conn:
                text = generate(conn)
        finally:
            server.cleanup()
    target = ROOT / "docs" / "SCHEMA_REFERENCE.md"
    target.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {target.relative_to(ROOT)} ({text.count(chr(10))} lines)")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    main()
