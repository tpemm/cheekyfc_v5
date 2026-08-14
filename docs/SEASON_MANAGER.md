# SeasonManager

## Status

SeasonManager was implemented in Sprint 1.1 and is now the production source of
season context for the application shell, every migrated page, DataManager,
and OperationsService. Analytics builders and refresh scripts retain their
existing compatibility interfaces.

Implementation:

- context model: `core/models/season_context.py`
- service: `core/services/season_manager.py`
- tests: `tests/test_season_manager.py`

## Responsibilities

SeasonManager centralizes:

- loading the existing `config/seasons.json`;
- validation of season IDs, labels, statuses, booleans, and defaults;
- lookup by season ID;
- resolution by ID or display name;
- default viewing-season resolution;
- active ingestion-season resolution;
- working versus snapshot namespace policy;
- finalized and mutable state;
- page capability identifiers;
- operation capability identifiers;
- immutable season-root context.

It does not load datasets, calculate analytics, execute operations, mutate
configuration, or import pandas or Streamlit.

## SeasonContext

SeasonContext is a frozen, slotted dataclass representing one resolved season.

| Field | Meaning |
| --- | --- |
| `season_id` | Canonical catalog identifier |
| `display_name` | User-facing season label |
| `status` | Configured lifecycle status |
| `enabled` | Whether the season is available |
| `data_ready` | Whether league data is ready |
| `namespace` | Default `working` or `snapshot` namespace |
| `working_root` | Root of mutable working data |
| `snapshot_root` | Root of the season's immutable snapshot |
| `finalized` | Whether status is `finalized` |
| `mutable` | Whether working data may be changed |
| `supported_pages` | Framework-neutral page capability identifiers |
| `supported_operations` | Operation capability identifiers |

The context contains no behavior. Lifecycle policy remains in SeasonManager.

## Configuration

The service continues to use `config/seasons.json` without changing its
format. It also preserves `config.settings.DEFAULT_SEASON_ID`.

The current catalog resolves as follows:

| Season | Status | Default namespace | Mutable | Primary capabilities |
| --- | --- | --- | --- | --- |
| `2526` | finalized | snapshot | no | Historical league pages and snapshot validation |
| `2627` | preseason | working | yes | Draft, operations, and data inspection |
| `all_time` | not built/disabled | working | no | Inspection page identifiers only |

Roots are represented in SeasonContext because DataManager will eventually use
them. SeasonManager does not inspect their contents or derive readiness from
filesystem state.

## Public API

### `list_seasons(enabled_only=False)`

Returns immutable contexts in configuration order. The optional filter removes
disabled seasons.

### `get(season_id)` / `context(season_id)`

Returns a context by canonical ID. Unknown IDs raise `KeyError`.

### `resolve(selection=None)`

Resolves a season ID or exact display name. With no selection, returns the
default viewing season.

### `default_viewing_season()`

Returns the context identified by the existing default-season setting.

### `active_ingestion_season()`

Returns the single enabled season marked `active`. The current catalog has no
active season, so compatibility policy selects the last enabled mutable
non-all-time season: `2627`.

### `supports_page(season_id, page_key)`

Checks a framework-neutral page capability. It does not import or render the
page.

### `supports_operation(season_id, operation_key)`

Checks whether lifecycle policy permits an operation identifier.

### `resolve_namespace(season_id, requested=None)`

Returns the season's default namespace or validates an explicit `working` or
`snapshot` request.

### `assert_mutable(season_id, namespace=None)`

Returns normally for mutable working data. Raises `SeasonMutationError` for a
snapshot, finalized season, or disabled/non-mutable season.

### `validate_catalog()`

Validates the loaded definitions. Invalid catalogs raise
`SeasonCatalogError`.

## Lifecycle Policy

```text
not_built -> preseason -> active -> finalized -> archived
                |           |          |
                |           |          +-- immutable snapshot validation
                +-----------+------------- mutable working operations
```

SeasonManager describes and validates lifecycle state. A future
OperationsService will execute transitions and filesystem changes.

Finalized and archived seasons expose only snapshot validation. Preseason and
active seasons expose refresh, master build, analytics build, draft build, and
finalization identifiers. Disabled seasons expose no operations.

## Examples

Conceptual usage:

```python
seasons = SeasonManager()

viewing = seasons.default_viewing_season()
target = seasons.active_ingestion_season()

if seasons.supports_operation(target.season_id, "refresh"):
    seasons.assert_mutable(target.season_id)
```

DataManager will later use:

```python
context = seasons.context("2526")
namespace = seasons.resolve_namespace("2526")
```

These examples resolve state only; SeasonManager never loads or writes data.

## Extension Guidance

- Keep canonical IDs independent of display labels.
- Add new lifecycle statuses only with explicit validation and capability
  policy.
- Keep capabilities as stable identifiers, not callables or UI objects.
- Do not infer `data_ready` from directory existence.
- Do not put dataset filenames into SeasonManager.
- Do not perform season transitions as side effects of resolution.
