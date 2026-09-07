#!/usr/bin/env python3
"""Local-only orchestration for Fantrax + WhoScored current weekly data."""
from __future__ import annotations
import argparse,importlib.util,json,os,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fantrax.live.config import load_live_season_config
from fantrax.live.normalization import load_cached_json
from fantrax.live.weekly_acquisition import _auth_path,plan_periods,read_period_metadata
from integrations.whoscored.live_refresh import acquisition_plan,build_live_manifest,cached_provider_schedule,validated_cache_manifest
from integrations.whoscored.workflows import atomic_json
from scripts.refresh_understat_live import refresh_plan as understat_plan
from fantrax.live.provider_maturity import provider_plan
from core.services.machine_role import require_commissioner_writer
import pandas as pd

def command(script,*args):return [sys.executable,str(ROOT/'scripts'/script),*map(str,args)]
def browser_command(script,*args):
    executable=os.environ.get('FANTRAX_BROWSER_PYTHON','').strip()
    if not executable:executable=sys.executable if importlib.util.find_spec('playwright') else 'python'
    return [executable,str(ROOT/'scripts'/script),*map(str,args)]
def plan(season):
    config=load_live_season_config();league_path=config.raw_root/f'league/league_metadata_{season}_latest.json';league=load_cached_json(league_path);fp=plan_periods(league,config.raw_root);period=fp['current_period'];meta=read_period_metadata(config.raw_root,period) if period else {}
    fixtures=pd.read_csv(config.model_root/f'team_matches_{season}.csv');manifest_path=ROOT/f'data/reference/whoscored_season_manifest_{season}.csv';existing=pd.read_csv(manifest_path) if manifest_path.exists() else pd.DataFrame();provider=cached_provider_schedule(ROOT/f'data/raw/whoscored/{season}/poc/_soccerdata_native');wm=build_live_manifest(fixtures,existing=existing,provider_schedule=provider);wm,ws_meta=validated_cache_manifest(wm,ROOT/f'data/raw/whoscored/{season}/poc');wp=acquisition_plan(wm)
    up=understat_plan(season)
    weekly_path=config.model_root/f'current_player_weekly_{season}.csv';weekly=pd.read_csv(weekly_path,low_memory=False) if weekly_path.exists() else pd.DataFrame();period_rows=weekly[pd.to_numeric(weekly.get('period'),errors='coerce').eq(period)] if period and not weekly.empty else pd.DataFrame();fantrax_maturity='FINALIZED' if meta.get('finalized') else 'COMPLETE_PENDING_CORRECTIONS' if len(period_rows) and period_rows.get('period_complete',pd.Series(False,index=period_rows.index)).fillna(False).astype(bool).all() else meta.get('maturity','MISSING')
    eligible_ws=wp.get('stable',0)+wp.get('preliminary',0)+wp.get('missing_eligible',0)+wp.get('failed_retryable',0)
    matchup_meta_path=config.raw_root/f'matchups/period_{int(period or 1):02d}/metadata.json'
    try:matchup_meta=json.loads(matchup_meta_path.read_text(encoding='utf-8'))
    except Exception:matchup_meta={}
    team_path=config.model_root/f'team_match_analytics_{season}.csv';team=pd.read_csv(team_path,low_memory=False) if team_path.exists() else pd.DataFrame();fantasy_path=config.model_root/f'team_fantasy_allowed_position_match_{season}.csv';fantasy=pd.read_csv(fantasy_path,low_memory=False) if fantasy_path.exists() else pd.DataFrame()
    tactical_path=ROOT/f'data/models/season_{season}/team_tactical_profile_{season}.csv';tactical=pd.read_csv(tactical_path) if tactical_path.exists() else pd.DataFrame();tactical_version=tactical.get('methodology_version',pd.Series(dtype=object)).dropna().astype(str).mode()
    team_status={'rows':len(team),'completed_matches':int(team.get('canonical_match_id',pd.Series(dtype=object)).nunique()),'clubs':int(team.get('club_id',pd.Series(dtype=object)).nunique()),'whoscored_team_coverage':int(team.get('event_count',pd.Series(dtype=float)).notna().sum()),'understat_xg_coverage':int(team.get('xg',pd.Series(dtype=float)).notna().sum()),'formation_coverage':int(team.get('formation',pd.Series(dtype=object)).notna().sum()),'manager_coverage':int(team.get('manager_id',pd.Series(dtype=object)).notna().sum()),'fantasy_position_rows':len(fantasy),'historical_reference_available':(ROOT/'data/models/season_2526/team_tactical_profile_2526.csv').exists(),'tactical_methodology_version':None if tactical_version.empty else tactical_version.iat[0],'current_tactical_rows':len(tactical),'current_tactical_clubs':int(tactical.get('club_id',pd.Series(dtype=object)).nunique()),'trait_confidence_state':None if tactical.empty else tactical.get('confidence',pd.Series(dtype=object)).mode().iat[0],'tactical_products_status':'CURRENT' if len(tactical)==20 else 'STALE_OR_MISSING','status':'CURRENT' if len(team)==20 else 'STALE_OR_MISSING'}
    previous=int(period)-1 if period and int(period)>1 else None;previous_meta=read_period_metadata(config.raw_root,previous) if previous else {};previous_status=previous_meta.get('maturity','FINALIZED' if previous is None else 'MISSING')
    marker_path=ROOT/f'data/quality/season_{season}/desktop_source_refresh_latest.json'
    try:marker=json.loads(marker_path.read_text(encoding='utf-8'))
    except Exception:marker={}
    previous_checked=bool(previous and marker.get('previous_gw')==previous and marker.get('previous_correction_check')=='PASS')
    return {'season':season,'fantrax_current_period':period,'previous_gw_status':previous_status,'previous_correction_checked':previous_checked,'fantrax_maturity':fantrax_maturity,'pending_correction_confirmation':fantrax_maturity=='COMPLETE_PENDING_CORRECTIONS','manager_csv_expected':len(league.get('teamInfo',{})),'manager_csv_current':meta.get('manager_exports_acquired',0),'all_player_state':'CURRENT' if meta.get('all_player_rows',0) else 'MISSING','matchup_data':{'status':'AUTHORITATIVE_CURRENT' if matchup_meta.get('validation_status')=='valid' else 'MISSING','matchups':matchup_meta.get('matchup_rows',0),'teams':matchup_meta.get('team_coverage',0),'acquired_at':matchup_meta.get('acquired_at')},'team_models':team_status,'fantrax_targets':fp['targets'],'fantrax_auth_state_present':_auth_path(ROOT).exists(),'whoscored':{**wp,'maturity':provider_plan('whoscored',ws_meta,eligible_ws)},'understat':{**up,'maturity':up['maturity']},'model_rebuild_required':bool(fp['targets']) or matchup_meta.get('validation_status')!='valid' or wp['would_acquire']+wp['would_recheck']+up['would_acquire']>0}
def main():
    p=argparse.ArgumentParser();p.add_argument('--season',default='2627');p.add_argument('--plan',action='store_true');p.add_argument('--skip-whoscored',action='store_true');p.add_argument('--period',type=int);p.add_argument('--finalize',action='store_true',help='Commissioner confirmation after the correction window closes');a=p.parse_args()
    if a.season!='2627':raise SystemExit('Commissioner refresh currently supports season 2627 only')
    started=time.perf_counter();initial=plan(a.season)
    if a.plan:print(json.dumps({'mode':'PLAN_ONLY',**initial},indent=2));return 0
    require_commissioner_writer("weekly commissioner refresh")
    if not initial['fantrax_auth_state_present']:print('Fantrax authentication required',file=sys.stderr);return 2
    stages=[]
    for name,cmd in [('fantrax_weekly',browser_command('refresh_live_fantrax.py','--source','weekly_stats')),
                     ('fantrax_matchups',browser_command('refresh_live_fantrax.py','--source','matchup_scores','--period',a.period or initial.get('fantrax_current_period') or 1))]:
        done=subprocess.run(cmd,cwd=ROOT,check=False);stages.append({'stage':name,'returncode':done.returncode})
        if done.returncode:continue
    for name,cmd in [('core_build',command('build_live_season.py')),('understat_acquisition',command('refresh_understat_live.py','--season',a.season)),('understat_products',command('build_understat_live_products.py'))]:
        done=subprocess.run(cmd,cwd=ROOT,check=False);stages.append({'stage':name,'returncode':done.returncode})
    if not a.skip_whoscored:
        done=subprocess.run(command('weekly_advanced_refresh.py','--season',a.season,'--session-backed'),cwd=ROOT,check=False);stages.append({'stage':'whoscored_advanced','returncode':done.returncode})
    else:
        done=subprocess.run(command('build_current_player_participation.py','--season',a.season),cwd=ROOT,check=False);stages.append({'stage':'canonical_player_participation','returncode':done.returncode})
    done=subprocess.run(command('build_live_weekly_unified.py','--season',a.season),cwd=ROOT,check=False);stages.append({'stage':'unified_models','returncode':done.returncode})
    done=subprocess.run(command('build_team_analytics_2627.py','--season',a.season),cwd=ROOT,check=False);stages.append({'stage':'team_analytics','returncode':done.returncode})
    done=subprocess.run(command('build_team_tactical_99c.py','--season',a.season),cwd=ROOT,check=False);stages.append({'stage':'team_tactical','returncode':done.returncode})
    period=a.period or initial.get('fantrax_current_period') or 1
    done=subprocess.run(command('build_current_data_integrity.py','--season',a.season,'--period',period),cwd=ROOT,check=False);stages.append({'stage':'correction_and_identity_reconciliation','returncode':done.returncode})
    done=subprocess.run(command('build_fantrax_whoscored_semantic_audit.py','--season',a.season,'--period',period),cwd=ROOT,check=False);stages.append({'stage':'cumulative_semantic_validation','returncode':done.returncode})
    done=subprocess.run(command('build_live_ui_propagation.py'),cwd=ROOT,check=False);stages.append({'stage':'propagation_audit','returncode':done.returncode})
    if a.finalize and done.returncode==0:
        weekly_path=ROOT/f'data/models/season_{a.season}/current_player_weekly_{a.season}.csv';weekly=pd.read_csv(weekly_path,low_memory=False) if weekly_path.exists() else pd.DataFrame()
        selected=weekly[pd.to_numeric(weekly.get('period'),errors='coerce').eq(int(period))] if not weekly.empty else pd.DataFrame()
        matchup_meta_path=load_live_season_config().raw_root/f'matchups/period_{int(period):02d}/metadata.json'
        try:matchup_meta=json.loads(matchup_meta_path.read_text(encoding='utf-8'))
        except Exception:matchup_meta={}
        recon_path=ROOT/f'data/quality/season_{a.season}/fantrax_matchup_three_way_reconciliation_{a.season}.csv';recon=pd.read_csv(recon_path) if recon_path.exists() else pd.DataFrame()
        matchup_gate=matchup_meta.get('validation_status')=='valid' and matchup_meta.get('matchup_rows')==6 and matchup_meta.get('team_coverage')==12 and len(recon)==12 and pd.to_numeric(recon.get('diff_matchup_vs_live'),errors='coerce').abs().le(.01).all()
        if selected.empty or not selected.get('period_complete',pd.Series(False,index=selected.index)).fillna(False).astype(bool).all() or not matchup_gate:
            stages.append({'stage':'commissioner_finalization','returncode':2,'detail':'period or authoritative matchup reconciliation gate failed'});done=subprocess.CompletedProcess([],2)
        else:
            metadata_path=load_live_season_config().raw_root/f'player_stats/period_{int(period):02d}/metadata.json'
            metadata=read_period_metadata(load_live_season_config().raw_root,int(period));metadata['finalized']=True;metadata['maturity']='FINALIZED';metadata['finalized_at']=datetime.now(timezone.utc).isoformat();metadata['finalization_method']='explicit commissioner confirmation after final refresh and reconciliation';atomic_json(metadata,metadata_path);final_path=ROOT/f'data/quality/season_{a.season}/finalization_gw{period}_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}.json';atomic_json({'season':a.season,'period':period,'status':'FINALIZED',**metadata},final_path);stages.append({'stage':'commissioner_finalization','returncode':0,'manifest':str(final_path)})
    done=subprocess.run(command('build_refresh_status.py','--season',a.season),cwd=ROOT,check=False);stages.append({'stage':'refresh_status','returncode':done.returncode})
    final=plan(a.season);failed=[x for x in stages if x['returncode']];status='SUCCESS' if not failed else 'PARTIAL' if any(x['returncode']==0 for x in stages) else 'FAILED';report={'status':status,'started_at':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':round(time.perf_counter()-started,3),'stages':stages,'final_plan':final};atomic_json(report,ROOT/f'data/quality/season_{a.season}/weekly_commissioner_refresh_latest.json');print(json.dumps(report,indent=2));return 0 if status=='SUCCESS' else 2
if __name__=='__main__':raise SystemExit(main())
