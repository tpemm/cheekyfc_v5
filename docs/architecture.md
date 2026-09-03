# Current Architecture

Historical views are allowed a purpose-built presentation layer. `views/league_hub.py` derives only chart-ready pivots and cumulative display ranks from already-finalized matchup rows; `views/managers.py` retains the established historical analytical renderer. Neither writes data nor changes historical builders.

The Cup domain is a pure engine in `analytics/cup`, fed by registered configuration, immutable seed snapshot, and official manager-week scores. Artifact mutations occur only through four approved OperationsService entries. Historical archives continue using the snapshot namespace. See [cup_tournament.md](cup_tournament.md) and [season_archive.md](season_archive.md).

Player comparison is a cached presentation derivation under `analytics/players`, with rendering in `components/player_radar.py`. It consumes DataManager-loaded frames, creates no datasets, performs no HTTP calls, and exposes session-only state for future Trade HQ reuse.

The shared presentation boundary now consists of semantic tokens (`components/design_tokens.py`), centralized scoped CSS (`components/styles.py`), reusable primitives (`components/presentation.py`), and chart theming (`components/charts.py`). Views own content; analytics modules remain free of styling. See [design_system.md](design_system.md).

## Dependency direction

```text
DatasetRegistry
      ↓
SeasonManager
      ↓
DataManager
      ↓
OperationsService (state-changing workflows)
      ↓
Presentation views
```

The application starts at:

```text
app.py
  → core.legacy_renderer.render_application()
  → custom season selector and sidebar
  → exactly one renderer from views/
```

`core.legacy_renderer` is retained as the application-shell compatibility
module. It owns shared page configuration, styling, season selection, custom
navigation, and dispatch. Streamlit native multipage navigation is disabled.

## Layer responsibilities

### DatasetRegistry

`core/services/dataset_registry.py` is the central catalog for stable dataset
keys, descriptions, path templates, lifecycle classifications, producers,
consumers, required columns, mutability, and required/optional status. It does
not read or write files.

### SeasonManager

`core/services/season_manager.py` resolves configured seasons and working versus
snapshot namespaces. It controls page availability and operation capabilities.
Finalized seasons are immutable; 2026/27 is the current mutable preseason.

### DataManager

`core/services/data_manager.py` resolves registered paths, reads supported
formats, validates initial contracts, returns provenance and status, caches
defensive copies, and exposes narrow cache invalidation. It is read-oriented;
it is not an arbitrary persistence API.

### OperationsService

`core/services/operations_service.py` is the allowlisted execution boundary.
It validates operation IDs, season capability, parameters, and JSON boundary
types; runs fixed project scripts with `shell=False`; and returns structured
results. It does not accept arbitrary commands or paths.

### Presentation views

Modules under `views/` translate service results into Streamlit controls and
output. Current views are League Hub, Award Detail, Managers, Draft HQ,
Identity Review, Update Pipeline, Raw Data Browser, Key Output Health, and
Reports. Views do not read or write files and do not import builders.

## Domain and artifact layout

- `analytics/` — reusable current-squad, player-registry, identity-review, and Draft logic
- `fantrax/` — ingestion and historical league/manager analytics
- `scripts/` — fixed operational entry points and validation wrappers
- `core/` — models, storage providers, and foundation services
- `views/` — presentation-only Streamlit modules
- `tests/` — unit, integration, architecture, and AppTest coverage
- `data/processed/` — working processed player and manager datasets
- `data/analytics_views/` — working presentation-ready analytics
- `data/reference/` — bridges, current squads, registry, and reviewed overrides
- `data/models/draft_2627/` — current Draft model outputs
- `data/quality/` and `data/seasons/<season>/reports/` — validation and reports
- `data/seasons/2526/` — finalized historical snapshot

## Player identity flow

Current squads, Fantrax identities, historical records, and bridges feed the
Player Registry. Matching priority is stable IDs/manual overrides, exact name
plus club, unique exact name, explicit aliases, ordered-token expansion,
constrained fuzzy matching, then unresolved. Built-in aliases live in
`analytics/player_registry/aliases.py`; user decisions live in the registered
`player_alias_overrides` dataset. Identity Review suggestions never approve
themselves.

## Draft flow

The Draft builder consumes the Player Registry and registered/contextual
sources, calculates existing scores, tiers, ranks, and ADP comparisons, then
writes `draft_player_pool` and `draft_rankings`. Draft formulas are domain
logic, not service or view responsibilities.

## Non-negotiable rules

- Views never call `pandas.read_*`, write CSVs, construct artifact paths, or call builders.
- All dataset paths are registered centrally.
- All state-changing page actions use registered operations.
- Season availability and mutability are controlled centrally.
- Generated datasets are never manually edited.
- Overrides are registered reference data and must preserve unrelated records.
- Provider identifiers are preferred over normalized names.
- Identity methods, sources, confidence, club checks, and position checks remain auditable.
- Broad nickname inference and unconstrained fuzzy matching are prohibited.
- Writes invalidate affected reads, regenerate dependent artifacts when needed,
  and rerun the UI only after success.
# Sprint 7.0 cache-first boundary

The live-season network boundary is `fantrax.live.acquisition`, invoked only by a registered refresh script. `fantrax.live.pipeline`, DatasetRegistry/DataManager, analytics builders, and Streamlit views consume local cache/models only. Atomic validation gates both raw and normalized replacements. The existing OperationsService and DatasetRegistry architectures are extended, not replaced. Frozen Draft HQ and finalized 2025/26 namespaces are outside every live producer path.

# Sprint 7.1 presentation boundary

Season-aware routing selects finalized 2025/26 renderers or the 2026/27 live presentation layer. Live views load registered datasets exclusively through DataManager and build transient display models; they do not own acquisition, persistence, identity resolution, or analytical formulas. Shared presentation primitives allow Players and Managers to extend the same visual language without coupling domain logic.

# Sprint 7.3 operations workflow

The Operations Center orchestrates existing registered operations; it does not fetch, write datasets, or execute arbitrary commands itself. The primary workflow chains the live cache refresh and live model build. Technical and legacy operations remain registered but collapsed under Advanced. Status presentation reads the registered live manifest through DataManager.
# Live presentation boundary

Views read registered, cached presentation models through `DataManager`; they do not call Fantrax or directly read normalized CSV files. The live pipeline performs stable-ID enrichment once during refresh so widget interactions only filter prepared frames.
# Historical player presentation

`views/historical_players.py` loads finalized and frozen inputs exclusively through `DataManager`. `analytics/players/historical.py` creates an in-memory cached presentation frame; it does not write into the finalized season, call HTTP services, or rebuild source analytics. Radar preparation is shared with live Players and Draft HQ comparison rather than duplicated.
# Live player-performance boundary

Network access is confined to refresh. Normalization and aggregation read cached Fantrax/Understat artifacts only, and Streamlit reads registered normalized datasets only. This preserves repeatability and prevents widget interactions from calling providers.
# Supplemental source boundary

The canonical live Understat raw namespace is `data/raw/understat/2627/`. The cache-only build maps match timestamps through Fantrax `scoringPeriods`, performs exact-ID Player Registry resolution, and applies centralized source priority. Pages never merge providers themselves.

Authenticated Fantrax weekly acquisition is the other refresh-only boundary. Raw period files validate and commit atomically under `data/raw/fantrax/2627/player_stats/`; builds never invoke Playwright and pages never read raw exports.
Live manager views are cache-only consumers of DataManager datasets. Analytical
frames are built once in the live pipeline rather than rebuilt per profile.
League-level completed-period filtering and highlights live in
`fantrax.live.league_analytics`; the Hub is a DataManager presentation consumer.
Manager draft labels are normalized only for identity matching and resolve to a
stable manager ID. Frozen draft values and visible team names remain unchanged.
League Hub is the single user-facing 2026/27 default route; the internal Home
renderer alias remains available only for routing compatibility.
# Team fixture foundation

Live fixture context now follows: canonical club registry → one-row-per-match schedule → two-row team perspective → team/player presentation. Views read these registered products through `DataManager` and perform no acquisition.

Fixture acquisition is an explicit cache operation. Current football-data page 1 is always revalidated before its fresh pagination is followed; normal page renders remain network-free.

Schedule precedence is now cached soccerdata Sofascore first, with football-data.io retained as a non-overriding fallback. ClubElo is an independent optional strength layer feeding canonical team fixtures; Understat remains authoritative for expected metrics.

Matchup intelligence preserves Observed → Derived → Predicted boundaries. Sprint 9.1 implements the first two layers and model-ready frames only. Formation, role, lineup, and prediction datasets are not registered without proven observations.
# Optional advanced match data

WhoScored is an optional cache-first supplement. The app never acquires it on
render: explicit acquisition precedes immutable raw preservation,
normalization, canonical identity, and analytical enrichment. Failure leaves
all Fantrax and Understat paths intact.
# Historical advanced match acquisition

WhoScored historical acquisition uses a cache-first controller with one process per match, parent-enforced timeout, retry, atomic cache commit, schema/hash validation, and a durable manifest. Canonical player and manager identities are reference-layer concerns; normalized scale-test products remain outside finalized season datasets. See `docs/whoscored_scale_readiness.md` and `docs/manager_identity_architecture.md`.
# Supplemental advanced descriptive layer

The 2025/26 advanced layer is supplemental and read-only relative to finalized core history. `scripts/build_advanced_descriptive_products.py` consumes cached normalized products and writes UI-sized player, set-piece, formation, Fantasy Allowed, and team-playstyle tables. Shared definitions live in `analytics/advanced_descriptive.py`. Fantrax owns fantasy scoring, Understat owns xG/xA/xGI, and WhoScored owns supplemental event, rating, tactical-role, and set-piece evidence.

Cross-season presentation uses `core.services.historical_advanced`. Finalized core tables default to the immutable snapshot namespace, but supplemental advanced models are registered under `data/models/season_2526/advanced` and are deliberately loaded through the working namespace. The same helper applies the explicit legacy canonical bridge `afc_bournemouth → bournemouth` and `brighton_hove_albion → brighton`; all other eligible clubs use identity mapping.
