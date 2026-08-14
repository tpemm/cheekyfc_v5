# Fantrax player-stat API audit (2026/27)

Audit date: 2026-08-14. League: `o1wb36vdmrp1z5t8`.

## Result

The official calls already proven by this project all returned HTTP 200 against the real league:

| Operation | Endpoint | Response shape | Finding |
| --- | --- | --- | --- |
| League context | `getLeagueInfo` | object | `playerInfo` maps stable player IDs to `eligiblePos` and `status`; `scoringSystem.scoringCategorySettings` supplies stat IDs, labels and league weights. It contains no player-period values. |
| Standings | `getStandings` | list (12 teams) | League standings only. |
| Rosters | `getTeamRosters?period=1` | object keyed by team | Each roster item contains `id`, `position`, and `status`; IDs are stable. |

No documented official player-stat endpoint was found, and no speculative endpoint was called. The real preseason payloads contain neither weekly nor cumulative player fantasy points or event totals. Consequently the refresh operation remains limited to the three proven calls. The build may consume a cached weekly export, but never performs HTTP.

## Field classification

All Fantrax performance fields below are currently `EXPORT_FALLBACK`: fantasy points, appearances, starts, minutes, goals, assists, shots, shots on target, key passes/chances created, accurate crosses, successful dribbles, tackles won, interceptions, clearances, blocks, aerials won/lost, dispossessions, fouls drawn/committed, cards, clean sheets, goals against, saves, penalties saved/missed, own goals, and every other configured scoring event. The fallback accepts period, stable player ID and the existing export aliases; absent fields remain blank, never zero.

`xg`, `xa`, `xgi`, and `understat_minutes` are `UNDERSTAT_PRIMARY`. They remain blank until a live Understat observation is available and identity-matched. No Fantrax proxy is substituted.

The generated `fantrax_stat_dictionary` records each configured stat's ID, raw label, normalized field, category, weight, direction, endpoint, and the important distinction that `getLeagueInfo` exposes a scoring definition—not player values. Unknown categories are retained as `unmapped` rather than guessed.

## Capability matrix

| Capability | API availability | Parameters / response path | Period / season total | IDs | Reliability | Scoring / export |
| --- | --- | --- | --- | --- | --- | --- |
| Player identity, eligibility, status | Available | `getLeagueInfo`; `playerInfo.<id>` | Current context | Yes | Proven real response | Context only; also in export |
| Scoring stat IDs, names, weights | Available | `getLeagueInfo`; `scoringSystem.scoringCategorySettings[].configs[]` | League definition | No player rows | Proven real response | Defines league scoring |
| Submitted roster state | Available for retrieved period | `getTeamRosters?period=N`; `rosters.<team>.rosterItems[]` | Period accepted | Yes | Proven for period 1 | ACTIVE/RESERVE/IR-style status and slot position |
| Player fantasy score and event values | Not exposed by proven API | None | Neither proven | N/A | Unsupported | Existing weekly CSV/export fallback |
| xG/xA/xGI | Not sourced from Fantrax | Understat cache (future live feed) | Period/season after ingestion | Registry join | Source-owned | Understat primary |

## Submitted-lineup finding

`getTeamRosters` identifies active, reserve and injured-reserve state plus the roster-slot position for the requested period. That response is authoritative for a retrieved and cached period. It is not evidence of a complete immutable submitted-lineup history: only periods actually retrieved can be reconstructed. The existing weekly roster/export fallback therefore remains required for missing historical periods.

The preseason response is a successful context/roster response, not a failed or empty player-stat response. Since no proven player-stat response exists, the production `player_stats` raw directory is not populated with fabricated audit payloads.

## Understat compatibility audit

| Field | Observed | Compatibility | Strategy |
| --- | --- | --- | --- |
| Minutes, appearances | Minutes observed; appearance derived per player-match | Approximately comparable | Fantrax primary, Understat analytical fallback |
| Goals, shots, cards | Observed | Equivalent factual event in normal cases; corrections may differ | Fantrax primary, provenance-tracked fallback |
| Assists, key passes | Observed | Provider attribution can differ | Analytical fallback only; excluded from scoring reconstruction |
| xG, xA, xGI | xG/xA observed; xGI derived | Understat definition | Understat primary |
| Starts | No reliable explicit field | Unknown | Unavailable from Understat |
| Crosses, tackles, interceptions, clearances, blocks, aerials, dispossessions | Not observed | Unavailable | Fantrax only |

Every fallback retains source-specific values and `<metric>_source`. An explicit Fantrax zero always wins.

The authoritative weekly-value path is now the authenticated Fantrax CSV export documented in `fantrax_weekly_stats_acquisition.md`. It is not an undocumented API endpoint.
