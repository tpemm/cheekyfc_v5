# Live Manager Analytics

The 2026/27 Manager experience retains five tabs: Overview, Performance, Squad,
Decisions, and Explorer. Views load registered datasets through `DataManager` and
perform no HTTP or direct normalized-file reads.

## Data contracts

- `live_manager_analytics`: one row per stable Fantrax manager ID. It combines
  current standings, current ownership, roster projections, frozen draft facts,
  finalized 2025/26 player reference values, and completed live production.
- `manager_week_summary`: one row per manager and completed scoring period. It
  contains opponent/result, cumulative record, rank and points context. Advanced
  lineup fields remain null until submitted lineup evidence exists.
- `manager_player_weekly`: period ownership and player production; it is the only
  permitted input for future lineup decisions.
- `live_position_strength`: one canonical assignment per current player. The
  preseason basis is draft/projection and must be labeled.

## Source separation

League results come from Fantrax matchup/standings caches; player performance
comes from Fantrax weekly exports; xG/xA/xGI may be supplemented by Understat;
history comes from finalized 2025/26 data; draft expectations remain frozen; and
ownership comes from roster tracking. Missing evidence is never replaced with a
projection or inferred lineup.

Historical and current roster rates are ratio-of-sums. Points and Ghost use only
players with valid Fantrax minutes; xGI uses valid Understat minutes.

## Preseason and weekly activation

Before a completed scoring period, Overview shows roster, standings, draft,
historical, projection, activity, position-strength, and Cup context. Performance
and Decisions show intentional locked messages. Form, luck, consistency, weekly
averages, and efficiency are blank rather than zero.

After GW1, completed `manager_week_summary` rows automatically activate weekly
scoring, league-position history, form, windows, and performance summaries.
Decision analytics activate separately only when authoritative period roster and
submitted lineup state are present.

## Established formulas

Expected wins uses the finalized 2025/26 all-play method: compare a manager's
score with every other score that period, with ties worth half a win. Luck is
actual wins minus expected wins. Consistency is the standard deviation of weekly
scores; the definition is unchanged. Lineup efficiency is actual starter points
divided by the optimal legal XI points, but remains null without proven starters.

The existing optimizer enforces one goalkeeper, three to five defenders, two to
five midfielders, one to three forwards, eleven total players, multi-position
eligibility, and one appearance per player.
League-wide expected-record, luck, consistency, roster-rate and projection views
reuse these manager definitions; the League Hub does not recalculate them.
## Manager identity and draft origin

Draft retention resolves frozen draft display labels through a deterministic
alias crosswalk to the authoritative Fantrax manager ID. Unicode apostrophe,
case, punctuation and whitespace differences do not change identity. A retained
player was drafted by that stable manager and is still owned by that manager;
every other current player is acquired later. Dropped originals are tracked
separately. The invariant is retained plus acquired later equals current roster.
