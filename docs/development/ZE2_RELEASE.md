# ZeroEntry ZE2 release handoff

Use Python 3.11 or 3.12 from this repository:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
.venv/Scripts/python.exe scripts/dev.py --data-dir .pgdata/dbthon-ze2 --port 8000
```

Open http://127.0.0.1:8000 and use the local generated accounts/password printed by startup. Keep that terminal open.
Never expose this development server or share its password. In a second terminal run
`.venv/Scripts/python.exe scripts/prepare_demo.py` and enter that password privately. It creates an educational draft
with one acknowledgement missing. Prepare shortly before presenting because evidence expires.

Follow the [four-to-five-minute demonstration](DEMO_SCRIPT.md). Real scope fails closed; positive decisions are
educational simulations. Show acknowledgement, retained receipt, safety stop and truthful exit, completion review,
standalone two-victim intake and LAB proof.

Verified: **617 passing local tests**, no failures/errors/skips, three real-browser scenarios; 50 application tables,
97 FKs and 16 migrations. The independently installed wheel also passed all six static page/asset smoke checks.
All six LAB areas have actual evidence in [current.json](../evidence/current.json).
The [raw JUnit report](../evidence/integration.xml) and its [unchanged-source binding](../evidence/integration.source.json)
are included for inspection; local evidence is not external signed attestation.
See [restore](../evidence/restore.json), [equal-policy interleaving](../evidence/preview.json),
[E1-E3 measurements](../EVALUATION_RESULTS.md), [temporal results](../evaluation/RESULTS.md),
[rubric mapping](../SUBMISSION.md) and [integration guide](INTEGRATION_GUIDE.md).

The full [implementation plan](../plan/README.md) and detailed [A](WORKER_A_EXECUTION.md), [B](WORKER_B_EXECUTION.md),
[C](WORKER_C_EXECUTION.md) instructions are retained for your team. Work in non-overlapping lanes and agree on contracts.

Branch: `codex/zeroentry-ze2-integration`. Main is not merged or rewritten. Review before merging.
The integration starts from downloaded commit `a3db1b4`. During final publication, upstream main had advanced to
`6ebc5e2` with additional UI, startup and presentation work. Those newer changes are untouched and not merged here;
review overlapping UI/docs changes before any eventual merge. This branch's 617-test result applies to this branch only.

Do not commit
credentials, `.env`, `.pgdata`, dumps or virtual environments. To regenerate proof install `.[dev,browser]`, install
Chromium through Playwright, then run `python scripts/verify_release.py --workers 4`.

Limits: synthetic laboratory results, selected browser flows and locally trusted source fingerprints. No field/legal
certification, authenticated sensor truth, externally signed audit, global-first novelty or deaths-prevented claim.
Missing records require review; they are not proof of physical entry or wrongdoing.
