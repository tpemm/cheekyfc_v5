# Player Analytics Engine v1

## Purpose

Build dashboard-ready player tables from `data/processed/master_player_weekly_2526.csv` without pretending that waiver players have detailed Fantrax event statistics that are not present in the exports.

## Data availability rule

- Official Fantrax fantasy points are available for every player-week.
- Complete Fantrax event statistics are available only for rostered player-weeks.
- Understat fields are used where matched, but remain separate from Fantrax event-stat coverage.
- Hypothetical position scoring is only calculated for rostered player-weeks with the required event line.
- Missing waiver statistics remain missing; they are never converted to zeros.

## Builder

```bash
python -m fantrax.analytics.build_player_views
```

## Outputs

All outputs are written to `data/analytics_views/player/`.

### `player_weekly.csv`

Grain: one player + one gameweek.

Contains official points for all players, roster/manager status, starts, available detailed stats, Understat fields, and explicit coverage flags.

### `player_season_summary.csv`

Grain: one player + season.

Contains total points, averages, ceiling, rostered weeks, league starts, ownership count, and detailed-stat coverage.

### `player_manager_summary.csv`

Grain: one manager + one player.

Contains ownership span, rostered weeks, starts, bench weeks, points while owned, starter points, bench points, start rate, and points per start.

### `player_position_weekly.csv`

Grain: one rostered player + gameweek + eligible scoring position.

Contains the official score and the score the player would have received at each eligible position. The actual-position row must always equal the official Fantrax score.

### `player_data_coverage.csv`

Documents how much data is available for all, rostered, and waiver/unrostered player-week rows.

## Validation from the current season

- 34,423 player-week rows
- 34,423 unique player-week keys
- 921 season-summary rows
- 578 manager-player rows
- 9,651 position-candidate rows
- 7,165 rostered rows with complete Fantrax event statistics
- 27,258 official-points-only rows
