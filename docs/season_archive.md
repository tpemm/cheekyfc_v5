# Historical season archive

## Faithful League Hub target

The approved landing-page order is fixed: compact application header; Season Overview / Finalized Historical Season eyebrow; League Hub title and concise subtitle; exactly three summary cards; dominant Final League Table; four-column Season Awards grid; then historical charts and supporting highlights. The former Archive Contents box was removed from the first screen. Archive identity remains in navigation and the finalized shell badges rather than replacing the familiar League Hub title.

Polish is intentionally subtle: token-based white cards, 12px radii, light borders/shadows, compact padding, clean movement arrows and semantic form dots. At laptop width, the three summaries remain one row and award cards use Streamlit’s responsive four-column rows; native stacking is reserved for narrow layouts.

## Sprint 8.2.1 layout restoration

The archive keeps the pre-existing historical information architecture inside the Sprint 8 shell. The landing page again makes the Final League Table prominent, groups six historical highlights, restores side-by-side Weekly Scoring and League-Position History charts, and retains the emphasized awards/records grid. The archive framing is additive; it is not a generic directory replacing the analytical landing page.

Historical Manager pages retain their purpose-built hero, Recent Form, six-value overview strip, paired season-trend charts, identity metrics, performance/luck/momentum analysis, squad analysis, optimal-XI and formation decisions, and Explorer. The tab order is restored to Overview, Performance, Squad, Decisions, Explorer. A three-column historical directory restores rank, record, form, average scoring, consistency, and points-for/against context above the stable manager selector.

Git history was not available in this workspace (`fatal: not a git repository`). Restoration therefore used the surviving rich `views/managers.py`, historical regression tests, the archived V1 application as secondary evidence, and the finalized snapshot schemas. No old global stylesheet was reintroduced.

Finalized seasons are presented as intentional read-only archives. The 2025/26 navigation entry is **2025/26 Season Archive**, headed **Finalized Historical Season** and marked Frozen / Read only.

The archive retains the final league table, season timeline, weekly position/scoring history, awards, records, historical manager/player context, leaderboards, and settled analytics. Existing manager and award routes remain available. All content continues to load through the snapshot namespace; no live dataset or operation is substituted.

Future seasons should expose a season-specific archive entry backed by their immutable snapshot and may include retained Cup results/records. Archive views may change presentation but must never rebuild or rewrite finalized data.
# Historical Players access

The 2025/26 navigation includes Players directly alongside the Season Archive and Managers. Its tabs are Player Database, Player Profile, and Compare Players, all clearly labeled `2025/26 · Finalized Historical Data`.
