#!/usr/bin/env python3
"""Build production-sized Sprint 9.6 descriptive analytics from cached 2025/26 data."""
from __future__ import annotations
import argparse,json,sys,time
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from analytics.advanced_descriptive import SUPPLEMENT_POLICY,SAFE_SUPPLEMENT_POLICY,reconcile_safe_metric,dense_rank,canonical_venue,add_plot_coordinates
from integrations.whoscored.workflows import atomic_csv,atomic_json

ADV=ROOT/'data/models/season_2526/advanced';QUALITY=ROOT/'data/quality/season_2526'

def supplemental_player_match(a:pd.DataFrame, events:pd.DataFrame|None=None, fantrax_weekly:pd.DataFrame|None=None)->pd.DataFrame:
    out=a.copy()
    for metric in SAFE_SUPPLEMENT_POLICY:
        merged=reconcile_safe_metric(out,metric);out[metric]=merged[metric];out[f'{metric}_source']=merged[f'{metric}_source']
    if events is not None and not events.empty:
        event_assists=events[events.is_assist.fillna(False).astype(bool)].groupby(['canonical_match_id','canonical_player_id']).size().rename('event_assists')
        out=out.join(event_assists,on=['canonical_match_id','canonical_player_id'])
    if fantrax_weekly is not None and not fantrax_weekly.empty:
        weekly=fantrax_weekly.copy()
        weekly['fantrax_player_id']=weekly['fantrax_player_id'].astype(str).str.strip('*')
        weekly['fantrax_period']=pd.to_numeric(weekly['fantrax_gw'],errors='coerce')
        weekly=weekly.groupby(['fantrax_player_id','fantrax_period'],as_index=False)[['mgr_g','mgr_at']].sum(min_count=1)
        out['fantrax_player_id']=out['fantrax_player_id'].astype(str).str.strip('*')
        out=out.merge(weekly.rename(columns={'mgr_g':'fantrax_goals','mgr_at':'fantrax_assists'}),on=['fantrax_player_id','fantrax_period'],how='left')
    exact=out.get('fantrax_alignment',pd.Series('',index=out.index)).eq('EXACT_SINGLE_CLUB_MATCH_IN_PERIOD')
    fan_goals=pd.to_numeric(out.get('mgr_g',pd.Series(index=out.index)),errors='coerce').combine_first(pd.to_numeric(out.get('fantrax_goals',pd.Series(index=out.index)),errors='coerce'))
    fan_assists=pd.to_numeric(out.get('mgr_at',pd.Series(index=out.index)),errors='coerce').combine_first(pd.to_numeric(out.get('fantrax_assists',pd.Series(index=out.index)),errors='coerce'))
    observed_goals=pd.to_numeric(out.get('goals',pd.Series(index=out.index)),errors='coerce')
    observed_assists=pd.to_numeric(out.get('event_assists',pd.Series(index=out.index)),errors='coerce')
    out['goals']=fan_goals.where(exact,observed_goals)
    out['assists']=fan_assists.where(exact,observed_assists)
    out=out.rename(columns={'actual_position_standardized':'actual_tactical_role','aerials_attempted':'aerial_attempts','crosses':'raw_crosses','fantrax_ghost_points':'ghost_points'})
    keep=['canonical_player_id','fantrax_player_id','canonical_match_id','date','club_id','opponent_id','venue','fantrax_period','manager_id','manager_name','formation','actual_tactical_role','started','minutes','rating','fantrax_points','ghost_points','xg','xa','xgi','key_passes','key_passes_source','dribbles_attempted','dribbles_successful','aerial_attempts','aerial_wins','aerial_wins_source','interceptions','interceptions_source','tackles','clearances','recoveries','blocked_passes','passes_attempted','passes_completed','through_balls','raw_crosses','shots','shots_on_target','goals','assists','fouls','fantrax_alignment','understat_alignment']
    return out.reindex(columns=keep)

def player_profiles(d:pd.DataFrame)->pd.DataFrame:
    metrics=['key_passes','dribbles_attempted','dribbles_successful','aerial_attempts','aerial_wins','interceptions','tackles','clearances','recoveries','blocked_passes','passes_attempted','passes_completed','through_balls','raw_crosses','shots','shots_on_target','goals','assists','xg','xa','xgi','fantrax_points','ghost_points']
    d=d.copy();d['appearance']=True;d['minutes_authority']=pd.to_numeric(d.minutes,errors='coerce')
    agg={m:(m,'sum') for m in metrics};agg.update(appearances=('appearance','sum'),starts=('started','sum'),minutes=('minutes_authority','sum'),average_rating=('rating','mean'),matches=('canonical_match_id','nunique'))
    p=d.groupby('canonical_player_id',as_index=False).agg(**agg)
    for metric in metrics:
        p[f'{metric}_per_match']=p[metric]/p.matches.replace(0,pd.NA);p[f'{metric}_per_start']=p[metric]/p.starts.replace(0,pd.NA);p[f'{metric}_per90']=p[metric]*90/p.minutes.replace(0,pd.NA)
    roles=d[d.started&d.actual_tactical_role.notna()].groupby(['canonical_player_id','club_id','manager_id','manager_name','formation','actual_tactical_role'],dropna=False).size().rename('role_starts').reset_index();roles['role_share']=roles.role_starts/roles.groupby(['canonical_player_id','manager_id'],dropna=False).role_starts.transform('sum');roles['role_rank']=dense_rank(roles,['canonical_player_id','manager_id'],'role_starts')
    overall=roles.groupby(['canonical_player_id','actual_tactical_role'],as_index=False).role_starts.sum();overall['role_share']=overall.role_starts/overall.groupby('canonical_player_id').role_starts.transform('sum');overall['role_rank']=dense_rank(overall,['canonical_player_id'],'role_starts')
    primary=overall.sort_values(['canonical_player_id','role_rank','actual_tactical_role']).drop_duplicates('canonical_player_id').rename(columns={'actual_tactical_role':'primary_observed_role','role_share':'primary_role_share'})[['canonical_player_id','primary_observed_role','primary_role_share']]
    return p.merge(primary,on='canonical_player_id',how='left'),roles

def set_piece_products(events:pd.DataFrame,matches:pd.DataFrame)->tuple[pd.DataFrame,pd.DataFrame,dict]:
    q=events.qualifiers.astype(str);shot=events.event_type.isin(['MissedShots','SavedShot','ShotOnPost','Goal'])
    masks={
      'ALL_CORNERS':q.str.contains('CornerTaken',na=False),
      'DIRECT_FREE_KICKS':q.str.contains('DirectFreekick',na=False)&shot,
      'SHORT_INDIRECT_FREE_KICKS':q.str.contains('IndirectFreekickTaken',na=False),
      'PENALTIES':q.str.contains('"Penalty"',na=False)&shot,
      'SET_PIECE_KEY_PASSES':events.is_key_pass.fillna(False).astype(bool)&q.str.contains('CornerTaken|FreekickTaken|IndirectFreekickTaken|FromCorner|SetPiece',regex=True,na=False),
      'SET_PIECE_CROSSES':q.str.contains('"Cross"',na=False)&q.str.contains('CornerTaken|FreekickTaken|IndirectFreekickTaken',regex=True,na=False),
    }
    pieces=[]
    match_context=matches[['canonical_match_id','date','club_id','manager_id']].drop_duplicates(['canonical_match_id','club_id'])
    for kind,mask in masks.items():
        x=events.loc[mask&events.canonical_player_id.notna(),['canonical_match_id','canonical_player_id','club_id','minute','event_type','is_goal']].copy();x['set_piece_type']=kind;pieces.append(x)
    actions=pd.concat(pieces,ignore_index=True).merge(match_context,on=['canonical_match_id','club_id'],how='left')
    outputs=[]
    for window,n in [('SEASON',None),('LAST_10',10),('LAST_5',5)]:
        for club,g in match_context.groupby('club_id'):
            ids=g.sort_values('date').canonical_match_id.drop_duplicates();ids=ids if n is None else ids.tail(n);x=actions[(actions.club_id==club)&actions.canonical_match_id.isin(ids)].copy();x['window']=window;x['manager_id']=pd.NA;outputs.append(x)
    latest=match_context.sort_values('date').dropna(subset=['manager_id']).drop_duplicates('club_id',keep='last')[['club_id','manager_id']]
    regime=actions.merge(latest,on=['club_id','manager_id'],how='inner');regime['window']='CURRENT_MANAGER_REGIME';outputs.append(regime)
    expanded=pd.concat(outputs,ignore_index=True)
    group=['club_id','set_piece_type','window'];group_regime=group+['manager_id']
    usage=expanded.groupby(group_regime+['canonical_player_id'],dropna=False).agg(attempts=('canonical_match_id','size'),matches_with_action=('canonical_match_id','nunique'),goals=('is_goal','sum'),first_observed=('date','min'),last_observed=('date','max')).reset_index()
    totals=usage.groupby(group_regime,dropna=False).attempts.transform('sum');usage['player_share']=usage.attempts/totals;usage['rank']=dense_rank(usage,group_regime,'attempts');usage['sample_size']=totals
    hierarchy=usage.sort_values(group_regime+['rank','canonical_player_id']).copy();hierarchy['role_label']=hierarchy.apply(lambda r:f"{r.set_piece_type.replace('_',' ').title()} Taker #{int(r['rank'])}",axis=1)
    corner=events[q.str.contains('CornerTaken',na=False)];corner_validation={'corners':len(corner),'x_min':float(corner.x.min()),'x_max':float(corner.x.max()),'low_y':int(corner.y.lt(50).sum()),'high_y':int(corner.y.ge(50).sum()),'left_right_status':'NOT_APPROVED','reason':'coordinates prove two corner sides but do not independently prove human left/right label orientation'}
    return usage,hierarchy,corner_validation

def team_products(features:pd.DataFrame,allowed:pd.DataFrame,roles:pd.DataFrame)->tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    numeric=['passes_attempted','passes_completed','average_event_x','average_pass_start_x','average_pass_end_x','progressive_pass_distance_proxy','final_third_entries','box_entries','crosses','through_balls','shots','shots_on_target','key_passes','take_ons','aerial_player_events','tackles','interceptions','clearances','recoveries','defensive_action_average_x','shot_average_x']
    season=features.groupby(['club_id','manager_id','manager_name','formation'],dropna=False).agg(matches=('canonical_match_id','nunique'),**{f'{c}_per_match':(c,'mean') for c in numeric}).reset_index();season['scope']='OBSERVED_MANAGER_FORMATION'
    a=allowed.copy();a['points_allowed_per_match']=a.points_allowed/a.matches.replace(0,pd.NA);a['ghost_allowed_per_match']=a.ghost_allowed/a.matches.replace(0,pd.NA)
    for metric in ['points_allowed_per_match','ghost_allowed_per_match','goals_allowed','key_passes_allowed','xgi_allowed','dribbles_allowed','aerial_wins_allowed']:
        a[f'{metric}_ease_rank']=a.groupby('position_group')[metric].rank(method='min',ascending=False).astype('Int64')
    formation_roles=roles.groupby(['club_id','manager_id','formation','actual_tactical_role','canonical_player_id'],dropna=False).role_starts.sum().reset_index();formation_roles['role_rank']=dense_rank(formation_roles,['club_id','manager_id','formation','actual_tactical_role'],'role_starts')
    return season,a,formation_roles

def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--season',default='2526');a=p.parse_args()
    if a.season!='2526':raise SystemExit('Only validated 2526 inputs are supported')
    started=time.perf_counter();timings={}
    t=time.perf_counter();matches=pd.read_csv(ADV/'whoscored_match_2526.csv',low_memory=False);advanced=canonical_venue(pd.read_csv(ADV/'advanced_player_match_2526.csv',low_memory=False),matches);events=pd.read_csv(ADV/'player_event_data_2526.csv',low_memory=False);fantrax_weekly=pd.read_csv(ROOT/'data/seasons/2526/processed/master_player_weekly_2526.csv',low_memory=False);supp=supplemental_player_match(advanced,events,fantrax_weekly);timings['supplemental_player_match_seconds']=round(time.perf_counter()-t,3)
    t=time.perf_counter();profile,role_usage=player_profiles(supp);timings['player_advanced_profile_seconds']=round(time.perf_counter()-t,3)
    t=time.perf_counter();team_history=pd.read_csv(ADV/'team_formation_history_2526.csv');sp_usage,sp_hierarchy,corner=set_piece_products(events,team_history);timings['set_piece_hierarchy_seconds']=round(time.perf_counter()-t,3)
    t=time.perf_counter();features=pd.read_csv(ADV/'team_match_features_2526.csv');allowed=pd.read_csv(ADV/'historical_position_fantasy_allowed_2526.csv');team_style,allowed_ranked,formation_roles=team_products(features,allowed,role_usage);timings['team_products_seconds']=round(time.perf_counter()-t,3)
    identity=pd.read_csv(ROOT/'data/reference/whoscored_player_identity.csv');names=identity.dropna(subset=['canonical_player_id']).drop_duplicates('canonical_player_id')[['canonical_player_id','whoscored_player_name']].rename(columns={'whoscored_player_name':'player_name'})
    supp=supp.merge(names,on='canonical_player_id',how='left');profile=profile.merge(names,on='canonical_player_id',how='left');role_usage=role_usage.merge(names,on='canonical_player_id',how='left');sp_usage=sp_usage.merge(names,on='canonical_player_id',how='left');sp_hierarchy=sp_hierarchy.merge(names,on='canonical_player_id',how='left');formation_roles=formation_roles.merge(names,on='canonical_player_id',how='left')
    outputs={'supplemental_player_match':supp,'player_advanced_profile':profile,'player_role_usage':role_usage,'player_set_piece_usage':sp_usage,'team_set_piece_hierarchy':sp_hierarchy,'team_playstyle_profile':team_style,'historical_fantasy_allowed_ranked':allowed_ranked,'formation_player_usage':formation_roles}
    t=time.perf_counter()
    for key,frame in outputs.items():atomic_csv(frame,ADV/f'{key}_2526.csv')
    pitch_columns=['canonical_match_id','canonical_player_id','club_id','opponent_id','minute','second','expanded_minute','period','event_type','outcome','x','y','end_x','end_y','qualifiers','is_key_pass','is_goal','is_assist']
    events=add_plot_coordinates(events);pitch_columns += ['plot_x','plot_y','plot_end_x','plot_end_y']
    pitch_path=ADV/'player_pitch_events_2526.parquet';pitch_temp=pitch_path.with_suffix('.parquet.tmp');events.reindex(columns=pitch_columns).to_parquet(pitch_temp,index=False,compression='zstd');pitch_temp.replace(pitch_path)
    timings['write_seconds']=round(time.perf_counter()-t,3);timings['complete_seconds']=round(time.perf_counter()-started,3)
    policy=pd.DataFrame([{'metric':k,**v} for k,v in SUPPLEMENT_POLICY.items()]);atomic_csv(policy,ROOT/'data/reference/fantrax_supplemental_stat_policy_2526.csv')
    coverage=pd.DataFrame([{'dataset':k,'rows':len(v),'players':v.canonical_player_id.nunique() if 'canonical_player_id'in v else pd.NA,'clubs':v.club_id.nunique() if 'club_id'in v else pd.NA,'status':'PRODUCTION_READY'} for k,v in outputs.items()]);atomic_csv(coverage,QUALITY/'advanced_descriptive_coverage_2526.csv')
    source_counts=pd.concat([supp[f'{m}_source'].value_counts(dropna=False).rename_axis('source').reset_index(name='rows').assign(metric=m) for m in SAFE_SUPPLEMENT_POLICY],ignore_index=True);atomic_csv(source_counts,QUALITY/'supplemental_stat_source_counts_2526.csv')
    set_piece_quality=sp_usage.groupby('set_piece_type').agg(rows=('canonical_player_id','size'),players=('canonical_player_id','nunique'),clubs=('club_id','nunique'),attempts=('attempts','sum'),windows=('window','nunique')).reset_index();atomic_csv(set_piece_quality,QUALITY/'set_piece_hierarchy_coverage_2526.csv')
    pitch_quality=pd.DataFrame([
      {'layer':'Activity Density','events':len(events),'coordinate_coverage':events[['x','y']].notna().all(axis=1).mean(),'end_coordinate_coverage':events[['end_x','end_y']].notna().all(axis=1).mean()},
      *[{'layer':label,'events':int(mask.sum()),'coordinate_coverage':events.loc[mask,['x','y']].notna().all(axis=1).mean(),'end_coordinate_coverage':events.loc[mask,['end_x','end_y']].notna().all(axis=1).mean()} for label,mask in {
       'Passes':events.event_type.eq('Pass'),'Key Passes':events.is_key_pass.fillna(False).astype(bool),'Crosses':events.qualifiers.str.contains('"Cross"',na=False),'TakeOns':events.event_type.eq('TakeOn'),'Shots':events.event_type.isin(['MissedShots','SavedShot','ShotOnPost','Goal']),'Defensive Actions':events.event_type.isin(['Tackle','Interception','Clearance','BlockedPass']),'Recoveries':events.event_type.eq('BallRecovery'),'Aerials':events.event_type.eq('Aerial')}.items()]]
    );atomic_csv(pitch_quality,QUALITY/'player_pitch_event_coverage_2526.csv')
    atomic_csv(pd.DataFrame([{'quality_area':'role_usage','rows':len(role_usage),'players':role_usage.canonical_player_id.nunique(),'clubs':role_usage.club_id.nunique(),'coverage_status':'PRODUCTION_READY'},{'quality_area':'fantasy_allowed','rows':len(allowed_ranked),'players':pd.NA,'clubs':allowed_ranked.opponent_id.nunique(),'coverage_status':'PRODUCTION_READY'},{'quality_area':'team_playstyle','rows':len(team_style),'players':pd.NA,'clubs':team_style.club_id.nunique(),'coverage_status':'PRODUCTION_READY'}]),QUALITY/'advanced_ui_coverage_2526.csv')
    atomic_json(corner,QUALITY/'corner_side_validation_2526.json');atomic_json({'timings':timings,'rows':{k:len(v) for k,v in outputs.items()}},QUALITY/'advanced_descriptive_build_performance_2526.json');print(json.dumps({'timings':timings,'rows':{k:len(v) for k,v in outputs.items()},'corner':corner},indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
