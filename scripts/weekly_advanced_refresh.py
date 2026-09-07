#!/usr/bin/env python3
"""Canonical commissioner-only weekly advanced refresh workflow."""
from __future__ import annotations
import argparse,json,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from integrations.whoscored.controller import acquire,validate_cache
from integrations.whoscored.workflows import atomic_csv,atomic_json,build_season_manifest,eligible_completed
from integrations.whoscored.live_refresh import acquisition_plan,build_live_manifest,cached_provider_schedule,validated_cache_manifest,maturity_after_recheck
from core.services.machine_role import require_commissioner_writer

def live_2627(a,started)->int:
    fixtures=pd.read_csv(ROOT/'data/models/season_2627/team_matches_2627.csv')
    manifest_path=ROOT/'data/reference/whoscored_season_manifest_2627.csv'
    existing=pd.read_csv(manifest_path) if manifest_path.exists() else pd.DataFrame()
    cache_root=ROOT/'data/raw/whoscored/2627/poc/_soccerdata_native'
    provider=cached_provider_schedule(cache_root)
    manifest=build_live_manifest(fixtures,existing=existing,provider_schedule=provider)
    for column in ('acquisition_status','cache_status','first_acquired_at','last_checked_at','payload_hash','quality_status'):manifest[column]=manifest[column].astype('object')
    raw_root=ROOT/'data/raw/whoscored/2627/poc'
    for index,row in manifest.iterrows():
        if pd.isna(row.whoscored_match_id):continue
        checked=validate_cache(raw_root,row.to_dict())
        if checked['cache_valid']:
            meta=json.loads((raw_root/f"match_{int(row.whoscored_match_id)}"/'metadata.json').read_text(encoding='utf-8'))
            manifest.at[index,'acquisition_status']='ACQUIRED';manifest.at[index,'cache_status']=manifest.at[index,'cache_status'] if pd.notna(manifest.at[index,'cache_status']) else 'PRELIMINARY';manifest.at[index,'first_acquired_at']=manifest.at[index,'first_acquired_at'] if pd.notna(manifest.at[index,'first_acquired_at']) else meta.get('retrieved_at');manifest.at[index,'last_checked_at']=meta.get('retrieved_at');manifest.at[index,'payload_hash']=checked['payload_hash'];manifest.at[index,'event_count']=checked['event_count'];manifest.at[index,'quality_status']='VALID'
    manifest=build_live_manifest(fixtures,existing=manifest,provider_schedule=provider)
    manifest,_=validated_cache_manifest(manifest,raw_root)
    atomic_csv(manifest,manifest_path);plan=acquisition_plan(manifest)
    report={'season':'2627','mode':'PLAN_ONLY' if a.plan else 'SESSION_BACKED_ACQUISITION',**plan,'elapsed_seconds':round(time.perf_counter()-started,3)}
    quality=ROOT/'data/quality/season_2627/weekly_advanced_refresh_latest.json';atomic_json(report,quality)
    print('2026/27 Advanced Refresh Plan');print(json.dumps(report,indent=2))
    if a.plan:return 0
    if not a.session_backed:
        print('2026/27 acquisition requires --session-backed and is local commissioner-only.',file=sys.stderr);return 2
    if plan['would_acquire']+plan['would_recheck']==0 and plan['missing_eligible']:
        print('No exact WhoScored provider IDs are cached for eligible fixtures; acquisition was not guessed.',file=sys.stderr);return 2
    targets=manifest[manifest.planner_status.isin(['ELIGIBLE_MISSING','FAILED_RETRYABLE'])&manifest.whoscored_match_id.notna()]
    result=acquire(targets,root=ROOT,manifest_path=manifest_path,timeout_seconds=a.timeout,retries=a.retries,session_backed=True,season='2627',force_recheck=False)
    for item in result.to_dict('records'):
        hit=manifest.whoscored_match_id.eq(item.get('whoscored_match_id'))
        if item.get('cache_valid') is True and item.get('status') in {'ACQUIRED','CACHE_HIT'}:
            previous=manifest.loc[hit].iloc[0].copy()
            # Payload hash covers lineup/rating content as well as events.
            maturity=maturity_after_recheck(previous,item)
            manifest.loc[hit,'acquisition_status']='ACQUIRED';manifest.loc[hit,'cache_status']=maturity;manifest.loc[hit,'last_checked_at']=datetime.now(timezone.utc).isoformat();manifest.loc[hit,'payload_hash']=item.get('payload_hash');manifest.loc[hit,'event_count']=item.get('event_count');manifest.loc[hit,'quality_status']='VALID'
        elif item.get('status') in {'FAILED','TIMEOUT'}:manifest.loc[hit,'acquisition_status']=item.get('status')
    manifest=build_live_manifest(fixtures,existing=manifest,provider_schedule=provider)
    manifest,_=validated_cache_manifest(manifest,raw_root)
    atomic_csv(manifest,manifest_path)
    build=subprocess.run([sys.executable,str(ROOT/'scripts/build_whoscored_live_products.py'),'--season','2627'],cwd=ROOT,check=False)
    if build.returncode==0:build=subprocess.run([sys.executable,str(ROOT/'scripts/build_current_player_participation.py'),'--season','2627'],cwd=ROOT,check=False)
    plan=acquisition_plan(manifest);status=result.get('status',pd.Series(dtype=object));report.update(plan);report.update({'acquired_this_run':int(status.eq('ACQUIRED').sum()),'cache_hits':int(status.eq('CACHE_HIT').sum()),'changed':int(result.get('changed',pd.Series(False,index=result.index)).fillna(False).sum()),'recheck_details':result.to_dict('records'),'failures':int(status.isin(['FAILED','TIMEOUT']).sum()),'advanced_build':'SUCCESS' if build.returncode==0 else 'FAILED','elapsed_seconds':round(time.perf_counter()-started,3)});atomic_json(report,quality);print(json.dumps(report,indent=2));return 1 if report['failures'] or build.returncode else 0

def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--season',default='2526');p.add_argument('--plan',action='store_true');p.add_argument('--cache-only',action='store_true');p.add_argument('--session-backed',action='store_true');p.add_argument('--timeout',type=float,default=120);p.add_argument('--retries',type=int,default=1);a=p.parse_args()
    started=time.perf_counter()
    if not a.plan and not a.cache_only:require_commissioner_writer("WhoScored advanced acquisition")
    if a.season=='2627':return live_2627(a,started)
    manifest=build_season_manifest(ROOT,a.season);manifest_path=ROOT/f'data/reference/whoscored_season_manifest_{a.season}.csv';atomic_csv(manifest,manifest_path);eligible=eligible_completed(manifest)
    result=acquire(eligible,root=ROOT,manifest_path=manifest_path,timeout_seconds=a.timeout,retries=a.retries,cache_only=a.plan or a.cache_only,session_backed=a.session_backed,season=a.season)
    acquisition_path=ROOT/f'data/quality/season_{a.season}/whoscored_weekly_acquisition_manifest_{a.season}.csv';atomic_csv(result,acquisition_path)
    build_status='NOT_RUN_PLAN_ONLY' if a.plan else 'NOT_RUN_ACQUISITION_FAILURE'
    if not a.plan:
        command=[str(ROOT/'.venv/Scripts/python.exe'),str(ROOT/'scripts/build_whoscored_scale_products.py'),'--manifest',str(manifest_path),'--season',a.season]
        completed=subprocess.run(command,cwd=ROOT,check=False);build_status='SUCCESS' if completed.returncode==0 else 'FAILED'
        if build_status=='SUCCESS' and a.season=='2526':subprocess.run([str(ROOT/'.venv/Scripts/python.exe'),str(ROOT/'scripts/build_whoscored_scale_quality.py')],cwd=ROOT,check=False)
    report={'season':a.season,'started_at':datetime.now(timezone.utc).isoformat(),'mode':'PLAN_ONLY' if a.plan else ('CACHE_ONLY' if a.cache_only else 'ACQUIRE_MISSING'),'schedule_matches':len(manifest),'completed_eligible':len(eligible),'valid_caches':int(result.cache_valid.eq(True).sum()),'missing_or_failed':int(result.cache_valid.ne(True).sum()),'cache_hits':int(result.status.eq('CACHE_HIT').sum()),'acquired':int(result.status.eq('ACQUIRED').sum()),'failed':int(result.status.isin(['FAILED','TIMEOUT']).sum()),'advanced_build':build_status,'elapsed_seconds':round(time.perf_counter()-started,3)}
    atomic_json(report,ROOT/f'data/quality/season_{a.season}/weekly_advanced_refresh_latest.json');print(json.dumps(report,indent=2));return 1 if report['failed'] or build_status=='FAILED' else 0
if __name__=='__main__':raise SystemExit(main())
