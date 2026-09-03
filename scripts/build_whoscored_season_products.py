#!/usr/bin/env python3
"""Build supplemental full-season advanced products from validated caches."""
from __future__ import annotations
import argparse,json,sys,time
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from integrations.whoscored.workflows import atomic_csv,atomic_json
from scripts.build_whoscored_scale_products import main as build_normalized
from analytics.teams.matchup import primary_position

def main(season:str)->dict:
    timings={};started=time.perf_counter();manifest=ROOT/f'data/reference/whoscored_season_manifest_{season}.csv'
    t=time.perf_counter();build_normalized(manifest,season);timings['normalized_identity_manager_team_build_seconds']=round(time.perf_counter()-t,3)
    staging=ROOT/f'data/models/season_{season}';out=staging/'advanced';out.mkdir(parents=True,exist_ok=True)
    def read(name):return pd.read_csv(staging/f'{name}_scale_{season}.csv')
    match=read('whoscored_match');team=read('whoscored_team_match');lineup=read('whoscored_lineup');event=read('whoscored_event');advanced=read('advanced_player_match');features=read('team_event_features');activity=read('player_event_activity')
    t=time.perf_counter()
    roles=lineup[lineup.started.eq(True)&lineup.canonical_player_id.notna()].merge(team[['canonical_match_id','club_id','manager_id']],on=['canonical_match_id','club_id'],how='left')
    roles=roles[['canonical_match_id','canonical_player_id','whoscored_player_id','club_id','opponent_id','manager_id','formation','actual_position_raw','actual_position_standardized','started','source']]
    profile=roles.groupby(['canonical_player_id','club_id','manager_id','formation','actual_position_standardized'],dropna=False,as_index=False).agg(starts_at_role=('canonical_match_id','nunique'))
    totals=profile.groupby(['canonical_player_id','club_id'],as_index=False).starts_at_role.sum().rename(columns={'starts_at_role':'starts_observed'});profile=profile.merge(totals,on=['canonical_player_id','club_id']);profile['role_share']=profile.starts_at_role/profile.starts_observed
    primary=profile.sort_values(['canonical_player_id','club_id','starts_at_role'],ascending=[True,True,False]).drop_duplicates(['canonical_player_id','club_id'])[['canonical_player_id','club_id','actual_position_standardized']].rename(columns={'actual_position_standardized':'primary_tactical_role'});profile=profile.merge(primary,on=['canonical_player_id','club_id'])
    formation_history=team.copy();formation_profile=formation_history.groupby(['club_id','manager_id','formation','venue'],dropna=False,as_index=False).agg(matches=('canonical_match_id','nunique'));formation_profile['formation_share']=formation_profile.matches/formation_profile.groupby(['club_id','manager_id']).matches.transform('sum')
    timings['role_formation_build_seconds']=round(time.perf_counter()-t,3)
    t=time.perf_counter();registry=pd.read_csv(ROOT/'data/reference/master_player_crosswalk_identity_only.csv')[['registry_player_id','fantrax_position']].drop_duplicates('registry_player_id');pos=advanced.merge(registry,left_on='canonical_player_id',right_on='registry_player_id',how='left');pos['position_group']=pos.fantrax_position.map(primary_position);pos=pos[pos.position_group.notna()&pos.fantrax_alignment.eq('EXACT_SINGLE_CLUB_MATCH_IN_PERIOD')]
    positional=pos.groupby(['opponent_id','position_group'],as_index=False).agg(matches=('canonical_match_id','nunique'),player_matches=('canonical_match_id','size'),points_allowed=('fantrax_points','sum'),ghost_allowed=('fantrax_ghost_points','sum'),goals_allowed=('goals','sum'),key_passes_allowed=('key_passes','sum'),xgi_allowed=('xgi','sum'),dribbles_allowed=('dribbles_successful','sum'),aerial_wins_allowed=('aerials_won','sum'),defensive_opportunities=('tackles','sum'));positional['position_method']='canonical_single_primary_fantrax_position_only';positional['fantrax_authority']=True
    timings['positional_build_seconds']=round(time.perf_counter()-t,3)
    products={'whoscored_match':match,'whoscored_lineup':lineup,'whoscored_event':event,'advanced_player_match':advanced,'player_match_roles':roles,'player_role_profile':profile,'team_formation_history':formation_history,'team_formation_profile':formation_profile,'team_match_features':features,'player_event_data':activity,'historical_position_fantasy_allowed':positional}
    t=time.perf_counter()
    for name,frame in products.items():atomic_csv(frame,out/f'{name}_{season}.csv')
    timings['atomic_product_write_seconds']=round(time.perf_counter()-t,3);timings['complete_build_seconds']=round(time.perf_counter()-started,3)
    summary={'season':season,'rows':{k:len(v) for k,v in products.items()},'timings':timings};atomic_json(summary,ROOT/f'data/quality/season_{season}/whoscored_season_build_performance_{season}.json');print(json.dumps(summary,indent=2));return summary
if __name__=='__main__':p=argparse.ArgumentParser();p.add_argument('--season',default='2526');a=p.parse_args();main(a.season)
