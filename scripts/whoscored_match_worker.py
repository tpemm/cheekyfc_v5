#!/usr/bin/env python3
"""One exact WhoScored match per isolated browser process."""
from __future__ import annotations
import argparse,hashlib,json,sys,time
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
from seleniumbase import Driver
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from analytics.advanced_match_poc import safe_write_raw

def atomic_bytes(path:Path,data:bytes):
    if path.exists():return
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_bytes(data);tmp.replace(path)

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--match-id',type=int,required=True);p.add_argument('--profile-dir',required=True);p.add_argument('--season',default='2526');a=p.parse_args()
    row=pd.read_csv(a.manifest).query('understat_match_id == @a.match_id').iloc[0];wsid=int(row.whoscored_match_id);target=ROOT/f'data/raw/whoscored/{a.season}/poc/match_{a.match_id}';target.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter();url=f'https://www.whoscored.com/Matches/{wsid}/Live';driver=None
    try:
        driver=Driver(uc=True,headed=True,uc_subprocess=False,user_data_dir=a.profile_dir,page_load_strategy='eager')
        driver.set_page_load_timeout(45);driver.set_script_timeout(15);driver.get(url)
        deadline=time.monotonic()+30;payload=None
        while time.monotonic()<deadline:
            try:payload=driver.execute_script("return require.config.params['args'].matchCentreData")
            except Exception:payload=None
            if isinstance(payload,dict) and payload.get('events'):break
            time.sleep(1)
        if not isinstance(payload,dict) or not payload.get('events'):raise ValueError('valid matchCentreData not available within 30 seconds')
        encoded=json.dumps(payload,ensure_ascii=False,sort_keys=True,indent=2).encode('utf-8');checksum=safe_write_raw(payload,target/'raw_match.json')
        atomic_bytes(target/'embedded_payload.json',encoded);atomic_bytes(target/'page.html',(driver.page_source or '').encode('utf-8'))
        native=ROOT/f'data/raw/whoscored/{a.season}/poc/_soccerdata_native/events/ENG-Premier League_{a.season}/{wsid}.json';atomic_bytes(native,encoded)
        meta={'match_id':a.match_id,'whoscored_match_id':wsid,'status':'acquired','source_url':url,'final_url':driver.current_url,'page_title':driver.title,'retrieved_at':datetime.now(timezone.utc).isoformat(),'acquisition_seconds':round(time.perf_counter()-started,3),'payload_bytes':len(encoded),'event_count':len(payload['events']),'player_count':len(payload.get('playerIdNameDictionary',{})),'checksum':checksum}
        (target/'metadata.json').write_text(json.dumps(meta,indent=2),encoding='utf-8');return 0
    except Exception as exc:
        failure={'match_id':a.match_id,'whoscored_match_id':wsid,'status':'error','attempted_at':datetime.now(timezone.utc).isoformat(),'error_type':type(exc).__name__,'error_message':str(exc)}
        (target/'last_failure.json').write_text(json.dumps(failure,indent=2),encoding='utf-8');return 1
    finally:
        if driver:
            try:driver.quit()
            except Exception:pass
if __name__=='__main__':raise SystemExit(main())
