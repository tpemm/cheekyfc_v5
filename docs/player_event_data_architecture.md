# Player event data architecture

Raw qualifiers are serialized losslessly alongside normalized columns. Direct
fields and coordinate-derived analytics must remain separate.

The real match proves `KeyPass` qualifier evidence on 23 events; no top-level
`isKeyPass` fields occurred. The normalizer accepts either explicit form;
it does not infer key passes from successful passes. `TakeOn` plus outcome is
the candidate dribble semantic, `Aerial` plus outcome is the candidate aerial
semantic, and tackle/interception/clearance require their corresponding event
types. Pass attempts/completions require `Pass` plus outcome. Crosses require
an explicit Cross qualifier. Shots use MissedShots, SavedShot, ShotOnPost, or
Goal; on-target uses SavedShot or Goal. `ShotOnPost` is a shot but not on
target. These mappings are tested against the real 1,374-event sample.

Coordinates are preserved as source `x/y/endX/endY`. The observed scale is
0–100 and 929 events have end coordinates. Multi-match attacking orientation
is not yet proven, so no heatmap is published. In this match both teams show
positive mean pass progression in both halves, supporting a provisional
left-to-right normalization inference rather than stadium-direction coordinates.

The eight-match sample upgrades this to sample-proven: all 32 club/half groups
have non-negative median pass progression. Aerials occur as winner/loser
player-event pairs, not one row per physical duel.
An Event Activity Heatmap would show recorded-action density, not player
movement or tracking data.
