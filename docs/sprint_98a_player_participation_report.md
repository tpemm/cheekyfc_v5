# Sprint 9.8A — Player Participation and Rate Foundation

1. **Executive summary:** Added a canonical current-season player-match participation layer and promoted its denominators into weekly, season-summary, match-log, and UI rate calculations.
2. **Canonical participation dataset rows:** 393 identity-resolved player-match squad rows.
3. **GW1 expected starters:** 220.
4. **GW1 observed starters:** 220.
5. **Starter validation:** 22 in every match, 11 in every club-match, no duplicate player-match rows.
6. **Appearance validation:** 307 observed appearances, defined only as a start or recorded substitute entry.
7. **Substitution validation:** 87 used substitutes and 86 mapped unused substitutes; unused substitutes are excluded from appearances.
8. **Minute source hierarchy:** match-attributable Fantrax detail, exact Understat player-match, then WhoScored lineup/substitution derivation.
9. **Minute coverage:** All 307 appearances have non-null, non-negative minutes: 157 Fantrax, 123 Understat, and 27 WhoScored-derived.
10. **Janelt root cause:** Understat supplied 90 minutes and an appearance, but the all-player Fantrax row had no detailed GS value and WhoScored starter evidence was not promoted into weekly denominators.
11. **Janelt corrected output:** Vitaly Janelt (`05tre`, WhoScored `298689`) now has GP 1, Starts 1, Minutes 90, FPts/Start 26, and FPts/90 26.
12. **Player Games coverage:** Explicit canonical Games values for all 617 current players; 307 played and 310 did not play.
13. **Player Starts coverage:** Explicit canonical Starts values for all 617 players; 220 started.
14. **Player Minutes coverage:** Explicit season-minute denominators for all 617 players; 307 appeared.
15. **FPts/Game coverage:** 307 valid values.
16. **FPts/Start coverage:** 220 valid values.
17. **FPts/90 coverage:** 306 valid values; the recorded 90th-minute substitute correctly has a zero-minute denominator.
18. **Ghost methodology audit:** Existing rostered Ghost remains Fantrax-authoritative; waiver Ghost is a separately labeled partial reconstruction from validated league-scored components.
19. **Ghost exact-source coverage:** 157 observed player-match rows use Fantrax Ghost.
20. **Derived Ghost coverage:** 150 observed waiver player-match rows have `PARTIAL_DERIVED` Ghost.
21. **Ghost component completeness:** Partial rows disclose 0.40 coverage (6 of 15 configured component concepts); exact rows disclose 1.00.
22. **Ghost/Game coverage:** 307 valid values.
23. **Ghost/Start coverage:** 220 valid values.
24. **Ghost/90 coverage:** 306 valid values.
25. **Assist fallback behavior:** 150 waiver observations use WhoScored official assists without double-counting.
26. **Fantasy-assist authority behavior:** 157 detailed rows retain Fantrax fantasy assists and `FANTRAX_FANTASY_ASSIST` semantics.
27. **Clean-sheet derivation rule:** Team conceded zero, player appeared for at least 60 minutes, and primary Fantrax position is G/D/M. Forwards are scoring-ineligible.
28. **Clean-sheet validation sample:** 157 detailed Fantrax player-match rows.
29. **Clean-sheet agreement:** 100% exact agreement on all 157 comparable rows.
30. **Clean-sheet waiver coverage:** 150 observed waiver rows receive match-context CS values; unused substitutes receive none.
31. **Validated TkW coverage:** 307 observed rows, with Fantrax detail first and successful WhoScored tackles as fallback.
32. **Validated accurate-cross coverage:** 307 observed rows, with Fantrax detail first and successful WhoScored crosses as fallback.
33. **SOT display behavior:** 307 observed rows; Fantrax detail wins and WhoScored-derived SOT is retained for waiver display only.
34. **Clearance display behavior:** 307 observed rows; Fantrax detail wins and WhoScored clearance remains source-specific/caveated fallback.
35. **Waiver player advanced coverage:** All 150 observed waiver rows include participation plus best-available football metrics; xG/xA cover 267 of 307 total observations.
36. **Current player summary rows:** 617, one per current Fantrax player.
37. **Current match-log rows:** 307, one per observed canonical player-match.
38. **Player Database result:** Existing compact database contract is preserved; its Per Game/Start/90 values now come from repaired weekly canonical denominators.
39. **Player Advanced result:** Current advanced observations retain roles, formations, rating, provider metrics, and the repaired denominators.
40. **Player Comparison rate result:** Comparison continues to consume the same weekly aggregation, now backed by the shared rate helper.
41. **Player Pitch confirmation:** Existing current event maps and canonical player-match filters are unchanged.
42. **Participation quality report:** `player_match_participation_gw1_2627.csv` and `player_participation_summary_2627.json` prove the starter and identity gates.
43. **Rate quality report:** `player_rate_validation_gw1_2627.csv` records canonical denominators and all points/Ghost rates.
44. **Ghost quality report:** `ghost_component_audit_gw1_2627.csv` records source and component completeness per observed player.
45. **AppTests:** Existing live Players AppTests passed in the focused run.
46. **Tests added:** 48 collected Sprint 9.8A cases, including 36 parameterized shared-denominator cases and 12 data-contract regressions.
47. **Focused tests:** 78 passed in 16.07 seconds.
48. **Full-suite result:** 821 passed in 121.79 seconds; the known Windows temporary-directory cleanup warning occurred after successful completion.
49. **Performance:** Canonical product build completes in approximately 2–3 seconds locally; the full suite completes in about 2 minutes.
50. **Files created:** participation module/builder, three current model products, five focused quality products, regression tests, and this report.
51. **Files modified:** player aggregation uses the shared rate helper; advanced/commissioner orchestration rebuilds participation; registry exposes the three products.
52. **Protected-path verification:** Git reports no changes under `data/seasons/2526`, `data/raw/whoscored/2526`, `data/models/season_2526`, or frozen Draft HQ.
53. **Remaining limitations:** Seven WhoScored squad rows lack canonical identity; partial waiver Ghost is deliberately not authoritative; one 90th-minute substitute has zero minutes and therefore no per-90 rate.
54. **Recommended next Player UI cleanup:** Use the registered season summary and match-log products directly for selectable compact columns and richer provenance help, without changing the underlying methodology.
55. **Final decision:** **A — PLAYER PARTICIPATION + RATE FOUNDATION READY.**
