# Fantrax Data v5 Documentation

Fantrax Data v5 is a season-aware fantasy Premier League analytics platform for
the Cheeky FC league. Draft HQ is the immediate development priority,
but the product scope spans preseason preparation, live and post-draft
analysis, in-season management, player and manager analytics, league history,
and commissioner operations.

## Current scope

- Finalized 2025/26 league, award, manager, report, and data-inspection views
- Preseason 2026/27 Draft HQ and Player Identity Review
- Registered datasets, season-aware loading, bounded operations, validation,
  current EPL squads, canonical player identities, and Draft outputs
- Custom Streamlit sidebar navigation through the root `app.py` entry point

## Documentation map

- [Architecture](architecture.md) — current layers, dependency direction, and boundaries
- [Dataset catalog](datasets.md) — all 49 registered logical datasets
- [Operations catalog](operations.md) — all 9 approved state-changing operations
- [Development standards](development_standards.md) — rules for future implementation
- [Testing guide](testing_guide.md) — PowerShell commands and safe test practices
- [Draft lifecycle](draft_lifecycle.md) — pre-draft through end-of-season vision
- [Roadmap](roadmap.md) — practical phased sequencing for the broader platform

Older uppercase documents in this directory record earlier audits and migration
milestones. Where they conflict with the documents above or current code, the
current code and this indexed documentation set are authoritative.

## Season support

| Season | State | Current pages |
| --- | --- | --- |
| 2025/26 (`2526`) | Finalized, immutable | League Hub, Award Detail, Managers, Update Pipeline, Raw Data Browser, Key Output Health, Reports |
| 2026/27 (`2627`) | Preseason, mutable | Draft HQ, Identity Review, Update Pipeline, Raw Data Browser, Key Output Health, Reports |
| All Time (`all_time`) | Not built, disabled | Registry metadata defines inspection/report pages, but the season is not enabled |

## Run and test

From the project root in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m streamlit run app.py
```

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The pre-sprint baseline is 305 passing tests.

## Architectural rules

- Dataset paths and contracts are registered in `DatasetRegistry`.
- `SeasonManager` owns season state, namespaces, page availability, and mutation policy.
- Views read registered data through `DataManager`; they do not construct paths.
- State-changing UI actions use `OperationsService`; views do not call builders.
- The root path is `app.py → core.legacy_renderer.render_application()`.
- The custom sidebar is the only navigation system; Streamlit native multipage
  navigation is disabled.
- Generated artifacts are reproducible outputs, not manually maintained inputs.
- Manual decisions live in registered reference datasets.
- Provider IDs outrank names; identity matching remains deterministic and auditable.
- Fuzzy matching remains constrained and never silently approves review suggestions.

