# Sprint 8 UI audit

Sprint 8.2.2 correction: the generic Archive Contents introduction and charts-before-awards ordering did not match the approved historical League Hub. The archive now opens directly with the compact League Hub identity, three summaries, final table, and award grid; trends are subordinate below.

Restoration follow-up: the 2025/26 Archive landing page had retained its table and awards but lost grouped highlights and both season-history charts; the Manager analytics remained present, but the directory had collapsed to a selector and Squad/Decisions order had drifted. Sprint 8.2.1 restores those structures without changing snapshot data or calculations.

Audit date: 2026-08-04. Scope: all registered Streamlit routes and their profile/dialog states. This is a source and AppTest audit; visual screenshots are tracked separately and must not be inferred from this document.

## Shared findings

- The application uses wide layout, but the previous 1600px shell and 3.75rem top padding waste space on a 1366×768 laptop. Page-specific CSS and the shell duplicated colors, radii, shadows, headings, cards, and responsive rules.
- “Page” headings were implemented with the same helper as section headings. Eyebrows, subtitles, season status, and refresh metadata therefore had no stable hierarchy.
- Native controls remain keyboard accessible. They should be retained. CSS selectors aimed at generated class names or internal dataframe cells are absent and should remain absent.
- Raw dataframes are functionally strong but vary in naming, density, numeric precision, missing values, and column count. Players and Managers expose too many secondary columns by default and scroll horizontally on laptop widths.
- Empty/preseason states rely heavily on generic `info` calls. They usually explain timing, but not always the next action. Coming-soon pages are especially sparse.
- Charts mix native Streamlit line/bar charts, Plotly, and Vega-Lite. Their calculations are settled; only Plotly had any opportunity for a reusable theme. Native charts inherit the Streamlit theme.
- Status colors and terminology vary: Live/Active, Free Agent/Available, reserve/IR, “Coming Soon,” raw event codes, and several encodings of missing data occur. Semantic tokens and badges are required.
- Cards use multiple page-local implementations and uneven content. Directory cards can become unequal height, while historical manager hero content has a different visual language.
- There is no intentional mobile information architecture. Native columns stack, but wide dataframes remain horizontally scrollable. Laptop-first prioritization is the practical target.

## Page inventory

| Surface | Current structure and strengths | Primary UX issues | Sprint treatment |
|---|---|---|---|
| 2026/27 League Hub | Heading, four KPIs, table, highlights, two charts, manager cards, leaderboards, activity and projections | Dense vertical run; duplicate metrics; raw activity codes; native charts lack shared semantics | Shared header/cards/theme; tighter shell; table remains prominent |
| Players / Available / Compare | Heading, filter controls, tabs, dataframe, profile state | Default table is very wide; four top-level tabs diverge from requested three; profile metrics are repeated 4-up strips; filter reset is not grouped | Shared page header and global control/table styling; preserve interactions; deeper restructuring deferred until screenshot-backed validation |
| Player Profile | Header, ownership, baseline, historical, floor, attack, minutes, fixtures, season, ownership history | Percentile decision context is buried; many equal-weight sections; little above-fold density | Shared hierarchy now; future pass should add a compact decision strip and percentile block without changing data |
| Managers / live profile | Large directory dataframe, selector, five profile tabs | Directory is table-first rather than cards; excessive default columns; profile selection visually competes with directory | Shared header/table density; retain stable selector/profile routing |
| 2025/26 League Hub | Bespoke heading/cards/tables/charts and award links | Older vocabulary and CSS differ from live pages; large cards and page-specific palette | Global shell/theme normalizes native surfaces; historical calculations and links untouched |
| 2025/26 Managers | Hero, selector, Overview/Performance/Decisions/Squad/Explorer | Most mature information design, but bespoke styling and mixed chart libraries | Global theme only; settled tab contents untouched |
| Draft HQ / Draft Grades | Multi-tab draft workspace, filters, tables, buttons, profile, exports | Interaction-heavy and regression-sensitive; bespoke presentation remains | Global shell/native-control consistency only in this pass; no routing or draft actions changed |
| Identity Review | Heading, status metrics, filters, evidence/decision controls and technical detail | Dense technical controls and mixed notice treatment | Global shell/control/table/notice normalization; logic untouched |
| Operations Center | Heading, health cards, primary refresh, status table, actions, activity, advanced diagnostics | Correct workflow; diagnostics visually compete in places; raw status glyphs | Shared page header/KPIs; Advanced remains secondary; actions unchanged |
| Raw Data Browser | Heading, dataset selection and dataframe | Technical terminology and very wide arbitrary datasets | Global shell/table styling; raw fidelity retained |
| Reports | Heading, selector and tall text area | Empty states are generic; fixed tall viewer adds scroll | Global shell/control styling; report fidelity retained |
| Key Output Health | Heading, status summary/table | Developer-facing vocabulary | Global semantics; validation output unchanged |
| Coming Soon | Heading plus single generic info banner | Large empty page; no next action | Full-width explanatory empty-state component |

## Accessibility, responsive, and performance risks

- Color must never be the sole signal; every badge, percentile, and operation status retains text.
- Muted text is set no smaller than 0.68rem badges / 0.72rem labels, with primary reading text at 0.78rem or larger.
- The page shell now targets 1480px and uses 1.5rem desktop / 0.8rem narrow padding. At narrow widths headers stack. Dataframes retain supported horizontal scrolling rather than brittle DOM overrides.
- Shared helpers are pure presentation functions. They do not load data, make HTTP requests, copy frames, or rebuild analytics.

## Terminology conventions

Use “Available” for the availability property and “Free Agent” for current ownership; “Reserve” and “IR” for roster locations; “Live,” “Finalized,” and “Coming Soon” for season/page state; “Refresh League” for the routine operation. Missing analytics display as an em dash, never `None`, `nan`, or a fabricated zero.
