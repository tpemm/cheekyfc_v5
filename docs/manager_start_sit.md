# Start / sit outcome explanation

Run `python -m fantrax.live.start_sit` to create the two registered season products
and `data/quality/season_2627/start_sit_quality_2627.json`. Generated products are
local and not automatically committed. The existing Decisions review calculates
the same read-only view on demand.

Actual players and scores come from `manager_player_weekly`. Included completed
result weeks and comparison values come from the same `manager_performance_weeks`
service used by League Hub. `optimal_legal_xi` supplies both score and player IDs.
Missing scores, duplicate identities, invalid XI counts or reconciliation failures
stop publication. No event replay or current ownership is used.

Roster eligibility is exactly the existing Efficiency roster, including its IR
handling. No new injury/appearance exclusions or formation rules are introduced.
Bench points total sums all non-starters in that roster. It is not recoverable
points: points left on bench is the nonnegative optimal-minus-actual difference.

Retained actual/optimal IDs receive CORRECT_START. Differences compare only
actual-only and optimal-only sets. A pairing requires a unique perfect matching
whose individual substitutions each admit a legal XI under the existing solver.
Compatible positions are considered first, but multiple valid pairings remain
STRUCTURAL; their complete sets and aggregate difference are preserved. A
structural row is a collective difference, not a claim about an individual swap.

EQUIVALENT denotes a zero-point paired difference. The existing solver chooses
one deterministic optimum; alternative tied optima can therefore change selected
player membership without changing points. Counts describe set membership, not
manager skill. No correct-start rate or manager grade is produced.

The quality report includes season-to-date total/average points left, average
Efficiency and included-week count per manager. Activity context never changes
outcome scores. GW4 receives no outcome without canonical completed result data.
