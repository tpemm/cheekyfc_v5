# Player profiles and comparison

Sprint 8.1 adds a presentation-derived player analysis layer. Canonical data is still loaded through `DataManager`; comparison state lives only in Streamlit session state and is never registered or written to disk.

## Modes, rate bases, and presets

Supported modes are Projection, Historical, Current Season, Draft Profile, and Custom. Rate basis is Total, Per Game, Per Start, or Per 90. Rate selection only swaps fields explicitly mapped in the catalog; percentage, rank, projection, context, and minutes metrics retain their natural unit.

Named presets are Balanced Profile, Projection, Historical Production, Floor and Minutes, Attacking Upside, and Draft Value. A custom selection must contain four to eight unique catalog metrics. Catalog order is retained because Streamlit has no stable native drag-reordering control.

Current Season mode uses current-season fields only. Before weekly performance exists it displays: “2026/27 performance data will appear after the first completed scoring period.” It never substitutes historical values.

## Metric catalog

`analytics/players/comparison_catalog.py` declares each supported field, label, family, valid mode, supported rate fields, unit, precision, direction, percentile eligibility, missing behavior, minimum requirement, and provenance. Views cannot request arbitrary dataframe columns. Families cover projection, fantasy production, ghost floor, attacking output, playing time, club, fixtures, draft, ownership, and current season where canonical fields exist.

Lower-is-better ADP and Draft Rank use reversed percentile direction and ranking. Missing data remains missing and is never converted to zero.

## Peer groups

League percentiles use every valid player in the loaded live-player frame. Position percentiles assign each player exactly once: canonical primary position when populated, otherwise the first valid Fantrax eligibility. A multi-position player is not duplicated across groups. Fewer than five valid positional peers triggers a warning.

Ties use pandas average percentile ranks and deterministic minimum competition ranks. Every compared player uses the same prepared distribution, axes, mode, rate basis, peer basis, and 0–100 scale.

## Radar and raw values

The reusable Plotly component supports four to eight axes, stable order, responsive size, restrained fills, five semantic trace colors, and no network calls. Hover contains label, raw value, percentile, rank, peer count/group, and source. Missing points remain gaps. If fewer than four metrics are valid, no polygon is drawn.

Every radar is followed by an exact-value table containing player, metric, raw value, percentile, rank/count, peer group, and source. This table is authoritative for reading exact values; the radar is a shape summary.

## Comparison state and layouts

`player_compare_ids` holds at most five stable registry IDs with Fantrax ID fallback. Duplicate additions are rejected. Users can add from a live profile or Draft HQ player detail, remove individual players, or clear the list. Normal reruns retain state; nothing is persisted to disk.

One player produces an instructional state. Two players receive a head-to-head title, deterministic tags, shared radar, and raw-value table without a Winner column. Three to five players receive a combined radar, legend, low-opacity fills (outlines beyond three), and the same compact raw table.

## Coverage and reuse

Tags and warnings are deterministic: high floor, historical production, xGI, minutes security/rotation, fixtures, free agent, multi-position, ADP value/reach, limited historical sample, missing ADP, and missing Understat sample. Profile previews use compact percentile bars; full Plotly radars are limited to profiles and comparison to protect database performance.

Draft HQ only adds a session-state handoff; Mine/Other, queue, rankings, board, and navigation are unchanged. Future Trade HQ should import the catalog, prepared percentile functions, radar/raw panel, and shared selected IDs rather than implementing another normalization system.
# Historical comparison

Historical Players reuses `analytics.players.comparison`, the controlled comparison catalog, and `components.player_radar`. It supports two through five players, League or Position percentiles, controlled four-to-eight-axis presets/custom selection, exact values, ranks, peer counts, and provenance. The shared table has no synthetic Winner column and preserves direction-aware percentile highlighting.
# Live comparison

Current fantasy points, Ghost Points, and xGI support the established Total, Per Game, Per Start, and Per 90 bases. Live comparisons use a common completed-period window and peer universe; historical and projection modes retain their existing inputs.
# Supplemental source compatibility

Supplemental factual fields may share a comparison universe only where the compatibility audit approves analytical comparison. Row-level provenance remains available. Fantrax-specific or materially incompatible definitions are not mixed.

Current Season comparisons use the same finalized Fantrax periods and selected Season/Last 3/5/10 window for every player.
