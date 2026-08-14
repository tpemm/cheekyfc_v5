# Modular Architecture Migration Completion

## Outcome

Sprints 1.0–2.8 replaced a monolithic Streamlit renderer with a modular,
service-backed analytics application while preserving the existing product
scope. The migration is complete as of Sprint 2.8.

## Start and completion state

The starting renderer combined application configuration, season/path
resolution, filesystem scanning, pandas readers, analytics presentation,
subprocess execution, and all page implementations.

The completed dependency direction is:

```text
DatasetRegistry
      |
SeasonManager
      |
DataManager
      |
OperationsService (only where execution is required)
      |
Page modules
      |
Application shell
```

The shell now owns only Streamlit configuration, shared branding/CSS, season
selection, navigation, and renderer delegation.

## Pages migrated

- Key Output Health
- Reports
- League Hub
- Managers
- Award Detail
- Draft HQ
- Raw Data Browser
- Update Pipeline

## Foundation services

- DatasetRegistry: immutable logical dataset metadata.
- SeasonManager: season contexts, capabilities, namespaces, and mutability.
- DataManager: safe, cached, read-only artifact access and inspection.
- OperationsService: approved logical operations and structured results.

## Legacy code removed

Sprint 2.8 removed inactive inline page implementations and their page-specific
path constants, loaders, scanners, pandas readers, formatting/analytics
helpers, and subprocess runners. No active page imports a legacy loader or
directly executes a script.

## Verification baseline

The authoritative command is:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Central tests enforce page artifact/execution boundaries, one-renderer
navigation dispatch, service dependency direction, a read-only DataManager,
and safe OperationsService registration.

AppTest verification covers every navigation page with representative working,
finalized, and preseason contexts. It does not run production refresh jobs.
Headless verification checks Streamlit startup and the health endpoint.

Automated UI checks and structural comparisons are not pixel-level browser
comparisons. No claim of pixel-perfect comparison is made.

## Intentional migration differences

- Raw Data Browser discovery is constrained to canonical safe namespaces.
- Update Pipeline shows logical operation IDs instead of physical commands.
- Unsafe legacy filesystem reach was removed.
- Non-operational pages do not expose direct operation buttons.

No analytics formulas, ranking rules, award logic, report content, navigation
labels, or operation semantics were intentionally changed.

## Known technical debt and deferred roadmap

- Existing Streamlit `use_container_width` deprecation warnings.
- Legacy producer scripts remain subprocess adapters behind OperationsService.
- Some analytics builders still use physical paths internally.
- No pixel-diff visual regression suite exists.
- The historical `core/legacy_renderer.py` filename remains as the shell's
  compatibility location.
- Draft HQ product enhancements remain deferred.
- Importable producer commands, declared output validation, progress streaming,
  concurrency controls, persistent history, scheduling, background workers,
  and queues require future product justification.

## Rules for future development

New features must live in a page module, obtain seasons and artifacts through
foundation services, use logical operation IDs for mutations, preserve
DataManager's read-only contract, add focused tests, and pass architecture,
navigation, AppTest, and startup verification.
