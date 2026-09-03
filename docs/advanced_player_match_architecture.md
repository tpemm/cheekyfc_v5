# Advanced player-match architecture

The POC is additive: preserved WhoScored raw data is normalized, explicitly
identity-mapped, aggregated, then joined analytically to Fantrax and Understat.
It never edits finalized inputs.

Fantrax remains fantasy-scoring authority. A period total may be attached to a
match only when the player's club has exactly one match in that Fantrax period;
otherwise attribution is marked ambiguous. Understat xG/xA must join from its
player-match table using canonical player, club/opponent, and match date.
WhoScored owns only proven event, lineup, formation, rating, role, and location
fields. Missing supplemental facts stay missing. There are no predicted fields.

The builder enforces one row per canonical player-match and records
`contains_prediction=False`. The first proven row is Emiliano Martinez in
WhoScored match 1903446 / Understat match 29140: explicit identity, starting
role, final rating, event totals, Understat xG/xA, and exact Fantrax period 37
context. Four bounded POC datasets are registered.
