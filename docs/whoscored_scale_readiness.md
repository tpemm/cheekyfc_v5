# WhoScored scale readiness (Sprint 9.3)

Sprint 9.3 validated a bounded, cache-backed 30-match sample covering Premier League gameweeks 36–38 of 2025/26 and all 20 clubs. It did not acquire the full season or promote data into finalized historical paths.

## Acquisition architecture

`refresh_whoscored_scale_sample.py` is a resumable controller. It validates the payload hash, provider match ID, and required schema before treating a cache as valid. Missing matches run in an independent worker process with a hard parent timeout, process-tree cleanup, one conservative retry, atomic writes, failure continuation, and a durable manifest. Supported modes are `--cache-only`, `--refresh-missing`, and `--force-match`.

Fresh isolated Chrome profiles could not reliably obtain real match data in this environment. The explicit `--session-backed` recovery worker succeeded using the already authenticated/working browser session: 30/30 valid caches, 11 cache hits, 19 acquisitions, and four recovered first-attempt timeouts. This environmental dependency is the remaining blocker to unattended full-season acquisition.

## Identity and manager context

`data/reference/whoscored_player_identity.csv` is the growing provider-ID-first crosswalk. A proven WhoScored ID is reused before deterministic historical Understat roster and exact Fantrax registry evidence are considered. No uncontrolled fuzzy matching is used. The 30-match sample maps 369/380 players with starts or substitute appearances (97.11%); unresolved records retain a reason.

WhoScored exposes manager names at `home.managerName` and `away.managerName`; exhaustive raw-payload inspection found no provider manager ID. Stable internal IDs are derived from normalized manager identity, not club. Tenures preserve only observed date ranges and explicitly do not claim exact appointment boundaries. The sample contains 20 managers and no manager transition, so transition support is structurally ready but not empirically exercised.

## Products and semantics

The scale products contain normalized match, team-match, lineup, player-match, and event layers plus manager-aware tactical-position and formation histories. Team features are observed or transparently derived event/spatial components; none is a prediction or an opaque style score. Event activity is explicitly labeled `EVENT_ACTIVITY_NOT_TRACKING`. Fantrax remains the scoring authority and is joined only when a scoring period is attributable to one club fixture. Understat remains the xG/xA/xGI authority.

Quality evidence is in `data/quality/season_2526/whoscored_scale_readiness_gates_2526.csv`. The acquisition itself met the requested gates, but production readiness is decision **B — small fix required** because unattended isolated-profile acquisition remains unreliable.

## Sprint 9.4 recommendation

Make isolated acquisition independently authenticatable and repeatable, then rerun a small missing-cache canary with zero dependency on a manually maintained browser session. If that passes, authorize a resumable full-season acquisition in a separate sprint.
