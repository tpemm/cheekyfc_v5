# DatasetRegistry

## Status

DatasetRegistry is the production catalog used by DataManager and all migrated
display pages. It is the single source of truth for logical dataset metadata;
analytics builders and refresh commands continue producing their existing
physical outputs during the compatibility phase.

Implementation:

- model: `core/models/dataset_definition.py`
- service: `core/services/dataset_registry.py`
- tests: `tests/test_dataset_registry.py`

## Purpose

DatasetRegistry is the single catalog of logical dataset metadata. It gives
datasets stable keys that do not depend on physical directory layout.

The registry contains metadata only. It does not read files, resolve project
paths, load data frames, write artifacts, or calculate analytics. Those
responsibilities belong to future services and existing producers.

## DatasetDefinition

Each immutable definition contains:

| Field | Meaning |
| --- | --- |
| `key` | Canonical lowercase snake-case identifier |
| `display_name` | Human-readable name |
| `description` | Concise purpose and content |
| `classification` | Data lifecycle/type classification |
| `namespace` | Logical storage namespace |
| `filename_template` | Filename only; may contain `{season_id}` |
| `required` | Whether the dataset is part of its core contract |
| `producer` | Module or workflow that creates it |
| `consumers` | Pages or analytics that use it |
| `aliases` | Legacy or alternate logical names |
| `cacheable` | Whether a future DataManager may cache reads |
| `mutable` | Whether the logical working artifact can change |
| `schema_name` | Stable identifier for future schema validation |
| `working_subdirectory` | Registered relative directory below a working season root |
| `snapshot_subdirectory` | Registered relative directory below a snapshot root |
| `required_columns` | Initial tabular schema requirements |
| `family` | Whether the filename template identifies a file family |

Definitions use frozen, slotted dataclasses. Consumers cannot accidentally
change shared metadata.

## Implemented Datasets

The registry contains 43 core datasets after the Sprint 2.5 Draft HQ
migration.
The first 24 were introduced in Sprint 1.0; 13 existing analytics artifacts
were registered in Sprint 2.0, followed by four additional stable report
definitions and one registered report family in Sprint 2.1. Sprint 2.5 added
the optional curated draft eligibility override consumed by the existing
Draft HQ page.

### Processed

| Key | Filename template |
| --- | --- |
| `master_player_weekly` | `master_player_weekly_{season_id}.csv` |
| `manager_player_weekly` | `manager_player_weekly_{season_id}.csv` |
| `manager_week_summary` | `manager_week_summary_{season_id}.csv` |
| `manager_season_summary` | `manager_season_summary_{season_id}.csv` |
| `matchup_week_summary` | `matchup_week_summary_{season_id}.csv` |
| `lineup_quality_summary` | `lineup_quality_summary_{season_id}.csv` |

Classification and namespace are both `processed`.

### Analytics

| Key | Filename |
| --- | --- |
| `league_table` | `league_table.csv` |
| `weekly_awards` | `weekly_awards.csv` |
| `award_leaderboards` | `award_leaderboards.csv` |
| `manager_profile_summary` | `manager_profile_summary.csv` |
| `manager_streaks` | `manager_streaks.csv` |
| `lineup_changes` | `lineup_changes.csv` |
| `closest_games` | `closest_games.csv` |
| `biggest_blowouts` | `biggest_blowouts.csv` |
| `league_hub_cards` | `league_hub_cards.csv` |
| `manager_efficiency_weekly` | `manager_efficiency_weekly_v2.csv` |
| `lineup_decision_details` | `lineup_decision_details_v2.csv` |
| `manager_efficiency_season` | `manager_efficiency_season.csv` |
| `ghost_points_player_leaders` | `ghost_points_player_leaders.csv` |
| `ghost_points_manager_weekly` | `ghost_points_manager_weekly.csv` |
| `ghost_points_manager_season` | `ghost_points_manager_season.csv` |
| `position_points_manager_season` | `position_points_manager_season.csv` |
| `roster_adds_weekly` | `roster_adds_weekly.csv` |
| `roster_adds_leaders` | `roster_adds_leaders.csv` |
| `manager_awards_dynamic` | `manager_awards_dynamic.csv` |
| `manager_behavior_weekly` | `manager_behavior_weekly.csv` |
| `manager_behavior_season` | `manager_behavior_season.csv` |
| `formation_weekly` | `formation_weekly.csv` |
| `formation_manager_summary` | `formation_manager_summary.csv` |
| `formation_league_summary` | `formation_league_summary.csv` |

Classification and namespace are both `analytics`.

Behavior and formation definitions are optional because their expected
producers are not present in the current repository. Their missing status
remains visible on Key Output Health.

### Reference

| Key | Filename template |
| --- | --- |
| `scoring_periods` | `fantrax_scoring_periods_{season_id}.csv` |
| `api_player_bridge` | `api_to_master_player_id_bridge_{season_id}.csv` |
| `understat_crosswalk` | `understat_fantrax_player_id_map.csv` |
| `draft_eligibility_overrides` | `draft_eligibility_overrides_{season_id}.csv` |

Classification and namespace are both `reference`. The eligibility override
uses the explicit `imports/draft` subdirectory rather than the default
reference directory.

### Draft

| Key | Classification | Namespace | Filename template |
| --- | --- | --- | --- |
| `draft_rankings` | `model` | `draft` | `draft_rankings_{season_id}.csv` |
| `draft_player_pool` | `model` | `draft` | `draft_player_pool_{season_id}.csv` |

### Reports and manifests

| Key | Classification | Namespace | Filename template |
| --- | --- | --- | --- |
| `season_manifest` | `manifest` | `reports` | `season_manifest.json` |
| `api_merge_report` | `report` | `reports` | `api_merge_validation_report_{season_id}.txt` |
| `finalization_validation_report` | `report` | `reports` | `finalization_validation_report.txt` |
| `league_awards_report` | `report` | `reports` | `league_awards_report.txt` |
| `efficiency_ghost_awards_report` | `report` | `reports` | `efficiency_ghost_awards_report.txt` |
| `formation_report` | `report` | `reports` | `formation_report.txt` |
| `recent_season_reports` | `report` | `reports` | `*.txt` |

`recent_season_reports` is an optional family for TXT files directly inside a
season reports directory. Stable definitions remain separate so Reports can
preserve its fixed ordering before the recent-report list. This also preserves
the legacy duplicate finalization-report choice when that file is both a fixed
artifact and a recent family member.

## Aliases

Aliases resolve to canonical keys before lookup.

| Alias | Canonical key |
| --- | --- |
| `master_weekly` | `master_player_weekly` |
| `manager_efficiency_weekly_v2` | `manager_efficiency_weekly` |
| `manager_efficiency_weekly_legacy` | `manager_efficiency_weekly` |
| `lineup_decision_details_v2` | `lineup_decision_details` |
| `lineup_decision_details_legacy` | `lineup_decision_details` |
| `api_to_master_player_id_bridge` | `api_player_bridge` |
| `api_player_id_bridge` | `api_player_bridge` |
| `understat_fantrax_player_id_map` | `understat_crosswalk` |
| `finalization_manifest` | `season_manifest` |
| `api_merge_validation_report` | `api_merge_report` |

Aliases identify logical datasets; they do not select alternate physical files.
A future DataManager will own compatibility path fallback.

## Public API

### `DatasetRegistry()`

Creates and validates the default core registry.

An iterable of `DatasetDefinition` objects may be supplied to create an
isolated registry for tests or future approved extensions.

### `get(key)`

Returns a definition by canonical key or alias. Raises `KeyError` for an
unknown value.

### `list_all()`

Returns an immutable tuple in deterministic registration order.

### `find_by_classification(classification)`

Returns all definitions with an exact classification match.

### `find_by_namespace(namespace)`

Returns all definitions in an exact logical namespace.

### `resolve_alias(key)`

Returns the canonical key for an alias. A canonical or unknown key is returned
unchanged; use `get()` when existence must be enforced.

### `describe(key)`

Returns a concise human-readable description including classification,
namespace, requirement status, and filename template.

### `validate()`

Checks every definition and rebuilds the lookup indexes. It raises
`RegistryValidationError` for:

- duplicate keys;
- duplicate or conflicting aliases;
- invalid keys or aliases;
- blank required metadata;
- filename templates containing directory paths;
- objects that are not DatasetDefinition instances.

## Extension Rules

Future registry additions should:

1. Use a semantic logical key, not a versioned filename.
2. Keep physical directory information out of `filename_template`; declare it
   in the working/snapshot subdirectory fields.
3. Prefer aliases for legacy logical names.
4. Identify one authoritative producer.
5. Name actual consumers rather than speculative ones.
6. Use a stable `schema_name` when the dataset has a tabular contract.
7. Add lookup, classification, namespace, and integrity tests.

Sprint 1.2 added the final four metadata fields above without changing any
existing key, alias, or constructor requirement. They allow DataManager to
resolve paths and validate simple schemas without guessing filesystem layout.

DatasetRegistry must remain independent of pandas, Streamlit, filesystem path
resolution, analytics calculations, and data loading.
