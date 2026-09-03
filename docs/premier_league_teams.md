# Premier League Teams

The live 2026/27 `Teams` page is backed only by registered, cache-first datasets loaded through `DataManager`: `premier_league_clubs`, `team_matches`, `team_fixtures`, and the existing live player analytics.

The directory exposes all 20 canonical clubs. Profiles contain Overview, Squad, Fixtures, Fantasy Allowed, and Playstyle tabs. Squad rows reuse the canonical live player pool. Fixtures are chronological and distinguish competition and Fantrax period. Fantasy Allowed and Playstyle show honest limited/preseason states until registered observations exist.

Current schedule coverage is 17/38 league matches per club. The UI reports that limitation rather than describing the cache as a complete season schedule.

Sprint 9.0.1 revalidated the provider live and confirmed that 170 remains its published total. Teams therefore continues to display the full provider-known schedule, marked partial, while all 170 matches now show current 2026/27 Fantrax periods.

Sprint 9.0.2 promotes the complete cached soccerdata Sofascore schedule. Every club now has 38 league fixtures and every match maps to a current Fantrax period. Overview has compact Elo slots and next-opponent context; they intentionally display unavailable while ClubElo acquisition is blocked.

Fantasy Allowed now supports canonical positions, transparent windows, venue splits, samples, exact values, and ease ranks when completed Fantrax observations exist. Playstyle consumes only proven attack/defense profile fields. Both retain explicit preseason states today.
