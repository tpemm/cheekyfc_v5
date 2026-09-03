# Team matchup source audit

Audit date: 2026-08-19, before the first 2026/27 Premier League match.

## Fantrax

`current_player_weekly_2627.csv` has a production schema for fantasy points, Ghost points, appearances, starts, minutes, goals, assists, shots/SOT, key passes, crosses, dribbles, tackles, interceptions, clearances, blocks, aerials, cards, clean sheets, goalkeeper events, club, opponent, position, period, xG/xA supplements, field-level provenance, and period completion. It currently contains zero rows. Fantrax remains the fantasy authority.

## Understat

The live weekly schema supports player xG, xA, xGI, shots, key passes, goals, assists, minutes, and mapped period. Current player and team match observations are empty before completed matches. The existing 2026/27 soccerdata probe returned structurally empty frames. Understat remains the expected-stat authority; no historical value is presented as current observation.

## Sofascore

soccerdata 1.9.1 exposes `read_schedule`, `read_league_table`, `read_leagues`, and `read_seasons`. Schedule coverage is complete. It does not expose team match stats, player match stats, lineups, formations, substitutions, events, or average positions in this installed reader. No page performs live acquisition.

## WhoScored

soccerdata 1.9.1 exposes schedule, event, missing-player, stage, and season methods through a Selenium-backed reader. The project has no reproducible 2026/27 schedule or event cache, so no prototype match is promoted. Potential event fields remain unproven against real cached 2026/27 data.

Current quality artifacts distinguish `preseason`, `method unavailable`, and `blocked` from successful coverage.
# Sprint 9.2 historical POC update

One real WhoScored 2025/26 match is now cached and semantically validated. See
`whoscored_historical_poc_audit.md`. It remains POC-only and is not promoted
into current-season matchup values.
