# Sprint 9.8B Player Research Experience

The Player Profile Overview follows a fixed research hierarchy: current ownership header, eight KPIs, Fantasy/Attacking/Defensive radars, season trend, five fixtures, and full gameweek statistics. Deeper match, event, role, and provider detail lives in dedicated tabs.

Current 2026/27 observations are primary. Metric authority is Fantrax observed value, validated provider-derived equivalent, caveated provider observation, then missing. An observed Fantrax zero is authoritative. Historical values never fill current missingness.

The fixed radar cohort is the player's deterministic primary Fantrax eligibility: GK, DEF, MID, or FWD. Multi-position players use their first listed Fantrax position consistently across all three charts. Current and 2025/26 percentiles are calculated separately within the same positional cohort; the historical layer is secondary. Profile axes use rates except the Fantasy Profile's season-production percentile, which ranks the current sample only against current peers rather than against full historical totals.

Assists use Fantrax fantasy assists when detailed data exists and validated official assists otherwise. The normal label is “Assists”; model provenance retains the semantic distinction. Ghost uses exact Fantrax Ghost first and explicitly partial-derived Ghost second. Clean sheets use detailed Fantrax values first and the validated 60-minute G/D/M match-context rule otherwise.

Waiver players retain WhoScored and Understat observations through the canonical 9.8A summary and match log. Being unowned never suppresses advanced columns. Unplayed players keep missing advanced observations and missing rates rather than manufactured zeroes.

Ownership is overlaid from the latest `player_ownership_2627` snapshot at render time. A refreshed add/drop therefore changes the header and database without browser or network work during rendering. All Overview inputs are registered compact CSV/model products; historical event parquet remains lazy-loaded only after a profile and advanced season are selected.
