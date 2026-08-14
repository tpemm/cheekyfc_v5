# Platform Roadmap

Sprint 8.2.2 completes the faithful historical League Hub correction. Future shared-style work must preserve the approved three-card/table/awards-first structure.

Sprint 8.2.1 restores the proven historical hierarchy inside the unified shell. Future design-system migrations must inventory mature page structures before replacing local presentation helpers.

Sprint 8.2 establishes season-scoped Cup configuration/results and the future archive pattern: each finalized season receives a named read-only archive, with Cup history fitting naturally beside league history.

Sprint 8.1 supplies the comparison boundary future Trade HQ should reuse: controlled metrics, presets, rate and peer bases, cached percentile distributions, radar/raw-value output, and session-selected player IDs.

Sprint 8 establishes the reusable global visual system and laptop-first shell. Future Trades, Weekly Reports, and History pages must adopt [the design system](design_system.md) instead of creating page-local palettes or CSS.

This roadmap sequences the whole fantasy league analytics platform. Draft
Center is the urgent workflow, not the product boundary. No calendar dates are
assigned; priorities are dependency-based.

## Phase 1 — Foundation

**Status: substantially complete.**

- DatasetRegistry, SeasonManager, DataManager, and OperationsService
- Modular `views/` presentation and custom navigation
- Finalized-season isolation and working preseason support
- Current EPL squad pipeline
- Player Registry, matching, aliases, identity review, and validation
- Draft Builder and current Draft HQ
- Automated unit, integration, architecture, and AppTest coverage

Remaining foundation maintenance includes documentation upkeep, explicit
schema expansion where justified, and preserving immutable snapshots.

## Phase 2 — Immediate Pre-Draft Tools

**Priority: required for this weekend.**

Sequence:

1. Improve ranking table readability and sortable metrics.
2. Complete position, club, tier, and name filters.
3. Make tier breaks, value versus ADP, and best available prominent.
4. Add player detail and comparison.
5. Add a persistent watchlist/queue.
6. Add positional scarcity and roster-construction planning.

Dependencies: current squads, Player Registry, stable Draft outputs, reliable
eligibility, and explicit UI-state persistence. Do not require a live Draft API.

## Phase 3 — Draft Results Ingestion

**Priority: immediately after the draft.**

Sequence:

1. Define registered draft-result and immutable snapshot datasets.
2. Capture/freeze the model inputs and outputs used on draft day.
3. Add CSV upload and raw-upload preservation.
4. Normalize manager and player identities.
5. Reconstruct picks and manager rosters.
6. Investigate Fantrax API draft-result coverage.
7. Add API ingestion only if proven complete enough; retain CSV fallback.

Dependencies: versioned snapshot contract, Player Registry, manager identity
normalization, upload validation, and duplicate-pick safeguards.

## Phase 4 — Draft Grading

**Priority: after normalized ingestion.**

- Define and version pick-grade dimensions
- Grade value versus frozen rank, ADP, and tier
- Evaluate projected value captured and positional scarcity
- Assess roster construction, balance, and risk concentration
- Produce pick, position-group, and manager grades
- Identify steals and reaches

Dependencies: immutable draft-day snapshot, complete pick order, roster rules,
and approved/tested formulas. Frozen-snapshot 2026/27 Pick Grades, manager grades, rankings, and awards are now implemented; in-season hindsight evaluation remains separate.

## Phase 5 — In-Season Draft Tracking

- Link original picks to current roster identities
- Track retained, dropped, traded, waived, and free-agent status
- Compare frozen expectations with actual weekly/cumulative production
- Model replacement-player chains
- Separate draft skill from in-season management
- Recalculate explicitly versioned evolving grades

Dependencies: weekly player facts, roster snapshots, transaction history,
manager/player identities, and stable event dates.

## Phase 6 — Broader League Analytics

- Richer manager profiles and decision analysis
- Team/squad analyzer and lineup optimization
- Waiver, drop, transfer, and transaction analytics
- Matchup and opponent analysis
- Player explorer and comparison
- League records and cross-season history
- Commissioner operations, health, and update tooling
- End-of-season Draft review and league-wide draft history

Some capabilities already exist in partial form for 2025/26. This phase means
integrating and extending them into the current service architecture, not
discarding existing analytics.

## Sequencing principles

- Build on registered canonical identities rather than page-local name matching.
- Register source, generated, and snapshot datasets before building views.
- Preserve immutable baselines before calculating retrospective value.
- Prefer file-based workflows before relying on unverified external APIs.
- Version formulas before comparing grades across time or seasons.
- Keep operational mutation bounded and presentation read-oriented.
- Deliver immediate draft usability without coupling the global architecture to
  a single weekend workflow.

## Sprint 7.1 — League Hub foundation

The 2026/27 homepage consumes the Sprint 7.0 registered live models through DataManager. It establishes the live League Hub, reusable presentation cards, manager-profile foundation, Players shell, and forward navigation for Trades, Weekly Reports, and History. Later sprints activate placeholders only when authoritative registered models exist.

## Sprint 7.2 — Roster tracking

Current ownership now advances through immutable, checksum-linked roster snapshots. Deterministic events and continuous intervals establish the data foundation for waiver analysis, roster evaluation, dropped-player outcomes, confirmed transactions/trades, and season-long draft grading.

## Sprint 7.3 — Operations Center

Routine league maintenance is now one user-facing action with staged progress, plain-language health, quick actions, and recent session activity. Technical diagnostics and legacy rebuilds remain available under Advanced. Players and Managers expose registered draft, ownership, projection, and historical context before current-season scoring begins.
# Live-season sequence

Sprint 7.0 establishes acquisition/cache/model/quality/registry plumbing. Next, capture the real 2627 league response, verify manager/team IDs and API status vocabulary, prove a transaction/player-pool refresh source, and connect weekly player scoring. After real data flows, polish—not redesign—the settled League Hub. Later sprints can activate full Players, Managers, and Trade Tool analytics using the gaps listed in `live_season_data.md` and `trade_tool_foundation.md`.
# Sprint 7.4 status

Live player and manager presentation foundations are implemented. Current-season rolling form, lineup optimization, decision quality, and waiver evaluation remain gated on completed weekly player-stat and submitted-lineup data.
# Sprint 8.3 status

The finalized 2025/26 archive now includes a searchable player encyclopedia, historical profile radar, and multi-player comparison. Coverage limitations remain explicit for players without complete rostered event, ghost, or Understat history.
# After Sprint 8.4

- Prove a documented official Fantrax player-stat endpoint before replacing the weekly export fallback.
- Add live Understat ingestion and identity coverage when 2026/27 observations exist.
- Validate Ghost Points against a known post-match Fantrax score.
- Expand current-window controls across comparison and Available Players once real weekly rows exist.
# Supplemental-provider decision

Reassess provider needs after several completed periods using fantasy-relevant coverage. Do not add another provider unless Fantrax plus Understat leaves material gaps for important players, particularly defensive events.

After GW1, reconcile known player weekly scores and manager starter totals, then monitor authenticated-session expiry and real scoring-category coverage before enabling lineup-efficiency presentation.
# Sprint 8.5

Live Manager Analytics is structurally ready for post-GW1 activation. Submitted
lineup-dependent analysis remains intentionally gated on authoritative evidence.
Sprint 8.6 establishes the preseason homepage and automatic post-GW1 League Hub
activation. Power Rankings and waiver-success grading remain future designs.
Sprint 8.7 completed stable manager draft-origin reconciliation, compact League
Hub table/cards, readable position labels, and stable-ID manager-card selection.
