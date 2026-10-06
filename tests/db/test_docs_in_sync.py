"""Documentation generated from the database cannot silently drift from it."""

from pathlib import Path

from zeroentry.schema_doc import generate

ROOT = Path(__file__).resolve().parents[2]


def test_schema_reference_matches_the_migrated_database(conn):
    committed = (ROOT / "docs" / "SCHEMA_REFERENCE.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert generate(conn) == committed, "docs/SCHEMA_REFERENCE.md is out of date: run `python scripts/gen_docs.py` and commit the result"
