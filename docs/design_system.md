# Fantrax design system

Approved page hierarchy is a protected product contract. Shared components may refine typography, color, borders, spacing, responsiveness, and accessibility, but must enhance—not replace or flatten—the established order and visual grouping.

Shared visual language does not imply identical information architecture. Mature historical views may keep purpose-built card groupings, chart placement, and interaction hierarchy while consuming semantic tokens, the global font/theme, chart helpers, and responsive shell. Generic components must not flatten established analytical pages.

Player analytical graphics use the shared Plotly theme and semantic five-color trace palette. Interactive radars belong in profiles/comparison only; database previews use compact bars. See [player_comparison.md](player_comparison.md).

The interface is a compact, light, laptop-first sports-data product. It favors hierarchy, readable tables, and native accessible controls over decorative effects.

## Foundations

`components/design_tokens.py` is the source of truth. The palette uses a neutral near-white background, white cards, dark ink, teal-blue accent, and restrained semantic green/amber/red. Colors mean accent, positive, above-average, neutral, warning, negative, or missing; views must not create new arbitrary palettes.

The type hierarchy is eyebrow (0.72rem), page title (2rem), section title (1.18rem), card title (0.9rem), metric label (0.72rem), metric value (1.45rem), annotation (0.78rem), table text (0.82rem), and badge (0.68rem). Page padding is 1.5rem, section gap 1.5rem, card gap 0.75rem, card padding 1rem, and compact control gap 0.5rem. Cards use a 12px radius; controls use 8px.

The page shell has a 1480px maximum width and 1120px compact-content target. At 800px and below, headers stack and page padding reduces to 0.8rem. Wide analytical tables keep native scrolling; identity and decision columns should be prioritized before adding more pinned or default columns.

## Components

- `page_header`: one per page; accepts eyebrow, title, subtitle, badge, and refresh metadata.
- `section_header`: introduces a content group, with optional supporting text and status.
- `metric_card`: compact KPI or highlight; supports detail, trend, rank, tone, and missing values.
- `status_badge`: textual state plus semantic tone. Never depend on color alone.
- `percentile_bar`: label, percentile, rank, raw value, and explicit missing state.
- `empty_state`: explains what is missing, whether expected, and the next useful action.
- `notice_card`: success, warning, error, information, preseason, or missing-data context.
- `manager_card_html`: compact directory/league summary rather than a duplicate standings table.
- `format_value`: em-dash missing values and deliberate precision.

Filters should live together above results, use concise labels, preserve stable widget keys, expose the active count when useful, and offer Reset without forcing unrelated analytics work. Related metrics belong in a group rather than many large cards.

## Tables and charts

Counts use whole numbers; most analytics one decimal; rates such as xGI/90 may use two decimals; percentages include `%`; missing values use `—`. ADP remains blank/missing and sorts last. Preserve multi-position strings. Default player tables prioritize identity, club/position, owner/status, projection, Draft Score, points/90, ghost/90, xGI/90, projected minutes, and fixture ease.

`components/charts.py` applies transparent paper, white plotting surface, semantic gridlines, compact margins and horizontal legends. Rank axes are explicitly reversed. Helpers change presentation only, never chart inputs or missing-value semantics.

## CSS safety

All shared CSS lives in `components/styles.py`. Selectors target stable Streamlit `data-testid` or application-owned `ft-*` classes. Do not style generated class names, dataframe cell internals, dialog internals, or every button globally. Prefer `.streamlit/config.toml` and native components. Test the shell, tabs, dialogs, dataframe scrolling, and sidebar after selector changes.

## Adoption checklist

Inject the shared stylesheet once through the application shell, render a page header, group content with section headers, use semantic components/tokens, prioritize laptop-width columns, apply the Plotly theme to new figures, and provide explanatory empty states. Analytics modules remain styling-free.
# Historical player UI

Historical player cards use the existing Fantrax Data card surface, border, radius, typography, and chart theme. Database rows remain lightweight; Plotly profiles render only for a selected profile or an active two-to-five-player comparison.
Live Managers preserves the established five-tab information architecture and
shared presentation components; Sprint 8.5 intentionally introduces no redesign.
The live League Hub preserves the settled hierarchy. Unsupported metrics use an
em dash, an intentional notice, or omission rather than a misleading zero card.
League Hub headline cards share one minimum height and internal structure. The
shared shell header no longer uses a negative top margin, preventing clipping
without changing fonts, colors, sidebar behavior or the wider design system.
## Live player information hierarchy

The live Players database favors a compact decision scan: identity, ownership, rate production, minutes outlook, and fixture ease. Deeper historical and radar context belongs in the profile. Draft-day context remains available below live performance, historical context, playing-time/fixtures, and ownership.
### Player scouting hierarchy

Live player profiles use one headline strip and one primary radar, then seven purpose-specific tabs. Current performance and playing-time facts are separated from outlooks; historical comparison is context; ownership and frozen draft-day values are secondary. Repeated metric dumps are avoided, and charts are used only for profile shape, rate comparison, or real weekly trends.
### Match-analysis layout

Performance uses two compact chart rows followed by one detailed table: full-season and recent-form charts, venue and composition charts, then gameweek facts. Shared Plotly theming is used throughout. Negative scoring uses signed bar/line geometry; donut geometry is reserved for nonnegative components.
### Overview scouting card

The Overview uses a 3:2 visual-to-stat desktop row that stacks naturally on narrow screens and stops after its exact-value panel.

### Player comparison surface

Comparison uses equal white cards with shared borders, 12px radii, compact two-column labels/values, and a 3:2 radar-to-table desktop row. Best exact values use the semantic `positive` token with bold type; ties receive equal emphasis. The presentation never introduces a Winner column or overall recommendation.
# Teams page states

Team profiles use the existing compact page header, section header, metric, tab, dataframe, and informational-state patterns. Unsupported preseason Fantasy Allowed and Playstyle data is represented with a clean explicit unavailable state.
