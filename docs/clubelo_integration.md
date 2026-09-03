# ClubElo integration

soccerdata 1.9.1 exposes `ClubElo.read_by_date(date)` and `ClubElo.read_team_history(team)`, caching CSV responses. The production contracts `club_elo_current` and `club_elo_history` are registered, and normalization supports explicit canonical name mappings, Premier-League-only rank, ordered history, raw Elo fixture context, and Next 5 opponent Elo lookup.

Acquisition is currently blocked: soccerdata's configured `http://api.clubelo.com` endpoint timed out, and an HTTPS reachability check also timed out on 2026-08-19. No valid response was cached, no provider names were guessed, and no substitute ratings were generated. Empty registered datasets preserve the UI/data contract; Teams displays `Unavailable` until a validated cache exists.

Once reachable, current ratings must resolve 20/20 through explicit names before publication. PL Elo rank is calculated only among those 20 teams. History should be acquired only for resolved teams and stored as canonical club/date/Elo rows. Fixture context exposes team Elo, opponent Elo, Elo difference, and venue separately; no arbitrary home adjustment or hidden ease formula is introduced.
