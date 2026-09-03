# soccerdata fixture-provider audit

Audit date: 2026-08-19. Environment: Python 3.13.14, soccerdata 1.9.1. Installed readers are Sofascore, WhoScored, ESPN, FBref, Understat, ClubElo, MatchHistory, and SoFIFA. Schedule methods exist for all five requested schedule readers; WhoScored and FBref are Selenium-backed, while Sofascore, ESPN, and Understat use request-based readers.

## Scorecard

The detailed machine-readable scorecard is `data/quality/season_2627/soccerdata_schedule_provider_audit_2627.csv`.

- **Sofascore:** 380 matches, 20 clubs, 380 stable game IDs, all dates, home/away, scores, and rounds. Its cache contains all 38 round payloads. Selected primary source.
- **ESPN:** 380 matches and stable IDs, but the exported schedule lacks round and explicit status/score fields. Reliable secondary corroboration, not selected.
- **FBref:** returned 462 historical rows beginning in 1926 while labeled as season 2627. Season resolution is invalid for production.
- **Understat:** the current preseason export has no usable schedule rows. It remains the expected-stat source after matches begin.
- **WhoScored:** soccerdata exposes schedule and detailed-event methods, but no reproducible 2627 cache was produced by the existing evaluation. It is not needed for schedule authority and remains a future event/formation source.
- **football-data.io:** retained only as a 170-match fallback and corroboration source.

Provider precedence is complete Sofascore → complete ESPN if explicitly approved later → football-data.io fallback → unresolved. Providers are never blindly combined. Stable provider IDs are preferred; deterministic date/home/away keys are reserved for disagreement reporting.

The installed league catalog does not define the requested FA Cup, EFL Cup, Champions League, Europa League, or Conference League identifiers. Cup/Europe integration is therefore deferred and does not enter Fantrax fixture ease.
