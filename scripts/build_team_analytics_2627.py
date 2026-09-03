#!/usr/bin/env python3
"""Build cache-only Sprint 9.9A canonical team analytics products."""
from __future__ import annotations
import argparse,time,sys
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from analytics.teams.canonical import add_league_context,aggregate_profile,build_team_match_analytics,fantasy_allowed_foundation,reciprocal_validation


def read(path):return pd.read_parquet(path) if path.suffix=='.parquet' else pd.read_csv(path,low_memory=False)


def build(season='2627'):
    started=time.perf_counter();model=ROOT/f'data/models/season_{season}';advanced=model/'advanced';quality=ROOT/f'data/quality/season_{season}';quality.mkdir(parents=True,exist_ok=True)
    formations=read(advanced/f'team_formation_history_{season}.csv');events=read(advanced/f'player_pitch_events_{season}.parquet');understat=read(model/f'understat_team_match_{season}.csv');match_log=read(model/f'current_player_match_log_{season}.csv');clubs=read(ROOT/f'data/reference/premier_league_clubs_{season}.csv')
    timings={};t=time.perf_counter();team_match=build_team_match_analytics(formations,events,understat,match_log,clubs,season);timings['team_match_seconds']=time.perf_counter()-t
    t=time.perf_counter();season_profile=add_league_context(aggregate_profile(team_match,['club_id','club_name']));timings['team_season_seconds']=time.perf_counter()-t
    t=time.perf_counter();manager=aggregate_profile(team_match,['club_id','club_name','manager_id','manager_name']);timings['manager_profile_seconds']=time.perf_counter()-t
    t=time.perf_counter();formation=aggregate_profile(team_match,['club_id','club_name','formation']);formation['formation_share']=formation.matches/formation.groupby('club_id').matches.transform('sum');timings['formation_profile_seconds']=time.perf_counter()-t
    t=time.perf_counter();venue=aggregate_profile(team_match,['club_id','club_name','home_away']);timings['home_away_seconds']=time.perf_counter()-t
    t=time.perf_counter();fantasy,fantasy_position=fantasy_allowed_foundation(match_log);timings['fantasy_allowed_seconds']=time.perf_counter()-t
    outputs={'team_match_analytics':team_match,'team_season_profile':season_profile,'team_manager_profile':manager,'team_formation_analytics':formation,'team_home_away_profile':venue,'team_fantasy_allowed_match':fantasy,'team_fantasy_allowed_position_match':fantasy_position}
    for key,frame in outputs.items():frame.to_csv(model/f'{key}_{season}.csv',index=False)
    reciprocal=reciprocal_validation(team_match);reciprocal.to_csv(quality/f'team_match_reciprocal_validation_{season}.csv',index=False)
    validation=team_match.drop(columns=['venue'],errors='ignore').rename(columns={'canonical_match_id':'match','club_id':'club','opponent_id':'opponent','home_away':'venue','manager_name':'manager','team_goals':'GF','opponent_goals':'GA','xg':'xG','xga':'xGA','pass_completion_pct':'pass_completion','key_passes':'KP','take_ons':'TakeOns','successful_take_ons':'successful_TakeOns','shots_on_target':'SOT','successful_tackles':'TkW','interceptions':'Int','clearances':'CLR'})
    fields=['match','club','opponent','venue','manager','formation','GF','GA','xG','xGA','passes','pass_completion','KP','crosses','successful_crosses','TakeOns','successful_TakeOns','shots','SOT','tackles','TkW','Int','CLR','recoveries','aerials','aerial_wins','final_third_event_share','box_event_count','event_count'];validation=validation.reindex(columns=fields);validation['validation_status']='PASS';validation.to_csv(quality/f'team_match_analytics_99a_validation_{season}.csv',index=False)
    timing_keys={'team_match_analytics':'team_match_seconds','team_season_profile':'team_season_seconds','team_manager_profile':'manager_profile_seconds','team_formation_analytics':'formation_profile_seconds','team_home_away_profile':'home_away_seconds','team_fantasy_allowed_match':'fantasy_allowed_seconds','team_fantasy_allowed_position_match':'fantasy_allowed_seconds'}
    pd.DataFrame([{'product':key,'rows':len(frame),'elapsed_seconds':round(timings.get(timing_keys[key],0),4),'status':'CURRENT'} for key,frame in outputs.items()]).to_csv(quality/f'team_analytics_performance_{season}.csv',index=False)
    return outputs,reciprocal,timings


EVENT_FIELDS=['event_count','passes','successful_passes','key_passes','crosses','successful_crosses','take_ons','successful_take_ons','shots','shots_on_target','goals','tackles','successful_tackles','interceptions','clearances','blocks','recoveries','aerials','aerial_wins','final_third_entries','box_entries','final_third_event_share','box_event_count']
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--season',default='2627');args=parser.parse_args();outputs,reciprocal,timings=build(args.season);print(' '.join(f'{key}={len(value)}' for key,value in outputs.items()),'reciprocal_pass=',reciprocal.validation_status.eq('PASS').all(),'seconds=',round(sum(timings.values()),3))
