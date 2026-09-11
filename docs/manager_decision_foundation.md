# Manager decision activity foundation

`manager_player_weekly` is the sole final-lineup authority. The review selects its
manager/gameweek rows directly, with no event replay, inferred base state, or scoring.
Missing canonical periods (currently GW4) have null final counts, not zero starters.

Run `python -m fantrax.live.manager_decisions` from the project root to materialize
`manager_week_decision_summary_2627.csv` and `manager_event_timeline_2627.csv` under
`data/models/season_2627`, plus the quality report under `data/quality/season_2627`.
Generated products are local artifacts and are not automatically published.

Managers → select manager → Decisions → Review decision event history exposes
canonical Active/Reserve/Inj Res rows, descriptive counts, and the chronological
timeline. The review uses the imported products directly, so no materialization
is required. If hosted imports are absent, event coverage is explicitly unknown.

Lineup counts measure the dedicated lineup export. The two transaction-export
Lineup Change rows remain transaction-context observations, without assuming they
are additional distinct lineup moves. Every input event survives in the timeline.
Equal timestamps are ordered by source event ID for deterministic presentation;
this tie-break does not establish actual event order within the exported minute.

Groups remain candidate associations, not official transaction IDs. Timestamps
and exported GW tags are preserved; overlapping windows are not reclassified.
Repeated tinkers counts players with more than one dedicated lineup event per GW.

Without a coverage manifest, observed activity is partial coverage and zero rows
mean NO_EVENT_COVERAGE. Explicit complete manager/GW coverage may establish
NO_ACTIVITY; the current exports do not establish it for absent managers/windows.
All metrics describe recorded activity, not decision quality or lock timing.
