# Fantrax scoring configuration

The commissioner-provided 2026/27 rules live in `config/fantrax_scoring_2627.json`. The file is season-keyed and models the league as a goalkeeper profile plus a default outfield profile with defender, midfielder, and forward overrides. A future season must receive a separate file such as `fantrax_scoring_2728.json`; historical calculations continue to request `2627` explicitly.

`fantrax/analytics/core/fantrax_scoring.py` loads a season, resolves inheritance and overrides, and scores flat or cumulative-range rules. Missing seasons, positions, and stats fail explicitly. The outfield goal range is cumulative: goals one and two score nine each, and each goal from the third onward scores twelve. Thus a hat trick is 30, not 36, and no separate hat-trick bonus is added. Goalkeepers score 12 per goal. No defender goal override was encoded because the supplied evidence did not prove one.

Confirmed overrides are defender AER=1, defender AT=7, defender GA (first conceded zero, each subsequent goal -2), midfielder CS=1, and forward CS=0. Goalkeeper GA uses the same evidenced range. Other outfield rules inherit the default table. The effective-rule audit is written to `data/quality/season_2627/fantrax_scoring_effective_rules_2627.csv`.

The scoring-position authority is the Fantrax started/scoring position when present in the detailed cached export. Otherwise the existing deterministic canonical/first-eligibility position is used. The fallback is disclosed in validation; it does not invent a different position for multi-eligible players.

The cached detailed validation reconstructs points only to audit configuration transcription. Exported Fantrax FPts remains authoritative. Missing export components remain explicit and mismatches are not fitted away. Results are in `data/quality/season_2627/fantrax_scoring_config_validation_2627.csv`.

## Existing hardcodes audited

Before this sprint, `fantrax/analytics/core/league_rules.py` held position-sensitive G/AT/CS/GA tables, `fantrax/analytics/core/scoring_engine.py` implemented the third-goal range, `fantrax/live/player_performance.py` derived weekly Ghost by subtracting G/AT/CS/GA, and `fantrax/live/ghost.py` held separate return-only G/AT constants. The central resolver now owns scoring semantics for the scoring engine and both current Ghost paths. Roster constraints remain appropriately in `league_rules.py`. Historical frozen products and prediction prototypes were not rewritten.

## Ghost terminology and method

Fantrax supplies FPts and detailed components, not a native Ghost column in the current export. The prior weekly `ghost_points` value was calculated by this application, so its source is now named `FANTRAX_COMPONENT_DERIVED`, not `FANTRAX_EXACT`. It keeps precedence where already present.

For rows without that value, Ghost is authoritative FPts minus the central configuration's goal, assist, and clean-sheet awards. KP, SOT, AC, TkW, Int, CLR, AER, dribbles, blocks, dispossessions, cards, and GA are not subtracted. Fantrax fantasy assists are preferred; validated official assists are an explicitly labeled fallback. Clean sheets reuse the canonical participation derivation. Unknown return evidence produces partial/missing output rather than a silent zero.

Jack Hinshelwood is the current canary: MID, 28.5 FPts, two goals, zero assists, and one clean sheet. The engine removes 18 + 0 + 1 and yields 9.5 Ghost without player-specific logic.
