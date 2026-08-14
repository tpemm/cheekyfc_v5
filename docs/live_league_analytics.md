# Live League Hub Analytics

The 2026/27 League Hub is the live default homepage. It consumes registered,
cache-only datasets through `DataManager`; the view performs no HTTP or direct CSV
reads.

## Preseason

Before a completed scoring period the Hub shows official current standings,
current roster projections, draft retention/churn, projection-based position
strength, verified roster activity, available players, Cup schedule and refresh
context. Weekly score, movement, form, luck, Jester and trend fields remain blank.

## Automatic activation

Completed `manager_week_summary` rows activate scoring, form, movement, highlights
and league-position history. Movement compares the latest completed rank with the
immediately preceding completed rank. Up is `\u25b2`, down is `\u25bc`, and missing or
unchanged is `\u2014`. Future/incomplete rows are excluded.

Manager of the Week is the highest score in the latest completed period. Weekly
Jester retains the historical definition: lowest manager score in that period.
Closest Match and Biggest Blowout use the smallest and largest absolute margins
from completed Fantrax matchups. Ties therefore have a zero margin.

Expected wins and luck are reused from live Manager Analytics: all-play weekly
win share with half credit for ties, and actual wins minus expected wins.
Consistency remains weekly score standard deviation.

## Sources

- Standings/matchups: Fantrax API cache
- Weekly scores: `manager_week_summary`
- Manager roster rates/projection: `live_manager_analytics`
- Position strength: `live_position_strength`, one canonical player assignment
- Activity: deterministic `roster_change_events`
- Available players: free-agent-only `available_players`
- Cup: registered `cup_*` outputs; bracket calculations are not duplicated
- Draft: frozen Draft HQ facts, read-only

The Hub does not define Power Rankings, a Waiver Score, waiver-success grades, or
unproven ownership popularity trends.
## Awards and compact table

Weekly Jester is the lowest completed manager score. Season Jester leaders are
counted from that history, preserving ties. Manager of the Month uses completed
calendar months only: most wins, then draws, then fewest losses, with monthly
fantasy points as the tiebreak; a remaining exact tie is preserved.

The approved table columns are Rank, Team, Movement, Record, Form, Pts / GW,
Ghost / GW, Efficiency, and Lineup Changes. Ghost, efficiency and lineup changes
require complete authoritative coverage and never use proxies. Position-strength
leaders display fantasy-team/manager labels and an explicit Draft / Projection
Basis during preseason; internal IDs are not displayed.
