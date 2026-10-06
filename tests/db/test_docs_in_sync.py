"""Documentation about the database cannot silently drift from the database."""

import re
from pathlib import Path

from zeroentry.schema_doc import generate

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
RELATIONSHIP = re.compile(r"^\s*(\w+)\s+[|o}{]{2}--[|o}{]{2}\s+(\w+)\s*:", re.M)


def _tables(conn) -> set[str]:
    return {r["relname"] for r in conn.execute(
        "SELECT relname FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relkind = 'r' AND relname <> 'alembic_version'")}


def _foreign_keys(conn) -> set[tuple[str, str]]:
    """(parent, child) for every foreign key."""
    return {(r["parent"], r["child"]) for r in conn.execute(
        "SELECT confrelid::regclass::text AS parent, conrelid::regclass::text AS child FROM pg_constraint "
        "WHERE contype = 'f' AND connamespace = 'public'::regnamespace")}


def test_schema_reference_matches_the_migrated_database(conn):
    committed = (DOCS / "SCHEMA_REFERENCE.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert generate(conn) == committed, "docs/SCHEMA_REFERENCE.md is out of date: run `python scripts/gen_docs.py` and commit the result"


def test_the_er_diagrams_draw_every_table_and_only_real_foreign_keys(conn):
    text = (DOCS / "ER_DIAGRAM.md").read_text(encoding="utf-8")
    drawn = {tuple(m) for m in RELATIONSHIP.findall(text)}
    fks = _foreign_keys(conn)
    invented = {d for d in drawn if d not in fks}
    assert not invented, f"ER_DIAGRAM.md draws relationships that are not foreign keys (write them parent first): {invented}"
    missing = {fk for fk in fks if fk not in drawn and fk[0] != "app_user"}
    assert not missing, f"foreign keys missing from ER_DIAGRAM.md: {missing}"
    named = set(re.findall(r"^\s*(\w+)\s+\{", text, re.M)) | {t for d in drawn for t in d}
    assert _tables(conn) <= named, f"tables missing from ER_DIAGRAM.md: {_tables(conn) - named}"


def test_database_design_mentions_every_table(conn):
    text = (DOCS / "DATABASE_DESIGN.md").read_text(encoding="utf-8")
    missing = {t for t in _tables(conn) if f"`{t}`" not in text}
    assert not missing, f"tables not described in DATABASE_DESIGN.md: {missing}"
