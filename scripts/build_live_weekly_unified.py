#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys,time
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fantrax.live.unified_weekly import build_unified_weekly,current_fantasy_allowed,source_coverage
from integrations.whoscored.workflows import atomic_csv,atomic_json
def read(path):return pd.read_csv(path,low_memory=False) if path.exists() else pd.DataFrame()
def main(season='2627'):
    started=time.perf_counter();model=ROOT/f'data/models/season_{season}';advanced=model/'advanced';quality=ROOT/f'data/quality/season_{season}'
    fan=read(model/f'current_player_weekly_{season}.csv');ws=read(advanced/f'advanced_player_match_{season}.csv');us=read(model/f'understat_player_weekly_{season}.csv');identity=read(ROOT/'data/reference/whoscored_player_identity.csv');fixtures=read(model/f'team_matches_{season}.csv');clubs=read(model/f'premier_league_clubs_{season}.csv')
    unified=build_unified_weekly(fan,ws,us,identity,fixtures,clubs);allowed=current_fantasy_allowed(unified);coverage=source_coverage(unified);atomic_csv(unified,model/f'live_player_weekly_enriched_{season}.csv');atomic_csv(allowed,model/f'team_position_fantasy_allowed_current_{season}.csv');atomic_csv(coverage,quality/f'weekly_source_coverage_{season}.csv');report={'status':'CURRENT' if len(unified) else 'BLOCKED_NO_FANTRAX_WEEKLY_EXPORT','unified_rows':len(unified),'all_player_unique':int(unified.fantrax_player_id.nunique()) if len(unified) else 0,'rostered':int(unified.fantrax_detail_source.eq('FANTRAX_DETAILED').sum()) if len(unified) else 0,'all_player_only':int(unified.fantrax_detail_source.eq('FANTRAX_ALL_PLAYER_ONLY').sum()) if len(unified) else 0,'waiver_rows':int(unified.fantrax_detail_source.eq('FANTRAX_ALL_PLAYER_ONLY').sum()) if len(unified) else 0,'whoscored':int(unified.whoscored_available.sum()) if len(unified) else 0,'understat':int(unified.understat_available.sum()) if len(unified) else 0,'fantasy_allowed_rows':len(allowed),'elapsed_seconds':round(time.perf_counter()-started,3)};atomic_json(report,quality/f'weekly_unified_latest_{season}.json');print(json.dumps(report,indent=2));return 0 if len(unified) else 2
if __name__=='__main__':p=argparse.ArgumentParser();p.add_argument('--season',default='2627');a=p.parse_args();raise SystemExit(main(a.season))
