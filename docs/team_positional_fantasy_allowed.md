# Team positional fantasy allowed

`team_position_fantasy_allowed` derives opponent production only from completed Fantrax player-period facts. Players receive one group: canonical primary position, otherwise the first valid Fantrax position, otherwise unresolved. A D/M player contributes once to DEF.

Rows cover GK, DEF, MID, and FWD; Season, Last 3, Last 5, and Last 10; and All/Home/Away opponent venue splits. Partial windows retain the actual periods and labels such as `Last 5 (3 available)`. Metrics store match, appearance, start, and minute samples alongside raw totals and per-match/per-start/per-90 rates. More points allowed ranks as an easier matchup.

Double-gameweek player-period facts are not arbitrarily split between matches. Missing values remain missing and legitimate zero totals remain zero. The current artifact is intentionally empty because no 2026/27 Fantrax period is completed.
