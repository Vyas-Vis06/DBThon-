-- rules_in_app_code.sql: THE CONVENTIONAL BASELINE for enforcement, used ONLY by scripts/evaluate.py in a throwaway
-- database. It keeps the same tables, keys, CHECK, UNIQUE and EXCLUDE constraints, and disables every user-defined
-- trigger (the gate, freezes, guards, append-only rules, audit). That is the usual design in which the business rules
-- live in application code: the database still holds the data but accepts any write a client sends.
-- Foreign keys keep working (DISABLE TRIGGER USER leaves the internal constraint triggers on).
DO $$
DECLARE
  t record;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('ALTER TABLE %I DISABLE TRIGGER USER', t.tablename);
  END LOOP;
END $$;
