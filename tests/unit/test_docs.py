"""The documentation hangs together: links resolve, and every rule ID the code cites is defined in PROJECT_SPEC."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = sorted([*ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md")])
LINK = re.compile(r"\]\(([^)\s]+)\)")
CODE = [p for d in ("src", "database", "tests", "scripts") for p in (ROOT / d).rglob("*")
        if p.suffix in (".py", ".sql", ".js") and "__pycache__" not in p.parts]


def test_every_relative_link_in_the_docs_resolves():
    broken = []
    for doc in DOCS:
        for target in LINK.findall(doc.read_text(encoding="utf-8")):
            path = target.split("#", 1)[0]
            if path and not re.match(r"^[a-z]+:", path) and not (doc.parent / path).exists():
                broken.append(f"{doc.relative_to(ROOT)} -> {target}")
    assert not broken, "broken links:\n" + "\n".join(broken)


def test_every_rule_and_assumption_cited_in_code_is_defined_in_the_spec():
    spec = (ROOT / "PROJECT_SPEC.md").read_text(encoding="utf-8")
    defined = set(re.findall(r"^\| ((?:BR|A)-\d{2}) \|", spec, re.M))
    cited = {m for p in CODE for m in re.findall(r"\b(?:BR|A)-\d{2}\b", p.read_text(encoding="utf-8"))}
    assert cited - defined == set(), f"cited but not defined in PROJECT_SPEC.md: {sorted(cited - defined)}"
