# Manager Pages

The finalized 2025/26 experience deliberately differs from the live directory: historical cards emphasize final rank, record, form, average score, consistency, and points for/against. Profiles preserve Overview, Performance, Squad, Decisions, and Explorer with the established historical charts and drill-downs.

Live profiles include Cup status, record, opponent/history when artifacts exist, and an intentional pre-Cup empty state. Historical manager analytics remain frozen.

Live and historical manager surfaces share the global shell, typography, table density, accessible controls, and semantic missing states from [the design system](design_system.md). Manager aggregation definitions are unchanged.

The live Managers foundation provides selection and a compact profile from registered standings and manager-week data. Current fields are rank, record, recent form, points for/against, weekly score, average score, and position movement.

Decision quality, luck, transaction, and roster-construction analytics remain placeholders until registered live models support them. The 2025/26 manager pages and definitions are unchanged.

Sprint 7.2 adds the current roster table, active/reserve/IR counts, drafted-player retention, observed adds/drops, total roster moves, and recent events. Waiver success remains intentionally unavailable until current-season performance exists.

Sprint 7.3 adds position eligibility breakdown and roster averages for projection, Draft Score, ADP, historical fantasy points per 90, historical ghost points per 90, and projected minutes. These are read from registered Draft HQ context and do not recalculate draft models.
# 2026/27 live managers

The live directory and profiles consume `live_manager_analytics`, `live_player_analytics`, and `live_position_strength`. Manager aggregation uses numeric non-null means for projection, Draft Score, ADP, and projected minutes. Historical Points/90 and Ghost/90 are total points times 90 divided by positive historical minutes; xGI/90 uses Understat minutes. Draft retention is retained picks divided by all picks originally made by that manager.

Position strength assigns each player once by canonical position, preventing multi-position double counting. Weekly performance and decision tabs use explicit preseason messages until completed scoring and lineup inputs exist.
# Manager-player-week readiness

`manager_player_weekly` is built only from authoritative player-period facts joined to cached period roster/lineup state and Player Registry IDs. It remains schema-only in preseason and is the future input for decisions, bench points, formations, and optimal-XI analysis.

The join is period-specific. Current ownership is never projected backward. ACTIVE/RESERVE/IR and started slot are retained only when the corresponding historical roster/API cache proves them; lineup efficiency remains disabled when that evidence is absent.
# 2026/27 live managers

The live Manager section uses the same Overview, Performance, Squad, Decisions,
and Explorer structure as the finalized page. Its data contract and activation
rules are documented in `live_manager_analytics.md`. The finalized 2025/26 page
and its formulas remain unchanged.
Live manager directory cards use stable manager IDs. The integrated Open action
stores that ID in session state, reruns the Managers page, selects the matching
profile, and opens the default Overview tab without query parameters.
