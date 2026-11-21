# Agent guide

## Start here

- Run `git status --short` and review relevant diffs before changing anything. Preserve all existing work; never reset, stash, delete, or reformat unrelated changes.
- Read `docs/project-status.md` for the current Fotouni state, agreed rules, and remaining work. Use `docs/requirements.md` for the dated decision history, then consult `README.md`, `docs/system-design.md`, and `deploy/README.md` as needed.
- Repository state and the latest handoff/status document take precedence over older notes. Do not turn rough meeting notes into requirements without confirmation.

## Project rules

- Do not commit, push, deploy, publish to OpenStreetMap, restart shared services, or modify shared/production data unless the user explicitly asks.
- Never test data-changing behavior on `projects/fotouni` or `cache/naming-rules-check/project`. Make a new copy and keep backups before risky writes.
- Keep personal survey data, household names, phone numbers, project databases, and `input/households.csv` out of git and output. Do not expose anything from sensitive document folders.
- Use Esri imagery (including the approved Wayback layer) for tracing. Do not trace from Google imagery. Only genuine community/official street names may be exported to OSM; internal street numbers and derived names stay internal.
- Preserve the event history, undo/redo, audit authorship, stable road identities, and backwards compatibility. Geometry changes can alter street IDs and addresses, so verify downstream behavior.
- Work on Windows/PowerShell with the repository `.venv`. Avoid downloads or installs unless necessary and approved. Do not touch the lockfile incidentally.
- Documents written for other people use the user's first-person voice and never invent names or decisions.

## Tests

Run the smallest relevant tests first, using a fresh temporary directory each time (pytest may clear it):

```powershell
.venv\Scripts\python.exe -m pytest tests\test_relevant_file.py -q -p no:cacheprovider --basetemp "$env:TEMP\osmaddress-test-UNIQUE"
```

Before handoff of substantial code changes, run the full suite:

```powershell
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp "$env:TEMP\osmaddress-full-UNIQUE"
```

Browser tests use an installed Edge/Chrome/Chromium and skip if unavailable; `ADDRESS_TEST_BROWSER` can select another executable. Never use a real project folder as `--basetemp`. Report commands, results, skipped tests, and anything not verified. Do not commit or push unless explicitly requested.
