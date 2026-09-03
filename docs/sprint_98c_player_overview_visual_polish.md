# Sprint 9.8C — Player Overview visual polish

The Player Overview retains the 9.8B/9.8B.1 data contract while presenting it as one compact research dashboard.

## Layout contract

The page order remains player identity, KPI strip, comparison toggle, profile row, comparison table, fixtures, and full gameweek research table. Wide layouts use a four-column row for the three fixed radars and Season Trend. Streamlit columns wrap naturally, while fixture CSS uses five, three, and two-column breakpoints for wide, medium, and narrow viewports.

## Formatting and missingness

Fantasy production uses one or two decimals according to the metric; xG/90 and xA/90 use two. Games/starts remain integers and ownership remains concise. Missing values render as an em dash and are never converted to zero.

## Profile visuals

Radars remain on the 0–100 percentile scale. The current season uses the accent color, stronger line, markers, and restrained fill. Historical data uses a neutral dotted line with reduced opacity and no fill. Missing axes remain gaps with `connectgaps=False`; the three-axis threshold is unchanged.

Season Trend uses compact current-gameweek, venue, and Ghost/major-return summaries. Missing venue samples show an em dash. Ghost carries a subtle partial-derivation hint.

## Header, set pieces, fixtures, and table

The player header integrates name, club, position, roster state, and manager. Set-piece evidence is rendered as wrapping chips and omitted when absent. Fixtures use compact equal-width cards. The wide gameweek table retains all research fields with Fantrax abbreviations and horizontal scrolling.

## Provenance and performance

Provider detail remains in help text rather than cluttering every value. Overview rendering remains cache-only; historical event data stays lazy behind the contextual Pitch / Events season selector. No acquisition, scoring, identity, participation, rate, percentile, or fixture methodology changed.
