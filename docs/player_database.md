# Player Database

Dynamic profile modes, controlled metrics, league/position percentiles, radar behavior, and 2–5 player comparison are specified in [player_comparison.md](player_comparison.md).

Players and profiles use the shared page hierarchy and laptop-first table conventions in [the design system](design_system.md). Profile actions, multi-position display, missing ADP behavior, frozen Draft Score, and navigation state remain protected.

The Players page is a live-season shell backed by registered `player_ownership`, `current_rosters`, and `current_fantrax_player_pool` data. It exposes available authoritative profile fields without creating derived player analytics.

Form, schedule, roster context, comparison, and market views are reserved for future sprints. Empty or incomplete inputs produce explicit states; the view never alters Player Registry identities or source/generated data.

Sprint 7.2 adds current owner/team, availability, lineup state, draft origin/retention, ownership-change count, and recent roster events. Draft HQ and historical inputs are displayed as registered read-only context and are not recalculated.

The page now exposes those ownership and draft fields immediately after the draft. Current-season performance remains an explicit placeholder until matches provide authoritative scoring data.
# Sprint 7.4 live player database

The 2026/27 Players page loads the registered `live_player_analytics` dataset through `DataManager`. It provides database, profile, and two-to-five-player comparison views. Multi-position filtering matches any eligible Fantrax position. Missing ADP remains null and sorts last in either server-side direction.

Profiles separate live ownership, frozen draft-day values, 2025/26 historical production, projected context, and current-season facts. Before weekly facts exist, the current-season section states that performance begins after Gameweek 1.
# Historical Players (2025/26)

The finalized-season Players page is a separate historical encyclopedia backed by the registered `master_player_weekly` snapshot. A deterministic cached presentation frame aggregates official points and identity for 920 players. Where IDs match, the immutable 2026/27 draft-day snapshot enriches the frame with finalized 2025/26 starts, minutes, ghost points, and Understat values. This enrichment is historical input provenance, not draft projection data.

Database controls include search, club, multi-position Fantrax eligibility, minimum minutes, minimum starts, and `Total | Per Game | Per Start | Per 90`. Rates require positive denominators; missing values remain missing.

The three contexts remain distinct: **Historical Performance → Live Performance → Draft-Day Context**. Historical Players never displays live-season performance as a historical result.
# Live-season behavior

Current performance columns and the window control appear only when registered player-week facts exist. Historical 2025/26, current 2026/27, and frozen draft-day contexts remain distinct. Missing live statistics remain blank.
# Supplemental live facts

Approved Understat facts automatically improve current and available-player coverage after a cache refresh. Main tables remain uncluttered; source provenance stays in the registered weekly facts. Fantasy Points and Ghost Points remain blank for Understat-only rows.

Finalized Fantrax weekly caches activate existing current points, playing time, advanced events, Ghost, recent-form, and rate fields without a page redesign.
## Live 2026/27 decision database (Sprint 8.9)

The live database is one compact table. Availability is an authoritative `All Players` / `Available Only` filter rather than a duplicate page. Its primary rate basis is Per Game, Per Start, or Per 90; current Points, Ghost, and xGI columns change together. The default view contains player, club/position, owner/availability, those three rates, Minutes Outlook, and Next 5 Fixture Ease. Draft fields remain in the analytical dataset but are intentionally excluded from this table. Before completed live periods, current production remains missing while minutes and fixture context continue to render.
### Sprint 8.9.2 profile navigation

Players uses a stateful, tab-like segmented subview control because native Streamlit tabs did not provide reliable table-action activation. A database action stores the authoritative Fantrax player ID and activates Player Profile before rerendering. The profile selector uses that ID internally, so duplicate visible names cannot redirect to another player; no profile is rendered under the database.
### Match analysis

Player Profile opens detailed current or finalized historical gameweek analysis without changing the app season. The work is scoped to the selected Fantrax identity and is loaded only in Player Profile, not while scanning the database.
### Compact Overview card

The Player Profile Overview pairs one radar with an adjacent exact-stat panel and stops there. Database metric ordering and Overview ranks use the same numeric ranking preparation. Draft context and match analysis remain in their existing deeper tabs.
# Canonical fixture context

Player Next Fixture and Next 5 Fixture Ease are now derived at presentation time from the player's exact canonical club mapping and registered team fixtures. Players no longer maintain independent club-name matching. Generic fixture ease retains the established preseason methodology.

Canonical fixtures take precedence over embedded Fantrax opponent strings. Unknown club identities remain unresolved. Next-five context excludes non-league and completed rows and is ordered by actual kickoff time.

The enrichment layer now carries optional next-opponent raw Elo and PL Elo rank fields. Player presentation is unchanged while the ClubElo cache is unavailable.
