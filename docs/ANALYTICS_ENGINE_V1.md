# Analytics Engine v1: Position-Aware Lineup Optimization

## What this version adds

- Canonical league rules in `config/league_rules.py`.
- Position-aware scoring in `fantrax/analytics/scoring_engine.py`.
- A legal 11-player optimizer in `fantrax/analytics/optimizer.py`.
- A manager decision builder in `fantrax/analytics/build_manager_decision_views.py`.
- Validation tests in `tests/test_scoring_optimizer.py`.

## League constraints

- 16 total roster spots
- 11 active starters
- 4 reserves
- 1 injured-reserve player
- Exactly 1 goalkeeper
- 3–5 defenders
- 2–5 midfielders
- 1–3 forwards

## Incomplete waiver-player statistics

The all-player weekly exports contain official Fantrax points and eligible
positions for waiver players, but not the complete event-level Fantrax stat
line. The team-roster weekly exports contain the detailed stats needed for
position-dependent scoring.

The scoring engine therefore uses this rule:

1. The exported Fantrax score is always the authoritative score at the player's
   actual position.
2. For rostered players with detailed event stats, the engine removes the
   position-sensitive scoring component and adds it back at each other eligible
   position.
3. For waiver players without detailed stats, the official points remain usable
   for rankings and waiver analysis, but the engine does not invent a
   hypothetical score at another position.

This prevents missing waiver statistics from corrupting manager lineup
efficiency while preserving all available-player point totals.

## New outputs

- `data/analytics_views/manager_efficiency_weekly_v2.csv`
- `data/analytics_views/lineup_decision_details_v2.csv`
- `data/analytics_views/manager_decision_validation_report.txt`

The v2 suffix is intentional so the existing dashboard is not silently changed
before the new results are reviewed.

## Validation result on the uploaded 2025/26 project

- 456 manager-week groups processed
- 456 legal optimal lineups found
- 6,771 rostered player-week rows position-rescored
- 0 optimizer failures
