"""Process-isolated, resumable WhoScored acquisition controller."""
from __future__ import annotations
import hashlib,json,os,shutil,subprocess,sys,time,uuid
from datetime import datetime,timezone
from pathlib import Path
from typing import Callable
import pandas as pd
from integrations.whoscored.session_browser import dead_session_error

TEAM_NAMES={'arsenal':'arsenal','aston villa':'aston_villa','bournemouth':'afc_bournemouth','brentford':'brentford','brighton':'brighton_hove_albion','burnley':'burnley','chelsea':'chelsea','coventry':'coventry_city','coventry city':'coventry_city','crystal palace':'crystal_palace','everton':'everton','fulham':'fulham','hull':'hull_city','hull city':'hull_city','ipswich':'ipswich_town','ipswich town':'ipswich_town','leeds':'leeds_united','leeds united':'leeds_united','liverpool':'liverpool','man city':'manchester_city','manchester city':'manchester_city','man utd':'manchester_united','manchester united':'manchester_united','newcastle':'newcastle_united','newcastle united':'newcastle_united','nottingham forest':'nottingham_forest','sunderland':'sunderland','tottenham':'tottenham_hotspur','west ham':'west_ham','wolves':'wolverhampton_wanderers','wolverhampton wanderers':'wolverhampton_wanderers'}

def _cache_key(row:dict)->int:
    """Current seasons use the permanent provider ID; legacy manifests keep Understat keys."""
    value=row.get('understat_match_id')
    return int(value) if value is not None and not pd.isna(value) else int(row['whoscored_match_id'])

def validate_cache(base:Path,row:dict)->dict:
    target=base/f"match_{_cache_key(row)}";raw=target/'raw_match.json';meta=target/'metadata.json'
    result={'cache_valid':False,'payload_bytes':0,'event_count':0,'payload_hash':pd.NA,'error_type':pd.NA,'error_message':pd.NA}
    try:
        if not raw.exists() and meta.exists():
            failure=json.loads(meta.read_text(encoding='utf-8'))
            if failure.get('error_type'):
                result.update(error_type=failure['error_type'],error_message=failure.get('error_message'))
                return result
        payload=json.loads(raw.read_text(encoding='utf-8'));metadata=json.loads(meta.read_text(encoding='utf-8'))
        digest=hashlib.sha256(raw.read_bytes()).hexdigest()
        if not isinstance(payload.get('home'),dict) or not isinstance(payload.get('away'),dict) or not payload.get('events'): raise ValueError('required matchCentreData schema missing')
        if int(metadata.get('whoscored_match_id'))!=int(row['whoscored_match_id']): raise ValueError('provider match identity mismatch')
        if TEAM_NAMES.get(str(payload['home'].get('name','')).casefold())!=row.get('home_club_id') or TEAM_NAMES.get(str(payload['away'].get('name','')).casefold())!=row.get('away_club_id'): raise ValueError('payload club identity mismatch')
        rescheduled='rescheduled' in str(row.get('resolution_method','')).casefold()
        if str(payload.get('startDate',''))[:10]!=str(row.get('date',''))[:10] and not rescheduled: raise ValueError('payload match date mismatch')
        if metadata.get('checksum')!=digest: raise ValueError('payload hash mismatch')
        result.update({'cache_valid':True,'payload_bytes':raw.stat().st_size,'event_count':len(payload['events']),'payload_hash':digest})
    except Exception as exc: result.update({'error_type':type(exc).__name__,'error_message':str(exc)})
    return result

def terminate_tree(proc:subprocess.Popen,profile_dir:str|None=None)->None:
    if proc.poll() is not None:return
    if os.name=='nt': subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,check=False)
    else:
        try: os.killpg(proc.pid,9)
        except ProcessLookupError: pass
    try: proc.kill()
    except OSError: pass
    if profile_dir:
        try:
            import psutil
            for child in psutil.process_iter(['pid','name','cmdline']):
                command=' '.join(child.info.get('cmdline') or [])
                if profile_dir.casefold() in command.casefold():
                    try: child.kill()
                    except (psutil.NoSuchProcess,psutil.AccessDenied): pass
        except ImportError: pass

def run_worker(command:list[str],timeout_seconds:float)->dict:
    flags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0
    proc=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,text=True,creationflags=flags,start_new_session=os.name!='nt')
    started=time.perf_counter()
    try:
        proc.wait(timeout=timeout_seconds)
        return {'timed_out':False,'returncode':proc.returncode,'stdout':'','stderr':'','seconds':time.perf_counter()-started}
    except subprocess.TimeoutExpired:
        profile=command[command.index('--profile-dir')+1] if '--profile-dir' in command else None
        terminate_tree(proc,profile)
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill()
        return {'timed_out':True,'returncode':-9,'stdout':'','stderr':'','seconds':time.perf_counter()-started}

def acquire(rows:pd.DataFrame,*,root:Path,manifest_path:Path,timeout_seconds:float=120,retries:int=1,
            worker:Callable[[list[str],float],dict]=run_worker,retry_delay:float=2,cache_only:bool=False,session_backed:bool=False,season:str='2526',progress:Callable[[dict],None]|None=None,checkpoint_path:Path|None=None,force_recheck:bool=False)->pd.DataFrame:
    base=root/f'data/raw/whoscored/{season}/poc';results=[]
    python=root/".venv/Scripts/python.exe" if (root/".venv/Scripts/python.exe").exists() else Path(sys.executable);all_rows=rows.to_dict('records');batch_started=time.perf_counter()
    def emit():
        if checkpoint_path and results:
            checkpoint_path.parent.mkdir(parents=True,exist_ok=True);temp=checkpoint_path.with_suffix(checkpoint_path.suffix+'.tmp');pd.DataFrame(results).to_csv(temp,index=False)
            for attempt in range(10):
                try:temp.replace(checkpoint_path);break
                except PermissionError:
                    if attempt==9:break
                    time.sleep(.25)
        if not progress:return
        done=len(results);acquired=sum(x['status']=='ACQUIRED' for x in results);hits=sum(x['status']=='CACHE_HIT' for x in results);failed=sum(x['status'] in {'FAILED','TIMEOUT'} for x in results);rate=(time.perf_counter()-batch_started)/max(1,done-hits);remaining=len(all_rows)-done
        progress({'current':done,'total':len(all_rows),'cache_hits':hits,'acquired':acquired,'failed':failed,'remaining':remaining,'eta_seconds':round(remaining*rate,1)})
    for row in all_rows:
        common={k:row.get(k) for k in ('canonical_match_id','understat_match_id','whoscored_match_id','date','home_club_id','away_club_id')}
        checked=validate_cache(base,row)
        if checked['cache_valid'] and not force_recheck:
            results.append({**common,'status':'CACHE_HIT','attempt_count':0,'timeout_count':0,'last_attempt':pd.NA,'acquisition_seconds':0.0,**checked});emit();continue
        if cache_only:
            results.append({**common,'status':'MISSING','attempt_count':0,'timeout_count':0,'last_attempt':pd.NA,'acquisition_seconds':0.0,**checked});emit();continue
        old_checked=checked.copy();target=base/f"match_{_cache_key(row)}";archive=None
        if force_recheck and checked['cache_valid']:
            stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');archive=target/'snapshots'/stamp;archive.mkdir(parents=True,exist_ok=False)
            shutil.copy2(target/'raw_match.json',archive/'raw_match.json');shutil.copy2(target/'metadata.json',archive/'metadata.json')
        attempts=0;timeouts=0;elapsed=0.0;last={};status='FAILED';child_attempts=[]
        # Every live attempt is a separate interpreter; at most one crash retry.
        worker_retries = min(max(retries,0),1) if season == '2627' else retries
        for attempt in range(worker_retries+1):
            attempts+=1;key=_cache_key(row);profile=root/f'data/raw/whoscored/{season}/worker_profiles'/f"match_{key}_{uuid.uuid4().hex}"
            if season=='2627':
                command=[str(python),str(root/'scripts/refresh_whoscored_live_match.py'),'--manifest',str(manifest_path),'--match-id',str(int(row['whoscored_match_id'])),'--season',season,'--force']
            else:
                command=([str(python),str(root/'scripts/refresh_whoscored_historical_poc.py'),'--manifest',str(manifest_path),'--match-id',str(int(row['understat_match_id'])),'--season',season,'--force']
                         if session_backed else [str(python),str(root/'scripts/whoscored_match_worker.py'),'--manifest',str(manifest_path),'--match-id',str(int(row['understat_match_id'])),'--profile-dir',str(profile),'--season',season])
            last=worker(command,timeout_seconds);elapsed+=last['seconds'];timeouts+=int(last['timed_out'])
            shutil.rmtree(profile,ignore_errors=True)
            checked=validate_cache(base,row)
            if season=='2627':
                metadata_path=target/'metadata.json'
                metadata=json.loads(metadata_path.read_text(encoding='utf-8')) if metadata_path.exists() else {}
                child_attempts.append({'attempt':attempts,'returncode':last['returncode'],'timed_out':last['timed_out'],'metadata':metadata})
                target.mkdir(parents=True,exist_ok=True)
                (target/'acquisition_attempts.json').write_text(json.dumps(child_attempts,indent=2),encoding='utf-8')
            if checked['cache_valid'] and last['returncode']==0 and not last['timed_out']:status='ACQUIRED';break
            status='TIMEOUT' if last['timed_out'] else 'FAILED'
            if season=='2627' and not dead_session_error(RuntimeError(str(checked.get('error_message','')))) and last['returncode'] not in (3221225725,-1073741571):break
            if attempt<worker_retries:time.sleep(retry_delay)
        failure_type=checked.get('error_type');failure_message=checked.get('error_message')
        if status in {'FAILED','TIMEOUT'} and archive is not None:
            shutil.copy2(archive/'raw_match.json',target/'raw_match.json');shutil.copy2(archive/'metadata.json',target/'metadata.json');checked=validate_cache(base,row)
        message=failure_message; message=last.get('stderr') or f"Worker exited {last.get('returncode')}" if pd.isna(message) else message
        results.append({**common,'status':status,'worker_mode':'SESSION_BACKED' if session_backed else 'ISOLATED_PROFILE','attempt_count':attempts,'child_attempts':child_attempts,'timeout_count':timeouts,'last_attempt':datetime.now(timezone.utc).isoformat(),'acquisition_seconds':round(elapsed,3),**checked,
          'old_payload_hash':old_checked.get('payload_hash'),'changed':bool(old_checked.get('payload_hash')!=checked.get('payload_hash')) if old_checked.get('cache_valid') and checked.get('cache_valid') else pd.NA,'snapshot_path':str(archive) if archive else pd.NA,'error_type':'TimeoutExpired' if status=='TIMEOUT' else failure_type,'error_message':'worker exceeded process timeout' if status=='TIMEOUT' else message})
        emit()
    return pd.DataFrame(results)
