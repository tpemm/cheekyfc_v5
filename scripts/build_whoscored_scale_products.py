#!/usr/bin/env python3
"""Build the bounded GW36-38 advanced historical scale-test products."""
from __future__ import annotations
import argparse,hashlib,json,re,sys,time,unicodedata
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from analytics.advanced_match_poc import normalize_match,normalize_lineups,normalize_events,build_advanced_player_match
from scripts.build_whoscored_historical_poc import build_crosswalk

def norm(v):return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',str(v)).encode('ascii','ignore').decode().casefold())
def manager_id(name):return 'mgr:'+hashlib.sha1(norm(name).encode()).hexdigest()[:12]

def main(manifest_path:Path|None=None,season:str='2526'):
    build_started=time.perf_counter();timings={};manifest=pd.read_csv(manifest_path or ROOT/'data/reference/whoscored_scale_sample_2526.csv');payloads=[]
    for _,s in manifest.iterrows():
        raw=ROOT/f'data/raw/whoscored/{season}/poc/match_{int(s.understat_match_id)}/raw_match.json'
        if raw.exists():payloads.append((s,json.loads(raw.read_text(encoding='utf-8'))))
    t=time.perf_counter();cross=build_crosswalk(payloads,manifest);cross.to_csv(ROOT/f'data/reference/whoscored_player_crosswalk_scale_{season}.csv',index=False)
    identity=cross.rename(columns={'registry_player_id':'canonical_player_id'});identity.to_csv(ROOT/'data/reference/whoscored_player_identity.csv',index=False)
    pmap=dict(zip(pd.to_numeric(cross.loc[cross.mapping_status.eq('PROVEN'),'whoscored_player_id']).astype(int),cross.loc[cross.mapping_status.eq('PROVEN'),'registry_player_id']));timings['identity_seconds']=round(time.perf_counter()-t,3);t=time.perf_counter()
    matches=[];lineups=[];events=[];manager_obs=[]
    for s,p in payloads:
        meta=json.loads((ROOT/f'data/raw/whoscored/{season}/poc/match_{int(s.understat_match_id)}/metadata.json').read_text())
        c={'canonical_match_id':s.canonical_match_id,'whoscored_match_id':int(s.whoscored_match_id),'date':s.date,'home_club_id':s.home_club_id,'away_club_id':s.away_club_id,'retrieved_at':meta.get('retrieved_at')}
        matches.append(normalize_match(p,c));l=normalize_lineups(p,c);l['canonical_player_id']=pd.to_numeric(l.whoscored_player_id).map(pmap);lineups.append(l);events.append(normalize_events(p,c,pmap))
        for side in ('home','away'):
            name=p[side].get('managerName');manager_obs.append({'canonical_match_id':s.canonical_match_id,'date':s.date,'club_id':s[f'{side}_club_id'],'manager_id':manager_id(name),'manager_name':name,'source':'WhoScored observed match payload'})
    match=pd.DataFrame(matches);lineup=pd.concat(lineups,ignore_index=True);event=pd.concat(events,ignore_index=True);mo=pd.DataFrame(manager_obs);timings['normalization_seconds']=round(time.perf_counter()-t,3);t=time.perf_counter()
    managers=mo.groupby(['manager_id','manager_name'],as_index=False).agg(first_observed_date=('date','min'),last_observed_date=('date','max'),observed_clubs=('club_id',lambda x:'|'.join(sorted(set(x)))));managers['normalized_name']=managers.manager_name.map(norm);managers['source']='WhoScored observed match payload';managers['source_manager_id']=pd.NA;managers['mapping_status']='INTERNAL_CANONICAL_NO_PROVIDER_ID'
    tenures=mo.sort_values('date').groupby(['club_id','manager_id','manager_name'],as_index=False).agg(start_date=('date','min'),end_date=('date','max'),first_observed_match=('canonical_match_id','first'),last_observed_match=('canonical_match_id','last'),matches_observed=('canonical_match_id','nunique'));tenures['season']=season;tenures['source']='WhoScored observed match payload';tenures['confidence_status']='OBSERVED_RANGE_NOT_EXACT_TENURE_BOUNDARY'
    # Team-match perspectives with manager and formation.
    tm=[]
    for r in match.itertuples():
        for side,opp,venue in (('home','away','H'),('away','home','A')):
            gf=getattr(r,f'{side}_score');ga=getattr(r,f'{opp}_score');tm.append({'canonical_match_id':r.canonical_match_id,'whoscored_match_id':r.whoscored_match_id,'date':r.date,'club_id':getattr(r,f'{side}_club_id'),'opponent_id':getattr(r,f'{opp}_club_id'),'venue':venue,'goals_for':gf,'goals_against':ga,'result':'W' if gf>ga else ('D' if gf==ga else 'L'),'formation':getattr(r,f'{side}_formation'),'manager_name':getattr(r,f'{side}_manager_name'),'manager_id':manager_id(getattr(r,f'{side}_manager_name')),'source':'WhoScored/Opta observed'})
    team_match=pd.DataFrame(tm);timings['manager_team_context_seconds']=round(time.perf_counter()-t,3);t=time.perf_counter()
    # Player-match aggregation and observed manager context.
    advanced=build_advanced_player_match(lineup[lineup.canonical_player_id.notna()],event[event.canonical_player_id.notna()])
    advanced=advanced.merge(manifest[['canonical_match_id','understat_match_id','date','fantrax_period']],on='canonical_match_id',how='left').merge(team_match[['canonical_match_id','club_id','venue','manager_id','manager_name']],on=['canonical_match_id','club_id'],how='left')
    advanced=advanced.merge(cross[['registry_player_id','fantrax_player_id','understat_player_id']].dropna(subset=['registry_player_id']).drop_duplicates('registry_player_id'),left_on='canonical_player_id',right_on='registry_player_id',how='left')
    us=pd.read_csv(ROOT/f'data/seasons/{season}/raw_index/understat_player_match_stats_{season}_ENG-Premier_League.csv');advanced['understat_player_id']=pd.to_numeric(advanced.understat_player_id,errors='coerce');us['player_id']=pd.to_numeric(us.player_id,errors='coerce')
    advanced=advanced.merge(us[['game_id','player_id','xg','xa','minutes']].rename(columns={'game_id':'understat_match_id','player_id':'understat_player_id','minutes':'understat_minutes'}),on=['understat_match_id','understat_player_id'],how='left');advanced['xgi']=advanced.xg+advanced.xa;advanced['understat_alignment']=advanced.xg.notna().map({True:'EXACT_PLAYER_MATCH',False:'UNRESOLVED'})
    # Fantrax totals are match-attributable only for one club fixture in the period.
    oriented=pd.concat([manifest[['canonical_match_id','fantrax_period','home_club_id']].rename(columns={'home_club_id':'club_id'}),manifest[['canonical_match_id','fantrax_period','away_club_id']].rename(columns={'away_club_id':'club_id'})]);counts=oriented.groupby(['club_id','fantrax_period']).size().rename('club_period_fixtures').reset_index();advanced=advanced.merge(counts,on=['club_id','fantrax_period'],how='left')
    master=pd.read_csv(ROOT/f'data/seasons/{season}/processed/master_player_weekly_{season}.csv');master['fantrax_id_clean']=master.fantrax_player_id.astype(str).str.strip('*').str.casefold();master['fantrax_period']=pd.to_numeric(master.fantrax_gw,errors='coerce');advanced['fantrax_id_clean']=advanced.fantrax_player_id.astype(str).str.strip('*').str.casefold()
    fcols=['fantrax_id_clean','fantrax_period','mgr_fantasy_points','avail_fpts','mgr_min','mgr_kp','mgr_tkw','mgr_int','mgr_clr','mgr_cos','mgr_aer','mgr_sot','mgr_ac'];advanced=advanced.merge(master[fcols].drop_duplicates(['fantrax_id_clean','fantrax_period']),on=['fantrax_id_clean','fantrax_period'],how='left')
    ghost=pd.read_csv(ROOT/f'data/seasons/{season}/analytics_views/ghost_points_player_weekly.csv');ghost['fantrax_id_clean']=ghost.fantrax_player_id.astype(str).str.strip('*').str.casefold();ghost=ghost.rename(columns={'fantrax_gw':'fantrax_period','ghost_points':'fantrax_ghost_points'})
    advanced=advanced.merge(ghost[['fantrax_id_clean','fantrax_period','fantrax_ghost_points']].drop_duplicates(['fantrax_id_clean','fantrax_period']),on=['fantrax_id_clean','fantrax_period'],how='left');advanced['fantrax_points']=advanced.mgr_fantasy_points.combine_first(advanced.avail_fpts)
    ambiguous=advanced.club_period_fixtures.ne(1);advanced.loc[ambiguous,['fantrax_points','fantrax_ghost_points']]=pd.NA;advanced['fantrax_alignment']=ambiguous.map({True:'AMBIGUOUS_MULTI_FIXTURE_PERIOD',False:'EXACT_SINGLE_CLUB_MATCH_IN_PERIOD'});timings['advanced_player_match_seconds']=round(time.perf_counter()-t,3);t=time.perf_counter()
    # Observed position/formation histories with manager context.
    starts=lineup[lineup.started&lineup.canonical_player_id.notna()&lineup.actual_position_standardized.notna()].merge(team_match[['canonical_match_id','club_id','manager_id']],on=['canonical_match_id','club_id'],how='left')
    roles=starts.groupby(['canonical_player_id','club_id','manager_id','actual_position_standardized'],as_index=False).agg(starts_at_position=('canonical_match_id','size'),matches_observed=('canonical_match_id','nunique'));roles['starts_observed']=roles.groupby(['canonical_player_id','club_id','manager_id']).starts_at_position.transform('sum');roles['position_share']=roles.starts_at_position/roles.starts_observed
    formations=team_match.groupby(['club_id','manager_id','formation'],as_index=False).agg(formation_count=('canonical_match_id','size'),matches_observed=('canonical_match_id','nunique'));formations['formation_share']=formations.formation_count/formations.groupby(['club_id','manager_id']).formation_count.transform('sum');timings['role_formation_seconds']=round(time.perf_counter()-t,3);t=time.perf_counter()
    # Transparent team-match event/spatial features.
    d=event.copy();typ=d.event_type.astype(str);d['pass_attempted']=typ.eq('Pass');d['pass_completed']=d.pass_attempted&d.outcome.eq('Successful');d['cross']=d.qualifiers.str.contains('Cross',case=False,na=False);d['through_ball']=d.qualifiers.str.contains('Throughball',case=False,na=False);d['final_third_entry']=d.pass_attempted&d.x.lt(66.67)&d.end_x.ge(66.67);d['box_entry']=d.pass_attempted&~(d.x.ge(83)&d.y.between(21.1,78.9))&d.end_x.ge(83)&d.end_y.between(21.1,78.9);d['progressive_distance_proxy']=(d.end_x-d.x).clip(lower=0).where(d.pass_attempted,0);d['defensive_action']=typ.isin(['Tackle','Interception','Clearance','BallRecovery','BlockedPass'])
    group=['canonical_match_id','club_id'];features=d.groupby(group,as_index=False).agg(events=('event_id','size'),passes_attempted=('pass_attempted','sum'),passes_completed=('pass_completed','sum'),average_event_x=('x','mean'),average_pass_start_x=('x',lambda s:s[d.loc[s.index,'pass_attempted']].mean()),average_pass_end_x=('end_x',lambda s:s[d.loc[s.index,'pass_attempted']].mean()),progressive_pass_distance_proxy=('progressive_distance_proxy','sum'),final_third_entries=('final_third_entry','sum'),box_entries=('box_entry','sum'),crosses=('cross','sum'),through_balls=('through_ball','sum'),shots=('is_shot','sum'),shots_on_target=('event_type',lambda s:s.isin(['SavedShot','Goal']).sum()),key_passes=('is_key_pass','sum'),take_ons=('event_type',lambda s:s.eq('TakeOn').sum()),aerial_player_events=('event_type',lambda s:s.eq('Aerial').sum()),tackles=('event_type',lambda s:s.eq('Tackle').sum()),interceptions=('event_type',lambda s:s.eq('Interception').sum()),clearances=('event_type',lambda s:s.eq('Clearance').sum()),recoveries=('event_type',lambda s:s.eq('BallRecovery').sum()),defensive_action_average_x=('x',lambda s:s[d.loc[s.index,'defensive_action']].mean()),shot_average_x=('x',lambda s:s[d.loc[s.index,'is_shot']].mean()))
    features['pass_completion_rate']=features.passes_completed/features.passes_attempted;features['final_third_pass_share']=features.final_third_entries/features.passes_attempted;features=team_match.merge(features,on=group,how='left');features['feature_class']='observed_or_transparently_derived';features['contains_prediction']=False;timings['team_feature_seconds']=round(time.perf_counter()-t,3);t=time.perf_counter()
    activity=event[event.whoscored_player_id.notna()].copy();activity['dataset_label']='EVENT_ACTIVITY_NOT_TRACKING'
    out=ROOT/f'data/models/season_{season}';out.mkdir(parents=True,exist_ok=True)
    products={'whoscored_match_scale_2526':match,'whoscored_team_match_scale_2526':team_match,'whoscored_lineup_scale_2526':lineup,'whoscored_event_scale_2526':event,'advanced_player_match_scale_2526':advanced,'player_tactical_position_history_scale_2526':roles,'team_formation_history_scale_2526':formations,'team_event_features_scale_2526':features,'player_event_activity_scale_2526':activity}
    for name,df in products.items():df.to_csv(out/f'{name}.csv',index=False)
    managers.to_csv(ROOT/'data/reference/manager_registry.csv',index=False);tenures.to_csv(ROOT/'data/reference/team_manager_tenures.csv',index=False);timings['write_seconds']=round(time.perf_counter()-t,3);timings['complete_seconds']=round(time.perf_counter()-build_started,3)
    perf=ROOT/f'data/quality/season_{season}/whoscored_build_stage_performance_{season}.json';perf.parent.mkdir(parents=True,exist_ok=True);perf.write_text(json.dumps(timings,indent=2),encoding='utf-8')
    print(json.dumps({'matches':len(match),'team_matches':len(team_match),'lineups':len(lineup),'events':len(event),'unique_players':int(lineup.whoscored_player_id.nunique()),'mapped_players':int(cross.mapping_status.eq('PROVEN').sum()),'advanced_rows':len(advanced),'managers':len(managers),'tenures':len(tenures),'fantrax_exact':int(advanced.fantrax_alignment.eq('EXACT_SINGLE_CLUB_MATCH_IN_PERIOD').sum()),'understat_exact':int(advanced.xg.notna().sum()),'timings':timings}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path);p.add_argument('--season',default='2526');a=p.parse_args();main(a.manifest,a.season)
