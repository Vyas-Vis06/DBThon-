-- rules_in_app_code.sql: THE CONVENTIONAL BASELINE for enforcement, used ONLY by scripts/evaluate.py in a throwaway
-- database. It keeps the same tables, keys, CHECK, UNIQUE and EXCLUDE constraints, and disables every user-defined
-- trigger (the gate, freezes, guards, append-only rules, audit). This is a controlled unguarded-database ablation,
-- not an implementation or benchmark of an application validator, and not a claim about the usual production design.
-- It isolates the contribution of database triggers when a write bypasses any application validator.
-- Foreign keys keep working (DISABLE TRIGGER USER leaves the internal constraint triggers on).
--
-- Scope: this measures whether the database schema itself rejects the listed malformed writes when its guards are
-- present. It does not establish that a recorded event happened physically, authenticate a worker or instrument, or
-- protect either design from a privileged database owner/superuser who can alter data or disable triggers. The owner
-- disables triggers here only to construct a controlled comparison in a disposable evaluation database.
DO $$
DECLARE
  t record;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('ALTER TABLE %I DISABLE TRIGGER USER', t.tablename);
  END LOOP;
END $$;
