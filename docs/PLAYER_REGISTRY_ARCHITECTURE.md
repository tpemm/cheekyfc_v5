# Player Registry Architecture

## Purpose

The Player Registry is the platform’s canonical, season-aware player identity layer. It centralizes current EPL membership, external IDs, name normalization, historical linkage, transfer status, and match diagnostics for every downstream analytics module.

The finalized platform architecture remains unchanged:

`DatasetRegistry → SeasonManager → DataManager → OperationsService → pages`

The registry is infrastructure beneath that boundary. Pages never call providers or read registry files directly.

## Data flow

`Fantrax export + historical master/bridge + Understat IDs + cached current squad → Player Registry → Draft builder and future consumers`

Refresh and build are deliberately separate:

1. `Refresh Current Squad` calls the selected provider and writes a deterministic snapshot.
2. `Build Player Registry` reads only cached/local inputs.
3. `Validate Player Registry` checks identity and uniqueness invariants.
4. `Generate Registry Reports` rebuilds quality outputs from cached data.

The registry build never performs a live HTTP call.

## Current Squad Service

Package: `analytics/current_squads`

### Provider abstraction

`CurrentSquadProvider` defines one method:

```python
def fetch_players(self) -> pandas.DataFrame
```

Providers return the same normalized schema and do not perform identity matching, registry construction, or Draft calculations.

### Official FPL provider

`FPLCurrentSquadProvider` is the default. It uses the public Official Fantasy Premier League endpoint:

`https://fantasy.premierleague.com/api/bootstrap-static/`

The provider reads `elements` and `teams`, validates required fields, rejects empty/malformed responses, rejects duplicate player IDs, requires 20 teams, normalizes position/team values, and records retrieval metadata.

The cached 2026/27 snapshot contains 564 players across 20 clubs.

### Deprecated FootballData.io provider

`FootballDataCurrentSquadProvider` implements the same interface for compatibility and testing. It is not the default because the season-filtered cached endpoint returned empty player arrays.

### Provider-neutral snapshot schema

- `provider_player_id`
- `player_name`
- `first_name`
- `last_name`
- `team_name`
- `team_code`
- `position`
- `active_epl`
- `availability_status`
- `injury_news`
- `provider`
- `retrieved_at`
- `season_id`

### Cache

Snapshot:

`data/reference/current_squads/fpl_players_<season>.csv`

Metadata:

`data/reference/current_squads/fpl_players_<season>.metadata.json`

Metadata records provider, retrieval time, season, player count, team count, API surface, and snapshot filename. Rows are sorted by team, name, and provider ID before writing.

## Registry schema

Dataset:

`data/reference/player_registry_<season>.csv`

Identity:

- `registry_player_id`
- `fantrax_player_id`
- `fpl_player_id`
- `understat_player_id`
- `historical_player_id`

Names:

- `canonical_name`
- `fantrax_name`
- `fpl_name`
- `historical_name`
- `normalized_name`

Current state:

- `current_team`
- `current_team_code`
- `current_position`
- `active_epl`
- `availability_status`
- `injury_news`

Historical context:

- `historical_team`
- `historical_position`
- `historical_minutes`
- `historical_starts`
- `historical_points`

Classification and diagnostics:

- `registry_status`
- `match_method`
- `identity_confidence`
- `source`
- `last_verified`
- `match_diagnostic`
- `season_id`

`registry_player_id` is a deterministic hash of stable source IDs. Duplicate registry IDs and duplicate active FPL identities fail the build.

## Matching pipeline

The current implementation applies available identifiers in this order:

1. normalized Fantrax ID establishes the Fantrax row;
2. the existing bridge selects the historical Fantrax ID;
3. curated Fantrax-to-FPL override, when supplied;
4. exact normalized name plus club;
5. unique exact normalized name;
6. unique club-constrained fuzzy name;
7. unresolved.

FPL-only active players enter through their FPL ID. Understat ID is inherited only from a valid historical identity. Ambiguous exact names and reused current-player matches are never silently accepted.

Confidence:

| Method | Confidence |
|---|---:|
| Fantrax ID / manual override | 100 |
| Historical bridge | 98 |
| FPL ID | 97 |
| Exact name + club | 95 |
| Exact name | 90 |
| Unique fuzzy | 75 |
| Unresolved | 0 |

## Registry statuses

Every row has exactly one status from the approved vocabulary. The current build produces:

- `Confirmed`: linked active current player with historical context;
- `Transferred`: linked active player whose current and historical clubs differ;
- `New EPL Arrival`: linked current player without historical EPL context;
- `Historical Only`: Fantrax/historical player absent from the current FPL population;
- FPL-only players remain `Confirmed` because FPL confirms their active identity; absence from Fantrax is retained in diagnostics and is not assumed to mean academy status;
- `Unresolved`: Fantrax player without current or historical confirmation.

`Confirmed Override`, `Loan`, `Promoted`, `Academy`, and `Inactive` remain valid future classifications when supporting evidence/overrides are supplied. The builder does not infer academy, loan, or promoted-player status without a source.

## Diagnostics

Generated reports:

- `data/quality/player_registry_<season>/player_registry_quality_report.csv`
- `data/quality/player_registry_<season>/player_registry_unresolved.csv`

The quality report covers total, active, Fantrax/FPL/historical linkage, unresolved identities, transfers, and duplicate invariants. The unresolved report preserves the complete registry row and match diagnostic.

## Dataset and operation registration

Registered datasets:

- `current_squad_snapshot`
- `player_registry`
- `player_registry_quality`
- `player_registry_unresolved`

They resolve through `DatasetRegistry`, `SeasonManager`, and `DataManager`.

Registered operations:

- `refresh_current_squad`
- `build_player_registry`
- `validate_player_registry`
- `generate_registry_reports`

Operations are constrained by season mutability/capabilities through `OperationsService`.

## Draft integration

The Draft producer consumes `player_registry_2627.csv` by normalized Fantrax ID. It receives:

- historical source ID;
- current FPL identity and club;
- current position and active status;
- registry status and confidence;
- transfer classification;
- verification source/time.

The producer no longer invokes current-squad matching or its legacy eligibility classifier. Unresolved registry players remain included conservatively; `Historical Only` players are excluded by default. The approved Draft Score, confidence weights, ranking keys, tier bands, ADP comparison, and fixture method are unchanged.

## Downstream use

Draft HQ is the first consumer. League Hub, Awards, Player Explorer, Trade Analyzer, Live Draft Assistant, and future analytics should request `player_registry` through `DataManager`. They must not implement local identity matching or call providers.

## Adding a provider

1. Implement `CurrentSquadProvider`.
2. Return the provider-neutral snapshot schema.
3. Validate empty, malformed, duplicate, and incomplete responses.
4. Add provider-specific tests with injected downloads/fixtures.
5. Select it only in the refresh operation.
6. Keep matcher and registry builder provider-agnostic.
