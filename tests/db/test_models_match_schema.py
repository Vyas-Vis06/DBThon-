"""The ORM models are a mapping, not a schema: fail loudly if they drift from the migrated database."""

from sqlalchemy import create_engine, inspect

from zeroentry.models import Base


def test_models_match_the_migrated_schema(db):
    engine = create_engine(db.owner_url)
    insp = inspect(engine)
    db_tables = set(insp.get_table_names()) - {"alembic_version"}
    assert db_tables == set(Base.metadata.tables), "a table exists without a model (or the reverse)"

    problems: list[str] = []
    for name, table in Base.metadata.tables.items():
        cols = {c["name"]: c for c in insp.get_columns(name)}
        if set(cols) != set(table.columns.keys()):
            problems.append(f"{name}: columns differ: db-only={set(cols) - set(table.columns.keys())} "
                            f"model-only={set(table.columns.keys()) - set(cols)}")
            continue
        for col in table.columns:
            if cols[col.name]["nullable"] != col.nullable and not col.primary_key:
                problems.append(f"{name}.{col.name}: nullable db={cols[col.name]['nullable']} model={col.nullable}")
        pk_db = set(insp.get_pk_constraint(name)["constrained_columns"])
        pk_model = {c.name for c in table.primary_key.columns}
        if pk_db != pk_model:
            problems.append(f"{name}: primary key db={pk_db} model={pk_model}")
        fk_db = {(tuple(f["constrained_columns"]), f["referred_table"]) for f in insp.get_foreign_keys(name)}
        fk_model = {(tuple(c.name for c in fk.columns), fk.referred_table.name) for fk in table.foreign_key_constraints}
        # composite FKs are declared once as a constraint in the model; single-column ones per column
        if fk_db != fk_model:
            problems.append(f"{name}: foreign keys db-only={fk_db - fk_model} model-only={fk_model - fk_db}")
    engine.dispose()
    assert not problems, "\n".join(problems)
