# Fantrax Data v5

Fantrax Data v5 is a multi-season fantasy Premier League analytics platform for
the Cheeky FC league. It combines Fantrax, Understat, current EPL squad,
canonical player identity, Draft, manager, award, matchup, and operational
analytics behind a season-aware Streamlit application.

Draft HQ is the current development priority because the league draft is
this weekend. It is one workflow within a broader platform covering pre-draft,
live and post-draft analysis, in-season management, player and manager
analytics, league history, and commissioner operations.

## Run

From the project root in Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m streamlit run app.py
```

If the project environment has not been created:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Pytest discovery is limited to `tests/`. The pre-Sprint 3.6 baseline is 305
passing tests.

## Supported seasons

- **2025/26:** finalized, immutable league/manager/award analytics and reports
- **2026/27:** mutable preseason Draft HQ, Identity Review, and operations
- **All Time:** configured but not built or enabled

## Current major features

- DatasetRegistry, SeasonManager, DataManager, and OperationsService
- Custom season-aware navigation through `app.py`
- Current EPL squad snapshots
- Canonical Player Registry with guarded matching and reviewed aliases
- Player Identity Review with approve, ignore, clear, regeneration, and rerun
- Draft Builder, rankings, tiers, ADP/value context, and Draft HQ
- League, award, manager, raw-data, health, reports, and update views
- Registry/Draft validation and automated regression coverage

## Documentation

- [Documentation index](docs/README.md)
- [Architecture](docs/architecture.md)
- [Dataset catalog](docs/datasets.md)
- [Operations catalog](docs/operations.md)
- [Development standards](docs/development_standards.md)
- [Testing guide](docs/testing_guide.md)
- [Draft lifecycle](docs/draft_lifecycle.md)
- [Platform roadmap](docs/roadmap.md)

The indexed documentation above is the current source of truth. Older uppercase
documents under `docs/` retain historical audit and migration context.

