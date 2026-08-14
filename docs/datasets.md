# Dataset Catalog

Completed-draft definitions: `draft_results`, immutable `draft_day_rankings_snapshot`, `draft_pick_grades`, `draft_manager_grades`, `draft_category_scores`, `draft_awards`, and `draft_match_report`. The fixed grading pipeline produces them and Draft HQ consumes them through `DataManager`.

This catalog reflects the 49 definitions currently returned by
`DatasetRegistry`. A definition does not guarantee that a physical artifact
exists for every season. Dataset definitions do not contain individual season
allowlists: `SeasonManager` resolves a configured season and namespace, and
`DataManager` reports actual availability.

Paths below are working-root-relative registered patterns. `{season_id}` is
resolved from the selected season. For finalized seasons, the corresponding
snapshot subdirectory contract is used.

## Registry names and descriptions

The following display names and descriptions are copied from the current
DatasetRegistry definitions.

| Key | Display name | Registered description |
| --- | --- | --- |
| `master_player_weekly` | Master Player Weekly | Canonical player-by-gameweek table combining Fantrax and Understat data. |
| `manager_player_weekly` | Manager Player Weekly | Player-week facts enriched with manager ownership and lineup status. |
| `manager_week_summary` | Manager Week Summary | Manager-level scoring and result summary for each gameweek. |
| `manager_season_summary` | Manager Season Summary | Season-to-date manager performance summary. |
| `matchup_week_summary` | Matchup Week Summary | Head-to-head matchup results and scores by gameweek. |
| `lineup_quality_summary` | Lineup Quality Summary | Manager lineup completeness and quality checks by gameweek. |
| `league_table` | League Table | Presentation-ready league standings. |
| `weekly_awards` | Weekly Awards | Award winners calculated for each gameweek. |
| `award_leaderboards` | Award Leaderboards | Season award standings and counts. |
| `manager_profile_summary` | Manager Profile Summary | Consolidated manager performance and style metrics. |
| `manager_streaks` | Manager Streaks | Winning, losing, and scoring streaks for managers. |
| `lineup_changes` | Lineup Changes | Week-over-week manager lineup changes. |
| `closest_games` | Closest Games | Smallest winning margins across league matchups. |
| `biggest_blowouts` | Biggest Blowouts | Largest winning margins across league matchups. |
| `league_hub_cards` | League Hub Cards | Presentation-ready headline metrics for the League Hub. |
| `manager_efficiency_weekly` | Manager Efficiency Weekly | Preferred weekly lineup-efficiency view. |
| `lineup_decision_details` | Lineup Decision Details | Preferred player-level lineup decision and optimization detail. |
| `manager_efficiency_season` | Manager Efficiency Season | Season-level manager lineup-efficiency summary. |
| `ghost_points_player_leaders` | Ghost Points Player Leaders | Player leaderboard for unrostered fantasy points. |
| `ghost_points_manager_weekly` | Ghost Points Manager Weekly | Weekly manager totals for missed unrostered-player points. |
| `ghost_points_manager_season` | Ghost Points Manager Season | Season manager totals for missed unrostered-player points. |
| `position_points_manager_season` | Position Points Manager Season | Manager scoring totals by player position for the season. |
| `roster_adds_weekly` | Roster Adds Weekly | Weekly player additions by manager. |
| `roster_adds_leaders` | Roster Adds Leaders | Season leaderboard for roster additions. |
| `manager_awards_dynamic` | Manager Awards Dynamic | Derived manager awards and supporting metrics. |
| `manager_behavior_weekly` | Manager Behavior Weekly | Weekly manager behavior metrics. |
| `manager_behavior_season` | Manager Behavior Season | Season-level manager behavior metrics. |
| `formation_weekly` | Formation Weekly | Weekly manager formation selections and results. |
| `formation_manager_summary` | Formation Manager Summary | Manager-level formation usage summary. |
| `formation_league_summary` | Formation League Summary | League-level formation usage summary. |
| `scoring_periods` | Fantrax Scoring Periods | Mapping between Fantrax gameweeks and scoring-period dates. |
| `api_player_bridge` | API Player Bridge | Crosswalk from Fantrax API player IDs to canonical Fantrax player IDs. |
| `understat_crosswalk` | Understat–Fantrax Crosswalk | Curated identity map between Understat and Fantrax players. |
| `draft_rankings` | Draft Rankings | Ranked preseason player recommendations for the target draft season. |
| `draft_player_pool` | Draft Player Pool | Enriched player pool used to calculate draft rankings. |
| `draft_eligibility_overrides` | Draft Eligibility Overrides | Optional curated overrides for current-season draft eligibility. |
| `current_squad_snapshot` | Current Squad Snapshot | Cached provider-neutral current Premier League player population. |
| `player_registry` | Player Registry | Canonical season-aware player identity and current-club registry. |
| `player_registry_quality` | Player Registry Quality Report | Aggregate validation and coverage metrics for the Player Registry. |
| `player_registry_unresolved` | Player Registry Unresolved | Unresolved and ambiguous player identity diagnostics. |
| `player_identity_review` | Player Identity Review | Ranked, non-binding current-player candidates for unresolved identities. |
| `player_alias_overrides` | Player Alias Review Decisions | Audited pair-specific approvals and ignored identity suggestions. |
| `season_manifest` | Season Manifest | Immutable inventory and checksums for a finalized season snapshot. |
| `finalization_validation_report` | Finalization Validation Report | Validation summary generated when a season snapshot is finalized. |
| `api_merge_report` | API Merge Validation Report | Human-readable validation report for the Fantrax API roster merge. |
| `league_awards_report` | League Awards Report | Validation and output summary for league awards analytics. |
| `efficiency_ghost_awards_report` | Efficiency and Ghost Awards Report | Validation summary for efficiency, ghost-points, and manager awards. |
| `formation_report` | Formation Report | Validation summary for formation analytics. |
| `recent_season_reports` | Recent Season Reports | Text reports stored directly in a season reports directory. |

## Loading and validation behavior

- Required missing artifacts raise/report a required-dataset failure.
- Optional missing artifacts return a structured `MISSING` result and warning.
- Zero-byte artifacts return `EMPTY`; consumers decide whether optional empty
  data is usable.
- CSV and Parquet frames are checked against declared `required_columns`.
- No dataset currently declares optional-column metadata; columns not listed as
  required remain producer-defined.
- Cached results are defensive copies and are invalidated when file signatures
  change or when `DataManager.invalidate()` is called.
- “Source/manual” below means no registered producer; it does not imply that the
  file is safe to overwrite.

## Processed historical and weekly datasets

| Key | Registered path | Req. | Producer | Consumers |
| --- | --- | --- | --- | --- |
| `master_player_weekly` | `processed/master_player_weekly_{season_id}.csv` | Yes | `fantrax.analytics.core.build_master_weekly` | manager, player, Draft analytics |
| `manager_player_weekly` | `processed/manager_player_weekly_{season_id}.csv` | Yes | `fantrax.api.merge_master_with_api_rosters_v2` | Managers, team/manager analytics |
| `manager_week_summary` | `processed/manager_week_summary_{season_id}.csv` | Yes | API roster merge | League Hub, Managers, team analytics |
| `manager_season_summary` | `processed/manager_season_summary_{season_id}.csv` | Yes | API roster merge | team/manager analytics |
| `matchup_week_summary` | `processed/matchup_week_summary_{season_id}.csv` | Yes | API roster merge | League Hub, Managers, team analytics |
| `lineup_quality_summary` | `processed/lineup_quality_summary_{season_id}.csv` | Yes | API roster merge | Managers, Key Output Health |

These are generated working datasets. Their registry definitions do not declare
column-level schemas beyond an associated schema name.

## League, manager, and player analytics

All paths in this group are below `analytics_views/`.

| Key | Filename | Req. | Producer | Primary consumers |
| --- | --- | --- | --- | --- |
| `league_table` | `league_table.csv` | Yes | league awards builder | League Hub, Managers |
| `weekly_awards` | `weekly_awards.csv` | Yes | league awards builder | League Hub, Award Detail |
| `award_leaderboards` | `award_leaderboards.csv` | Yes | league awards builder | League Hub, Award Detail |
| `manager_profile_summary` | `manager_profile_summary.csv` | Yes | efficiency/ghost builder | League Hub, Managers |
| `manager_streaks` | `manager_streaks.csv` | Yes | league awards builder | League Hub, Award Detail, Managers |
| `lineup_changes` | `lineup_changes.csv` | Yes | league awards builder | League Hub, manager analytics |
| `closest_games` | `closest_games.csv` | Yes | league awards builder | League Hub, Award Detail |
| `biggest_blowouts` | `biggest_blowouts.csv` | Yes | league awards builder | League Hub, Award Detail |
| `league_hub_cards` | `league_hub_cards.csv` | Yes | league awards builder | League Hub |
| `manager_efficiency_weekly` | `manager_efficiency_weekly_v2.csv` | Yes | decision views builder | Managers |
| `lineup_decision_details` | `lineup_decision_details_v2.csv` | Yes | decision views builder | Managers |
| `manager_efficiency_season` | `manager_efficiency_season.csv` | Yes | efficiency/ghost builder | health, manager analytics |
| `ghost_points_player_leaders` | `ghost_points_player_leaders.csv` | Yes | efficiency/ghost builder | health, manager analytics |
| `ghost_points_manager_weekly` | `ghost_points_manager_weekly.csv` | Yes | efficiency/ghost builder | Managers, health |
| `ghost_points_manager_season` | `ghost_points_manager_season.csv` | Yes | efficiency/ghost builder | health, manager analytics |
| `position_points_manager_season` | `position_points_manager_season.csv` | Yes | efficiency/ghost builder | Managers, health |
| `roster_adds_weekly` | `roster_adds_weekly.csv` | Yes | efficiency/ghost builder | Managers, health |
| `roster_adds_leaders` | `roster_adds_leaders.csv` | Yes | efficiency/ghost builder | health, manager analytics |
| `manager_awards_dynamic` | `manager_awards_dynamic.csv` | Yes | efficiency/ghost builder | health, manager analytics |
| `manager_behavior_weekly` | `manager_behavior_weekly.csv` | No | Not registered | Managers, health |
| `manager_behavior_season` | `manager_behavior_season.csv` | No | Not registered | Managers, health |
| `formation_weekly` | `formation_weekly.csv` | No | Not registered | Managers, health |
| `formation_manager_summary` | `formation_manager_summary.csv` | No | Not registered | Managers, health |
| `formation_league_summary` | `formation_league_summary.csv` | No | Not registered | health |

The first 19 are generated outputs with registered producers. The five optional
behavior/formation artifacts have no producer recorded in DatasetRegistry, so
this document does not infer one.

## Reference, current-squad, and identity datasets

| Key | Registered path | Req. | Producer/type | Required columns |
| --- | --- | --- | --- | --- |
| `scoring_periods` | `reference/fantrax_scoring_periods_{season_id}.csv` | Yes | Source/manual, immutable | None declared |
| `api_player_bridge` | `reference/api_to_master_player_id_bridge_{season_id}.csv` | Yes | name-based API bridge builder | None declared |
| `understat_crosswalk` | `reference/understat_fantrax_player_id_map.csv` | Yes | Source/manual | None declared |
| `current_squad_snapshot` | `reference/current_squads/fpl_players_{season_id}.csv` | Yes | current-squad builder | provider ID, name, team, position, active flag, provider, retrieval time, season |
| `player_registry` | `reference/player_registry_{season_id}.csv` | Yes | Player Registry builder | registry ID, canonical name, status, method, confidence, season |
| `player_registry_quality` | `quality/player_registry_{season_id}/player_registry_quality_report.csv` | No | Player Registry builder | `metric`, `value` |
| `player_registry_unresolved` | `quality/player_registry_{season_id}/player_registry_unresolved.csv` | No | Player Registry builder | None declared |
| `player_identity_review` | `reference/player_registry/player_identity_review_{season_id}.csv` | No | identity-review builder | season, registry/Fantrax IDs, names, candidate ID/name, score/class, uniqueness, review status |
| `player_alias_overrides` | `reference/player_registry/player_alias_overrides_{season_id}.csv` | No | Identity Review | season, both identities/IDs, decision, note, time, source |
| `draft_eligibility_overrides` | `imports/draft/draft_eligibility_overrides_{season_id}.csv` | No | Source/manual | None declared |

`player_alias_overrides` is user-managed, pair-specific reference data.
Built-in reviewed aliases remain in code. Neither overrides nor generated
registry/review reports should be edited through arbitrary page or filesystem
access.

## Draft model outputs

| Key | Registered path | Producer | Consumers |
| --- | --- | --- | --- |
| `draft_player_pool` | `models/draft_{season_id}/draft_player_pool_{season_id}.csv` | `analytics.draft.builder` | Draft HQ, Draft builder |
| `draft_rankings` | `models/draft_{season_id}/draft_rankings_{season_id}.csv` | `analytics.draft.builder` | Draft HQ |

Both are required, mutable generated outputs. DatasetRegistry currently
associates schema names but declares no required columns for them. Rebuild them
through `build_draft_outputs`; never inject ranks or edit formulas in the files.

## Manifests and reports

| Key | Registered path/pattern | Req. | Mutable | Producer |
| --- | --- | --- | --- | --- |
| `season_manifest` | `seasons/{season_id}/season_manifest.json` | Yes | No | season finalizer |
| `finalization_validation_report` | `seasons/{season_id}/reports/finalization_validation_report.txt` | No | No | season finalizer |
| `api_merge_report` | `processed/api_merge_validation_report_{season_id}.txt` | Yes | Yes | API roster merge |
| `league_awards_report` | `seasons/{season_id}/analytics_views/league_awards_report.txt` | No | Yes | league awards builder |
| `efficiency_ghost_awards_report` | `seasons/{season_id}/analytics_views/efficiency_ghost_awards_report.txt` | No | Yes | efficiency/ghost builder |
| `formation_report` | `seasons/{season_id}/analytics_views/formation_report.txt` | No | Yes | Not registered |
| `recent_season_reports` | `seasons/{season_id}/reports/*.txt` | No | Yes | Not registered; file family |

The report family is loaded through the bounded family APIs. Manifest and
finalization report definitions are immutable snapshot contracts.

## Update operations and downstream dependencies

- Fantrax refresh and analytics operations produce the processed and analytics
  families used by league, manager, health, and report views.
- `refresh_current_squad` writes `current_squad_snapshot`.
- `build_player_registry` writes registry, quality, and unresolved artifacts.
- `generate_identity_review` reads registry, current squads, optional Draft
  rankings, and decisions; it writes the review artifact.
- `save_identity_review_decision` updates only the registered decision store.
- `build_draft_outputs` consumes the registry and contextual inputs and writes
  the two Draft outputs.

See [operations.md](operations.md) for exact registered operations and safe
sequences.
# Live-season 2026/27 additions

The registered live model namespace resolves under `data/models/season_{season_id}`. New keys are `league_teams`, `current_rosters`, `roster_history`, `league_standings`, `weekly_matchups`, `manager_week_summary`, `league_transactions`, `player_ownership`, and `live_season_manifest`. They are optional until a validated source refresh/build succeeds. Declared producer is `fantrax.live.pipeline`; consumers are League Hub, Players, Managers, Draft HQ tracking, Trade Tool, Update Pipeline, and Key Output Health as recorded in DatasetRegistry.

Finalized 2025/26 `manager_week_summary` continues resolving from its snapshot `processed` directory; only the mutable working-season path now resolves to the season model directory.
# Live roster tracking datasets

- `current_rosters`: one row per player in the authoritative current snapshot, including registry identity and lineup flags.
- `roster_change_events`: append-only deterministic events between distinct snapshots.
- `roster_history`: continuous manager/roster/lineup intervals with open and close event IDs.
- `player_ownership`: reconciled Rostered, Free Agent, or Unresolved state plus draft origin and change counts.
- `roster_snapshots_manifest`: latest snapshot/checksum-chain status.
- `roster_tracking_quality`: current roster, event ID, ownership, and snapshot-chain checks.
# Sprint 7.4 registered models

- `live_player_analytics`: one row per represented Fantrax player with stable-ID joins.
- `live_manager_analytics`: centralized current-roster aggregates for all league teams.
- `live_position_strength`: one canonical position assignment per rostered player.
- `available_players`: free-agent subset of the canonical player frame.

`manager_player_weekly` remains registered metadata only for 2026/27 until weekly player statistics exist.
# Historical player presentation inputs

- `master_player_weekly` (`2526`, snapshot namespace): finalized universal player-week identity and official fantasy points.
- `draft_day_rankings_snapshot` (`2627`, working namespace resolving to the immutable draft snapshot): matched finalized 2025/26 detailed history plus separately labeled 2026/27 draft context.

No new finalized CSV is created. The presentation frame is deterministic and cached in memory, and missing source values remain null.
# Sprint 8.4 registrations

| Key | Path | Grain | Preseason |
| --- | --- | --- | --- |
| `current_player_weekly` | `data/models/season_2627/current_player_weekly_2627.csv` | player × completed period | schema-only |
| `manager_player_weekly` | `data/models/season_2627/manager_player_weekly_2627.csv` | manager × player × completed period | schema-only |
| `fantrax_stat_dictionary` | `data/reference/fantrax_stat_dictionary_2627.csv` | configured Fantrax stat/position rule | populated from league metadata |
# Supplemental live registrations

| Key | Path | Grain | Preseason |
| --- | --- | --- | --- |
| `understat_player_weekly` | `data/models/season_2627/understat_player_weekly_2627.csv` | player × authoritative Fantrax period | schema-only |

`player_source_coverage_2627.csv` records player-level source coverage. Its companion summary reports the entire pool separately from the evidence-based fantasy-relevant subset.

`weekly_period_status_2627.csv` records cache/finalization/checksum status for current and completed Fantrax periods. `current_player_weekly` consumes only validated `period_XX/weekly_player_stats.csv` caches.
# Live manager presentation datasets

`live_manager_analytics`, `manager_week_summary`, `manager_player_weekly`, and
`live_position_strength` support the 2026/27 Managers page. They are registered
DataManager datasets produced by the cache-only live pipeline.
`live_league_summary` contains one row per live manager and supports League Hub
standings, movement, form, scoring and roster context without view-time rebuilds.
`manager_draft_origin_validation_2627.csv` audits all live managers against frozen
draft identities and current ownership, including retained, acquired, dropped,
unresolved and reconciliation counts.
