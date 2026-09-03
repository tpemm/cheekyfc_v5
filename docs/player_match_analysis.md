# Player Match Analysis

The live Player Profile Performance tab uses registered `current_player_weekly` data for 2026/27 and finalized `master_player_weekly` data for 2025/26. Views are prepared for one authoritative Fantrax player ID at a time; the page performs no HTTP or scraper access.

Points by Gameweek and Last 5 include completed Fantrax scoring periods only. Missing periods are not inserted, future/incomplete periods are excluded, legitimate zero remains zero, and negative scores remain negative. Multiple source rows in one scoring period are retained deterministically as match detail rather than silently discarded.

The default table is GW, Opponent, H/A, FDR, Minutes, Started, Points, Ghost Points, Goals, and Assists. Optional fields appear only when the selected season/player contains numeric data. `Started` requires a proven start. `Sub` requires an appearance without a start. DNP is offered only for a zero-minute, zero-appearance row with roster context; an absent row is never interpreted as DNP.

Opponent and H/A come from the registered Fantrax opponent string (`@` means away). No player-week FDR is currently registered, so FDR remains blank and the filter is omitted. Historical player-week Ghost is also not registered; historical breakdown therefore reports an intentional unavailable state rather than recalculating finalized scoring.

Home/Away uses the selected profile basis and valid denominators only. Points Breakdown is authoritative total Fantrax Points and Ghost Points, with `Non-Ghost Points = Total − Ghost`. A donut is used only when both components are nonnegative; otherwise a bar chart represents the signed values honestly.

No authoritative set-piece-role dataset is registered. Penalty, corner, and free-kick badges are intentionally omitted until such data exists.
