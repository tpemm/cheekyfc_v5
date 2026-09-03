# Fantrax matchup and live-scoring authority

## Proven private operation

The authenticated Fantrax Matchups route is `/fantasy/league/{leagueId}/livescoring;period={period}`. The Angular client sends `POST /fxpa/req` with `getLiveScoringStats` (`sppId=-1`, `period`, `newView=true`) and `getScoresSummaryData`. Authentication is the existing commissioner-local Playwright storage state. Cookies, headers, session values, and credentials are never persisted in diagnostics.

`getLeagueInfo` remains the browser-free schedule/configuration source. It supplies matchup pairings but not manager scores. `getStandings` supplies standings, and `getTeamRosters?period=N` supplies roster/slot state. None replaces the live-scoring operation.

## Authority policy

- Official manager score, result, record, margin, and League Hub score-derived features: `getLiveScoringStats`.
- Current player FPts and official active-lineup attribution: `getLiveScoringStats` when present and validated.
- Detailed rostered-player scoring components: authenticated manager CSV exports.
- Player universe and waiver FPts: all-player CSV export.
- Advanced/event/tactical supplements: WhoScored.
- xG, xA, and xGI: Understat.

The three Fantrax surfaces have independent acquisition timestamps and may expose different correction states. Detailed CSV active sums therefore never overwrite a validated matchup score.

## GW1 evidence

The validated response contains six unique matchups, 12 unique fantasy teams, 190 player rows, and an 11-player active scoring lineup for every manager. All 12 active live-scoring sums equal the official matchup totals. Eight managers also equal the detailed CSV active sum; four have documented source-state differences. The player reconciliation identifies nine corrected active players, proving that the private live-scoring surface is newer than the manager CSV state for those points.

Commissioner acquisition is local/private and browser-backed. Hosted Core Refresh remains cache-only and browser-free. Plan mode reads status only. A malformed or failed acquisition is rejected before replacing the last valid cache.
