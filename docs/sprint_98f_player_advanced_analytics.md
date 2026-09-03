# Sprint 9.8F — Player Advanced Analytics

## Purpose and audit

Advanced remains the deep statistical Player Profile tab. Before 9.8F it contained a useful rate selector, Advanced Snapshot, observed tactical-role chart, grouped WhoScored/Understat profile, set-piece hierarchy, and a match-detail table. The grouped profile, transparent rates, role evidence, and set pieces were preserved. The duplicated match-detail table was removed because Match Analysis owns match logs; pitch analysis remains exclusively in Role & Tactical.

The refined order is analysis controls, fantasy production, grouped statistical components, tactical/set-piece evidence, fantasy contribution, positional context, current-versus-historical comparison, and collapsible provenance. Current 2026/27 remains the default. Historical is explicit and loads compact profiles without loading historical pitch events.

## Rate basis

One resolver applies Total, Per Start, or Per 90 to compatible metrics. Starts and minutes come from canonical participation observations. Rating, ranks, and success percentages are never divided. A zero denominator returns missing; zero successes with a positive denominator returns 0%. Missing historical minutes produce missing Per 90 and are never replaced by Per Start.

## Source hierarchy and fantasy contribution

The hierarchy is Fantrax detailed (including explicit zero), validated provider fallback, source-specific provider observation, then missing. Attempted TakeOns, raw crosses, tackle attempts, recoveries, and similar event concepts remain WhoScored-specific. Understat remains xG/xA authority. Tactical role never determines Fantrax scoring position.

Fantasy contributions use `config/fantrax_scoring_2627.json` through the centralized scoring resolver. The table shows component, count, effective scoring weight, contribution, and human-readable source. Official Fantrax FPts is never replaced by reconstructed points. Observed FPts, known contribution, and the unreconciled difference are shown together when reconstruction is incomplete.

Return Points are the configured contributions of goals, assists, and clean sheets where observed. Ghost remains the authoritative/established 9.8D.1 value; the component table explains known peripheral contributions without redefining Ghost or forcing reconciliation.

## Metric inventory

| UI group / labels | Canonical fields | Priority | Rate compatible | Historical | Caveat |
|---|---|---|---|---|---|
| Fantasy: FPts, Ghost, G, A, CS | `fantrax_points`, `ghost_points`, `goals`, `assists`, `clean_sheets` | Fantrax; established Ghost derivation | Yes | Yes where observed | Official FPts remains authoritative |
| Chance Creation: KP, xA, TB, Cross Attempts, AC | `key_passes`, `xa`, `through_balls`, `cross_attempts`, `accurate_crosses` | Fantrax KP/AC; Understat xA; WhoScored attempts/TB | Yes | Yes | Raw crosses are not AC |
| Shooting: G, xG, Shots, SOT, xG/Shot, G-xG, SOT% | `goals`, `xg`, `shots`, `shots_on_target` and derived rates | Fantrax G/SOT; Understat xG; WhoScored shots | Counts yes; derived ratios no | Yes where covered | No shot-level xG join |
| Passing: attempts, completions, completion % | `passes_attempted`, `passes_completed`, `pass_completion_pct` | WhoScored | Counts yes; percent no | Yes | Recorded passes, not tracking |
| Dribbling: attempts, CoS, success % | `dribbles_attempted`, `successful_dribbles`, `dribble_success_pct` | Fantrax CoS then successful TakeOn | Counts yes; percent no | Yes | Attempts are WhoScored-specific |
| Defense: tackle attempts, TkW, Int, CLR, recoveries, blocks, DIS | corresponding canonical fields | Fantrax detail then validated/provider fallback | Yes | Yes where covered | Tackle attempts differ from TkW |
| Aerials: attempts, wins, win % | `aerial_attempts`, `aerial_wins`, `aerial_win_pct` | Fantrax wins then WhoScored; attempts WhoScored | Counts yes; percent no | Yes | Counts are not fantasy points |
| Rating | `rating` | WhoScored | No | Yes | Provider rating |
| Set pieces: type, rank, attempts, share, sample | set-piece usage product | WhoScored validated context | No | Yes | No left/right corner claims |

## Peer and historical context

Positional context uses the deterministic primary Fantrax cohort—GK, DEF, MID, or FWD—and compares rate-compatible current metrics with the cohort average and percentile. Sample size is displayed above the section. Current-versus-historical tables use like-for-like fields and absolute differences; missing values remain missing.

Waiver players do not require manager membership. Their WhoScored, Understat, derived Ghost, clean-sheet, and other evidence remains available under the same hierarchy. No predictions, fixture models, match filters, event maps, browser calls, network calls, or provider acquisition were added.
