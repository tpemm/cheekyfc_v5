# Fantrax Data v5.0

This project is a compatibility-first refactor of the working v4 application.
It preserves the complete application, scripts, data, and integrations while
establishing the final modular architecture for future development.

## Run

From the project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

You may also double-click `run_app.bat` after creating the virtual environment.

## What changed in v5.0

- Added the stable root `app.py` launcher.
- Reduced `core/legacy_renderer.py` to the shared application shell.
- Added a central season-aware page registry at `views/registry.py`.
- Migrated every navigation page into a dedicated module under `views/`.
- Added DatasetRegistry, SeasonManager, read-only DataManager, and the bounded
  OperationsService.
- Made Draft HQ available under 2026/27 without falsely requiring live-season league data.
- Kept 2025/26 league pages tied to finalized historical data.
- Added the stable draft builder command `python -m analytics.draft.builder`.
- Retained all v4 data, scripts, reports, tests, and integrations.

## Architecture status

The modular migration is complete. The historical renderer filename remains
only as the application-shell compatibility location; it contains no page
implementation, dataset reader, analytics logic, or script runner. See
`docs/MIGRATION_COMPLETION.md` and `docs/FOUNDATION_ARCHITECTURE.md`.

Run the authoritative test suite with:

```powershell
.\.venv\Scripts\python.exe -m pytest
```
