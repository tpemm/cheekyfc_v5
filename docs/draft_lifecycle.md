# Draft Lifecycle

The completed 2026/27 phase freezes draft-day rankings before grading. These are decision grades, not hindsight evaluation. The live draft contained 15 selectable roster spots; the configured 16th slot is IR-only.

## Product position

Draft HQ is the immediate user-facing priority because the league draft
is this weekend. It is not the entire application and must not dominate the
global architecture. Draft work is one lifecycle within a season-long fantasy
league analytics platform.

Status labels in this document:

- **Current** — implemented and supported now
- **Planned** — accepted direction, not yet implemented
- **Proposed** — likely design requiring refinement
- **Under investigation** — capability or provider support is unverified

## 1. Pre-Draft Preparation

**Priority: immediate.**

### User goals

Rank and compare eligible players, understand tiers and market value, plan
positional construction, and maintain a shortlist before and during the draft.

### Current inputs and outputs

- Inputs: Player Registry, current squads, historical production, projections,
  ADP, team/fixture context, ghost points, identity bridges.
- Outputs: Draft player pool and Draft rankings with score, rank, tier, value
  versus ADP, availability/eligibility, and supporting metrics.
- View: Draft HQ with rankings, filters, player context, and detail.

## Draft-day session behavior

Draft HQ status tracking (`Available`, `Drafted by Me`, and
`Drafted by Other`) and the Draft Queue are browser-session state only. Reset
Draft Session clears only those temporary values; it does not create or modify
a draft-results dataset.

The workspace exposes Fantrax multi-position eligibility separately from the
canonical analytics position. Fantrax projected points come from the current
preseason export's `FPts` field, retained as `fantrax_projected_points`; they do
not affect Draft Score.

The Draft HQ uses four local workspace tabs: Draft Board, Compare Players,
My Queue, and My Team. The single user-facing Position column comes from the
registered current Fantrax player pool's `fantrax_position` field; canonical
registry position remains internal.

The live board uses one native Streamlit data editor. Its leading columns are
`Rank`, `Player`, a compact `ⓘ` detail action, `Mine`, and `Other`; all five
remain pinned while the table scrolls. `Mine` and `Other` update session draft
state in the same click. The icon opens the advanced player-detail dialog in
place through session-state selection, without URL/query-parameter navigation.

The premium player profile is organized into Elite Draft Score, Projection,
Market Context, Production, Ghost, Playing Time, deterministic Story, Model,
Actions, and a collapsed Draft Score explanation. Tier and status pills provide
compact identity context. Numeric presentation uses one decimal except for
natural counts. League and canonical-position percentiles, deterministic
strength/risk threshold summaries, and bounded model progress bars use retained
Draft data only and do not alter model calculations.

Compare transfers the current player into Player 1, clears Player 2, and
activates the Compare Players tab on rerun. Player 2 remains intentionally empty
until a challenger is chosen. The matchup view identifies the winner for each
shared numeric Draft metric, respecting whether higher or lower values are
better; no new analytics are calculated.
The compact default board exposes Rank, Player, detail/Mine/Other actions,
Fantrax position, club, tier, Draft Score, ADP, ADP value, Fantrax projection,
Minutes Outlook, Ghost/90, xGI/90, Team Strength Percentile, and Fixture Ease
Percentile when those fields exist. Optional Core, Production, Ghost,
Attacking, Playing Time, Context, and Draft Model groups persist in Streamlit
session state and expose retained or presentation-derived metrics.

Understat 2025/26 `understat_xg`, `understat_xa`, and `understat_minutes` enter
the registered `master_player_weekly` player/gameweek facts through the
canonical Fantrax/Understat identity merge. Draft Builder deduplicates by
Fantrax player and gameweek and retains season sums as `understat_xg_2526`,
`understat_xa_2526`, and `understat_minutes_2526`. Draft HQ
derives xGI as xG + xA and derives xG/90, xA/90, and xGI/90 only with a positive
Understat-minute denominator. No attacking field is filled when its source is
missing.

Team Strength Percentile is a presentation percentile of unique-club
`team_strength_rating`, sourced from `overall_team_rating`; higher means a
stronger club. Fixture Ease Percentile is a presentation percentile of unique
club `fixture_ease_next_5`; the fixture builder already defines higher ease as
more favorable, so no inversion is applied. Neither presentation percentile
changes its Draft Score component.

My Team is a session-only roster command center. Totals sum player totals;
historical rates use `sum(total) * 90 / sum(historical minutes)` over valid
rows, while simple averages are labeled as averages. Team Floor Score is a
separate 0–100 construction summary: 40% mean Ghost Score, 35% mean Minutes
Score, and 25% mean Minutes Confidence. It is not a weekly-points prediction.

Roster slots come from canonical Cheeky FC league rules: 16 total, 11 active,
the registered G/D/M/F minimums, four flexible active slots, four bench slots,
and one injured-reserve slot. Maximum-cardinality bipartite matching assigns
single-position slots before flex/bench slots and prioritizes less-flexible
players, so a multi-position player is never counted twice. Need labels are
explicit ratios of unfilled required slots: Complete, Low (<25%), Medium
(25–49%), High (50–66%), or Critical (67%+).

Best Available Fits remains separate from Draft Score. It distinguishes legal
slot need from strategic priority, fractional position scarcity, and tier
cliffs. F uses a 100 baseline, M uses 95, D uses 40, and G uses 0 until an unfilled
goalkeeper reaches the final two roster slots or critical scarcity. Default
session strategy is Pick 2 in a configurable 12-team snake, so the calculated
next-pick gap informs tier and survival urgency.
Strategy weights, including Scarcity Aware, are documented in `draft_hq.md`.
Reasons are deterministic, drafted players are excluded, and all selections
remain session-only.

An ADP-only refresh backs up and replaces the discoverable Fantrax preseason
export, validates it with `scripts/validate_fantrax_adp.py`, and runs Build Draft
Outputs. Player Registry is unnecessary unless identity, ID, team, position, or
material current-pool membership changed.

### Immediate planned improvements

- Better rankings table and sortable Draft metrics
- Position, club, tier, and search filters
- Clear tier breaks and tier-cliff visibility
- Player detail and side-by-side comparison
- Watchlist/queue
- Value-versus-ADP indicators
- Best available
- Positional scarcity and roster-construction context

These improvements should work without a live Draft API.

### Dependencies and limitations

Reliable Player Registry identity, current-squad eligibility, stable Draft
formulas, and a preserved draft-day baseline are prerequisites. Current
rankings are rebuildable working outputs, not yet an immutable draft snapshot.

## 2. Live Draft

**Priority: planned after immediate pre-draft usability.**

### User goals

Track selections, remove drafted players from availability, understand runs and
roster needs, identify reaches/value, and estimate who may survive to the
user’s next pick.

### Proposed inputs

- Draft-day immutable ranking snapshot
- Pick events containing round, overall pick, manager, player, and timestamp
- League roster/position constraints
- Watchlist/queue and manager roster state

### Proposed outputs and views

- Live draft board and best-available list
- Per-manager roster construction
- Position-run and tier-cliff indicators
- Value/reach flags relative to frozen rank and ADP
- Next-pick availability estimate

### Likely operations

Initialize draft session, import/record pick, correct pick, refresh availability,
and close/finalize draft. None are registered today.

### Limitations

Real-time Fantrax draft endpoints are unverified. The first live workflow should
support manual or file-based tracking and must not depend on an unproven API.

## 3. Post-Draft Grading

**Priority: immediately after draft-results ingestion.**

### Ingestion path A — file upload

**Planned.** Accept a Fantrax CSV export, retain the original upload, normalize
manager names, resolve players through the Player Registry, and preserve round,
pick, manager, player, and timestamps when supplied.

### Ingestion path B — Fantrax API

**Under investigation.** Determine whether the available Fantrax API exposes
complete draft results. Preserve raw payload snapshots and normalize provider
IDs through the Player Registry. Fall back to CSV when endpoints are missing or
incomplete. This project does not currently prove API draft-result support.

### Required immutable draft snapshot

Before grading, preserve the exact draft-day:

- Registry ID and provider IDs
- Player name, club, position, and availability
- Draft rank, Draft Score, tier, and ADP
- Projected points and projected minutes
- Model/version identifier and timestamp

Later working rebuilds must never rewrite this historical baseline.

### Proposed grading dimensions

- Value versus frozen Draft rank and ADP
- Tier value and positional scarcity
- Projected points/minutes captured
- Roster balance and construction
- Risk concentration
- Pick-by-pick grade and full-manager grade
- Steals, reaches, strengths, and weaknesses

Grading formulas are not finalized. They require explicit versioning and tests
before becoming Current.

## 4. In-Season Draft Evaluation

**Priority: planned after grading.**

### User goals

Separate draft quality from management quality and understand how drafted
assets, drops, trades, waivers, and replacements changed the original result.

### Required tracking

- Original drafting manager and current manager
- Current status: active, bench, injured reserve, free agent, dropped, traded
- Drop, waiver-add, and trade dates
- Weekly/cumulative fantasy and ghost points
- Starts, minutes, expected statistics, and projections
- Replacement-player chains linking failed picks to later additions

### Outputs and questions

- Expected versus actual value by pick, round, position, and manager
- Retained/dropped/traded views and evolving grades
- Best/worst picks and most valuable undrafted players
- Dropped players who later became valuable
- Managers who recovered best from failed picks
- Managers who drafted well but managed poorly, and the reverse
- Original roster versus current roster

Likely datasets include immutable draft picks/snapshot, weekly canonical player
facts, roster history, transaction history, and replacement links. Those
datasets and operations are not yet registered.

## 5. End-of-Season Draft Review

**Priority: planned after a complete in-season history exists.**

### Expected analysis

- Best/worst pick, biggest steal/reach, and best late-round selection
- Highest-value undrafted player
- Best dropped player and most damaging drop
- Most successful replacement chain
- Manager draft rankings
- Return by round and position
- Draft-day grade versus final grade
- League-wide, cross-season draft history

The final review must preserve the distinction between the original selection,
subsequent roster decisions, and replacement value. Cross-season comparisons
require stable scoring definitions and versioned snapshots.
