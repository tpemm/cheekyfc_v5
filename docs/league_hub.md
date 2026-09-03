# League Hub

For 2025/26, navigation says Season Archive while the page itself retains the familiar League Hub identity. Its protected visual sequence is three summaries → final table → award grid → charts/supporting analytics. No documentation/index panel belongs above the dashboard.

The archive landing page restores the historical League Hub hierarchy: grouped summary/highlight cards, prominent final table, paired weekly-scoring and rank-history charts, followed by awards and records. It retains the archive header and current design tokens rather than restoring obsolete global styling.

The live Hub includes a Cup status/countdown group. The finalized 2025/26 route is now the [historical season archive](season_archive.md), not a live Hub.

The page uses the shared header, KPI/highlight cards, table surface, responsive shell, empty-state vocabulary, and semantic status colors defined in [the design system](design_system.md). League calculations are unchanged.

The 2026/27 League Hub is the live-season home. It presents the latest registered standings, record and form, points for/against, completed-week highlights, position history, weekly scoring, and compact manager cards.

The view reads `league_teams`, `league_standings`, `weekly_matchups`, `manager_week_summary`, `current_rosters`, and `player_ownership` through `DataManager`. It performs presentation shaping only: it does not read files directly, call Fantrax, write outputs, or redefine historical metrics. Missing models receive explicit awaiting-data or Coming Soon states.

The finalized 2025/26 League Hub remains a separate historical renderer and retains its settled analytics.

The live page now includes recent verified roster activity. An unchanged baseline shows “No roster changes detected since the initial 2026/27 snapshot.” Manager transfers are not presented as trades unless transaction data confirms them.

League Hub data is refreshed through the Operations Center’s single weekly workflow; its analytical definitions remain unchanged.
# Sprint 7.4 additions

The settled live hub now adds supported current-roster projections, top position groups, verified activity, and available free agents ranked by the frozen Draft HQ baseline. These are preseason context, not power rankings or waiver-success claims.
# Live player-week readiness

Canonical weekly player facts can support future manager scoring trends and weekly awards, but League Hub continues using its existing authoritative standings/matchup calculations. This sprint does not duplicate or redesign those calculations.
The League Hub remains unchanged; its registered manager summary inputs are also
consumed by the dedicated live Managers page.
## 2026/27 live homepage

The live Hub uses `live_league_summary` for cached manager/table context and
activates weekly sections only from completed scoring periods. Definitions and
empty-state behavior are documented in `live_league_analytics.md`.
## Sprint 8.7 refinements

The four top cards are Latest Jester, Jester Leader, Latest Manager of the Month,
and Cup Status. The live table defaults exactly to Rank, Team, Movement, Record,
Form, Pts / GW, Ghost / GW, Efficiency, and Lineup Changes. Unsupported live
fields remain blank. The duplicate manager-card grid was removed from the Hub.
## Sprint 8.8 approved live hierarchy

The 2026/27 Hub now stops after: League Hub title; four compact headline cards;
the compact League Table; four weekly highlights; Weekly Scoring and League
Position History; and four top-three player leaderboards. Roster activity,
projections, position-strength, available-player and manager-directory content
belongs to the specialized pages and is no longer repeated here.
