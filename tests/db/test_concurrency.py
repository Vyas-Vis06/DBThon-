"""Two sessions at once cannot break the proof behind a permit decision (BR-08, BR-09, BR-10).

Each test holds a permit mid-decision in one transaction while a second connection tries to change the evidence. Before
migration 0010 the second change slipped through: the guards read the permit's status without a lock, so both
transactions committed and an AUTHORISED permit no longer matched its proof.
"""

import threading
from datetime import timedelta

import psycopg

from tests.factories import Factory, yesterday_ist

STANDBY_COUNT = "SELECT count(*) AS n FROM permit_crew WHERE permit_id = %s AND crew_role = 'STANDBY'"


def _in_background(db, sql, params):
    """Run one autocommit statement on a separate connection in a thread. Returns (thread, outcome dict)."""
    outcome = {}

    def run():
        try:
            with db.connect() as other:
                other.execute(sql, params)
            outcome["ok"] = True
        except psycopg.Error as exc:
            outcome["sqlstate"] = exc.sqlstate

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(timeout=1)        # unguarded, the statement has finished by now; guarded, it is waiting for our lock
    return thread, outcome


def _scenario(db):
    with db.connect() as setup:
        return Factory(setup).gate_scenario(yesterday_ist())


def test_crew_cannot_be_removed_while_authorise_entry_is_deciding(db):
    s = _scenario(db)
    with db.connect(autocommit=False) as decider:
        rows = decider.execute("SELECT * FROM authorise_entry(%s, %s, %s)", (s["permit"], s["supervisor"], s["at"])).fetchall()
        assert {r["permit_status"] for r in rows} == {"AUTHORISED"}
        thread, outcome = _in_background(db, "DELETE FROM permit_crew WHERE permit_id = %s AND crew_role = 'STANDBY'", (s["permit"],))
        decider.commit()
    thread.join(timeout=10)
    assert outcome == {"sqlstate": "ZE003"}                       # it waited, then saw AUTHORISED: crew is frozen
    with db.connect() as check:
        assert check.execute(STANDBY_COUNT, (s["permit"],)).fetchone()["n"] == 1


def test_an_entrant_added_while_authorise_entry_is_deciding_is_refused_once_it_commits(db):
    """The foreign key alone made this insert WAIT (tests/db/test_entry_gate.py), but then it went through: an AUTHORISED
    permit gained an entrant with no gear. The permit lock makes it re-read the status after the wait."""
    s = _scenario(db)
    with db.connect() as setup:
        late = Factory(setup).worker(s["contractor"])
    with db.connect(autocommit=False) as decider:
        decider.execute("SELECT * FROM authorise_entry(%s, %s, %s)", (s["permit"], s["supervisor"], s["at"]))
        thread, outcome = _in_background(
            db, "INSERT INTO permit_crew (permit_id, worker_id, crew_role) VALUES (%s, %s, 'ENTRANT')", (s["permit"], late))
        decider.commit()
    thread.join(timeout=10)
    assert outcome == {"sqlstate": "ZE003"}


def test_a_raw_update_waits_for_an_uncommitted_crew_change_and_then_denies(db):
    s = _scenario(db)
    with db.connect(autocommit=False) as editor:
        editor.execute("DELETE FROM permit_crew WHERE permit_id = %s AND crew_role = 'STANDBY'", (s["permit"],))
        thread, outcome = _in_background(
            db, "UPDATE entry_permit SET status = 'AUTHORISED', authorised_at = %s, authorised_by = %s WHERE permit_id = %s",
            (s["at"], s["supervisor"], s["permit"]))
        editor.commit()
    thread.join(timeout=10)
    assert outcome == {"sqlstate": "ZE001"}                       # the gate re-proved the clauses after the change
    with db.connect() as check:
        assert check.execute("SELECT status FROM entry_permit WHERE permit_id = %s", (s["permit"],)).fetchone()["status"] == "DRAFT"


def test_no_entry_can_start_while_the_permit_is_being_closed(db):
    s = _scenario(db)
    with db.connect() as setup:
        setup.execute("SELECT * FROM authorise_entry(%s, %s, %s)", (s["permit"], s["supervisor"], s["at"]))
    with db.connect(autocommit=False) as closer:
        closer.execute("UPDATE entry_permit SET status = 'CLOSED' WHERE permit_id = %s", (s["permit"],))
        thread, outcome = _in_background(
            db, "INSERT INTO entry_log (permit_id, worker_id, period, recorded_by) "
                "VALUES (%s, %s, tstzrange(%s, NULL, '[)'), %s)",
            (s["permit"], s["e1"], s["at"] + timedelta(minutes=10), s["supervisor"]))
        closer.commit()
    thread.join(timeout=10)
    assert outcome == {"sqlstate": "ZE003"}                       # a closed permit never has a worker still inside
    with db.connect() as check:
        assert check.execute("SELECT count(*) AS n FROM entry_log WHERE permit_id = %s", (s["permit"],)).fetchone()["n"] == 0
