# Advanced data inventory — 2025/26

Sprint 9.6 production use is governed by `data/reference/fantrax_supplemental_stat_policy_2526.csv`: key passes, aerial wins, and interceptions may fill genuine Fantrax missingness; tackles, crosses, and other definition-mismatched fields remain separate.

Generated from the complete cached 380-match layer. This document describes observed and deterministic derived data only; it contains no predictions or opaque scores.

## 1. Identity / context

The inventory covers 15 source/model tables, 380 validated raw matches, 20 clubs, 677 observed WhoScored players, and 31 managers. Canonical player identity is proven for 522/537 meaningful appearance players (97.21%). Tactical role is distinct from Fantrax eligibility.

## 2. Playing time / substitutions

`SubstitutionOn` and `SubstitutionOff` are explicit event types: 3132 on-events and 3132 off-events. Expanded minute is suitable for an observed substitution timestamp, including provider stoppage-time expansion. It is not an exact elapsed-minutes clock. `estimated_minutes_played` may be derived as `sub_off_expanded_minute` for starters or `match_expanded_max - sub_on_expanded_minute` for used substitutes, but remains **RESEARCH_ONLY** until reconciled against authoritative minutes. Unused substitutes have neither event. Existing `minutes` remains usable only where the player payload or exact Understat/Fantrax context supplies it.

## 3. Rating

Final rating extraction is deterministic: take the rating-history value at the greatest numeric history key. All rated values are bounded 0–10. All appearances: 11492/15189 (75.66%), median 6.5, range 4.07–10.0. Starters: 100.0%; used substitutes: 100.0%; unused substitutes: 0.0%; goalkeepers: 100.0%. Unused-player missingness is expected.

## 4. Tactical roles

17 raw position values were observed. Known values map deterministically into the established role taxonomy; unmapped values remain missing. Starting-role coverage is 97.15%. Starting formation is production-ready. In-match `FormationChange` events exist (1129) but are research context rather than a complete continuous formation timeline.

## 5. Passing

Pass attempts and completion are directly observed from `Pass` plus outcome. Explicit passing qualifiers include: Cross, Throughball, Longball, HeadPass, CornerTaken, ThrowIn. Final-third entry and box entry are deterministic coordinate-derived metrics. The existing positive x-distance field is labeled a progression proxy, not a validated “progressive pass.” Switches, distance bands, and direction groups remain research until a written geometry threshold is adopted.

## 6. Chance creation

Key passes require the explicit `KeyPass` qualifier. Assists retain explicit provider evidence where present. Open-play versus set-piece key passes can be safely derived by combining `KeyPass` with restart/situation qualifiers. Understat remains authoritative for xA.

## 7. Set pieces

Observed qualifier support: CornerTaken, DirectFreekick, Penalty, ThrowIn, SetPiece, FromCorner. Corners, free-kick passes/crosses/key passes, penalties, and set-piece shots are safe when their explicit qualifier is present. “Set-piece taker” profiles are derived counts, not assigned roles. Absence of a qualifier must not be treated as proof of a different restart type.

## 8. Dribbling / carries

`TakeOn` plus outcome supplies attempts, successes, failures, and locations. Final-third and box TakeOns are safe spatial derivatives. No continuous tracking/carry stream exists; WhoScored TakeOns must not be labeled complete carries.

## 9. Shooting

Shots are `MissedShots`, `SavedShot`, `ShotOnPost`, and `Goal`. Locations, body-part and situation qualifiers support transparent splits where present. WhoScored supplies outcomes; Understat remains xG authority. No WhoScored xG approximation is approved.

## 10. Defensive actions

Tackle, interception, clearance, recovery, blocked-pass, and relevant block events are directly observed. Outcome can split tackle success where populated, but WhoScored tackles are not Fantrax tackles won. Defensive-action height is a safe average-location derivative.

## 11. Aerials

Each participant has an `Aerial` player-event with outcome-based win/loss semantics. Player attempts count participant events. Team physical-contest counts must pair related opponent events or divide validated paired events; summing both participants double-counts contests.

## 12. Fouls / discipline

Foul, Card, and offside event types plus card/penalty/misconduct qualifiers provide explicit evidence. “Foul won” versus “foul committed” requires related-player/team semantics and remains usable with caveat until every pairing is validated.

## 13. Goalkeeping

Goalkeeper evidence is distributed across events, qualifiers, and player stat histories rather than one complete event type. Saves and explicit claim/punch/smother/parry evidence may be used individually. A complete goalkeeper-actions total is not approved without a dedicated reconciliation.

## 14. Spatial / pitch data

Coordinates are normalized 0–100 and provider-oriented left-to-right for the acting team. Base-coordinate coverage is 100%; complete end-coordinate coverage is 66.52%. Safe labels are **Event Activity**, **Event Activity Density**, and **Event Activity Heatmap**, never player tracking. Production layers: activity, passes, key passes, crosses, TakeOns, shots, defensive actions, recoveries, and aerial player-events. Pass lines require end coordinates; point layers do not.

## 15. Team / formation

`team_match_features_2526` has 760 unique club-match rows. Production-ready inputs include formation, manager, event totals, passing, creation, shooting, defensive actions, aerial player-events, and transparent spatial averages. Understat owns xG/xGA; Fantrax owns fantasy production allowed.

## 16. Manager context

Manager per club-match, observed date ranges, formation under manager, player role under manager, and event rates under manager are available. Observed ranges are not exact employment dates and causal manager effects are not claimed.

## 17. Fantrax integration

Fantasy points and Ghost points remain Fantrax-authoritative and are attributed only for exact single-league-match periods. Season reconciliation shows provider-definition agreement without forcing equivalence. Tackle and cross comparisons retain caveats because Fantrax fields are tackles won and accurate crosses.

## 18. Understat integration

Understat is authoritative for xG, xA, and xGI, with 11,237 exact player-match joins (76.56%). Missing exact joins stay missing; season aggregates are not substituted.

## 19. Rates and future modeling inputs

Totals, per-match, per-appearance, and per-start rates are safe with explicit denominators. Per-90 is allowed only when compatible authoritative minutes are non-null; substitution timestamps alone are not sufficient. Available future inputs include recent starts, roles, formation, manager, prior lineup, venue, opponent, exact historical minutes, positional fantasy allowed, xG/xGA, event/spatial profiles, and schedule context. They remain inputs—not predictions.

## Readiness summary

- **PRODUCTION_READY:** canonical_match_id, canonical_player_id, club_id, opponent_id, whoscored_player_id, rating, formation, actual_position_standardized, started, key_passes, dribbles_attempted, dribbles_successful, aerials_attempted, aerials_won, interceptions, clearances, recoveries, blocked_passes, through_balls, shots, shots_on_target, goals, passes_attempted, passes_completed, understat_match_id, date, fantrax_period, venue, manager_id, manager_name, fantrax_player_id, understat_player_id, fantrax_ghost_points, fantrax_points
- **USABLE_WITH_CAVEAT:** minutes, tackles, crosses, fouls, xg, xa, understat_minutes, xgi, understat_alignment, club_period_fixtures, mgr_fantasy_points, mgr_min, mgr_kp, mgr_tkw, mgr_int, mgr_clr, mgr_cos, mgr_aer, mgr_sot, mgr_ac, fantrax_alignment
- **RESEARCH_ONLY:** feature_class, registry_player_id, fantrax_id_clean, avail_fpts
- **REJECT:** contains_prediction

Machine-readable evidence lives in `data/reference/advanced_metric_inventory_2526.csv` and the season quality dictionaries. Inventory build time: 43.327 seconds.
