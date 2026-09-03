# WhoScored full-season advanced layer

Sprint 9.5 acquires the finalized 2025/26 Premier League schedule into supplemental advanced storage. The protected Fantrax and Understat season sources remain read-only.

## Acquisition and recovery

The authoritative target is `data/reference/whoscored_season_manifest_2526.csv`: 380 unique canonical matches, 380 unique WhoScored IDs, 20 clubs, and 38 fixtures per club. Each match runs behind an independent process boundary with a parent timeout, one bounded retry, payload/hash/schema validation, atomic raw commit, and process-tree cleanup. Valid caches are always skipped.

For operational wall-time only, the authorized run may divide this manifest into non-overlapping shards. A shard remains sequential and isolated per match; shard manifests have distinct filenames and cannot acquire the same fixture. Raw match directories remain the shared source of truth, so any interrupted or failed shard can be rerun safely.

## Dataset layers

- Raw: immutable accepted payload, page evidence, metadata, and checksum per match.
- Normalized: season match, lineup, and canonical event datasets.
- Identity: persistent WhoScored player IDs and stable internal manager IDs.
- Derived supplemental: advanced player-match, tactical roles, role profiles, formation history/profile, transparent team-match event features, Event Activity data, and exact-attribution positional fantasy allowed.
- Quality: raw-cache classification, unresolved identities, manager transitions, spatial evidence, Fantrax reconciliation, season gates, performance, and storage reports.

The advanced layer lives under `data/models/season_2526/advanced`. It does not replace finalized core historical data. Event Activity represents event locations, not player tracking or literal movement.

## Authority boundaries

Fantrax remains authoritative for fantasy scoring. Period totals are assigned to a player-match only when the club has exactly one league fixture in that period. Understat remains authoritative for xG, xA, and xGI. WhoScored supplies supplemental football events, roles, formations, ratings, managers, and event locations. Provider-definition differences are measured and retained rather than forced into agreement.

## Promotion

Only a complete 380-match raw layer and passing season gates can be recommended for Player/Teams UI promotion. Prediction, expected playing time, matchup scoring, and causal manager claims remain outside Sprint 9.5.

## Sprint 9.5 validation outcome

The completed build contains 380/380 strictly validated raw matches, 577,884 unique normalized events, 15,189 lineup observations, and 14,677 advanced player-match rows. All 12 season quality gates pass. Meaningful-appearance identity coverage is 522/537 (97.21%); all 20 clubs are mapped; 31 managers and seven clubs with observed manager transitions are represented. Refresh status is `Complete` with zero missing or failed fixtures.

One provider-native cache-key collision was found during the strict club/date audit: WhoScored ID 1903188 contained Tottenham–Aston Villa instead of Nottingham Forest–Sunderland. The invalid payload was quarantined, fetched cleanly, and every downstream dataset was rebuilt. This is why club and date checks are required in addition to provider ID, schema, and checksum checks.

Decision: **A — full historical advanced data validated and ready for model/UI promotion.** The layer remains supplemental until Sprint 9.6 deliberately integrates it.
