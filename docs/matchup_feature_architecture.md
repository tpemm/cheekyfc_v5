# Matchup feature architecture

Production boundaries:

- **Observed:** Fantrax points, Ghost, minutes, starts, events; Understat xG/xA; source-proven formations.
- **Derived:** opponent allowed rates, transparent windows, ranks, venue splits, rest days, and Premier-League-only congestion counts.
- **Predicted:** none in Sprint 9.1.

`team_matchup_features` contains one club perspective per future league fixture with club/opponent, venue, Fantrax period, rest/congestion, available attack/defense context, and source coverage. `player_matchup_features` joins stable player identity and one primary position to the next canonical fixture, ownership context, observed recent playing time, historical rates, and opponent positional allowed metrics where available. Every player row has `contains_prediction=False`.

Small samples are exposed through observation counts. Raw values are retained; no shrinkage or final fixture/player score is applied.
# Sprint 9.2 supplemental boundary

Future WhoScored features must originate in preserved raw match payloads and
remain optional. Sprint 9.2 adds no predictions and no fixture-difficulty score.
