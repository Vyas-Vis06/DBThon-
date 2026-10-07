-- rules_in_app_code.sql: THE CONVENTIONAL BASELINE for enforcement, used ONLY by scripts/evaluate.py in a throwaway
-- database. It keeps the same tables, keys, CHECK, UNIQUE and EXCLUDE constraints, and disables every user-defined
-- trigger (the gate, freezes, guards, append-only rules, audit). That is the usual design in which the business rules
-- live in application code: the database still holds the data but accepts any write a client sends.
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
