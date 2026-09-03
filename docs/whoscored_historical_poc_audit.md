# WhoScored historical proof-of-concept audit

## Installed reader

The installed package is `soccerdata 1.9.1`. `WhoScored` exposes
`read_schedule`, `read_events`, `read_missing_players`, `read_season_stages`,
`read_seasons`, and `read_leagues`; `_read_game_info` is internal. The event
reader supports `events`, `raw`, `spadl`, `atomic-spadl`, and `loader` output.

The native cache path for events is
`events/{competition}_{season}/{game_id}.json`. That JSON is the full
`matchCentreData` payload and is therefore the preservation source, rather
than the `raw` return value (which contains only the event list).

## Acquisition result and diagnosed delay

The 90-second watchdog misclassified a slow schedule traversal. The installed
reader serially fetched the season page and ten monthly calendar endpoints,
applying a randomized 5–10 second delay to every uncached request. Cache
timestamps show that traversal completing after the watchdog threshold. It
resolved canonical/Understat match 29140 to WhoScored match 1903446 and
preserved a real 1,374-event payload.

A direct diagnostic subsequently reached
`https://www.whoscored.com/matches/1903446/live`, title `Aston Villa 4-2
Liverpool - Premier League 2025/2026 Live`, with a complete document, working
JavaScript, useful HTML, and embedded `matchCentreData`. Its checksum exactly
matched the preserved raw cache. WhoScored was accessible; the problem was
wrapper traversal latency, not network denial. Known provider IDs can bypass
the calendar through the local direct-match adapter.

## Real schema findings

The payload contains 40 players and 1,374 events. Starting formations live in
`home/away.formations[0]`, ratings are minute-keyed histories under player
stats, and tactical positions use `GK/DR/DC/DL/DMC/AMC/AML/AMR/FW/Sub` codes.
Key passes use an explicit qualifier. Source x/y values span 0–100; 929 events
have end coordinates. Direction consistency beyond this match remains open.

Sprint 9.2.2 expands validation to eight matches; see
`whoscored_multimatch_validation.md`. Multi-match evidence supports stable
schemas, event semantics, and left-to-right coordinate normalization.
