# Live season UI policy

The primary application season is **2026/27 Current (`2627`)**. The finalized **2025/26 Historical (`2526`)** season remains an explicitly selectable reference and is never used to fill an unlabeled current-season field.

Current pages load their registered `2627` working-namespace products first. Player and Teams advanced selectors default to current data when the selected identity has current observations. Historical views remain selectable and legitimately unavailable history is shown as unavailable, including promoted clubs and new players.

## Sprint 9.7.6 propagation findings

- The League Hub was reading the correct 2627 datasets, but `manager_week_summary_2627.csv` was empty because its builder required matchup scores from league metadata and ignored valid live detailed-export scores. Current active-lineup totals now overlay the GW1 matchup schedule and are labeled provisional.
- WhoScored current products were generated, but their descriptive builder intentionally emitted blank Fantrax points and Understat xG/xA. Exact player-period Fantrax facts and exact player-match Understat facts are now reconciled under the established authority policy.
- Teams loaded current formation products, but its playstyle branch described the selected current bundle as historical. Current Fantasy Allowed also used a registry product with a different schema and filtered `club_id` instead of the current product's `opponent_id`. The current product now has its own registered key and explicit current/baseline selector.
- Player Overview defaulted its radar to historical. Pitch carried a hardcoded historical caption, and changing from a no-current-data player could retain the historical advanced selector for a current-covered player. Defaults and widget identity are now player-specific and current-first.

## Cache behavior

`DataManager` caches by dataset key, season, namespace, path, file modification time, and size. Replaced artifacts therefore invalidate naturally on the next load. Its targeted `invalidate()` API remains available for long-lived manager instances. Streamlit's cached League Hub model is keyed by the input DataFrames, so changed frame contents produce a new entry. Successful hosted-safe Core Refresh actions call `st.cache_data.clear()` before rerendering; commissioner refresh remains a local CLI and publishes atomically, after which a normal Streamlit rerun observes the new file signatures. Browser/session authentication state is not cleared.

Core Refresh remains hosted-safe and does not call Playwright, Selenium, Chrome, or browser-backed WhoScored acquisition. Commissioner Weekly Refresh remains the local authenticated workflow.
