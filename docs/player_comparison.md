# Player Comparison

The live comparison is a session-only research surface over registered `DataManager` datasets. It supports two through five stable player identities and follows one hierarchy: title, selection and controls, compact player cards, then a 3:2 shared-radar/exact-table row. Nothing is written to disk and no profile sections are appended.

## Selection and controls

The selector stores stable registry IDs with Fantrax ID fallback while showing name, club, and position rather than internal IDs. Duplicate additions are rejected, five players is the maximum, and individual removal or clear-all preserves valid state.

Controls retain Projection, 2025/26 Historical, Current Season, Draft Profile, and Custom modes, plus Per Game, Per Start, Per 90, League/Position percentiles, and three-to-eight catalog-backed editable metrics. There is no second metric catalog or large comparison preset control.

## Player cards

Each equal-width card shows identity followed by Points, Ghost, and xGI for the selected basis; Minutes Outlook; Next Fixture; Home Avg; Away Avg; and authoritative Owner/Available status. Current mode never backfills absent live production with historical values. Historical mode uses finalized 2025/26 weekly data for venue splits.

Opening fixtures retain the registered Fantrax venue evidence: an `@` opponent is away, an explicit venue wins, and a scheduled non-`@` fixture is home. The display is `Opponent (H)` or `Opponent (A)`. A bare opponent with no supported venue evidence is displayed without a suffix; missing fixtures use an em dash.

Home and Away averages use valid appearances, starts, or minutes for the selected basis. Missing samples remain missing and are never zero-filled.

## Shared radar

The shared radar continues to use `analytics.players.comparison`, `comparison_catalog`, and `components.player_radar`. Every player receives identical selected axes and the established League or primary-Position percentile universe. Missing values remain gaps. Rich comparison hover retains raw value, percentile, rank, peer count/group, and provenance. Two or three valid traces may use restrained fill; four or five use outlines to limit overlap.

## Exact comparison

The exact table contains Stat plus one column per selected player and no Winner column. Stable rows are Season Points; Points/Game, Points/Start, Points/90; Ghost/Game, Ghost/Start, Ghost/90; Goals; Assists; xGI/90; Home Avg; Away Avg; Minutes Outlook; and Next 5 Fixture Ease. Rows missing for every player are omitted.

Selected radar metrics absent from the stable set are appended once. Direction comes from comparison-catalog metadata. Every tied best valid value is bold and uses the semantic dark green `positive` token; missing values are neither compared nor highlighted. The tool deliberately provides evidence without an overall winner, composite score, or recommendation.

## Season behavior

Current Season uses current 2026/27 fields and completed current weekly rows only. Historical uses finalized 2025/26 fields and weekly rows. Projection, Draft Profile, and Custom retain their existing catalog inputs. Compare has no merged season-composite or synthetic overlay mode; the separate Player Profile season overlay remains unchanged.
