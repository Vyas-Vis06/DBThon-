# Screenshots of the current interface

Captured on **8 October 2026** from the operations-console UI at application revision `1e5bd79`.
All names, complaints, contractors, readings, invoices and incident records shown are synthetic seed data.
Images are direct browser screenshots from a running application, with no mock interface or altered record values.

| Screenshot | Role and state | Reproduce |
|---|---|---|
| [dashboard.jpg](dashboard.jpg) | ENGINEER: safety operations overview on seeded data | Sign in as `engineer@zeroentry.example` and open Dashboard. |
| [entry-gate-denied.jpg](entry-gate-denied.jpg) | SUPERVISOR: DRAFT permit #2 on CHN-ADY-010, five clauses denied | Open the draft and press **Ask the database to authorise entry**. The failed clauses are CREW_STANDBY, GEAR_ALL, GAS_TOP, GAS_MID and GAS_BOTTOM. |
| [shadow-entry-alerts.jpg](shadow-entry-alerts.jpg) | ENGINEER: five persisted alerts, including one with late evidence | Open Shadow entries on freshly seeded data. |
| [late-evidence-review.jpg](late-evidence-review.jpg) | ENGINEER: CHN-ADY-006 alert remains EVIDENCE_RECEIVED; its invoice is HELD | Open that alert without dismissing or confirming it. The screenshot includes its history, source-linked hold and review form. |

The capture used a separate database directory:

```bash
python run.py --data-dir .pgdata/docs-screenshots-20261008 --port 8020
```

For a new capture, choose a new directory if that one already contains changed demo state. Use the generated login
password printed by the launcher; never include the password or the local secrets file in screenshots or a commit.
The browser viewport was 1600 pixels wide with full-page captures, India Standard Time and reduced motion enabled.

These screenshots document the UI and its seeded workflow. They do not measure field safety or validate that an
actual worker used equipment. Counts and dates come from the captured demo instance and change with later actions.

See the [pitch cue card](../PITCH_CUE_CARD.md), [spoken pitch](../PITCH_SCRIPT.md), and
[demo guide](../guide/README.md) for the presentation sequence.
