# Sprint 9.8E — Player Role & Tactical

## Purpose and information architecture

Player Profile now uses four canonical tabs: Overview, Match Analysis, Role & Tactical, and Advanced. Role & Tactical answers where recorded actions occurred, which provider-observed role and formation accompanied them, and how those descriptions change by season, window, match, venue, start status, observed tactical role, and formation. It contains no prediction or opponent-style classification.

The page is organized around compact scope controls, a Role Snapshot, the Event Activity Map, zone summaries, set-piece evidence, and match-by-match role history. Selectors with only one meaningful tactical role or formation are omitted. Historical products are requested only after the historical season is explicitly selected; the registered data service retains its cache and player-first filtering behavior. Page rendering performs no browser or network acquisition.

## Event evidence, not tracking

WhoScored rows are recorded event locations. “Event Activity Density,” “Event Activity Center,” and “Event Activity by Zone” must not be interpreted as tracking, every touch, physical movement, average position, or occupancy. Raw provider coordinates and semantics remain immutable.

## Coordinate normalization

The canonical player pitch is vertical: own goal at the bottom, opponent goal at the top, and attacking depth increases upward. WhoScored `x` is therefore mapped to `plot_y`. After rotation, the provider lateral axis was mirrored; the corrected mapping is:

```
plot_x     = 100 - raw_y
plot_y     = raw_x
plot_end_x = 100 - raw_end_y
plot_end_y = raw_end_x
```

This transform is shared by current and historical data at display time. It corrects both origins and endpoints while leaving `x`, `y`, `end_x`, and `end_y` unchanged. The Cole Palmer goal `ws:2959574243:1` is the mandatory canary: raw `(96.9, 65.0)`, former display `(65.0, 96.9)`, corrected display `(35.0, 96.9)`. It remains at the opponent goal and moves to the correct left side.

## Pitch and layers

The reusable Plotly pitch includes touchlines, goal lines, halfway line, center circle and spot, both penalty areas and six-yard boxes, penalty spots and arcs, four corner arcs, and goal indications. Cartesian axes are hidden and event marks remain dominant.

Layers are: Event Activity Density; Passes; Key Passes; Crosses; Dribbles / TakeOns; Successful Dribbles; Shots; Defensive Actions; Recoveries; and Aerials. Pass, key-pass, and cross endpoints are drawn only when provider endpoints exist. TakeOn events are locations, never invented carry paths. Crosses use WhoScored Cross semantics and are not all labeled Fantrax Accurate Crosses. Successful Dribbles filters WhoScored `TakeOn + Successful`, so its selected-layer success rate is 100% when non-empty. Layer summaries use appropriate attempt/completion, contest/win, or action/success labels.

## CoS authority

The Overview Full Gameweek Stats table now displays compact `CoS` between AC and TkW. It means Successful Dribbles, not attempts. The existing match-product authority is retained: detailed Fantrax CoS, including explicit zero, wins; successful WhoScored TakeOns fill only missing Fantrax detail; otherwise the value remains missing. Pitch locations remain WhoScored event evidence.

## Role, formation, zones, and set pieces

Primary role is the most frequent provider-observed tactical role among starts. Role Stability is its share of observed starts and always exposes the sample. Primary formation and formation share use the same transparent start population. Tactical role never substitutes for Fantrax eligibility or scoring position.

Event Activity by Zone divides normalized event origins into defensive, middle, and final thirds plus left, center, and right lanes. Box activity uses the displayed penalty-area geometry (`plot_y >= 82`, `20 <= plot_x <= 80`). These are event shares, not tracking presence. Set-piece tables retain provider-supported rank, attempts, share, and sample; no unsupported left/right corner assignment is made.

Opponent strength remains absent unless an existing canonical FDR value is safely available. The filter model accepts additional context dimensions later, but High Press, Low Block, Possession Dominant, Transition, and other opponent types are deliberately not created here.

## Performance and boundaries

Current event products are compact. Historical loading remains explicit, registered, cached, and player-filtered. No finalized historical source data, frozen Draft HQ data, or immutable GW1 evidence is modified. Existing Overview, Match Analysis, centralized scoring, and Ghost methodology are not recalculated by this sprint.
