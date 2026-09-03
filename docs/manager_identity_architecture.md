# Manager identity and tenure architecture

The canonical manager registry lives at `data/reference/manager_registry.csv`. `manager_id` is stable across clubs and is derived from normalized manager identity because WhoScored supplies a name but no stable manager ID. Source names, normalized names, observation dates, provenance, and mapping status remain explicit.

`data/reference/team_manager_tenures.csv` represents club/manager observed ranges. Its start and end dates mean “first and last observed in acquired matches,” not exact employment boundaries. Match-date attachment therefore supports multiple managers per club and must select only a tenure whose proven range contains the observation date; unknown gaps remain unknown.

Team-match, formation-history, player-role-history, and advanced player-match scale products carry `manager_id`. This supports observational questions such as formation or player role under a manager without implying causality.
