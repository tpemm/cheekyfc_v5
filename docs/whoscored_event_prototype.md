# WhoScored event prototype

Status: blocked, not ingested.

The installed soccerdata reader advertises schedule and event methods, but the existing probe produced no reproducible 2026/27 cache. A whole-season scrape was not attempted. Consequently match IDs, lineups, formations, player IDs, timestamps, event types/outcomes, coordinates, qualifiers, key passes, dribbles, aerials, tackles, interceptions, crosses, and shots are not marked available.

Future promotion requires a small cached sample, repeatable IDs, stable event fields, exact team/player identity, and a second cache-only parse yielding the same records. No heatmaps, formations, roles, or lineup datasets are inferred meanwhile.
