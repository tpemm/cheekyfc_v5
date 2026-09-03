# Live player performance

The 2026/27 pipeline is cache-first. Refresh may update the three proven Fantrax raw responses; `fantrax.live.pipeline` reads those caches plus optional CSV files in `data/raw/fantrax/2627/player_stats/`. Pages read only registered model outputs.

## Datasets

`current_player_weekly` has one row per stable Fantrax player ID and completed scoring period. It retains identity, club, multi-position eligibility, owner/roster/lineup context, fantasy points, individual scoring events, Understat expected metrics, opponent, provenance, retrieval/build timestamps, and a completion flag. Missing source observations stay blank.

`manager_player_weekly` is a projection of those facts at manager-player-period grain. It is deliberately schema-only before authoritative weekly facts exist. It does not recreate `rosters_by_week.csv`.

Season and recent-form aggregates are derived from completed rows only. Supported windows are Season, Last 3, Last 5 and Last 10; short early-season windows are labeled, for example, `Last 5 (3 available)`. Supported numeric bases are Total, Per Game, Per Start and Per 90. Zero or missing denominators produce blank rates.

## Source ownership

- Fantrax weekly export: authoritative fallback for fantasy score and configured scoring events until an official player-stat API is documented and proven equivalent.
- Understat: authoritative for xG, xA, xGI and the minutes denominator used for their per-90 rates.
- Player Registry: authoritative cross-source identity.
- Fantrax period roster cache: ownership and lineup state for the retrieved period.

## Ghost points

The live calculation reuses the finalized league scoring engine and the established definition:

`ghost_points = fantasy_points - goal_points - assist_points - clean_sheet_points`

Removed contributions use the season-versioned commissioner scoring configuration. Goals-against and all peripheral scoring remain Ghost. If fantasy score or any required return component is unavailable, Ghost Points remains blank. This avoids silently treating missing scoring components as zero.

## Players experience

Preseason presentation is unchanged while the weekly dataset is empty. Once facts exist, the Players page adds a shared completed-period window, current-season columns, a Current Performance profile section, and a compact rate-based 2025/26 versus 2026/27 comparison. Historical values and the frozen draft-day projection/rank/ADP context remain separate; current facts only overlay `current_*` fields.

The comparison catalog exposes current fantasy points, Ghost Points and xGI under the established Total/Per Game/Per Start/Per 90 basis. The same registered weekly dataset is ready to drive Available Players and 2–5 player comparisons without page HTTP calls or independently scaled source calculations.

## Quality and preseason behavior

The build writes player-week uniqueness/identity/minutes checks, stat coverage, manager-player-week checks, and Understat coverage under `data/quality/season_2627/`. An absent weekly source is a valid preseason condition: model files contain headers and zero rows, and no future or false zero-valued performance rows are generated.

## Supplemental Understat facts

The proven 2025/26 player-match schema contains player/team identity, match ID and kickoff, position, minutes, goals, own goals, shots, assists, key passes, cards, xG, xA, xG chain, and xG buildup. It does not contain a reliable starts field. The 2026/27 probe currently returns an intentional empty preseason result.

`understat_player_weekly` maps match timestamps into `getLeagueInfo.scoringPeriods` boundaries and then aggregates player × Fantrax period. It never assumes Understat/EPL gameweek equals Fantrax period, so rescheduled and multiple matches follow the authoritative date boundary. Identity requires an exact `understat_player_id` in Player Registry; name-only attachment is prohibited.

Approved analytical fallback fields are appearances, minutes, goals, assists, shots, key passes, and cards. Fantrax wins whenever present—including explicit zero. Source-specific values and `<metric>_source` are retained. Assists, key passes, minutes, appearances, and cards are analytically comparable but not proven scoring-equivalent; supplemental values never enter Fantrax fantasy or Ghost calculations. xG/xA/xGI remain Understat-primary.

Coverage is reported for the entire Fantrax pool and separately for an evidence-based fantasy-relevant population (rostered, drafted, projected for minutes, or historically active). This is a coverage filter, not a new score.

Validated finalized period caches now populate this dataset automatically after Refresh League. Raw Fantrax facts are normalized first, approved Understat supplementation follows, and only completed-period rows drive Season/Last 3/5/10 aggregations.
Manager roster rates use the shared completed-period player facts and ratio-of-sums
aggregation; no separate manager rate engine is maintained.
The live League Hub may display supported current free-agent facts only after
weekly data exists; missing preseason production is never rendered as zero.
## Players-page rate presentation

Per Game, Per Start, and Per 90 are presentation choices over the registered live analytical fields. They do not change fantasy-points, Ghost, xGI, projected-minutes, fixture, ownership, or historical formulas. Historical values are contextual profile data and never backfill preseason live production.
### Compact live profile

The scouting profile has a compact identity/header and six current decision metrics, followed by Overview, Performance, Playing Time, Advanced, Fixtures, History, and Ownership / Draft tabs. Preseason current production stays blank; historical radar/context, Minutes Outlook, fixtures, ownership, and draft context remain usable. Weekly production and minutes trends activate only from registered completed-period observations.
### Match-by-match performance

Performance now contains Points by Gameweek, Last 5, Home/Away rates, an authoritative Ghost/non-Ghost breakdown, and sortable Full Gameweek Stats. Current views require completed `period_complete` observations. Finalized 2025/26 detail uses the registered master weekly frame. Missing weeks and metrics remain missing rather than becoming zero.
### Overview dimensions

Overview summarizes exact production beside the radar and adds no secondary score or percentile-bar layer. Current production remains unavailable during preseason instead of borrowing historical values.
# Matchup observation use

Completed `current_player_weekly` facts feed positional allowed and recent playing-time features. Multi-position eligibility is reduced to one canonical primary group; weekly facts are never duplicated across groups. Current preseason files remain empty rather than zero-filled.
