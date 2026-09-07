"""Evidence-derived refresh status for the Operations Center."""
from __future__ import annotations
import json
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd

def _mtime(path:Path):return datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat() if path.exists() else None
def _json(path:Path)->dict:
    try:return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    except (OSError,json.JSONDecodeError):return {}
def _frame(path:Path)->pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def team_model_status(team:pd.DataFrame)->str:
    if team.empty or not {'canonical_match_id','club_id'}.issubset(team):return 'STALE_OR_MISSING'
    valid=not team.duplicated(['canonical_match_id','club_id']).any() and team.groupby('canonical_match_id').size().eq(2).all()
    return 'CURRENT' if valid else 'STALE_OR_MISSING'


def published_period_progress(fixtures:pd.DataFrame,current_period:int|None,results:pd.DataFrame)->dict:
    from fantrax.live.season_state import live_period_phase
    observed=fixtures.copy()
    if not results.empty and {'canonical_match_id','home_score','away_score'}.issubset(results) and 'match_id' in observed:
        ids=set(results.dropna(subset=['home_score','away_score']).canonical_match_id)
        observed['completed']=observed.get('completed',pd.Series(False,index=observed.index)).fillna(False)|observed.match_id.isin(ids)
    return live_period_phase(observed,current_period)


def derive_refresh_status(root:Path|None=None,season:str='2627')->pd.DataFrame:
    root=root or Path(__file__).resolve().parents[2]
    rows=[];live=root/f'data/models/season_{season}/live_season_manifest_{season}.json'
    rows.append({'area':'Core Data','state':'Current' if live.exists() else 'Unavailable','last_successful_refresh':_mtime(live),'coverage':pd.NA,'detail':'Registered Fantrax/API build manifest' if live.exists() else 'No live build manifest'})
    model=root/f'data/models/season_{season}';quality=root/f'data/quality/season_{season}'
    report=_json(quality/'weekly_commissioner_refresh_latest.json');plan=report.get('final_plan',{})
    periods=_frame(quality/f'weekly_period_status_{season}.csv')
    period=int(pd.to_numeric(periods.period,errors='coerce').max()) if not periods.empty else plan.get('fantrax_current_period')
    latest=periods[pd.to_numeric(periods.period,errors='coerce').eq(period)].iloc[-1].to_dict() if not periods.empty else {}
    expected=int(plan.get('manager_csv_expected') or 12)
    same_period=plan.get('fantrax_current_period')==period
    acquired=int(plan.get('manager_csv_current',0)) if same_period else 0
    all_rows=int(latest.get('row_count',0));maturity=plan.get('fantrax_maturity','MISSING')
    weekly_state='Current' if acquired==expected and all_rows and latest.get('validation_status')=='valid' else ('Partial' if acquired or all_rows else 'Unavailable')
    rows.append({'area':'Fantrax Weekly Exports','state':weekly_state,'last_successful_refresh':latest.get('retrieved_at'),'coverage':f'{acquired}/{expected} managers','detail':f"GW{period or '?'} {maturity} | all-player {all_rows} rows | {max(expected-acquired,0)} manager exports missing"})
    matchups=_frame(model/f'fantrax_matchups_{season}.csv')
    matchups=matchups[pd.to_numeric(matchups.period,errors='coerce').eq(period)].drop_duplicates('matchup_id') if not matchups.empty else matchups
    scored=matchups.dropna(subset=['home_score','away_score']) if not matchups.empty else matchups
    matchup_rows=len(scored);matchup_teams=len(set(scored.home_team_id)|set(scored.away_team_id)) if len(scored) else 0
    matchup_current=matchup_rows==expected//2 and matchup_teams==expected
    rows.append({'area':'Fantrax Matchup Scores','state':'Current' if matchup_current else 'Unavailable','last_successful_refresh':scored.acquired_at.max() if len(scored) else None,'coverage':f'{matchup_teams}/{expected} teams | {matchup_rows}/{expected//2} matchups','detail':f"GW{period} authoritative published matchup scores" if matchup_current else 'No validated matchup authority product'})
    recon_path=root/f'data/quality/season_{season}/fantrax_matchup_three_way_reconciliation_{season}.csv';recon=pd.read_csv(recon_path) if recon_path.exists() else pd.DataFrame()
    if not recon.empty:
        recon=recon[pd.to_numeric(recon.period,errors='coerce').eq(period)].drop_duplicates('fantrax_team_id',keep='last')
    exact_live=int(pd.to_numeric(recon.get('diff_matchup_vs_live'),errors='coerce').abs().le(.01).sum()) if not recon.empty else 0;exact_all=int(recon.get('status',pd.Series(dtype=str)).eq('EXACT_ALL').sum()) if not recon.empty else 0
    rows.append({'area':'Player / Matchup Reconciliation','state':'Current' if len(recon)==12 and exact_live==12 else ('Partial' if len(recon) else 'Unavailable'),'last_successful_refresh':_mtime(recon_path),'coverage':f'{exact_live}/12 live exact','detail':f'{exact_all} all-source exact · {len(recon)-exact_all} documented CSV source-state differences'})
    unified_manifest=root/f'data/quality/season_{season}/weekly_unified_latest_{season}.json';unified=_json(unified_manifest);unified_rows=int(unified.get('unified_rows',0));waiver_rows=int(unified.get('waiver_rows',0));fantasy_allowed_rows=int(unified.get('fantasy_allowed_rows',0));unified_state='Current' if unified_rows else ('Blocked' if unified.get('status') else 'Unavailable')
    rows.append({'area':'Unified Player-Week','state':unified_state,'last_successful_refresh':_mtime(unified_manifest),'coverage':f'{unified_rows} players · {waiver_rows} waivers','detail':f"{fantasy_allowed_rows} Fantasy Allowed rows · {unified.get('status','no build manifest')}"})
    schedule_path=root/f'data/reference/whoscored_season_manifest_{season}.csv';schedule=pd.read_csv(schedule_path) if schedule_path.exists() else pd.DataFrame();expected=int(schedule.is_completed.sum()) if not schedule.empty and 'is_completed' in schedule else int(schedule.planner_status.isin(['ELIGIBLE_MISSING','ELIGIBLE_PRELIMINARY','FAILED_RETRYABLE','STABLE']).sum()) if 'planner_status' in schedule else 0
    validation=root/f'data/quality/season_{season}/whoscored_raw_cache_validation_{season}.csv'
    candidates=[validation,root/f'data/quality/season_{season}/whoscored_season_acquisition_manifest_{season}.csv',root/f'data/quality/season_{season}/whoscored_weekly_acquisition_manifest_{season}.csv',root/f'data/quality/season_{season}/whoscored_acquisition_manifest_{season}.csv'];acq_path=next((p for p in candidates if p.exists()),candidates[-1]);acq=pd.read_csv(acq_path) if acq_path.exists() else pd.DataFrame();valid=int(acq.classification.eq('VALID').sum()) if 'classification' in acq else (int(acq.cache_valid.eq(True).sum()) if not acq.empty else 0);failed=int(acq.status.isin(['FAILED','TIMEOUT']).sum()) if 'status' in acq else int(acq.classification.eq('INVALID').sum()) if 'classification' in acq else 0
    if 'cache_status' in schedule:
        valid=int(schedule.cache_status.isin(['PRELIMINARY','STABLE']).sum());failed=int(schedule.acquisition_status.isin(['FAILED','TIMEOUT']).sum()) if 'acquisition_status' in schedule else 0;preliminary=int(schedule.cache_status.eq('PRELIMINARY').sum());stable=int(schedule.cache_status.eq('STABLE').sum())
    else:preliminary=stable=0
    state='Unavailable' if not expected else ('Complete' if valid==expected and not failed else ('Partial' if valid else 'Stale'))
    valid_mask=acq.classification.eq('VALID') if 'classification' in acq else acq.cache_valid.eq(True) if 'cache_valid' in acq else pd.Series(False,index=acq.index)
    latest=acq.loc[valid_mask,'date'].max() if valid and 'date' in acq else pd.NA
    rows.append({'area':'WhoScored Advanced','state':state,'last_successful_refresh':_mtime(schedule_path),'coverage':f'{valid}/{expected}','detail':f'{preliminary} preliminary · {stable} stable · {expected-valid} missing · {failed} failed · latest {latest}'})
    understat=model/f'understat_team_match_{season}.csv';us=_frame(understat)
    represented=pd.to_numeric(us.get('period',pd.Series(dtype=float)),errors='coerce').max()
    us_report=_json(root/f'data/quality/season_{season}/understat_live_latest_{season}.json');matches=int(us_report.get('matches',0));team_rows=int(us_report.get('team_rows',0));player_rows=int(us_report.get('player_rows',0));unresolved=int(us_report.get('unresolved_players',0));us_state='Current' if matches and team_rows==matches*2 else ('Partial' if len(us) else 'Unavailable')
    rows.append({'area':'Schedule / Understat','state':us_state,'last_successful_refresh':_mtime(understat),'coverage':f'{matches} matches · {team_rows} team · {player_rows} player','detail':f'Latest completed GW {represented} · {unresolved} unresolved player identities' if pd.notna(represented) else 'No completed match evidence'})
    canonical=root/f'data/models/season_{season}/advanced';advanced=canonical/f'advanced_player_match_{season}.csv';events=canonical/f'whoscored_event_{season}.csv'
    if not advanced.exists():advanced=root/f'data/models/season_{season}/advanced_player_match_scale_{season}.csv'
    if not events.exists():events=root/f'data/models/season_{season}/whoscored_event_scale_{season}.csv'
    identity=root/'data/reference/whoscored_player_identity.csv'
    ar=len(pd.read_csv(advanced)) if advanced.exists() else 0;er=len(pd.read_csv(events)) if events.exists() else 0;unresolved=int(pd.read_csv(identity).mapping_status.ne('PROVEN').sum()) if identity.exists() else 0
    managers=root/f'data/reference/manager_observations_{season}.csv';managers=managers if managers.exists() else root/'data/reference/manager_registry.csv';manager_count=pd.read_csv(managers).manager_id.nunique() if managers.exists() else 0
    rows.append({'area':'Advanced Models','state':'Current' if ar and er else 'Unavailable','last_successful_refresh':max(filter(None,[_mtime(advanced),_mtime(events)]),default=None),'coverage':f'{ar} player-match · {er} events','detail':f'{unresolved} unresolved players · {manager_count} managers'})
    season_gates=root/f'data/quality/season_{season}/whoscored_season_quality_gates_{season}.csv';scale_gates=root/f'data/quality/season_{season}/whoscored_scale_readiness_gates_{season}.csv';understat_gates=root/f'data/quality/season_{season}/understat_gw1_quality_gates_{season}.csv';gates=next((p for p in (season_gates,scale_gates,understat_gates) if p.exists()),season_gates);g=pd.read_csv(gates) if gates.exists() else pd.DataFrame();fail=int(g.passed.eq(False).sum()) if not g.empty else 0
    rows.append({'area':'Quality','state':'Current' if not g.empty and fail==0 else ('Failed' if fail else 'Unavailable'),'last_successful_refresh':_mtime(gates),'coverage':f'{len(g)-fail}/{len(g)} gates' if len(g) else pd.NA,'detail':f'{fail} failed validation gates'})
    team=_frame(model/f'team_match_analytics_{season}.csv')
    rows.append({'area':'Team Models','state':team_model_status(team),'last_successful_refresh':_mtime(model/f'team_match_analytics_{season}.csv'),'coverage':f"{team.get('canonical_match_id',pd.Series(dtype=str)).nunique()} matches | {len(team)} team rows",'detail':'Published canonical team products'})
    return pd.DataFrame(rows)
