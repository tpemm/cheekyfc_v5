#!/usr/bin/env python3
"""Explicit, sample-limited WhoScored acquisition and validation command."""
from __future__ import annotations
import argparse, json, os, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from analytics.advanced_match_poc import safe_write_raw
from integrations.whoscored.controller import TEAM_NAMES

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument('--manifest',default=str(ROOT/'data/reference/advanced_match_poc_sample_2526.csv'));p.add_argument('--season',default='2526')
    g=p.add_mutually_exclusive_group(required=True); g.add_argument('--match-id',type=int); g.add_argument('--all-sample',action='store_true'); g.add_argument('--validate-only',action='store_true')
    p.add_argument('--force',action='store_true'); a=p.parse_args()
    import pandas as pd
    manifest=pd.read_csv(a.manifest)
    id_col='understat_match_id' if 'understat_match_id' in manifest else 'match_id'
    ids=[] if a.validate_only else ([a.match_id] if a.match_id else manifest[id_col].astype(int).tolist())
    base=ROOT/f'data/raw/whoscored/{a.season}/poc'; results=[]
    if a.validate_only:
        for mid in manifest[id_col]:
            path=base/f'match_{mid}'/'raw_match.json'; results.append({'match_id':int(mid),'status':'valid_cached' if path.exists() else 'missing'})
    else:
        os.environ.setdefault('SOCCERDATA_DIR',str(ROOT/'data/raw/soccerdata/runtime'))
        import soccerdata as sd
        reader=sd.WhoScored(leagues='ENG-Premier League',seasons=a.season,no_cache=False,data_dir=base/'_soccerdata_native')
        schedule=reader.read_schedule(force_cache=True).reset_index()
        for mid in ids:
            started=datetime.now(timezone.utc)
            try:
                sample=manifest.loc[manifest[id_col].astype(int).eq(int(mid))].iloc[0]
                if 'whoscored_match_id' in manifest and pd.notna(sample.whoscored_match_id):
                    wsid=int(sample.whoscored_match_id)
                else:
                    dates=pd.to_datetime(schedule['date'],errors='coerce').dt.date.astype('string')
                    hit=schedule[dates.eq(str(sample.date)) & schedule.home_team.eq(sample.home_team) & schedule.away_team.eq(sample.away_team)]
                    if len(hit)!=1: raise ValueError(f'exact schedule identity resolved {len(hit)} matches')
                    wsid=int(hit.iloc[0].game_id)
                reader.read_events(match_id=wsid,output_fmt=None,force_cache=True,on_error='raise')
                native=base/'_soccerdata_native'/'events'/'ENG-Premier League_2526'/f'{wsid}.json'
                payload=json.loads(native.read_text(encoding='utf-8'))
                if TEAM_NAMES.get(str(payload.get('home',{}).get('name','')).casefold())!=sample.home_club_id or TEAM_NAMES.get(str(payload.get('away',{}).get('name','')).casefold())!=sample.away_club_id: raise ValueError('acquired payload club identity mismatch')
                if str(payload.get('startDate',''))[:10]!=str(sample.date)[:10]: raise ValueError('acquired payload date mismatch')
                checksum=safe_write_raw(payload,base/f'match_{mid}'/'raw_match.json',force=a.force)
                result={'match_id':mid,'whoscored_match_id':wsid,'status':'acquired','event_count':len(payload['events']),'checksum':checksum}
            except Exception as exc:
                result={'match_id':mid,'status':'error','error':f'{type(exc).__name__}: {exc}'}
            result['retrieved_at']=started.isoformat(); results.append(result)
            meta=base/f'match_{mid}'/'metadata.json'; meta.parent.mkdir(parents=True,exist_ok=True); meta.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(results,indent=2)); return 1 if any(x['status']=='error' for x in results) else 0
if __name__=='__main__': raise SystemExit(main())
