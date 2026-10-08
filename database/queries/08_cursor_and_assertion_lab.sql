-- LAB6: explicit OPEN/FETCH/CLOSE, a table %ROWTYPE, a loop and exception rollback.
-- PostgreSQL 16 has no CREATE ASSERTION. The controlled two-table example uses
-- constraint triggers to express a cross-row invariant, not unsupported Oracle syntax.
-- All demonstration objects are TEMPORARY. This is not a concurrent production gate;
-- the application gate additionally serializes competing transactions on permit rows.

DO $$
DECLARE
  permit_cursor CURSOR FOR SELECT * FROM entry_permit ORDER BY permit_id;
  permit_row entry_permit%ROWTYPE;
  visited integer := 0;
BEGIN
  OPEN permit_cursor;
  LOOP
    FETCH permit_cursor INTO permit_row;
    EXIT WHEN NOT FOUND;
    visited := visited + 1;
    RAISE NOTICE 'cursor visited permit % in state %', permit_row.permit_id, permit_row.status;
  END LOOP;
  CLOSE permit_cursor;
  IF visited <> (SELECT count(*) FROM entry_permit) THEN
    RAISE EXCEPTION 'Cursor did not visit every permit in this controlled fixture';
  END IF;
  RAISE NOTICE 'cursor loop completed with % permit rows', visited;
END $$;

CREATE TEMP TABLE lab_assertion_state (entity_id integer PRIMARY KEY, active boolean NOT NULL);
CREATE TEMP TABLE lab_assertion_ack (
  entity_id integer NOT NULL REFERENCES lab_assertion_state,
  participant_id integer NOT NULL,
  PRIMARY KEY (entity_id, participant_id)
);
CREATE FUNCTION pg_temp.lab_assertion_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM lab_assertion_state s WHERE s.active
       AND NOT EXISTS (SELECT 1 FROM lab_assertion_ack a WHERE a.entity_id=s.entity_id)) THEN
    RAISE EXCEPTION 'active entity requires at least one participation row' USING ERRCODE='23514';
  END IF;
  RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER lab_state_guard AFTER INSERT OR UPDATE OR DELETE ON lab_assertion_state
  DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION pg_temp.lab_assertion_guard();
CREATE CONSTRAINT TRIGGER lab_ack_guard AFTER INSERT OR UPDATE OR DELETE ON lab_assertion_ack
  DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION pg_temp.lab_assertion_guard();
INSERT INTO lab_assertion_state VALUES (1, false);

DO $$
BEGIN
  BEGIN
    UPDATE lab_assertion_state SET active=true WHERE entity_id=1;
    RAISE EXCEPTION 'The invalid activation unexpectedly succeeded';
  EXCEPTION WHEN check_violation THEN
    RAISE NOTICE 'assertion-style trigger refused activation; the statement was rolled back';
  END;
END $$;
SELECT 'REFUSED_ACTIVATION' AS moment, active, (SELECT count(*) FROM lab_assertion_ack) AS acknowledgements
FROM lab_assertion_state;

INSERT INTO lab_assertion_ack VALUES (1, 101);
UPDATE lab_assertion_state SET active=true WHERE entity_id=1;
DO $$
BEGIN
  BEGIN
    DELETE FROM lab_assertion_ack WHERE entity_id=1;
    RAISE EXCEPTION 'Deleting the last participation unexpectedly succeeded';
  EXCEPTION WHEN check_violation THEN
    RAISE NOTICE 'assertion-style trigger refused the last acknowledgement deletion; rollback retained it';
  END;
END $$;
SELECT 'VALID_STATE_RETAINED' AS moment, active, (SELECT count(*) FROM lab_assertion_ack) AS acknowledgements
FROM lab_assertion_state;
