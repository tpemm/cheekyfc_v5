# Fantrax Data v3 Structure

This is the final analytics-package organization. New work extends these folders without moving them again.

```text
fantrax/analytics/
├── core/
│   ├── league_rules.py
│   ├── scoring_engine.py
│   ├── optimizer.py
│   ├── metrics.py
│   ├── ownership_engine.py
│   └── build_master_weekly.py
├── manager/
│   ├── build_decision_views.py
│   └── build_efficiency_ghost_awards_views.py
├── player/
│   └── build_player_views.py
├── team/
│   └── build_league_awards_views.py
├── explorer/
└── build_all.py
```

Old module paths remain as compatibility wrappers, so existing commands continue to work.

## Commands

```bash
python -m fantrax.analytics.build_all
python -m fantrax.analytics.build_all --rebuild-master
python -m fantrax.analytics.manager.build_decision_views
python -m fantrax.analytics.player.build_player_views
```
