"""Regenerate the documentation that is derived from code:

* docs/SCHEMA_REFERENCE.md: from a freshly migrated, throwaway embedded PostgreSQL's catalogue;
* the endpoint table in docs/API_SPEC.md: from the application's routes and role guards.

    python scripts/gen_docs.py

Run it after changing database/migrations/ or any router. The test suite fails if either file is out of date.
"""

import sys
import tempfile
from pathlib import Path

import pgserver
import psycopg
from alembic import command
from psycopg.conninfo import make_conninfo

from zeroentry.api_doc import endpoint_table, splice
from zeroentry.config import Settings
from zeroentry.db import url_for
from zeroentry.main import create_app
from zeroentry.schema_doc import generate

ROOT = Path(__file__).resolve().parents[1]


def schema_reference() -> str:
    from db import alembic_config  # noqa: PLC0415 - sibling script
    with tempfile.TemporaryDirectory(prefix="ze_schema_doc_") as tmp:
        server = pgserver.get_server(Path(tmp) / "cluster", cleanup_mode="delete")
        try:
            with psycopg.connect(server.get_uri(), autocommit=True) as admin:
                admin.execute("CREATE DATABASE schema_doc")
            command.upgrade(alembic_config(url_for(server.get_uri(), "schema_doc")), "head")
            with psycopg.connect(make_conninfo(server.get_uri(), dbname="schema_doc")) as conn:
                return generate(conn)
        finally:
            server.cleanup()


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {path.relative_to(ROOT)} ({text.count(chr(10))} lines)")


def main() -> None:
    write(ROOT / "docs" / "SCHEMA_REFERENCE.md", schema_reference())
    api_spec = ROOT / "docs" / "API_SPEC.md"
    app = create_app(Settings(database_url="postgresql+psycopg://unused@localhost/unused"))   # never connects
    write(api_spec, splice(api_spec.read_text(encoding="utf-8"), endpoint_table(app)))


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    main()
