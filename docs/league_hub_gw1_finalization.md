# League Hub GW1 finalization

League Hub accepts `COMPLETE_PENDING_CORRECTIONS` for result-dependent presentation. This is the existing fixture-complete state and does not claim that Fantrax's correction window is frozen. `FINALIZED` remains reserved for a closed/finalized Fantrax period export.

For GW1, all ten scheduled Premier League matches have cached WhoScored payloads with terminal `statusCode=6`. That terminal fixture evidence advances the period from `ACTIVE` to `COMPLETE_PENDING_CORRECTIONS`; the six Fantrax active-lineup totals remain the scoring authority.

`league_active_player_weekly_2627.csv` stores one row per active fantasy starter and scoring period. Contributions retain the manager/fantasy-team attribution recorded for that period, rather than being relabeled with a later current owner. Bench, IR, and unowned player production is excluded.

Manager efficiency is actual active-XI points divided by the maximum legal XI available from that manager's period roster. The optimizer uses exactly one goalkeeper, three to five defenders, two to five midfielders, one to three forwards, and eleven total players. Multi-position eligibility is handled deterministically by stable player ID.

Manager Awards aggregate goals, assists, Fantrax clean-sheet credits, and approved Ghost Points by the stable manager attached to each completed active-lineup row. Trades therefore do not rewrite historical contributions. Award ranks use competition ranking. When a tie would make a card visually large, it shows a deterministic alphabetical subset and discloses the omitted tied-manager count. The player-level leaderboard helper remains reusable elsewhere but is not consumed by League Hub.
