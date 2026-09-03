# Sprint 9.9B — Teams Research Experience

## UI audit and final information architecture

The previous Teams page used six tabs: Overview, Squad, Fixtures, Formations, Fantasy Allowed, and Playstyle. It also exposed separate advanced-data and fantasy-allowed season controls, mixed current fixture/Understat cards with historical advanced bundles, retained rank/ease language in Fantasy Allowed, and duplicated formation and playstyle tables. Useful fixture, formation, set-piece, and complete-pitch work was retained.

The page now has four team-driven tabs: Overview answers how strong the club is and what environment it creates; Match Analysis shows what happened match by match; Tactical Profile describes how and where recorded actions occurred; Fantasy Matchups reports observed fantasy production allowed. The canonical current club selector drives all four.

## Authority and preparation

`analytics/teams/research.py` prepares UI-free models from `team_match_analytics`, `team_season_profile`, `team_manager_profile`, `team_formation_analytics`, `team_home_away_profile`, `team_fantasy_allowed_match`, and `team_fantasy_allowed_position_match`. Canonical fixtures and the validated set-piece hierarchy are reused. Understat is the sole xG/xGA authority. Rendering performs no acquisition, browser, network, or raw provider aggregation.

Overview uses a curated KPI row, chronological Goals/xG/xGA trend, Next 5 canonical fixtures, manager/formation context, formation mix, and set-piece hierarchy. Its three fixed five-axis panels show team value, league average, neutral volume percentile, and volume rank across the full 20-club distribution. Higher percentile means more of the named characteristic, not better performance; xGA is therefore not inverted.

## Current and historical behavior

2026/27 is always primary. Overview has one optional `Compare to 2025/26` toggle. Historical fields remain compatibility-gated. Sprint 9.9B.1 subsequently restored historical xG/xGA from the matched 380-game Understat schedule. The internal `afc_bournemouth` to `bournemouth` bridge is preserved without exposing slugs. Promoted Coventry explicitly reports that no 2025/26 Premier League comparison is available; Championship data is not substituted.

Match Analysis offers season and H/A controls, a compact aggregate row, a chronological match table, and an xG/xGA trend. Tactical Profile offers season, Season/Last 10/Last 5/Individual Match scope, H/A, observed formation, and match-observed manager filters. Historical pitch maps are lazy: when compact compatible location evidence is unavailable, the numeric profile remains available and no pitch is fabricated.

## Tactical and fantasy semantics

Pitch layers are called Team Event Activity / recorded actions / event density, never touches, tracking, average position, or possession territory. The shared Sprint 9.8E transform leaves raw coordinates immutable and renders the opponent goal at the top. Zones are descriptive thirds and left/center/right shares. Final-third and box entries are successful passes entering those zones from outside; carries are excluded. Crossing attempts and successes, TakeOn attempts and successes, shooting, defensive actions, recoveries, and aerial activity remain distinct.

Fantasy Matchups is observational. FPts uses official match-attributable Fantrax observations; Ghost uses the established Ghost method. Detailed components use Fantrax when observed and may use validated provider supplements. Waiver detail is never fabricated. Position samples are reindexed to GK/DEF/MID/FWD: `—` means unavailable/no sample and `0` means an observed zero. Historical fantasy data is labeled as a different-grain reference. No rankings, ease/hardness claims, grades, style classifications, composites, recommendations, or predictions are produced.

## Sample size and limitations

The current GW1 sample is shown compactly in the header and relevant sections rather than repeated warning banners. A one-match formation share may correctly be 100% but is not interpreted. Current percentiles are volatile by design. Sprint 9.9B.1 restores historical xG and loads compact historical pitch evidence only when selected; detailed fantasy component completeness remains limited to validated observations.
