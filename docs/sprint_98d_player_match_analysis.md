# Sprint 9.8D — Player Match Analysis

Match Analysis is now the canonical match-by-match fantasy research view. It reads the current canonical player match log and the compact finalized historical supplemental player-match product. It never loads historical events.

## Statistical contract

All production-distribution metrics use starts only. Median is P50. Floor is P10 and ceiling is P90; both are suppressed until ten starts. Consistency is the population standard deviation of Fantrax points among starts, making lower values directly interpretable as steadier production. Substitute appearances remain in the chart and table but do not affect these start distributions.

Return Dependency is the non-Ghost share of observed fantasy points. It is shown only when match Ghost provenance is exact Fantrax; partial-derived Ghost makes the metric unavailable rather than falsely precise.

## Match contract

Current rows come from `current_player_match_log_2627.csv`, including authoritative Fantrax points, established Ghost/assist/clean-sheet semantics, canonical participation, role, formation, rating, and exact match-attributed Understat xG/xA. Historical rows come from the compact `supplemental_player_match_2526.csv`, using the established identity bridge and best available Fantrax, WhoScored, and Understat evidence.

Observed zero remains zero. Missing observations remain missing. Future fixtures, unsupported DNPs, and fabricated match xG/xA are not emitted.

## UI contract

The tab defaults to `2026/27 Current` and can browse `2025/26 Historical`. It presents production KPIs, median/floor/ceiling/dispersion, return dependency, scoring-band distribution, a chronological FPts/Ghost chart, and a horizontally scrollable canonical research table with per-match role context.

Historical minutes are unavailable in the finalized compact source and therefore historical FPts/90 and Min/Start remain blank. This is intentional missingness, not a zero or estimated-minute substitution.

## Refresh and future use

The commissioner refresh already rebuilds the current canonical participation, summary, and match-log products after provider corrections. Historical data is finalized. Match IDs, opponents, venue, role, formation, manager context, and provider observations remain available for Sprint 9.8E Role & Tactical without changing identity foundations.
