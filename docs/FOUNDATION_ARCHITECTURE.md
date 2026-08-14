# Foundation Service Architecture

## Implemented baseline — Sprint 2.8

The page migration is complete. The production dependency direction is:

```text
DatasetRegistry
      |
SeasonManager
      |
DataManager
      |
OperationsService (operational pages only)
      |
Page modules
      |
Streamlit application shell
```

Ordinary display pages use DatasetRegistry, SeasonManager, and DataManager;
they do not pass through OperationsService. The shell owns page configuration,
branding, season selection, navigation, shared CSS, and exactly-one-page
dispatch. It owns no dataset loading, analytics, or operation execution.

| Navigation label | Module | Responsibility |
| --- | --- | --- |
| League Hub | `views/league_hub.py` | League overview, standings, highlights, awards, and charts |
| Award Detail | `views/awards.py` | Award selection, podiums, leaderboards, and history |
| Managers | `views/managers.py` | Manager profile, performance, squad, and decision views |
| Draft HQ | `views/draft_center.py` | Existing preseason rankings and player research |
| Update Pipeline | `views/update_pipeline.py` | Approved refresh/build controls and result presentation |
| Raw Data Browser | `views/raw_data_browser.py` | Safe artifact catalog and bounded previews |
| Key Output Health | `views/key_output_health.py` | Required/optional output health presentation |
| Reports | `views/reports.py` | Registered reports, manifests, and validation output |

Pages load datasets by registered logical key through DataManager. Safe catalog
references are permitted only through its catalog and preview APIs.
SeasonManager resolves working, finalized/snapshot, and reference policy;
finalized snapshots are immutable. Operational pages invoke only registered
logical operation IDs, and DataManager remains read-only.

The authoritative test command is:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

`pytest.ini` limits discovery to `tests/`, excludes generated temporary
folders, and disables cache writes in restricted workspaces.

Future features must keep presentation in a page module, use foundation
services for season and artifact access, add generic capabilities only for a
demonstrated requirement, include focused/integration tests, and preserve
containment, read-only access, and approved-operation boundaries.

Explicit non-goals remain AnalyticsService, background workers, persistent
operation history, distributed queues, arbitrary data writes, and arbitrary
command execution.

## Purpose

This document defines the core service layer for the modular Fantrax analytics
platform. It is an architectural contract, not an implementation plan or code
specification.

The design has three priorities:

1. Preserve the behavior and data compatibility of the current application.
2. Separate filesystem, configuration, season, logging, and operational
   concerns from Streamlit pages and analytics.
3. Make new seasons, datasets, pages, and data providers additive rather than
   requiring edits to a monolithic renderer.

## Design Principles

### Stable logical names over physical paths

Callers should request `manager_week_summary` for a season, not construct
`data/seasons/2526/processed/manager_week_summary_2526.csv`.

### Read and write responsibilities are distinct

The DataManager reads and validates datasets. Ingestion and analytics producers
write artifacts through controlled operations. Pages do not write project
data.

### Season context is explicit

Every season-sensitive operation receives or resolves a season ID and data
namespace. The active working area and an immutable historical snapshot must
never be confused.

### Analytics remain independent

Scoring, optimization, metrics, normalization, and view-building remain domain
modules. The foundation services provide their inputs and manage their
artifacts; they do not absorb analytical rules.

### Framework independence

Core services do not import Streamlit. Streamlit pages translate service
results into widgets, tables, warnings, and charts.

### Compatibility through adapters

Existing filenames, commands, wrappers, and frozen season layouts remain
supported while callers migrate. Compatibility code has an explicit
deprecation path and does not become the new core.

## Proposed Layering

```text
Streamlit shell and page modules
            |
            v
      Application services
  OperationsService, SeasonManager
            |
            v
       Foundation services
  DatasetRegistry, DataManager,
  ConfigManager, LoggingService
            |
            v
 Analytics, ingestion, and integration modules
            |
            v
 Filesystem, APIs, subprocesses, and caches
```

The dependency direction is deliberate:

- Pages may use every foundation/application service.
- OperationsService may coordinate analytics and ingestion commands.
- DataManager may use DatasetRegistry, SeasonManager, ConfigManager, and
  LoggingService.
- DatasetRegistry must remain lightweight and must not depend on DataManager.
- Analytics functions must not depend on Streamlit or OperationsService.

## Shared Concepts

### Dataset key

A stable identifier such as:

- `master_player_weekly`
- `manager_week_summary`
- `league_table`
- `draft_rankings`
- `season_manifest`

Keys are independent of season suffixes, file extensions, and directory
layouts.

### Dataset namespace

The initial namespaces are:

- `working`: mutable current pipeline outputs
- `snapshot`: immutable finalized-season data
- `raw`: source captures
- `cache`: re-downloadable provider/library data
- `reference`: governed mappings and manual inputs
- `quality`: validation and review artifacts

Namespaces describe lifecycle and authority. They are not merely directory
names.

### Season context

A resolved season context contains:

- stable season ID
- display label
- status
- enabled/data-ready flags
- default data namespace
- working and snapshot roots
- supported page capabilities
- mutability policy

### Service result

Expected situations such as a missing optional dataset, empty table, stale
artifact, unavailable page capability, or skipped operation should be returned
as structured results. Exceptions are reserved for invalid contracts,
corruption, authorization failures, or unexpected execution errors.

## 1. DatasetRegistry

**Implementation status:** Implemented in Sprint 1.0. The production metadata
model is in `core/models/dataset_definition.py`, the service is in
`core/services/dataset_registry.py`, and the initial catalog contains 24 core
datasets. It is intentionally not integrated with pages or pipelines yet.

### Responsibilities

DatasetRegistry is the authoritative catalog of logical datasets. It separates
dataset identity from physical storage.

It owns:

- stable dataset keys and descriptions;
- classification as raw, processed, analytics, cache, reference, model,
  quality, report, or manifest;
- filename templates and allowed formats;
- namespace and season behavior;
- required versus optional status;
- expected producer and known consumers;
- schema identity or required-column references;
- aliases for legacy/versioned names;
- mutability, snapshot, caching, and retention policies;
- sensitivity flags, including exclusion of authentication state from generic
  browsing;
- dataset-family definitions for weekly exports and API response collections.

The registry should support both singular datasets and families. For example,
`fantrax_available_weekly` describes the family
`Fantrax_WeeklyStats_AvailablePlayers_GWNN.csv`, while
`master_player_weekly` describes one season-specific canonical table.

### Public API

Conceptual public operations:

- `get(dataset_key)` returns one dataset definition.
- `find(...)` returns definitions matching classification, namespace,
  producer, consumer, or season capability.
- `resolve_alias(name)` returns the canonical key and deprecation metadata.
- `list_for_page(page_key)` returns declared page dependencies.
- `list_for_operation(operation_key)` returns operation inputs and outputs.
- `validate_definition(dataset_key)` checks catalog completeness and internal
  consistency.
- `describe(dataset_key)` returns documentation-safe metadata.
- `register_extension(definition)` adds an approved plugin/provider dataset
  without modifying core callers.

The registry returns metadata and path templates, not loaded data.

### Dependencies

Required:

- ConfigManager for registry configuration locations and approved extension
  sources.
- LoggingService for catalog validation and alias/deprecation events.

It may use immutable definition types and schema descriptors, but should have
no dependency on pandas, Streamlit, API clients, or analytics builders.

### What It Must Never Do

- Read or write dataset contents.
- Call an API, scraper, analytics builder, or subprocess.
- Select the current season.
- Display Streamlit messages.
- Encode page rendering behavior.
- Silently map an unknown name to a guessed file.
- Permit runtime mutation of core definitions without validation.
- Treat credentials, browser authentication state, or lock files as ordinary
  browsable datasets.

### Existing Modules It Will Replace or Absorb

It replaces dataset metadata currently scattered across:

- `ANALYTICS_FILES` and `IMPORTANT_OUTPUTS` in
  `core/legacy_renderer.py`;
- hard-coded input/output constants in analytics, API, and refresh scripts;
- page-specific filename lists in the renderer;
- implicit dataset knowledge in `docs/DATA_FLOW.md`;
- version-specific selection such as
  `manager_efficiency_weekly_v2.csv` versus
  `manager_efficiency_weekly.csv`.

It does not replace `views/registry.py`. The page registry remains responsible
for page metadata, but it should reference DatasetRegistry keys for its data
requirements.

## 2. DataManager

**Implementation status:** Implemented in Sprint 1.2. Immutable result and
artifact models live under `core/models/`, the minimal read-only storage
abstraction lives under `core/storage/`, and the framework-independent service
is in `core/services/data_manager.py`. It supports registered local
CSV/JSON/Parquet/text reads, provenance, initial validation, families, safe
catalog/preview behavior, and defensive in-memory caching. Existing pages and
pipelines are intentionally not integrated yet.

### Responsibilities

DataManager is the single read-oriented gateway to registered project data.
It resolves a logical dataset against an explicit season and namespace, loads
it safely, validates its contract, and returns data without UI side effects.

It owns:

- logical-key-to-path resolution through DatasetRegistry;
- working versus snapshot path selection;
- CSV, JSON, Parquet, and text loading;
- caching and cache invalidation policy;
- required-column and schema validation;
- missing, empty, stale, or invalid status reporting;
- dataset-family discovery and ordering;
- generic artifact cataloging for the data browser;
- snapshot manifest/hash verification;
- safe preview limits for large or untrusted artifacts;
- compatibility fallback paths during migration;
- read-only enforcement for finalized snapshot data.

Write behavior should be narrow. If atomic artifact writers are exposed by the
foundation, they should be internal capabilities used by OperationsService,
not general page-facing methods.

### Public API

Conceptual public operations:

- `load(dataset_key, season_id, namespace=None, options=None)`
- `load_frame(...)` for tabular registered datasets
- `load_json(...)`
- `load_text(...)`
- `load_family(dataset_key, season_id, filters=None)`
- `resolve_path(dataset_key, season_id, namespace=None)`
- `exists(...)`
- `inspect(...)` for size, modification time, row/column summary, and status
- `validate(...)` for schema and manifest checks
- `catalog(season_id, namespace, filters=None)` for operational browsing
- `preview(artifact_ref, row_limit, column_limit)`
- `invalidate(dataset_key=None, season_id=None)`

Returns should include provenance: canonical key, resolved physical path,
namespace, season, modification time, validation status, and alias/fallback
use.

### Dependencies

Required:

- DatasetRegistry for definitions and aliases.
- SeasonManager for season roots, namespace defaults, and mutability rules.
- ConfigManager for storage roots, encoding defaults, and cache policy.
- LoggingService for load, fallback, validation, and performance events.

Optional infrastructure adapters may provide filesystem or remote-object-store
access later. DataManager should depend on an abstract storage interface rather
than expose storage details to callers.

### What It Must Never Do

- Calculate league analytics or business metrics.
- Fetch remote API data or drive a browser.
- Run refresh, build, or finalization commands.
- Import Streamlit or issue UI warnings.
- Guess a season from a filename when a context is available.
- Write into a finalized snapshot.
- Return credentials or auth-state files through generic browsing.
- Hide the use of a legacy fallback path.
- Mutate a loaded frame owned by another caller through shared cache state.
- Turn every exploratory cache file into a permanent public method.

### Existing Modules It Will Replace or Absorb

It replaces:

- `load_csv_cached()`, `load_preview()`, `scan_data_files()`,
  `file_info()`, and `require_csv()` in `core/legacy_renderer.py`;
- direct page-level `pd.read_csv`, `pd.read_parquet`, JSON, and text reads;
- repeated `read_csv()` helpers in analytics and API scripts where those
  modules are acting as application consumers;
- path resolution duplicated throughout builders;
- ad hoc snapshot-versus-working selection.

Low-level ingestion parsers may continue to read provider payloads directly
inside provider adapters. DataManager becomes mandatory at stable application
and analytics boundaries, not inside every parsing function.

## 3. SeasonManager

**Implementation status:** Implemented in Sprint 1.1. The immutable context is
defined in `core/models/season_context.py`, and the framework-independent
service is in `core/services/season_manager.py`. It continues to read the
existing season configuration and is intentionally not integrated with pages
or pipelines yet.

### Responsibilities

SeasonManager owns season identity, state, capabilities, and storage policy. It
is the only service allowed to decide what “current,” “active,” “preseason,” or
“finalized” means.

It owns:

- loading and validating season definitions;
- resolving a season ID from a user selection or configured default;
- returning immutable season contexts;
- enabled, data-ready, and finalized status;
- working and snapshot root selection;
- page/operation capability checks;
- mutability rules;
- transition rules such as preseason to active and active to finalized;
- all-time capability when it is eventually implemented;
- compatibility mapping for historical season labels.

SeasonManager should distinguish:

- the season selected for viewing;
- the season targeted by an operation;
- the active ingestion season;
- the namespace from which data is read.

These values may differ and must never be conflated.

### Public API

Conceptual public operations:

- `list_seasons(enabled_only=False)`
- `get(season_id)`
- `resolve(selection=None)`
- `default_viewing_season()`
- `active_ingestion_season()`
- `context(season_id, purpose="view")`
- `supports_page(season_id, page_key)`
- `supports_operation(season_id, operation_key)`
- `resolve_namespace(season_id, requested=None)`
- `assert_mutable(season_id, namespace)`
- `validate_catalog()`
- `plan_transition(season_id, target_status)`

Actual season transitions should be executed by OperationsService, not by
SeasonManager itself.

### Dependencies

Required:

- ConfigManager for the authoritative season catalog.
- LoggingService for resolution, validation, and lifecycle events.

It may reference page capability identifiers and dataset namespaces, but it
must not depend on Streamlit pages or DataManager.

### What It Must Never Do

- Load analytics datasets.
- Copy, delete, finalize, or refresh files.
- Run scripts or API calls.
- Infer readiness solely because a directory exists.
- Allow a finalized snapshot to become mutable.
- Use a display label as the canonical season identity.
- Store season selection in Streamlit session state.
- Decide page presentation.

### Existing Modules It Will Replace or Absorb

It replaces:

- `load_seasons()` and `active_season_id()` policy in
  `config/project_paths.py`;
- season selection and context construction at the top of
  `core/legacy_renderer.py`;
- duplicated `SEASON_ID = "2526"` constants as application policy;
- page availability checks split between the renderer and
  `views/registry.py`;
- season-root and finalized-status logic embedded in finalization, refresh,
  and UI code.

`config/seasons.json` can remain the initial storage format, but consumers will
access it through SeasonManager rather than parse it directly.

## 4. ConfigManager

### Responsibilities

ConfigManager provides validated, layered, read-only configuration to the
application. It separates configuration from data and secrets.

It owns:

- application identity and UI-neutral settings;
- project and storage root configuration;
- season catalog source;
- league identifiers and stable league metadata;
- provider endpoints and non-secret provider settings;
- environment-specific overrides;
- secret references without exposing secret values broadly;
- encoding, cache, timeout, and operational defaults;
- configuration validation and startup diagnostics;
- backward-compatible interpretation of current settings files.

Recommended precedence:

```text
validated defaults
    < project configuration
    < environment-specific configuration
    < environment variables / secret provider
    < explicit command invocation options
```

Precedence must be deterministic and inspectable, with secret values redacted.

### Public API

Conceptual public operations:

- `load()`
- `get(section, key, default=None)`
- `require(section, key)`
- `application_settings()`
- `storage_settings()`
- `provider_settings(provider_key)`
- `operation_defaults(operation_key)`
- `season_definitions()`
- `validate()`
- `describe(redact_secrets=True)`
- `reload()` for controlled development/operations use

Typed configuration views are preferred over unrestricted dictionary access.

### Dependencies

Required:

- LoggingService, or a minimal bootstrap logger until LoggingService is fully
  initialized.

It may use environment and secret-provider adapters. It must remain independent
of DatasetRegistry, DataManager, SeasonManager, OperationsService, pandas, and
Streamlit.

To avoid a startup cycle, ConfigManager is constructed first with bootstrap
logging; LoggingService is then configured from validated logging settings.

### What It Must Never Do

- Load project datasets.
- Contain analytics rules or roster constraints that belong to the domain.
- Execute commands or make API calls.
- Put secret values into logs or diagnostic output.
- Let pages read environment variables directly.
- Treat mutable runtime state as configuration.
- Rewrite configuration as a side effect of reading it.
- Hard-code workstation-specific absolute paths.

### Existing Modules It Will Replace or Absorb

It replaces or consolidates:

- `config/settings.py`;
- path-root configuration in `config/project_paths.py`;
- direct reads of `config/seasons.json`;
- provider configuration such as
  `football_data/sources/pundit/config.py`;
- scattered API URLs, league IDs, season IDs, timeouts, and output-root
  constants where they are true configuration;
- direct environment lookup in integration clients.

It must not absorb canonical scoring and lineup rules from
`fantrax/analytics/core/league_rules.py`. Those are versioned domain rules,
not infrastructure configuration.

## 5. LoggingService

### Responsibilities

LoggingService provides consistent structured observability across UI,
operations, ingestion, analytics, and data access.

It owns:

- structured event logging;
- correlation IDs for a user-triggered operation;
- operation, dataset, season, provider, duration, and outcome fields;
- console and rotating-file handlers;
- redaction of credentials, auth state, tokens, and sensitive paths;
- human-readable operation summaries;
- capture of subprocess output through OperationsService;
- warning/error normalization;
- retention and log location policy;
- optional progress-event subscriptions for Streamlit or CLI presentation;
- startup and configuration validation events.

LoggingService should distinguish logs from generated analytical reports.
Reports are durable business/validation artifacts registered as datasets;
logs are operational telemetry.

### Public API

Conceptual public operations:

- `debug(event, **context)`
- `info(event, **context)`
- `warning(event, **context)`
- `error(event, exception=None, **context)`
- `exception(event, exception, **context)`
- `bind(**context)` returns a context-bound logger.
- `start_operation(operation_key, season_id, parameters)` returns a run
  context/correlation ID.
- `record_progress(run_id, stage, current=None, total=None, message=None)`
- `complete_operation(run_id, outcome, artifacts=None, metrics=None)`
- `capture_subprocess(run_id, stream, text)`
- `recent_runs(filters=None)`

### Dependencies

Required:

- ConfigManager-provided logging settings after bootstrap.

It should wrap the standard logging framework or another replaceable backend.
It must not depend on DataManager, SeasonManager, OperationsService, Streamlit,
or a particular analytics module.

### What It Must Never Do

- Contain operation orchestration logic.
- Swallow exceptions or convert failed operations into success.
- Log secrets, API keys, browser auth state, or full sensitive payloads.
- Use `print()` as its persistence model.
- Make business decisions based on log content.
- Make page rendering calls.
- become the authoritative store for dataset lineage or season state.
- Rewrite analytical report files.

### Existing Modules It Will Replace or Absorb

It replaces:

- scattered `print()` statements in refresh, API, scraping, finalization, and
  analytics scripts;
- ad hoc timestamped refresh log assembly;
- direct subprocess stdout/stderr concatenation in
  `core/legacy_renderer.py`;
- inconsistent exception text and progress output;
- script-specific operational logging helpers such as `banner()` and
  `write_report_line()`.

Existing validation reports remain registered artifacts. LoggingService records
that they were generated and where they were stored.

## 6. OperationsService

**Implementation status:** Implemented in Sprint 2.7 with the minimum
production scope required by the Update Pipeline migration. It currently
registers refresh and League Hub analytics-build operations, enforces season
capabilities and mutability, validates parameters, executes fixed entry points
without a shell, and returns structured results. Persistent job history,
queues, cancellation, scheduling, output validation, and progress streaming
remain deferred.

### Responsibilities

OperationsService is the application-facing coordinator for state-changing or
long-running workflows. It provides stable operations while underlying scripts
are migrated into importable commands.

It owns:

- operation registration and discovery;
- validation of season capability and mutability before execution;
- dependency-aware refresh/build/finalize plans;
- invocation of ingestion and analytics commands;
- controlled subprocess compatibility for legacy scripts;
- parameter validation;
- progress and cancellation state;
- run IDs and structured outcomes;
- output artifact verification through DataManager;
- cache invalidation after successful writes;
- prevention of concurrent conflicting operations;
- dry-run and plan modes;
- retry policy for safe, idempotent stages;
- finalized-season protection;
- CLI and Streamlit adapters over the same operation contracts.

Initial operations should include:

- Fantrax refresh: AUTO, SPECIFIC, REBUILD, and FULL;
- build master weekly data;
- fetch/transform/validate Fantrax API data;
- rebuild team, manager, and player analytics;
- build preseason and draft datasets;
- finalize a season;
- validate snapshot health.

### Public API

Conceptual public operations:

- `list_operations(season_id=None)`
- `describe(operation_key)`
- `plan(operation_key, season_id, parameters=None)`
- `run(operation_key, season_id, parameters=None, dry_run=False)`
- `status(run_id)`
- `progress(run_id)`
- `result(run_id)`
- `cancel(run_id)` where the operation supports safe cancellation
- `recent_runs(filters=None)`
- `validate_outputs(run_id)`

An operation result includes status, timestamps, stage results, structured
errors, logs, produced dataset keys, resolved artifact paths, and validation
outcomes.

### Dependencies

Required:

- SeasonManager for capability and mutability checks.
- DatasetRegistry for declared inputs and outputs.
- DataManager for precondition checks, output verification, and cache
  invalidation.
- ConfigManager for executables, timeouts, provider settings, and operation
  defaults.
- LoggingService for run context, progress, stdout/stderr, and outcomes.

It coordinates analytics, ingestion, API, and finalization modules through
command adapters. During migration those adapters may invoke existing scripts
as subprocesses. The target state calls importable application commands
directly where isolation is not required.

### What It Must Never Do

- Render Streamlit components.
- Embed analytics formulas.
- Bypass season mutability or finalized-snapshot protection.
- Claim success before declared outputs are validated.
- Construct undocumented output paths outside DatasetRegistry.
- Run arbitrary user-provided commands.
- Hide partial failure in a multi-stage operation.
- Allow two operations to overwrite the same dataset concurrently.
- Delete or replace material data without an explicit registered operation and
  recovery policy.
- Make every page load trigger a refresh.

### Existing Modules It Will Replace or Absorb

It replaces or fronts:

- `run_script()`, `run_refresh()`, and `build_awards_views()` in
  `core/legacy_renderer.py`;
- the Update Pipeline page's direct subprocess handling;
- orchestration in `fantrax/refresh/refresh_all_fantrax_data.py`;
- orchestration in `fantrax/refresh/refresh_weekplayer_rawdata.py`;
- `fantrax/analytics/build_all.py`;
- root `fantrax.py` command dispatch;
- season setup/finalization orchestration;
- the `runpy` compatibility launch in `analytics/draft/builder.py`.

Producer modules such as scrapers, API clients, parsers, analytics builders,
and finalization validators remain behind operation adapters until they can be
called as stable importable commands.

## Service Dependency Matrix

| Service | Registry | DataManager | SeasonManager | ConfigManager | LoggingService | OperationsService |
| --- | --- | --- | --- | --- | --- | --- |
| DatasetRegistry | — | Never | Avoid direct dependency | Uses | Uses | Never |
| DataManager | Uses | — | Uses | Uses | Uses | Never |
| SeasonManager | Identifiers only | Never | — | Uses | Uses | Never |
| ConfigManager | Never | Never | Never | — | Bootstrap only | Never |
| LoggingService | Never | Never | Never | Uses | — | Never |
| OperationsService | Uses | Uses | Uses | Uses | Uses | — |

Recommended initialization order:

```text
ConfigManager
    -> LoggingService
        -> DatasetRegistry
        -> SeasonManager
            -> DataManager
                -> OperationsService
```

## Relationship to Pages and Analytics

### Streamlit application shell

The shell should:

- resolve a SeasonContext through SeasonManager;
- obtain page definitions from the page registry;
- inject required services into the selected page renderer;
- translate structured service results into UI feedback.

It should not know dataset paths or script locations.

### Page modules

Each page declares dataset keys and capabilities. It loads data through
DataManager and starts mutations through OperationsService. A page may perform
small presentation transformations, but reusable analytical calculations
belong in analytics modules.

### Analytics modules

Pure analytics functions should accept frames or typed domain inputs and return
frames/results. Application command adapters use DataManager to load inputs and
an operations-owned writer to persist registered outputs.

This separation permits analytics tests to remain fast and independent of the
filesystem, Streamlit, and season-selection state.

## Backwards-Compatibility Strategy

### Preserve physical files initially

The first service versions must resolve the filenames and directories already
used by the application. Introducing services does not require a data
migration.

### Preserve launch commands

These interfaces should continue to work during migration:

- `streamlit run app.py`
- `run_app.bat`
- `python fantrax.py <command>`
- existing `python -m fantrax.analytics...` commands

They become thin adapters to the new shell or OperationsService.

### Preserve compatibility wrappers

Existing modules under `fantrax/analytics/` can continue importing canonical
domain modules. They should emit deprecation events through LoggingService once
all callers have a supported replacement.

### Dataset aliases

DatasetRegistry should represent old names and preferred names explicitly.
Fallback behavior must be observable. Examples:

- legacy and v2 efficiency datasets;
- legacy and name-based API bridge outputs;
- working versus frozen copies of the same logical dataset.

### No automatic destructive migration

Legacy roots such as `raw_data/` and `processed_data/` remain readable until
producers and consumers have migrated and parity checks pass. Relocation is a
later registered operation, not a side effect of service startup.

## Migration Order

The migration should proceed in small, reversible stages. Each stage retains
the current root launcher and compatibility renderer until its replacement has
parity coverage.

### Phase 0: Freeze contracts and add characterization coverage

Before changing runtime behavior:

- treat `docs/DATA_FLOW.md` as the initial dataset inventory;
- capture current page-to-dataset dependencies;
- record expected path resolution for working and frozen 2025/26 data;
- add characterization tests for season selection, required outputs, dataset
  schemas, and operation command plans;
- record representative row counts/hashes for finalized snapshots;
- identify optional datasets and known missing behavior/formation outputs.

Exit condition: current behavior and compatibility requirements are testable.

### Phase 1: Introduce ConfigManager and LoggingService

These have the fewest dependencies and establish safe infrastructure for later
services.

- ConfigManager initially adapts `config/settings.py`,
  `config/project_paths.py`, `config/seasons.json`, and existing environment
  variables without changing values.
- LoggingService initially mirrors current console behavior while adding
  structured context and redaction.
- Existing scripts continue working through compatibility accessors.

Exit condition: configuration is validated centrally, secrets are redacted,
and new services use one logging interface.

### Phase 2: Introduce DatasetRegistry

- Register the stable datasets documented in `DATA_FLOW.md`.
- Represent working and snapshot templates.
- Add legacy aliases and sensitivity exclusions.
- Declare page and operation inputs/outputs without changing loaders.
- Validate the registry against the current filesystem and snapshot manifest.

Exit condition: every current page dependency and pipeline artifact has a
canonical key or an explicit catalog-only classification.

### Phase 3: Introduce SeasonManager

- Wrap the existing season JSON and preserve current defaults.
- Centralize viewing, ingestion, status, capability, namespace, and mutability
  decisions.
- Adapt `views/registry.py` to use season capabilities without changing page
  visibility.
- Keep Streamlit session-state selection in the shell, passing the selected ID
  to SeasonManager.

Exit condition: no page or new service constructs a season root or interprets
season status independently.

### Phase 4: Introduce DataManager as a compatibility reader

- Reproduce current CSV/JSON/Parquet/TXT loading and Streamlit cache behavior
  behind a framework-independent API.
- Resolve frozen 2025/26 files exactly as the current renderer does.
- Add provenance, schema status, safe preview, and artifact cataloging.
- Replace renderer helper internals with DataManager calls while retaining
  their old function signatures temporarily.

Exit condition: page output is unchanged and all path construction/data loading
inside the renderer is delegated to DataManager.

### Phase 5: Introduce OperationsService around existing scripts

**Status:** Partially implemented in Sprint 2.7. The Update Pipeline now uses
logical registered operations and structured results. Broader operation
coverage, output validation, concurrency controls, and CLI migration remain
future work.

- Register refresh, analytics, draft, validation, and finalization operations.
- Initially use subprocess adapters to preserve script isolation and behavior.
- Route Update Pipeline and CLI commands through the service.
- Validate declared outputs with DataManager before returning success.
- Protect finalized seasons and add concurrency controls.

Exit condition: Streamlit and root CLI no longer execute arbitrary script paths
or parse success from strings such as `Exit code: 0`.

### Phase 6: Extract page modules incrementally

**Migration status:** Complete. Sprint 2.0 migrated Key Output Health to
`views/key_output_health.py`. The legacy renderer retains navigation and now
delegates that branch to the modular renderer. The page obtains season state
from SeasonManager and all artifact status/loading from DataManager.

Sprint 2.1 migrated Reports to `views/reports.py` using registered stable
reports and a registered recent-report family. The legacy renderer retains
only the Reports delegation branch.

Sprint 2.2 migrated League Hub to `views/league_hub.py`. It resolves season
context and namespace through SeasonManager and loads its eleven registered
inputs exclusively through DataManager. No new foundation API or dataset
definition was required; the legacy renderer retains only a thin delegation
branch.

Sprint 2.3 migrated Managers to `views/managers.py`. The five-tab dashboard
loads its sixteen registered inputs through DataManager and obtains season
context and namespace from SeasonManager. No foundation API or dataset
definition was added.

Sprint 2.4 migrated Award Detail to `views/awards.py`. Award navigation,
leaderboards, podium cards, weekly winners, record-derived awards, and manager
history now use five registered datasets loaded through DataManager. No
foundation API or dataset definition was added.

Sprint 2.5 migrated Draft HQ to `views/draft_center.py`. The existing
single-board workflow uses DataManager for rankings and optional eligibility
overrides while SeasonManager owns its preseason namespace. The optional
`draft_eligibility_overrides` definition was added; no DataManager API changed.

Sprint 2.6 migrated Raw Data Browser to `views/raw_data_browser.py`. Safe
recursive discovery now uses DataManager `catalog()`, while the reusable
`preview_artifact()` API provides bounded previews for catalog artifacts that
do not have dedicated registry definitions. The page remains read-only.

Sprint 2.7 migrated Update Pipeline to `views/update_pipeline.py`. It uses
SeasonManager for season state, DataManager for finalized status artifacts, and
the initial OperationsService for the two existing update actions. The legacy
renderer retains only a thin delegation branch.

Recommended order:

1. Reports — completed in Sprint 2.1
2. Key Output Health — completed in Sprint 2.0
3. Raw Data Browser — completed in Sprint 2.6
4. Update Pipeline â€” completed in Sprint 2.7
5. Draft HQ — completed in Sprint 2.5
6. Award Detail — completed in Sprint 2.4
7. League Hub — completed in Sprint 2.2
8. Managers — completed in Sprint 2.3

The first pages exercise catalog, validation, preview, and operations services
with limited analytical UI risk. Managers moves last because it has the
largest dataset surface and contains the embedded explorer.

Each extracted page:

- declares dataset keys;
- receives services explicitly;
- contains no physical path or subprocess logic;
- receives characterization tests;
- is routed through the existing page registry.

Exit condition: `core/legacy_renderer.py` contains no active page
implementation.

Sprint 2.8 removed the obsolete inline implementations, legacy loaders, path
maps, pandas readers, analytics helpers, and execution helpers. The historical
module name now contains only the shared application shell and explicit
renderer delegation.

### Phase 7: Convert producers to importable application commands

- Split I/O adapters from pure transformations.
- Make analytics builders accept loaded inputs and return output frames.
- Replace versioned draft `runpy` execution with canonical modules.
- Move API and scraper constants into validated provider configuration.
- Use registered atomic writers and structured operation results.
- Retain old scripts as thin CLI adapters.

Exit condition: OperationsService normally coordinates stable importable
commands; subprocess adapters are limited to browser automation or deliberate
process isolation.

### Phase 8: Normalize storage and retire compatibility paths

Only after producer/consumer parity:

- choose the canonical raw API and processed API roots;
- migrate legacy `raw_data/` and `processed_data/` through an explicit,
  recoverable operation;
- remove the executable Python file from `data/processed`;
- deprecate old dataset aliases and wrapper modules;
- update snapshot manifests if a new snapshot format is introduced;
- retain readers for old frozen seasons indefinitely or provide a versioned
  snapshot adapter.

Exit condition: no active producer writes legacy roots and old finalized
seasons remain readable.

### Phase 9: Remove the compatibility renderer

**Status:** Completed functionally in Sprint 2.8. `app.py` imports the modular
shell directly. The historical `core/legacy_renderer.py` filename is retained
only as that shell's compatibility location; no legacy renderer behavior
remains.

- Make root `app.py` bootstrap the modular shell directly.
- Update `fantrax.py app` to the same canonical entry point.
- Optionally rename/archive the compatibility shell module in a later
  non-functional cleanup after downstream launchers no longer reference its
  historical name.
- Remove temporary helper adapters and expired aliases according to the
  published deprecation policy.

Exit condition: one application entry point, modular pages, service-owned
infrastructure, and no runtime dependency on the legacy renderer.

## Acceptance Criteria

The foundation architecture is successful when:

- pages contain no hard-coded dataset or script paths;
- every stable dataset has one canonical registry key;
- working and snapshot data cannot be confused;
- finalized snapshots are read-only and manifest-verifiable;
- operations return structured, validated outcomes;
- CLI and Streamlit invoke the same operation contracts;
- analytics can be tested without Streamlit or project filesystem state;
- missing optional data is distinguishable from corrupt required data;
- secrets and browser auth state are excluded from generic browsing and logs;
- a new season can be introduced primarily through configuration and dataset
  definitions;
- a new provider can add ingestion adapters and registered datasets without
  changing unrelated pages;
- existing 2025/26 pages and historical files remain usable throughout the
  migration.
