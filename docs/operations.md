# Operations Catalog

Cup operations are Initialize Cup, Build Cup Bracket, Rebuild Cup, and Validate Cup. They execute the local registered script without HTTP access. Initialize creates the seed snapshot once; subsequent builds preserve it.

Operations Center uses the shared page header and KPI system. Routine health and Refresh League remain primary; technical diagnostics remain available under Advanced. OperationsService and operation definitions are unchanged.

`Build Draft Grades` is a fixed registered operation with no caller-controlled path. It validates completed results, reuses the immutable snapshot, and regenerates deterministic grade/report artifacts.

`OperationsService` is the only application execution boundary. It exposes nine
logical operations, validates parameters and season capability, executes fixed
scripts with `shell=False`, and returns `OperationResult`. It does not expose
arbitrary scripts or filesystem writes.

Current season policy:

- 2026/27 is mutable preseason and supports the capabilities used below.
- 2025/26 is finalized and cannot run working update/build operations.
- All Time is not built and cannot run operations.

## Registered operations

### `refresh_fantrax_data` — Run refresh

- Purpose: run the approved Fantrax refresh pipeline.
- Inputs: `mode` (`AUTO`, `REBUILD`, `SPECIFIC`, or `FULL`);
  `specific_weeks` is permitted only for `SPECIFIC` and must be one week or a
  numeric range such as `34-36`.
- Entry point: `fantrax/refresh/refresh_all_fantrax_data.py`.
- Reads/writes: the legacy refresh pipeline owns multiple source, processed,
  API, and analytics artifacts; operation metadata does not enumerate them.
- Validation: mode and week syntax, registered parameters, mutable season.
- Success: zero return code plus captured standard output.
- Common failures: credentials/network/provider errors, invalid mode/week,
  unavailable source data, or producer exceptions.
- Rerun safety: designed for intentional refresh/rebuild use; `FULL` can be
  expensive and external data may change between runs.

### `build_league_analytics` — Only rebuild League Hub analytics

- Purpose: rebuild registered League Hub analytics from existing sources.
- Inputs: none.
- Entry point: `fantrax/analytics/build_league_awards_views.py`.
- Typical outputs: league table, awards, matchup extremes, streaks, lineup
  changes, and related report views.
- Validation: mutable season and `build_analytics` capability.
- Common failures: missing/invalid processed inputs or analytics exceptions.
- Rerun safety: deterministic for unchanged inputs.

### `refresh_current_squad` — Refresh Current Squad

- Purpose: download and cache the provider-neutral Official FPL squad snapshot.
- Inputs: none.
- Entry point: `scripts/refresh_current_squad.py` →
  `analytics.current_squads.builder`.
- Output: `current_squad_snapshot`.
- Validation: provider/builder validation plus operation/season policy.
- Common failures: provider/network errors or malformed provider response.
- Rerun safety: safe, but the upstream current squad can change.

### `build_player_registry` — Build Player Registry

- Purpose: rebuild canonical season-aware identities from cached sources.
- Inputs: none.
- Entry point: `scripts/build_player_registry.py`.
- Reads: current squad snapshot, current Fantrax draft import, historical
  master, API bridge when available, built-in aliases, and approved user alias
  overrides.
- Writes: `player_registry`, `player_registry_quality`, and
  `player_registry_unresolved`.
- Validation: deterministic matching safeguards and duplicate identity checks.
- Common failures: missing sources, malformed approved overrides, duplicate
  identities, or invalid source columns.
- Rerun safety: deterministic for unchanged inputs.

### `validate_player_registry` — Validate Player Registry

- Purpose: validate registry identity and uniqueness invariants.
- Inputs: none.
- Entry point: `scripts/validate_player_registry.py`.
- Reads: `player_registry`.
- Writes: no registered dataset.
- Checks: unique registry IDs, no duplicate active FPL IDs, non-null registry
  status.
- Common failures: missing registry or violated assertions.
- Rerun safety: read-only and safe.

### `generate_registry_reports` — Generate Registry Reports

- Purpose: regenerate registry output and its quality/unresolved reports.
- Inputs: none.
- Entry point: `scripts/generate_registry_reports.py`.
- Implementation: calls the same cached-source registry build as
  `build_player_registry`.
- Reads/writes: same registry sources and outputs as the registry builder.
- Common failures and rerun safety: same as `build_player_registry`.

### `generate_identity_review` — Generate Identity Review

- Purpose: rank conservative, non-binding current-player suggestions for
  Historical Only and Unresolved identities.
- Inputs: none through OperationsService; the script defaults to season `2627`.
- Entry point: `scripts/generate_identity_review.py`.
- Reads: `player_registry`, `current_squad_snapshot`, optional
  `draft_rankings`, and optional `player_alias_overrides`.
- Writes: `player_identity_review`.
- Validation: active candidates, deterministic ranking, identity evidence,
  team/position signals, uniqueness, and review-decision merge.
- Common failures: missing required registry/current-squad inputs or invalid
  tabular contracts.
- Rerun safety: deterministic for unchanged sources and decisions.

### `save_identity_review_decision` — Save Identity Review Decision

- Purpose: validate and upsert one pair-specific Approved/Ignored decision, or
  clear only that pair.
- Inputs: `fantrax_player_id`, `current_fpl_player_id`, `decision`,
  `review_note`, `acknowledge_transfer`, and `season_id`.
- Entry point: `scripts/save_identity_review_decision.py`.
- Reads: `player_identity_review` and optional `player_alias_overrides`.
- Writes: `player_alias_overrides`, preserving unrelated records.
- Validation: selected registered pair, active/unique candidate, position
  compatibility, team compatibility or transfer acknowledgement, no stronger
  existing match, and no duplicate FPL mapping.
- Boundary handling: pandas/NumPy values are normalized to strict JSON-native
  values; missing values become `null`.
- UI follow-up: after the operation synchronizes the affected review row, the
  page invalidates and reloads both authoritative datasets. It verifies the
  exact pair's persisted decision and projected review status before reporting
  success or rerunning.
- UI safety: transfer acknowledgement is pair-specific and required before an
  approval can be submitted. State-changing controls are locked while an
  Identity Review workflow runs. Subprocesses have a three-minute safety
  timeout; expected validation errors are summarized while stdout/stderr remains
  available as technical detail.
- Common failures: stale/missing pair, invalid decision, unsafe candidate,
  duplicate mapping, or malformed override data.
- Rerun safety: pair-specific deterministic upsert; Clear removes only the pair.

Decision saves now synchronize the affected persisted review-status projection
inside the same approved operation. They do not launch a second full candidate
generation. Manual Generate Identity Review remains available when source
identity data changes. Full generation pre-indexes linked FPL identities rather
than rescanning the registry for every candidate.

Post-decision filter restoration uses a pending non-widget session key. The
active filter is preserved and copied into the widget-owned filter key at the
beginning of the next render, before Streamlit instantiates that widget.
After authoritative verification, the completed selection is cleared so the
first remaining row matching the preserved filters becomes current. The page
reports a verified result and the refreshed global Unreviewed queue count.

### `build_draft_outputs` — Build Draft Outputs

- Purpose: rebuild the registered 2026/27 Draft model artifacts.
- Inputs: none.
- Entry point: `scripts/build_draft_outputs.py` →
  `analytics.draft.builder`.
- Reads: Player Registry, Fantrax target pool/import, historical master and
  bridge, team/fixture context, ghost-point history, and optional eligibility
  overrides.
- Writes: `draft_player_pool`, `draft_rankings`, and Draft quality reports.
- Validation: existing Draft builder contracts and eligibility checks.
- Common failures: missing source/context files, schema issues, or builder errors.
- Rerun safety: deterministic for unchanged inputs; it must not replace a
  future immutable draft-day snapshot.

## Recommended sequences

### Identity review and approval

```text
Refresh Current Squad
→ Build Player Registry
→ Validate Player Registry
→ Generate Registry Reports
→ Generate Identity Review
→ Save Identity Review Decision
→ Generate Identity Review (automatic after a page save)
→ Build Player Registry
→ Validate Player Registry
→ Generate Registry Reports
→ Build Draft Outputs
```

A review decision does not itself activate a player. Registry and Draft outputs
change only after their intentional rebuild operations.

### Draft refresh

```text
Refresh required sources
→ Refresh Current Squad when needed
→ Build Player Registry
→ Validate Player Registry
→ Build Draft Outputs
→ inspect Draft quality outputs and Draft HQ
```

Do not insert manual edits between these operations.

### ADP-only Draft refresh

The active market input is
`data/imports/draft/Fantrax-Players-Cheeky FC (7).csv`, using column `ADP`.
After making a timestamped backup and replacing that exact filename, run:

```powershell
.\.venv\Scripts\python.exe scripts\validate_fantrax_adp.py 'data\imports\draft\Fantrax-Players-Cheeky FC (7).csv'
.\.venv\Scripts\python.exe scripts\build_draft_outputs.py
```

Validation is read-only and reports required fields, missing IDs, malformed or
missing ADP, duplicate IDs, projection separation, and row-count plausibility.
The successful Update Pipeline operation clears Streamlit cache; DataManager
also resolves refreshed output metadata on its next load. Do not rebuild Player
Registry for ADP-only changes. Rebuild it only for identity, ID, club, position,
or material current-player-pool changes. Verify known ADP values in Draft HQ
and restore the backup if validation or build fails.
# Live-season operations

OperationsService now registers fixed-path `refresh_live_fantrax_sources`, `refresh_live_league_metadata`, `refresh_live_standings`, `refresh_live_rosters`, and `build_live_season_datasets`. The roster operation accepts only a validated period 1–38. Callers cannot supply scripts or paths.

Recommended sequence is refresh raw sources, validate responses, build cached datasets, join Player Registry, validate outputs, write quality/manifest files, clear application data cache, then expose results. A failed refresh preserves raw cache; a blocking build validation preserves prior normalized files. The build operation has no network dependency. `FANTRAX_LEAGUE_ID_2627` is required only for refresh.

Player-pool and transaction refresh controls remain documented but unautomated until a stable export/endpoint is proven. The old 2526 operation remains for compatibility and must not target finalized data.

## Windows CLI encoding

Fantrax command-line entry points initialize stdout and stderr as UTF-8 with replacement semantics through `fantrax.utils.cli`. CSV/JSON serialization remains lossless UTF-8; replacement applies only to console diagnostics. Transformer previews are best-effort and cannot invalidate an already-written file.

The Update Pipeline's older **Run refresh** / `AUTO` control is `refresh_fantrax_data` and still invokes `fantrax/refresh/refresh_all_fantrax_data.py`. Its legacy API fetch defaults to periods 1–38 when no `--periods` value is passed. This is separate from Sprint 7.0's **Refresh Current Season** operation, `refresh_live_fantrax_sources`, which invokes `scripts/refresh_live_fantrax.py`.
# Roster tracking operations

`Refresh Current Rosters` fetches only the authoritative current period by default. An explicit period or `full_history` mode is required for broader acquisition. `Build Roster Tracking` is cache-only: normalize, join Player Registry, validate, archive distinct state, detect changes, update intervals and ownership, write quality reports/manifest, then invalidate application caches through the existing operation flow. Failed fetches or validations preserve the prior valid cache and models.

# Operations Center

The former Update Pipeline is now the Operations Center. The recommended weekly workflow is a single **Refresh League** action: run the registered live source refresh, then the registered cache-only live build, validate outputs, clear Streamlit data caches, and present a friendly result and elapsed time. The source refresh uses the authoritative current roster period and does not request all 38 periods.

The normal workflow does not invoke `refresh_all_fantrax_data.py` and therefore does not depend on legacy `rosters_by_week.csv`. `current_rosters`, `player_ownership`, and `roster_history` are authoritative for live-season roster features. Legacy controls remain available only inside Advanced for historical/developer workflows.

Registered live subprocesses explicitly inherit the Streamlit environment. Refresh startup logs the resolved season, league ID, and script path. Failures emit a stable stage marker, exception type, and message. Operations Center retains operation, stage, command, exit code, streams, exception, and duration in session activity and exposes them under Technical details rather than presenting an empty manifest as the diagnosis.
# Player-stat refresh status

Refresh League has not gained an undocumented player-stat request. It continues to refresh the three proven official endpoints; the subsequent cache-only build consumes an optional weekly export and produces player-performance quality reports. Understat live acquisition remains pending a real 2026/27 source.
# Understat preparation

Understat acquisition is prepared for the single Refresh League workflow and writes atomically only beneath `data/raw/understat/2627/`. A missing or empty preseason response is a successful empty state. No second prominent refresh action or page-level network request was added.

Refresh League now includes incremental Fantrax weekly acquisition before the cache-only build. Advanced contains Backfill Weekly Player Stats, Force Refresh Current Period, Validate Player Performance, Rebuild Live Models, and source-coverage diagnostics. Valid finalized periods are skipped by default.
# Team fixture refresh cadence

Use `refresh_footballdata_full.py --execute --current-matches-only --skip-build` only for explicit fixture refreshes. It performs one budget check, revalidates current-season page 1, follows fresh pagination, and atomically caches pages. Refresh preseason, after announced schedule changes, and periodically during the season—not on page render and not team by team. Near-term status changes may justify more frequent selective refreshes once the provider offers complete coverage.

Refresh Fantrax league metadata with `refresh_live_fantrax.py` source `league_metadata`; validate and rebuild the scoring-period reference before canonical fixtures. Normal `Refresh League` remains focused on weekly live data and does not automatically spend schedule-provider requests.

Use `refresh_soccerdata_team_context.py --mode schedule --cache-only` for the reproducible schedule build. Remove `--cache-only` only for an explicit external refresh. ClubElo uses `--mode clubelo`; invalid or empty acquisition must never overwrite the registered production cache. These advanced operations remain separate from normal Refresh League.
