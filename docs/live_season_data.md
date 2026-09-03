# 2026/27 live-season data foundation

## Flow and configuration

`Fantrax refresh → validated raw cache → cache-only normalization → Player Registry → validation/quality → DatasetRegistry → DataManager → pages`

`config/live_season_2627.json` owns season 2627, Cheeky FC, 12 managers, periods 1–38, roster/start/bench/IR rules, draft format, scoring reference, and active status. The authoritative team/manager IDs are discovered from the live league payload rather than guessed. `FANTRAX_LEAGUE_ID_2627` is required for refresh and intentionally has no committed value.

## Raw cache

Root: `data/raw/fantrax/2627/`, with `league`, `managers`, `rosters`, `matchups`, `standings`, `transactions`, `players`, and `lineups` domains as sources become available. Current automated files are:

- `league/league_metadata_2627_latest.json`
- `standings/standings_2627_latest.json`
- `rosters/rosters_2627_period_01.json` through period 38 as requested

Each JSON has adjacent metadata containing source, UTC retrieval timestamp, season, league ID, request type, validation state, and SHA-256. Payloads validate in memory and replace the last valid artifact atomically. Failed fetches/validation leave the previous cache untouched.

## Normalized datasets

All live models reside in `data/models/season_2627` and are registered. The builder writes league teams, current rosters, roster history, standings, weekly matchups, manager-week summary, transactions, and player ownership. It makes no HTTP calls. It creates advanced manager-week fields as blank with an explicit coverage label until lineup/stat inputs make them calculable.

Player rows join `data/reference/player_registry_2627.csv` by Fantrax ID. Missing links remain unresolved and appear in `data/quality/season_2627/unresolved_live_player_identities.csv`; frozen draft-day identity links are not modified.

Quality outputs include `live_season_quality_summary.csv`, unresolved identities, and dataset-specific roster, matchup, standings, transaction, ownership, and league-team reports. Blocking errors prevent normalized replacement. Warnings record unavailable optional sources such as transactions before a proven export exists.

`live_season_manifest_2627.json` records each dataset key/path, producer, rows, period range, source/build timestamps, checksum, and validation result.

## Validation summary

- Teams: 12 active, unique/nonblank manager and team IDs/names.
- Rosters: valid player IDs, one owner per period, maximum roster size, known lineup status, valid eligibility text.
- Standings: 12 teams when available, unique numeric ranks, nonnegative record/points fields.
- Matchups: unique IDs, one appearance per team/period, numeric completed scores, consistent winner.
- Transactions: unique IDs, parsed timestamp, normalized/explicit type; unresolved player references remain reviewable.
- Ownership: one current row per player, rostered/available exclusivity, exact current-roster agreement.

## Future consumer readiness and gaps

League Hub definitions are unchanged: table/rank/team/record/points/against/form, highlights, hot/cold manager, jester, high score, leaderboards, timeframe, awards, and records remain intact. The foundation supplies teams, standings, matchups, and manager-week facts; visual polish waits for real data.

The Player page can use identity, club, eligibility, ownership, roster/transaction history, draft position/projection, and future weekly production. Current-season fantasy/ghost/xG/xA/xGI rates require the weekly player-stat export and Understat integration.

Manager analysis can use rank/record/scores, league-position history, current/period rosters, transactions, and draft results. Expected record, luck, momentum, position scoring, optimal XI, start/sit, ghost points, and dropped-player outcomes require weekly player scoring and finalized lineups.
# Sprint 7.2 roster tracking

An ordinary roster refresh requests the API-declared current scoring period. If cached league metadata does not expose one, the conservative fallback is the earliest configured/available period; future-period payloads are never promoted to history merely because they exist. Full 1–38 acquisition is opt-in.

Each valid normalized current roster has a stable SHA-256 over sorted content excluding `observed_at`, retrieval/build timestamps, and validation status. A materially distinct checksum creates an immutable CSV plus adjacent metadata under `data/snapshots/season_2627/rosters`. Metadata links the preceding distinct checksum. The first snapshot is a baseline and creates ownership intervals but no mass add events.

Subsequent states create deterministic `PLAYER_ADDED`, `PLAYER_DROPPED`, `PLAYER_TRANSFERRED_BETWEEN_MANAGERS`, active/reserve/IR movement, lineup-position, and identity events. Manager-to-manager movement stays unconfirmed and is not called a trade without an authoritative transaction ID.
# Presentation analytics

The cache-only live pipeline writes four additional 2026/27 models: `live_player_analytics`, `live_manager_analytics`, `live_position_strength`, and `available_players`. Current-season performance columns exist but remain null until weekly source facts arrive. No 2025/26 artifact is an output of this pipeline.
# Player performance extension

The live build now registers cache-only `current_player_weekly` and `manager_player_weekly` outputs. Before a proven weekly export exists both are valid, schema-only preseason datasets. Completed-period Season/Last 3/Last 5/Last 10 aggregates never manufacture future rows. See `live_player_performance.md`.
# Weekly acquisition activation

Refresh League now plans missing completed periods from `getLeagueInfo.scoringPeriods`, acquires validated Fantrax weekly CSVs incrementally, then runs the cache-only live build. Current partial-period caches are excluded from standard completed-window aggregates.
Live manager models separate standings, player performance, ownership, finalized
history, and frozen draft expectations. See `live_manager_analytics.md`.
`live_league_summary` is the cached League Hub presentation frame. It adds rank
movement, completed form and weekly distribution values to manager analytics.
# 2026/27 fixture coverage

The existing cache currently covers 170 Premier League matches (17 per club). Cached Fantrax scoring periods are stale 2025/26 windows, so canonical 2026/27 period fields remain blank until authoritative live periods are acquired.

The Fantrax gap is resolved: 38 live 2026/27 periods are validated and all 170 known fixtures map. The schedule gap remains blocked at the provider source, which returned 170 again on 2026-08-19.

The schedule gap is resolved through cached Sofascore: 380 matches, 760 perspectives, 38 per club, and 380/380 Fantrax mappings. ClubElo is separately blocked by endpoint timeouts.
