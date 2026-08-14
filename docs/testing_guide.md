# Testing Guide

The pre-Sprint 3.6 baseline is **305 passing tests**. `pytest.ini` limits
discovery to `tests/`, excludes virtual environments, archive and generated
pytest folders, and disables pytest cache writes.

## Environment

Run commands from the project root in Windows PowerShell. Use the project-local
environment; do not assume another Python installation contains the dependencies.

```powershell
.\.venv\Scripts\Activate.ps1
python --version
```

If `.venv` does not exist:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Full suite

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Concise output:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Focused suites

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_player_registry.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_identity_review.py tests\test_identity_review_page.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_operations_service.py tests\test_data_manager.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_draft_builder.py tests\test_draft_center_page.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_navigation_integration.py -q
```

Use a unique bounded temporary directory when diagnosing filesystem behavior:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.test_artifacts\pytest-local
```

## Launch Streamlit

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

The root `app.py` command is authoritative. Do not launch presentation modules
as native Streamlit multipage entry points.

## AppTest

Page tests use `streamlit.testing.v1.AppTest` to run `app.py`, choose a season,
select the custom `Page` radio control, interact with widgets, and inspect
exceptions and rendered elements. A passing AppTest should assert behavior,
not only absence of an exception.

For state-changing pages:

1. Prefer injected/fake DataManager and OperationsService tests.
2. If a real artifact workflow is required, choose one pair-specific record.
3. Record the starting state.
4. Exercise the action and verify persisted plus rendered state.
5. Clear only the test record.
6. Regenerate dependent review data.
7. Confirm unrelated rows and starting counts remain unchanged.

Never replace an entire user decision file with a fixture snapshot.

## Test organization and naming

- `test_*_page.py` — page rendering, controls, AppTest, and presentation boundaries
- `test_data_manager.py`, `test_dataset_registry.py`,
  `test_operations_service.py`, `test_season_manager.py` — foundation services
- `test_player_registry.py`, `test_identity_review.py`,
  `test_draft_builder.py` — domain behavior and generated-artifact contracts
- `test_navigation_integration.py`, `test_application_architecture.py` —
  cross-cutting dependency and routing rules

Name tests as observable contracts, for example
`test_failed_decision_save_does_not_regenerate_or_false_update_ui`.

## Temporary artifacts and cleanup

- Put test output under `.test_artifacts/` or pytest-provided temporary directories.
- Do not use broad recursive cleanup commands against the project root.
- Pytest/Streamlit may leave locked Windows temporary directories; these
  interpreter-exit warnings do not replace test assertions and should be
  cleaned only when their exact bounded paths are known.
- Do not commit runtime logs or temporary AppTest state.

## Protecting production data

- Do not refresh providers merely to run unit tests.
- Do not rebuild production artifacts unless the task explicitly requires it.
- Never clear `player_alias_overrides` as test setup.
- Treat Draft rankings, registry outputs, current squads, and finalized season
  snapshots as production artifacts.
- Use reversible decisions and verify the original decision count after testing.
- Do not use manual rank injection or fixture writes to make tests pass.
