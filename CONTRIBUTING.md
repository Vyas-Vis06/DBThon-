# Contributing

Welcome. This file is the workflow; the rules every change must follow are in [AGENTS.md](AGENTS.md) (written for humans and
coding agents alike). Setup is in [docs/SETUP.md](docs/SETUP.md).

## First hour

1. Set up and run it: `python scripts/dev.py`, sign in as `supervisor@zeroentry.example`, open the draft permit and press
   *Ask the database to authorise entry* (denied, with five reasons). Then read [README.md](README.md).
2. Run the tests: `python -m pytest -n auto`. They must be green before you change anything.
3. Read [PROJECT_SPEC.md](PROJECT_SPEC.md) (the rules, `BR-nn`) and the "Current state" of [ROADMAP.md](ROADMAP.md).
4. Pick a task from the ROADMAP (unchecked or backlog), or ask in the team chat which stream is free.

## Making a change

```bash
git switch -c feature/<short-name>          # or fix/<short-name>, docs/<short-name>
# ... edit ...
python -m pytest -n auto                     # the whole suite, every time
python scripts/gen_docs.py                   # if you touched a migration or a router
git add -p && git commit
git push -u origin feature/<short-name>      # then open a pull request
```

| You are changing | Do this |
|---|---|
| The schema or a rule | `python scripts/db.py new <name>`, write the SQL, add a pass **and** a fail test in `tests/db/`, update `docs/DATABASE_DESIGN.md` and `docs/ER_DIAGRAM.md`, run `scripts/gen_docs.py`. Never edit an applied migration. |
| An endpoint | Declare roles with `require(...)`; add the row to `tests/api/test_rbac.py`'s matrix; run `scripts/gen_docs.py`. |
| The UI | `src/zeroentry/web/static/pages/<screen>.js`; build DOM with `h(...)` and text, never `innerHTML`; no third-party scripts. |
| A rule's meaning | Update `PROJECT_SPEC.md` first (and say why in the PR). |
| Progress | Tick `ROADMAP.md` only for verified work; add a dated entry to `docs/development/DEV_LOG.md`. |

**Commit messages:** an imperative subject under ~70 characters ("Hold invoices when an alert opens"), a blank line, then *why*
and anything a reviewer must know. One logical change per commit.

## Pull request checklist

- [ ] `python -m pytest -n auto` passes locally (and CI is green)
- [ ] New behaviour has a test that fails without the change
- [ ] Docs updated in the same PR (see the table above); generated docs regenerated
- [ ] No secrets, `.env`, database dumps or personal data
- [ ] No new dependency, or the PR says why nothing installed could do the job

## Working with a coding agent

Agents (Claude Code, Codex, Cursor, Copilot...) read [AGENTS.md](AGENTS.md); Claude Code also reads [CLAUDE.md](CLAUDE.md).
A good first prompt:

> Read AGENTS.md, PROJECT_SPEC.md, ROADMAP.md and the latest entry of docs/development/DEV_LOG.md. Then <task>. Follow the
> definition of done in AGENTS.md, run the whole test suite, and tell me exactly which tests you ran and their result.

Review an agent's diff like a teammate's: check that the tests it added fail without its change, and that it did not edit an
applied migration or a generated document by hand.
