# Project Architecture Analysis

## Scope

This document describes the repository as it exists before the modular
analytics-platform refactor. No application code was changed during this
analysis.

The repository contains 1,300+ tracked/discoverable files, most of which are
generated CSV/JSON data, cached source responses, reports, or historical raw
Fantrax exports. The executable Python architecture is much smaller and is
concentrated in the root launchers, `core/`, `config/`, and the presentation
modules now located under `views/`,
`analytics/`, `fantrax/`, `football_data/`, `integrations/`, and `scripts/`.

## Executive Summary

The application is in a compatibility-first transition rather than being a
fully modular Streamlit application.

- The supported Streamlit entry point is root `app.py`.
- `app.py` delegates the entire application to
  `core/legacy_renderer.py` with `runpy`.
- `core/legacy_renderer.py` owns configuration setup, season selection,
  navigation, styling, data loading, subprocess execution, helpers, and all
  eight page implementations in one file.
- `views/registry.py` is a real modular boundary for page metadata and
  season visibility, but there are no independent page renderer modules yet.
- Analytics builders have mostly been moved into domain packages under
  `fantrax/analytics/{core,manager,player,team}`, with compatibility wrappers
  retained at older import paths.
- Data ingestion and transformation are organized by source or workflow, but
  there is no shared application-level data repository/service layer.
- Draft analytics is only partly migrated: its stable module is a wrapper
  around a versioned script in `scripts/`.

The current runtime flow is:

```text
run_app.bat
    -> streamlit run app.py
        -> runpy(core/legacy_renderer.py)
            -> config + season context
            -> views/registry.py navigation metadata
            -> CSV/JSON/TXT/Parquet reads
            -> one of eight inline page branches
```

## Current Entry Points

### Supported Streamlit entry point

`app.py` is the current supported application entry point, as confirmed by
`README.md`, `README_V5.md`, and `run_app.bat`.

It does not construct the application itself. It resolves
`core/legacy_renderer.py` and executes that file as `__main__` using
`runpy.run_path`.

### Windows launcher

`run_app.bat` activates `.venv` and runs:

```text
python -m streamlit run app.py
```

### Command-line command center

Root `fantrax.py` exposes `app`, `refresh`, `analytics`, and `finalize`
commands. Its non-app commands invoke scripts in the current `fantrax/`
package. However, its `app` command still targets
`app/fantrax_data_app.py`, a path that is not present in this repository.
Consequently, `python fantrax.py app` is stale even though it remains
documented in `README.md`.

### Pipeline/module entry points

- `python -m fantrax.analytics.build_all` runs the primary analytics builders
  in dependency order.
- `python -m analytics.draft.builder` is the advertised stable draft-builder
  command, but delegates to
  `scripts/build_draft_tool_v1_2_2_2627.py`.
- `fantrax/refresh/refresh_all_fantrax_data.py` orchestrates refresh steps.
- `fantrax/finalize/finalize_fantrax_season_2526.py` freezes and validates a
  historical season.
- Source-specific scripts under `football_data/sources/`, `fantrax/scraping/`,
  and `fantrax/api/` provide ingestion and transformation commands.

## Configuration Modules

### `config/settings.py`

Contains application presentation and league defaults:

- app name and version
- league and sport names
- default season ID
- Streamlit page title, icon, and layout

### `config/project_paths.py`

Defines repository-wide path constants and season path helpers. It owns:

- project, package, configuration, data, raw, processed, analytics, reference,
  reports, and season roots
- loading `config/seasons.json`
- active-season selection
- helpers for season-specific processed, analytics, reference, and reports
  directories

There are two storage conventions represented here: older root
`raw_data/`, `processed_data/`, and `reports/` locations, and the newer
`data/raw`, `data/processed`, `data/analytics_views`, `data/reference`, and
`data/seasons/<season_id>` locations.

### `config/seasons.json`

Is the central season catalog. It currently defines:

- `2526` as enabled, data-ready, and finalized
- `2627` as enabled preseason with league data not yet ready
- `all_time` as disabled and not built

### `config/league_rules.py`

Is a backward-compatible wildcard import. Canonical roster and scoring rules
live in `fantrax/analytics/core/league_rules.py`.

### Source configuration

`football_data/sources/pundit/config.py` contains the Pundit page/source
configuration. Environment-based FootballData credentials are resolved by
`integrations/footballdata_client.py`.

### Configuration still embedded in scripts

Some workflow configuration remains local to individual scripts, including
season-specific filenames, API endpoints, scraper URLs, team definitions, and
draft model parameters. The large renderer also constructs its analytics file
catalog and important-output catalog inline rather than obtaining them from a
dedicated data/configuration module.

## Data Loading and Ingestion Modules

There is no single shared data-loading package for the Streamlit application.
Loading currently occurs at three levels.

### Application data access in `core/legacy_renderer.py`

The active UI defines these loaders directly:

- `scan_data_files()` recursively inventories configured season directories.
- `load_preview()` reads CSV, Parquet, JSON, and TXT files for the browser and
  health pages.
- `load_csv_cached()` is the cached CSV reader used by the analytics pages.
- `require_csv()` wraps the cached reader with a Streamlit warning.

The renderer also declares the processed and analytics filenames consumed by
each page. This couples UI rendering, data contracts, path resolution, caching,
and error presentation.

### Fantrax ingestion and preparation

- `fantrax/scraping/` downloads weekly available-player and team-roster exports
  and collects Understat data.
- `fantrax/api/` fetches Fantrax API data, flattens responses, builds player-ID
  bridges, merges roster data, transforms JSON, and validates outputs.
- `fantrax/refresh/` coordinates scraping and rebuilding current working data.
- `fantrax/analytics/core/build_master_weekly.py` reads raw/processed CSVs and
  creates the canonical weekly tables used downstream.

These modules generally read and write files directly with pandas rather than
through shared repositories or typed dataset contracts.

### External football-data ingestion

- `integrations/footballdata_client.py` is a reusable HTTP/API client with JSON
  persistence helpers.
- `integrations/footballdata_normalizer.py` discovers saved JSON and normalizes
  teams, players, team statistics, and matches into data frames.
- `football_data/common/http.py` provides a cached HTTP session.
- `football_data/common/export.py` provides CSV/JSON output helpers.
- `football_data/sources/pundit/` separates scraping, parsing, configuration,
  and orchestration.
- `football_data/sources/whoscored/probe.py` probes/exports WhoScored data.

### Data layout

- `data/raw/`: active raw source data and downloaded caches
- `data/processed/`: active intermediate/canonical tables
- `data/analytics_views/`: active derived presentation views
- `data/reference/` and `data/crosswalk/`: identity mappings and reference data
- `data/models/`: preseason/draft model outputs
- `data/quality/` and `data/reports/`: validation artifacts
- `data/seasons/2526/`: frozen historical raw indexes, processed tables,
  analytics views, references, reports, and a season manifest
- `raw_data/` and `processed_data/`: older compatibility-era locations still
  referenced by path configuration and some workflows

## Analytics Modules

### Canonical Fantrax analytics package

`fantrax/analytics/` is the main analytics domain.

`fantrax/analytics/core/` contains:

- `league_rules.py`: canonical roster constraints and position-sensitive
  scoring constants
- `scoring_engine.py`: position normalization, eligibility parsing, and
  position-sensitive scoring
- `optimizer.py`: legal-lineup optimization
- `metrics.py`: reusable efficiency and summary metrics
- `ownership_engine.py`: an initial ownership-period model
- `build_master_weekly.py`: construction of core weekly processed datasets

`fantrax/analytics/manager/` contains:

- `build_decision_views.py`
- `build_efficiency_ghost_awards_views.py`

`fantrax/analytics/player/` contains:

- `build_player_views.py`

`fantrax/analytics/team/` contains:

- `build_league_awards_views.py`

`fantrax/analytics/build_all.py` orchestrates the domain builders.
`fantrax/analytics/explorer/` currently contains only package scaffolding; the
actual explorer is still implemented inside the Managers page in the legacy
renderer.

### Compatibility analytics modules

The modules directly under `fantrax/analytics/` named
`build_*`, `optimizer.py`, and `scoring_engine.py` are thin wildcard-import
wrappers around the canonical subpackages. They preserve old imports and
script paths but are not independent implementations.

### Draft and football-strength analytics

The top-level `analytics/` package is separate from
`fantrax/analytics/`:

- `build_team_strength.py` derives team ratings from normalized football data.
- `build_fixture_strength.py` derives fixture difficulty.
- `draft/builder.py` is a compatibility launcher for the versioned draft
  script.

This split reflects two domains, but the package names do not make the boundary
explicit: one contains Fantrax league analytics and the other contains
football/draft modeling.

### Tests

- `tests/test_scoring_optimizer.py` covers scoring and lineup optimization.
- `tests/test_player_views.py` covers player-view building.

The current tests exercise a small portion of the analytics layer and do not
cover application navigation, loaders, season routing, or most builders.

## Page Modules

### Page registry

`views/registry.py` defines immutable page metadata:

- title
- icon
- available seasons
- whether season data is required
- description

It exposes `pages_for_season()` and `get_page()`. This registry controls what
the sidebar displays and correctly allows preseason/operations pages without
claiming that live season data exists.

`components/navigation.py` currently provides only a helper that extracts page
titles from page definitions.

### Actual page implementations

There are no modular page renderer files. All pages are top-level branches in
`core/legacy_renderer.py`:

| Page | Current responsibility |
| --- | --- |
| League Hub | Standings, cards, profiles, streaks, matchup extremes, weekly awards |
| Award Detail | Award selection, leaderboards, podiums, weekly winners, manager history |
| Managers | Manager dashboard, decisions, efficiency, roster/position/ghost/formation analysis, squad and embedded explorer |
| Draft HQ | Preseason rankings, filters, comparison and player detail |
| Update Pipeline | Runs refresh and analytics subprocesses or displays finalized-season metadata |
| Raw Data Browser | File discovery, preview, filtering, and CSV download |
| Key Output Health | Required-file checks and table summaries |
| Reports | Displays validation, finalization, refresh, and analytics reports |

The Managers branch is especially broad: it spans most of the renderer and
contains an analytics explorer that conceptually belongs under the currently
empty `fantrax/analytics/explorer/` or a dedicated page.

## Legacy Code and Replacement Candidates

The following items should be replaced or retired incrementally. “Replace”
means migrate behavior behind stable modules and validate parity before
removal, not delete immediately.

### 1. `core/legacy_renderer.py`

This is the primary legacy target. It is the active application, so it cannot
be removed first. Its responsibilities should be separated into:

- application bootstrap and season context
- shared data access/cache services
- shared UI components and formatting
- one renderer per registered page
- operation/pipeline services that are independent of Streamlit widgets

The existing registry provides the natural migration seam: each page can move
behind its `PageDefinition` while the remaining branches continue to use the
compatibility renderer.

### 2. Stale CLI application path in `fantrax.py`

The `app` command references missing `app/fantrax_data_app.py`. It should
eventually launch root `app.py`, or the final modular application entry point.
Documentation should then advertise one canonical launch path.

### 3. Versioned draft-builder scripts

These scripts represent successive copies of the same evolving pipeline:

- `scripts/build_draft_tool_v1_1_2627.py`
- `scripts/build_draft_tool_v1_2_2627.py`
- `scripts/build_draft_tool_v1_2_1_2627.py`
- `scripts/build_draft_tool_v1_2_2_2627.py`

`analytics/draft/builder.py` still executes the newest copy with `runpy`.
The implementation should move into importable modules under
`analytics/draft/`; old versions can then be archived as historical references.
The renderer’s missing-data warning also names the older v1.1 command instead
of the stable builder command.

### 4. Compatibility wrappers

The thin modules under `fantrax/analytics/` and `config/league_rules.py` are
intentional migration aids. Callers should move to canonical domain paths;
wrappers can be deprecated after imports and documented commands are updated.

### 5. Duplicate analytics logic

`fantrax/analytics/manager/build_efficiency_ghost_awards_views.py` contains its
own position normalization, scoring helpers, lineup data classes, legality
checks, and optimizer even though canonical scoring and optimizer modules now
exist under `fantrax/analytics/core/`. This duplication risks different rules
or results and should converge on the core engines after parity tests exist.

### 6. Archived and misplaced executable code

- `archive/old_apps/fantrax_data_appV1.py`
- `archive/old_scripts/merge_master_with_api_rosters.py`
- `archive/old_scripts/scrape_understat_player_match_stats_OLD.py`

These are explicitly historical and should not be runtime dependencies.

`data/processed/merge_master_with_api_rosters.py` is executable source stored
among generated data. Its supported replacement is
`fantrax/api/merge_master_with_api_rosters_v2.py`; the data-directory copy
should be treated as legacy once references are verified.

### 7. Experimental/test scripts used as operational tooling

Large files such as `scripts/test_soccerdata_2627.py`,
`scripts/test_footballdata_coverage.py`, and
`scripts/evaluate_api_football.py` are exploratory commands rather than unit
tests. Reusable ingestion/evaluation behavior should move into source or
integration modules, leaving small CLI wrappers. Automated assertions belong
under `tests/`.

### 8. Parallel storage conventions

The coexistence of `data/...`, `data/seasons/...`, `raw_data/...`,
`processed_data/...`, and root report paths is a compatibility concern.
`config/project_paths.py` currently exposes all of them. A modular platform
will need one explicit policy for active working data versus immutable
season snapshots, followed by migration of callers away from older locations.

## Architectural Risks

- The active UI has a very large import-time execution surface. Importing or
  executing the renderer configures Streamlit and immediately renders a page,
  which makes isolated testing difficult.
- UI code knows exact filenames and schemas for many derived tables.
- Builders embed direct file I/O and season-specific assumptions, limiting
  reuse for future seasons.
- Streamlit can launch data-mutating subprocesses directly from the renderer;
  command construction and execution are not separated into an operations
  service.
- Page metadata and page behavior can drift because registry entries and
  renderer branches are maintained separately.
- Encoding artifacts are visible in icons and display-cleaning logic, which
  suggests inconsistent source-file encoding during previous migrations.
- Documentation is inconsistent: `README.md` advertises a stale CLI app path,
  while `README_V5.md` documents the working root launcher.

## Recommended Refactor Boundaries

Without changing behavior, the current system naturally divides into:

1. **Application shell**: Streamlit setup, global season selection, navigation,
   and routing.
2. **Page package**: one page module per registry entry with a small,
   consistent render interface.
3. **Data access layer**: season-aware dataset catalog, cached readers, schema
   validation, and missing-data results independent of Streamlit.
4. **Analytics domain**: pure scoring, optimization, metrics, and view-building
   functions.
5. **Ingestion/integrations**: Fantrax, Understat, Pundit, WhoScored, and
   FootballData adapters.
6. **Operations layer**: refresh, rebuild, finalize, reporting, and subprocess
   orchestration.
7. **Configuration**: typed settings, season catalog, league rules, dataset
   paths, and source credentials.

The safest migration order is to extract shared loaders and page renderers
behind the existing root launcher and page registry, then replace duplicated
analytics and versioned scripts. This preserves the working UI while reducing
the compatibility renderer one page at a time.
