"""docs/API_SPEC.md's endpoint table is generated from the routes and their role guards; it must not drift."""

from pathlib import Path

from zeroentry.api_doc import BEGIN, END, endpoint_table
from zeroentry.config import Settings
from zeroentry.main import create_app

ROOT = Path(__file__).resolve().parents[2]
APP = create_app(Settings(database_url="postgresql+psycopg://unused@localhost/unused"))   # never connects


def test_the_endpoint_table_matches_the_code():
    doc = (ROOT / "docs" / "API_SPEC.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    committed = BEGIN + doc.split(BEGIN, 1)[1].split(END, 1)[0] + END
    assert committed == endpoint_table(APP), "docs/API_SPEC.md is out of date: run `python scripts/gen_docs.py` and commit the result"


def test_the_table_lists_exactly_the_operations_in_the_openapi_schema():
    table = endpoint_table(APP)
    operations = {(m.upper(), p) for p, ops in APP.openapi()["paths"].items() for m in ops}
    listed = {(line.split("`")[1], line.split("`")[3]) for line in table.splitlines() if line.startswith("| `")}
    assert listed == operations


def test_every_api_endpoint_names_its_roles():
    """No route under /api/v1 may be reachable without a declared guard, except login."""
    unguarded = [line for line in endpoint_table(APP).splitlines() if "| public |" in line]
    assert [line.split("`")[3] for line in unguarded] == ["/api/v1/auth/login", "/health"]
