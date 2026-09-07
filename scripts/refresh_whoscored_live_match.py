#!/usr/bin/env python3
"""Acquire one exact current-season WhoScored match through the local session."""
from __future__ import annotations
import argparse,json,os,sys
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from analytics.advanced_match_poc import safe_write_raw
from integrations.whoscored.controller import TEAM_NAMES
from core.services.machine_role import require_commissioner_writer
from integrations.whoscored.session_browser import create_reader, read_events_once

def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--manifest',default=str(ROOT/'data/reference/whoscored_season_manifest_2627.csv'));p.add_argument('--match-id','--whoscored-match-id',dest='whoscored_match_id',type=int,required=True);p.add_argument('--season',default='2627');p.add_argument('--force',action='store_true');a=p.parse_args()
    require_commissioner_writer("WhoScored live match acquisition");manifest=pd.read_csv(a.manifest);hit=manifest[pd.to_numeric(manifest.whoscored_match_id,errors='coerce').eq(a.whoscored_match_id)]
    if len(hit)!=1:raise SystemExit(f'exact manifest lookup resolved {len(hit)} rows')
    row=hit.iloc[0];target=ROOT/f'data/raw/whoscored/{a.season}/poc/match_{a.whoscored_match_id}';target.mkdir(parents=True,exist_ok=True)
    result={'canonical_match_id':row.canonical_match_id,'whoscored_match_id':a.whoscored_match_id,'status':'error','retrieved_at':datetime.now(timezone.utc).isoformat()}
    result['browser_attempts']=[]
    try:
        os.environ.setdefault('SOCCERDATA_DIR',str(ROOT/'data/raw/soccerdata/runtime'))
        base=ROOT/f'data/raw/whoscored/{a.season}/poc'
        read_events_once(lambda:create_reader(season=a.season,data_dir=base/'_soccerdata_native'),match_id=a.whoscored_match_id,live=a.force,attempts=result['browser_attempts'])
        native=base/'_soccerdata_native'/'events'/f'ENG-Premier League_{a.season}'/f'{a.whoscored_match_id}.json';payload=json.loads(native.read_text(encoding='utf-8'))
        if TEAM_NAMES.get(str(payload.get('home',{}).get('name','')).casefold())!=row.home_club_id or TEAM_NAMES.get(str(payload.get('away',{}).get('name','')).casefold())!=row.away_club_id:raise ValueError('payload club identity mismatch')
        rescheduled='rescheduled' in str(row.get('resolution_method','')).casefold()
        if str(payload.get('startDate',''))[:10]!=str(row.date)[:10] and not rescheduled:raise ValueError('payload date mismatch')
        checksum=safe_write_raw(payload,target/'raw_match.json',force=a.force);result.update(status='acquired',event_count=len(payload['events']),player_count=len(payload.get('playerIdNameDictionary',{})),checksum=checksum)
    except Exception as exc:result.update(error_type=type(exc).__name__,error_message=str(exc))
    temp=(target/'metadata.json.tmp');temp.write_text(json.dumps(result,indent=2),encoding='utf-8');temp.replace(target/'metadata.json');print(json.dumps(result,indent=2));return 0 if result['status']=='acquired' else 1
if __name__=='__main__':raise SystemExit(main())
