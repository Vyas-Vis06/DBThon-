# ZeroEntry diagrams

These files are the standalone Mermaid sources for the current ZeroEntry build.

| Diagram | What it shows | Read alongside |
|---|---|---|
| [zeroentry-overview.mmd](zeroentry-overview.mmd) · [SVG](zeroentry-overview.svg) | A compact browser → authenticated API → database view for the pitch | [PITCH_SCRIPT.md](../PITCH_SCRIPT.md), [PITCH_CUE_CARD.md](../PITCH_CUE_CARD.md) |
| [zeroentry-er.mmd](zeroentry-er.mmd) | All 35 application tables, key columns and declared non-actor foreign-key relationships | [ER_DIAGRAM.md](../ER_DIAGRAM.md), generated [SCHEMA_REFERENCE.md](../SCHEMA_REFERENCE.md), [DATABASE_DESIGN.md](../DATABASE_DESIGN.md) |
| [zeroentry-architecture.mmd](zeroentry-architecture.mmd) | Local launch, request handling, PostgreSQL responsibilities, maintenance, real-server setup and isolated showcase/test modes | [ARCHITECTURE.md](../ARCHITECTURE.md), [guide/README.md](../guide/README.md) |

The `.mmd` files are raw Mermaid source. To render one, open it in a Mermaid-aware editor or copy its contents into the
[Mermaid Live Editor](https://mermaid.live). Mermaid code blocks inside the linked Markdown documents render directly on
GitHub. The full ER graph is intentionally kept as a separate source because all 35 tables make one dense picture; the
domain diagrams in [ER_DIAGRAM.md](../ER_DIAGRAM.md) are easier to read on the page.

## Ready-to-use exports

The sources were rendered with Mermaid 11.14.0 in headless Chrome. The scalable SVG files can be opened directly or
inserted into presentation software. Use the domain view for a spoken explanation; the full graph is a reference.

| Export | Purpose |
|---|---|
| [Architecture overview](zeroentry-overview.svg) | The compact pitch diagram |
| [Full runtime architecture](zeroentry-architecture.svg) | Launch, maintenance, application and database paths |
| [Full ER model](zeroentry-er.svg) | All 35 application tables and the drawn FK relationships |
| [Policy and provenance](er-policy-provenance.svg) | Sources, revisions, saved decisions and safety history |
| [Identity and access](er-identity.svg) | Accounts, roles, sessions and scoped identities |
| [Complaints and work](er-work.svg) | Municipal assets, jobs, machine deployments and waivers |
| [Entry gate](er-entry-gate.svg) | Crew membership, gear, gas and entry intervals |
| [Review and money](er-review-money.svg) | Alerts, incident cases, invoices and source-specific holds |

The five domain exports are rendered from the corresponding code blocks in [ER_DIAGRAM.md](../ER_DIAGRAM.md).
When changing a source or domain block, refresh its SVG export too; the source remains authoritative.

The ER graph leaves out action/audit foreign keys whose target is `app_user`, such as `recorded_by` and `reviewed_by`, to
reduce line crossings. It includes account scope and session ownership. All shown relationships are declared foreign keys;
it does not infer links from trigger behavior or shared column names. Attribute blocks list keys and selected fields, not every
column. Use `SCHEMA_REFERENCE.md` for the complete catalogue, including nullability, checks, indexes, triggers and RLS.
The Mermaid entity blocks show keys and selected domain fields; type labels use PostgreSQL type families, so precision such as
`numeric(12,2)` is abbreviated to `numeric`. The generated schema reference has the exact types and all columns.

The diagram drift guard is [`tests/db/test_docs_in_sync.py`](../../tests/db/test_docs_in_sync.py). It compares the domain ER
diagrams with the migrated PostgreSQL catalogue and checks that every application table is named and every non-actor foreign
key relationship is represented.
