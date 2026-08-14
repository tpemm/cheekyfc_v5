# OperationsService

## Status

`OperationsService` was introduced in Sprint 2.7 with the minimum scope required
to migrate the Update Pipeline page. Sprint 2.8 verified it as the final
execution boundary. It is framework-independent and exposes only registered,
application-owned operations.

## Responsibilities

The service:

- defines the operations the application may execute;
- exposes safe, human-readable operation metadata;
- validates operation parameters;
- checks season capabilities and mutability through `SeasonManager`;
- executes fixed script entry points without a shell;
- captures output, errors, timing, and return codes; and
- returns a structured `OperationResult`.

It does not render UI, import Streamlit, load datasets, calculate analytics,
accept arbitrary commands, or expose physical script paths to callers.

## Registered operations

| Key | Label | Season capability | Parameters |
| --- | --- | --- | --- |
| `refresh_fantrax_data` | Refresh Fantrax data | `refresh` | `mode`, plus `weeks` for `SPECIFIC` |
| `build_league_analytics` | Build League Hub analytics | `build_analytics` | None |

Refresh modes are `AUTO`, `REBUILD`, `SPECIFIC`, and `FULL`. Week input is
accepted only for `SPECIFIC` and must be a comma-separated list of positive
week numbers or ranges, such as `1,3-5`.

## Public API

- `list_operations(season_id=None)` returns immutable public definitions,
  optionally filtered to operations supported by a season.
- `inspect_operation(operation_key)` returns public metadata without exposing
  an executable path.
- `can_run(operation_key, season_id)` reports whether the registered operation
  is supported and permitted for the season.
- `run(operation_key, season_id, **parameters)` validates and invokes the fixed
  registered entry point, returning an `OperationResult`.

## Models

`OperationDefinition` is an immutable description containing the logical key,
display metadata, required season capability, and accepted parameter names.

`OperationResult` is an immutable execution record containing success state,
timestamps, duration, return code, safe message, captured output, and structured
exception information. Its `display_log()` method produces UI-ready log text.

## Safety boundary

Operations are selected by logical ID from an internal allowlist. Callers
cannot provide an executable, script path, working directory, shell syntax,
environment override, or unregistered parameter.

Execution uses an argument vector with `shell=False`. Script locations are
fixed internally and resolved relative to the application root. Parameter
builders translate validated values into the existing scripts' standard-input
protocol, preserving current behavior without permitting command injection.

## Season integration

`SeasonManager` remains the source of truth for season state. Before execution,
`OperationsService` resolves the season, checks the required supported
operation, and rejects finalized or immutable seasons. Snapshot seasons cannot
run update operations.

## Example

```python
service = OperationsService(season_manager)

if service.can_run("refresh_fantrax_data", "2627"):
    result = service.run(
        "refresh_fantrax_data",
        "2627",
        mode="SPECIFIC",
        weeks="1,3-5",
    )
```

## Deferred work

Sprint 2.7 intentionally does not add persistent job history, background
queues, cancellation, progress streaming, scheduling, distributed workers, or
operation-specific analytics logic. These can be added behind the same logical
operation boundary when required.
