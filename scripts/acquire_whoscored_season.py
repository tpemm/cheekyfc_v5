#!/usr/bin/env python3
"""Resumable full-season acquisition entry point; planning is the safe default."""
import argparse,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from integrations.whoscored.controller import acquire
from integrations.whoscored.workflows import atomic_csv,build_season_manifest,eligible_completed
p=argparse.ArgumentParser();p.add_argument('--season',default='2526');p.add_argument('--execute',action='store_true');p.add_argument('--session-backed',action='store_true');p.add_argument('--timeout',type=float,default=120);p.add_argument('--retries',type=int,default=1);p.add_argument('--shard-count',type=int,default=1);p.add_argument('--shard-index',type=int,default=0);p.add_argument('--only-match',type=int,help='Acquire one canonical match id from the validated manifest');a=p.parse_args()
if a.shard_count<1 or not 0<=a.shard_index<a.shard_count:raise SystemExit('shard-index must be between zero and shard-count minus one')
if a.season!='2526':raise SystemExit('Only the validated 2526 historical source is currently authorized')
manifest=build_season_manifest(ROOT,a.season);path=ROOT/f'data/reference/whoscored_season_manifest_{a.season}.csv';atomic_csv(manifest,path);all_targets=eligible_completed(manifest);targets=all_targets.iloc[a.shard_index::a.shard_count].copy()
if a.only_match is not None:
    targets=all_targets[all_targets.understat_match_id.eq(a.only_match)].copy()
    if targets.empty:raise SystemExit(f'Canonical match id {a.only_match} is not an eligible completed fixture')
summary={'season':a.season,'schedule_matches':len(manifest),'eligible_completed':len(all_targets),'shard_count':a.shard_count,'shard_index':a.shard_index,'shard_matches':len(targets),'provider_ids_resolved':int(targets.whoscored_match_id.notna().sum()),'mode':'EXECUTE' if a.execute else 'PLAN_ONLY','estimated_hours_at_30_9_seconds':round(len(targets)*30.9/3600,2)}
if not a.execute:print(json.dumps(summary,indent=2));raise SystemExit(0)
def show(item):print(f"Match {item['current']}/{item['total']} | Cache hit: {item['cache_hits']} | Acquired: {item['acquired']} | Failed: {item['failed']} | Remaining: {item['remaining']} | ETA: {item['eta_seconds']/60:.1f} min",flush=True)
suffix='' if a.shard_count==1 else f'_shard_{a.shard_index}_of_{a.shard_count}';out=ROOT/f'data/quality/season_{a.season}/whoscored_season_acquisition_manifest_{a.season}{suffix}.csv';started=time.perf_counter();result=acquire(targets,root=ROOT,manifest_path=path,timeout_seconds=a.timeout,retries=a.retries,session_backed=a.session_backed,season=a.season,progress=show,checkpoint_path=out);atomic_csv(result,out);summary.update({'seconds':round(time.perf_counter()-started,3),'cache_hits':int(result.status.eq('CACHE_HIT').sum()),'acquired':int(result.status.eq('ACQUIRED').sum()),'failed':int(result.status.isin(['FAILED','TIMEOUT']).sum()),'retries':int(result.attempt_count.gt(1).sum()),'timeouts':int(result.timeout_count.sum())});print(json.dumps(summary,indent=2));raise SystemExit(1 if summary['failed'] else 0)
