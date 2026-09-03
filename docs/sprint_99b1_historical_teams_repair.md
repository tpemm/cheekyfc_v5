# Sprint 9.9B.1 — Historical Teams Repair

## Exact failure and lineage

`data/models/season_2627/advanced/historical_fantasy_allowed_ranked_2627.csv` existed but contained only `0D 0A` (a CRLF newline). Direct `pandas.read_csv` raised `pandas.errors.EmptyDataError: No columns to parse from file`; `DataManager` correctly wrapped that exception as `DatasetValidationError`. This was not an encoding, delimiter, quoting, duplicate-header, coercion, or registry-parser defect. It was a stale headerless artifact produced outside the validated 2025/26 descriptive build.

The validated lineage is immutable 2025/26 Fantrax/WhoScored evidence → `advanced_player_match_2526` plus canonical single-primary Fantrax position → exact-alignment positional aggregation → rate and validated ease-rank normalization → a 2025/26 comparison product prepared under the 2026/27 application model tree → DatasetRegistry → Teams Fantasy Matchups. The 2627 location is intentional application-season routing; its rows retain historical club identities and 2025/26 methodology.

`scripts/build_historical_team_repair_99b1.py` now deterministically produces the 80-row comparison artifact. The registry contract was already correct and was not weakened.

## Historical inventory and restored data

The repaired team-match compatibility model retains 760 club-match rows, 380 EPL matches, and 20 clubs. The compact 571,844-row historical pitch cache provides complete raw start-coordinate coverage. Its legacy cached plot columns are not trusted; preparation reapplies the corrected transform (`plot_x = 100-y`, `plot_y = x`) without mutating raw coordinates. The repair applies the same current event aggregation definitions to passes, successful passes, KP, cross attempts/successes, TakeOn attempts/successes, shots/SOT, tackle attempts/wins, interceptions, clearances, blocks, recoveries, aerial contests/wins, entry metrics, zones, box activity, activity center, and defensive-event depth.

The protected Understat schedule contains all 380 2025/26 EPL matches with home/away xG. Match IDs align with the historical team rows, so xG/xGA and xG difference are now restored for all 760 club-match rows with reciprocal validation. No xG was fabricated or provider-blended.

Derived season, manager, formation, and H/A profiles were rebuilt outside protected paths. Nottingham Forest retains four match-observed manager regimes. The existing 2,438-row set-piece hierarchy covers all 20 historical clubs.

## Fantasy Allowed methodology

The repaired grain is opponent club × GK/DEF/MID/FWD: 80 unique rows across 20 clubs. FPts is official Fantrax, Ghost retains the established method, and G/A/KP/SOT/AC/TkW/Int/CLR/AER use exact single-club-match Fantrax alignment where observed. Missing remains null, notably unsupported accurate-cross samples; observed zero remains zero. Per-match rates and the existing validated historical ease ranks are retained. No current-season ranks were introduced.

## UI, identity, and compatibility

Overview now shows historical record, goals, xG/xGA, KP, shots, crosses, TakeOns, and historical league profiles. Match Analysis exposes the enriched 38-match rows. Tactical Profile lazily loads the compact historical parquet only when historical mode is selected and restores pitch layers, zones, manager, formation, and venue splits. Fantasy Matchups renders the repaired historical component table and keeps rank detail in an expander.

`afc_bournemouth → bournemouth` is applied before historical team and Fantasy Allowed selection. Coventry remains an explicit no-2025/26-Premier-League case. The compatibility map was regenerated from actual coverage rather than omissions in the earlier compact model.

Protected `data/seasons/2526` and `data/raw/whoscored/2526` evidence is read-only. All repaired outputs live under derived model or quality directories. No browser, network, style classification, or prediction is used.
