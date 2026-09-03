# Fantrax weekly export audit

## 2026/27 recovery proof (Sprint 9.7.4)

The authenticated diagnostic proved that the current control is an icon-only
Angular Material button with `mattooltip="Download all as CSV"` and child icon
`get_app`. The historical implementation failed because it waited for the
generated tooltip node and then followed its transient `aria-describedby` ID.

Chrome generates the CSV as a browser-managed download without a reusable CSV
request and, with the installed Chrome executable, without Playwright's normal
download event. Acquisition now assigns a unique controlled download directory
and polls for the completed file. Real GW1 proof acquired 615 all-player rows
and 12/12 detailed team exports using the 12 unique team IDs supplied by
`getLeagueInfo.teamInfo`. The period is `LIVE`: 190 players have detailed
manager-export coverage and 425 retain all-player-only coverage.

Endpoint replacement remains not proven. The selected acquisition strategy is
**B — browser export**.

## Historical workflow located

The proven 2025/26 workflow remains in `fantrax/scraping/scrape_team_rosters_weekly_fantrax.py` and `scrape_allplayers_weekly_fantrax.py`. It uses headed Playwright, a locally saved `fantrax_auth_state.json`, manual login/2FA when that state is created, Fantrax league/team pages, explicit scoring-period URL state, and the Angular Material **Download all as CSV** control.

The team exporter iterates 12 hard-coded historical team IDs, selects one period, waits for Playwright's download event, retries the click for a bounded interval, names files by manager and GW, hashes downloads, rejects empty/duplicate-period files, and archives forced replacements. The all-player exporter follows the same interaction on the league Players page and retains free-agent/waiver rows. `fantrax/analytics/core/build_master_weekly.py` parses the Goalkeeper/Outfielder sections and merges them with the all-player file.

Authentication state is local-only and ignored. No cookie, token, password, or storage-state content is logged or copied into normalized data.

## Current private-endpoint decision

The proven public/private JSON calls remain `getLeagueInfo`, `getStandings`, and `getTeamRosters`. They provide league configuration, identities, scoring definitions, standings, and roster-slot state, but no player-period fantasy points or detailed component values. Therefore they cannot reproduce either CSV.

The authenticated diagnostic found no separate CSV network response to compare
against the browser-generated file, so direct-request parity remains unproven.

Decision: **C — NOT VIABLE as a replacement**. The authenticated CSV workflow remains authoritative. This is a proof threshold decision, not a claim that no private endpoint exists.

## Promoted 2026/27 contract

`fantrax.live.weekly_acquisition` resolves the current league and 12 team IDs from cached 2026/27 league metadata. It validates CSV rather than HTML/login content, preserves the all-player source, continues independent manager downloads, records partial manager coverage, hashes normalized output, retains timestamped active-period snapshots, and marks maturity as `LIVE` or `FINALIZED`. Invalid acquisition never replaces a valid cache.

The all-player export is the league-wide fantasy-points authority. Detailed manager exports override overlapping Fantrax components for rostered players. An explicit Fantrax zero remains zero. Only the already-approved historical safe supplements may fill genuine detailed-field missingness, with WhoScored provenance retained. Understat remains xG/xA/xGI authority.

Current blocker: the saved browser session/UI interaction must be deliberately reauthenticated or its changed download control diagnosed before real GW1 files can be promoted.
