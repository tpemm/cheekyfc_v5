# Current-season Understat integration

Understat is the authority for 2026/27 xG, xA, xGI, and team xG/xGA. It supplements—but never replaces—Fantrax fantasy points, ownership, or official fantasy scoring components. WhoScored remains the event and tactical authority.

The live acquisition is cache-first. `scripts/refresh_understat_live.py` compares completed fixtures with the season-scoped cache and skips network work when coverage is stable. New data is acquired through the existing soccerdata scraper into `data/raw/understat/2627`; its soccerdata runtime cache is isolated inside the project.

`scripts/build_understat_live_products.py` creates:

- `understat_player_match_2627.csv`: provider player-match facts, with exact registry identity status and unresolved rows retained for audit.
- `understat_team_match_2627.csv`: two reciprocal club perspectives per match.
- `understat_match_identity_2627.csv`: exact UTC date plus canonical home/away identity joins.

Played zeroes are observations, not missing values. Unresolved player identities never receive a canonical player ID and do not join into the unified player-week. Team joins require exact match and club identity.

The weekly commissioner flow runs Fantrax, WhoScored, the cache-first Understat refresh, core models, Understat products, and unified models. The GW1 reference under `data/reference/validation` is immutable by default; replacement requires the explicit maintenance-only `--replace` flag.

The Fulham–Chelsea result was available at the first acquisition check roughly 2.5 hours after full time. This is empirical context only; no fixed provider-delay assumption is encoded.
