# 2026/27 weekly player data foundation

`manager_player_weekly_2627.csv` must not be synthesized before weekly facts exist. Its future grain is one manager-player-period interval derived from roster history/snapshots, official weekly Fantrax player-stat exports or a currently supported project API response, lineup-status observations, and Player Registry IDs.

Required fields are period, manager/team IDs, Fantrax and registry player IDs, roster and lineup status, fantasy and ghost score, minutes, goals, assists, xG, xA, xGI, starting position, eligible positions, opponent, and club. The current official API cache supplies roster status but not authoritative submitted historical lineups or weekly player scoring; those remain explicit acquisition gaps.
