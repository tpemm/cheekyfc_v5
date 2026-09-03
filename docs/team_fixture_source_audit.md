# Team and fixture source audit (Sprint 9.0)

Audit date: 2026-08-19. This report records observed repository evidence, not assumed provider capability.

## Proven sources

- The existing `football-data.io` client/normalizer cache supplies 20 2026/27 clubs and 170 normalized Premier League matches, covering August through December and exactly 17 fixtures per club. It is not a complete 380-match schedule.
- `fixture_difficulty_2627.csv` contains the same 170 matches in two-team perspective form (340 rows). Its existing overall-ease methodology is retained and joined by provider match and club IDs.
- Fantrax player exports supply club codes and an embedded opening-opponent string. That string was the previous `opening_opponent` source; it was player-export context, not a canonical schedule join.
- The cached Fantrax `raw_data/fantrax_api/league_info.json` has 38 `scoringPeriods`, but all period windows begin in 2025. It is stale 2025/26 data and is intentionally not applied to 2026/27 fixtures.
- Understat cache coverage is player/match context for finalized 2025/26 and live player supplements. No complete cached 2026/27 club schedule was found.
- No cached FPL or soccerdata 2026/27 schedule was found.

## Brighton root cause

Brighton has 17 football-data fixtures under provider team ID `180`; acquisition did not uniquely omit the club. The player model uses Fantrax code `BHA`, while fixture strength uses `Brighton & Hove Albion`, and some Fantrax player rows have a blank embedded opponent. The live player presentation did not join through a shared club identity. This is a deterministic identity/join defect compounded by an incomplete schedule cache—not a Brighton fixture absence. The canonical alias map now resolves `BHA`, `Brighton`, and `Brighton & Hove Albion` to `brighton_hove_albion`.

## Cup and Europe

No existing cached integration was proven to provide reliable 2026/27 FA Cup, EFL Cup, Champions League, Europa League, or Conference League schedules. They remain explicitly unsupported. The canonical model supports competition types, and non-league rows are excluded from player fixture ease.

No provider, endpoint, HTTP call, or scraper was added. A future acquisition change is necessary to reach 380 matches and obtain authoritative 2026/27 Fantrax scoring-period windows.

## Sprint 9.0.1 live verification — 2026-08-19

The 170-match root cause is incremental provider publication plus stale-pagination cache behavior. Page 1 was cached on 2026-07-28 with `total=170` and `total_pages=2`; the refresh planner inferred page count from that cache and skipped both existing pages, so it never revalidated pagination. The refresh now re-fetches current-season page 1 and follows only the pagination in that fresh response.

The corrected live request still returned exactly `total=170`, `total_pages=2` for football-data.io season `103535`, league `15`. Thus the provider feed itself does not currently expose the remaining 210 fixtures. One account-usage call and two match-page calls were used; 997 requests remained afterward with a protected reserve of 200. Cache timestamp: 2026-08-19 10:10 local.

The minimum next acquisition change is a single competition-level full-schedule source that supplies stable IDs, date/status, home/away clubs, and all 380 matches. It should feed the existing canonical normalizer; no architecture or Teams-page replacement is required. A second provider must be explicitly selected and evaluated before implementation.

## Sprint 9.0.2 resolution

The existing soccerdata 1.9.1 Sofascore cache supplies the missing complete source: 380 stable IDs, 20 clubs, all dates, and 38 rounds. It is now primary and produces 760 canonical team rows. ESPN independently corroborates 380 fixtures. football-data.io remains a non-overriding 170-match fallback.

The live Fantrax `getLeagueInfo` cache was refreshed separately for league `o1wb36vdmrp1z5t8` at 2026-08-19T15:04:30Z. Its 38 scoring windows span August 2026 through May 2027 and pass chronological, non-overlap, and season checks.
