# Sprint 9.9A — Team Data Foundation

## Existing-product audit and canonical choice

The repository already contained two useful but separate current concepts:

- `team_match_features_2627.csv`: 20 WhoScored club-match rows with event counts, manager, formation, venue, final-third entries, and box entries.
- `understat_team_match_2627.csv`: 20 exact reciprocal club-match xG/xGA rows.

It also contained schedule-oriented `team_match_observations`, current season-level positional Fantasy Allowed, and finalized 2025/26 `team_match_features`, formation, playstyle, set-piece, and Fantasy Allowed products. These products have different grains and authorities, so none alone was sufficient as the canonical integration layer.

The selected authoritative product is `team_match_analytics`. Its grain is one club × completed Premier League match. Current 2026/27 contains 20 rows for 10 GW1 matches and 20 clubs. It integrates cached WhoScored events/context, exact Understat xG, canonical participation-derived scores, and separately attributed fantasy observations. Existing `team_match_features` remains provider evidence; `team_playstyle_profile` remains a compatibility consumer until the 9.9B UI bridge and should not compete as a second canonical layer.

## Authority and identity

- Match, opponent, venue, manager, and starting formation: current observed WhoScored/canonical match context.
- Goals/result: canonical current player-match team facts, reconciled reciprocally.
- xG/xGA: exact current Understat club-match perspectives.
- Event counts and locations: unique WhoScored events attributed once to acting match/team.
- Fantasy allowed: official Fantrax FPts where present; established best-available component hierarchy remains provenance-sensitive.
- Scoring interpretation: `config/fantrax_scoring_2627.json`; 9.9A does not rescore official observations.

Every current match has two reciprocal rows. Opponents, goals, xG/xGA, and H/A are validated in both directions. Raw event coordinates are immutable. Spatial summaries reapply the 9.8E convention (`plot_x = 100 - raw_y`, `plot_y = raw_x`) exactly once at analysis time: opponent goal top and real left/right preserved.

## Team event feature inventory

| Future label | Canonical field | Definition / aggregation | Source | Current | Historical | Comparable | Caveat |
|---|---|---|---|---|---|---|---|
| Pass Attempts | `passes` | Count of Pass events | WhoScored | Yes | Yes | Yes | Recorded events |
| Successful Passes | `successful_passes` | Successful Pass outcome | WhoScored | Yes | Yes | Yes | — |
| Pass Completion | `pass_completion_pct` | successful / attempted | WhoScored | Yes | Yes | Yes | Missing at zero attempts |
| Key Passes | `key_passes` | Validated KeyPass flag | WhoScored | Yes | Yes | Yes | Provider semantics |
| Cross Attempts | `crosses` | Pass with Cross qualifier | WhoScored | Yes | Yes | Yes | Not accurate crosses |
| Successful Crosses | `successful_crosses` | Cross + Successful | WhoScored | Yes | No compact field | No | Current addition |
| TakeOns / Successful TakeOns | `take_ons`, `successful_take_ons` | TakeOn; TakeOn + Successful | WhoScored | Yes | attempts only | Partial | Event location, not carry path |
| Shots | `shots` | Goal, SavedShot, MissedShots, ShotOnPost | WhoScored | Yes | Yes | Yes | — |
| SOT | `shots_on_target` | Goal + SavedShot excluding explicit Blocked qualifier | WhoScored | Yes | Yes | Review | Retains current validated semantic status |
| Goals | `goals` | Goal events / reciprocal score | Canonical + WhoScored | Yes | Yes | Yes | Result uses canonical score |
| xG / xGA | `xg`, `xga` | Exact reciprocal team match xG | Understat | 20/20 | Missing in compact reference | No | Never derived from WhoScored |
| Tackle Attempts | `tackles` | Tackle events | WhoScored | Yes | Yes | Yes | Not Fantrax TkW |
| Successful Tackles | `successful_tackles` | Tackle + Successful | WhoScored | Yes | No compact field | No | Provider outcome semantics |
| Interceptions / Clearances / Recoveries | corresponding fields | Event counts | WhoScored | Yes | Yes | Yes | Volume, not quality score |
| Blocks | `blocks` | BlockedPass/BlockedShot | WhoScored | Yes | No compact field | No | — |
| Aerials / Wins | `aerials`, `aerial_wins` | Aerial events; successful outcomes | WhoScored | Yes | attempts only | Partial | Event counts differ from fantasy contribution |
| Event Activity Center | `event_activity_center_x/y` | Mean normalized recorded-event origin | WhoScored-derived | Yes | raw-depth summaries only | No | Not average position/tracking |
| Third Shares | `*_third_event_share` | Recorded event origins by pitch third | WhoScored-derived | Yes | partial | Review | Not possession territory |
| Box Activity | `box_event_count/share` | Event origins inside normalized opponent penalty area | WhoScored-derived | Yes | partial | Review | Not player/team presence |
| Final-third Entries | `final_third_entries` | Successful pass from outside to inside final third | WhoScored-derived | Yes | Yes | Yes | Pass-only; no invented carries |
| Box Entries | `box_entries` | Successful pass from outside to inside opponent box | WhoScored-derived | Yes | Yes | Yes | Pass-only; missing endpoints excluded |

No progressive-pass count is published. The prior positive pass-distance value remains provider evidence but is not called a progressive pass because no approved Opta/StatsBomb-equivalent definition has been selected.

## Aggregated products

- `team_season_profile`: one row per club with W/D/L, goals, xG, event rates, neutral volume ranks, league averages, and percentiles.
- `team_manager_profile`: one club/observed-manager regime; descriptive and non-causal.
- `team_formation_analytics`: one club/starting formation with match share and observed features.
- `team_home_away_profile`: canonical H/A splits from validated match orientation.
- `team_fantasy_allowed_match`: match-attributable opponent fantasy observations.
- `team_fantasy_allowed_position_match`: the same foundation by deterministic primary Fantrax GK/DEF/MID/FWD group.

The existing 76-row current Fantasy Allowed product is a season-to-date opponent × represented-position aggregation: it does not contain match identity, and four club-position combinations have no represented sample. The new foundation contains 79 match-position rows because it retains exact match grain and every position actually represented in GW1. Rankings remain deferred to 9.9D.

## Historical compatibility

The finalized 2025/26 `team_match_features` evidence is not rewritten. A derived aligned reference contains 760 club-match rows, 380 matches, and 20 clubs. Compatible WhoScored event/context fields are carried across; unavailable xG/xGA and newer success/spatial fields remain missing. Current `afc_bournemouth` continues to resolve to historical `bournemouth`. Promoted clubs such as Coventry City honestly have no 2025/26 Premier League history.

## Pipeline and future hooks

`scripts/build_team_analytics_2627.py` is cache-only and runs in the commissioner refresh after unified player products. Plan mode reports current rows/matches/clubs, WhoScored coverage, Understat coverage, manager/formation coverage, Fantasy Allowed rows, staleness, and historical-reference availability. No acquisition authority changes and no Operations UI expansion were required.

Player tactical data can later join opponent features by `canonical_match_id + opponent_id`. Future opponent-style work can consume observed numeric distributions, but 9.9A creates no Low Block, High Press, Possession, Transition, or composite style labels. Formation, manager, H/A, xG/xGA, event volumes, and Fantasy Allowed remain clean future prediction features, but no predictions are produced.
