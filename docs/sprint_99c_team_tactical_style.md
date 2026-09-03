# Sprint 9.9C — Team Tactical Style

## Architecture and existing-product decision

The legacy `team_playstyle_profile` is a 120-row 2025/26 manager/formation aggregate of observed event rates. It has no classifications, but overlaps the restored canonical team profiles and lacks the calibrated spatial, stability, confidence, and opponent-context layers required here. It is retained for compatibility but deprecated as a tactical authority. `team_tactical_v1` is the single canonical interpretation system.

The architecture deliberately separates four layers: canonical observations describe what happened; relative features express league percentiles; tactical dimensions combine explicitly listed feature percentiles with configured weights; traits translate dimensions through visible thresholds. No primary archetype or quality score exists.

## Calibration, scaling, and confidence

Calibration uses all 760 2025/26 club-match rows, 380 matches, 20 clubs, and 38 equally weighted matches per club. The current application contains 20 GW1 club rows. Historical club percentiles use the historical 20-club distribution; current percentiles use the current 20-club distribution and are labeled separately. Manager, formation, and venue contexts are scaled against the historical club reference distribution.

Traits enter high/heavy at the 80th percentile and low/light at the 20th percentile. A minimum five-match sample is required. Confidence is Very Early (1–2), Emerging (3–4), Developing (5–9), or Established (10+). Therefore every current GW1 team receives numeric observations and percentiles but `Observation only`, never an established trait. No hysteresis is used in v1.

## Accepted dimensions

- Territorial Activity: 50% final-third event-share percentile and 50% final-third entries/match percentile.
- Width: final-third attacking actions occurring in outer lateral thirds. It is independent from crossing.
- Crossing Tendency: 70% cross attempts/match and 30% crosses per 100 final-third attacking actions. Cross success is separate.
- Central Creation: share of final-third key-pass and shot actions in the central lateral third.
- Dribbling Tendency: 70% TakeOn attempts/match and 30% TakeOns per 100 final-third attacking actions. Success is separate.
- Box Penetration: 60% box entries/match and 40% box event share.
- Chance Creation: 60% key passes/match and 40% Understat xG/match. Shots were removed after the correlation audit showed `r=0.914` with KP.
- Defensive Activity Height: 70% defensive-event depth and 30% attacking-third defensive-action share. This is explicitly not a pressing claim.
- Defensive Disruption: equal-weight tackles won, interceptions, and recoveries per match. It is activity, not quality.
- Aerial Orientation: aerial-contest volume/match. Aerial win percentage remains separate effectiveness.

## Deferred dimensions

Possession is deferred because no exact possession-percentage field exists in the canonical products; event volume is not substituted. Directness and a progressive-pass trait are deferred because v1 lacks a sufficiently validated geometric definition and industry equivalence. “High Press” is rejected: advanced defensive actions are observable, but pressure/turnover mechanics are insufficient. Shot Volume is retained as an observed feature rather than a separate trait because of redundancy with creation inputs.

## Validation findings

Split-half Spearman stability is strong for final-third share, entries, crosses per 100 attacking events, TakeOn volume, KP, shots, xG, recoveries, and aerial volume; the remaining accepted spatial/activity features are moderate. Median partial-to-full rank recovery rises from roughly 0.23 after one match to 0.60 after five, 0.77 after ten, 0.90 after 19, and 1.00 at 38. This supports the five-match trait gate and Very Early GW1 state.

Home/away values are preserved in `team_venue_tactical_profile`; venue is not automatically adjusted because effects vary by feature. Manager rows retain match-observed regimes and do not claim causality. Formation is contextual, never treated as a style itself. Red-card matches are flagged and retained in v1 rather than silently removed. Score-state adjustment is deferred because reliable state-duration segmentation has not yet been validated.

## Integration and operation

Teams Overview and Tactical Profile show a compact fingerprint chart and an explanation table containing season, dimension, trait, percentile, underlying metric, value, confidence, explanation, and caveat. Current and historical scales are labeled separately. Before five current matches the UI says “Current vs 2025/26 observation,” not “style change.” Coventry has no historical fingerprint; Bournemouth uses the established identity bridge.

`team_opponent_tactical_context` is joinable by `canonical_match_id`, club, and opponent. Pure helpers join it to player-match and Fantasy Allowed observations without surfacing premature conclusions or rankings. Weekly commissioner refresh applies the frozen `team_tactical_v1` after canonical team analytics; historical calibration remains versioned and need not change weekly. Plan mode reports methodology version, baseline availability, tactical rows/clubs, current match count, confidence, and product freshness.

All products are cache-only. No browser, network, prediction, primary archetype, possession label, directness label, or pressing label is introduced.
