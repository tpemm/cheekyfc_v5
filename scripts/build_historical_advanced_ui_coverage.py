#!/usr/bin/env python3
"""Build cross-season UI wiring evidence without regenerating historical analytics."""
from __future__ import annotations
import json,sys,time
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core.services.data_manager import DataManager
from core.services.historical_advanced import get_historical_team_advanced,load_historical_advanced_frame,historical_club_id
from integrations.whoscored.workflows import atomic_csv,atomic_json

def main()->int:
    started=time.perf_counter();data=DataManager();clubs=data.load_frame('premier_league_clubs','2627','working').data;rows=[]
    for _,club in clubs.iterrows():
        current=str(club.canonical_club_id);bundle=get_historical_team_advanced(data,current)
        rows.append({'club':club.canonical_name,'canonical_club_id':current,'historical_canonical_club_id':bundle.historical_club_id,'current_club_resolved':True,'historical_eligible':bundle.historical_eligible,'formations_rows':len(bundle.formations),'fantasy_allowed_rows':len(bundle.fantasy_allowed),'playstyle_rows':len(bundle.playstyle),'manager_rows':bundle.playstyle.manager_id.nunique() if not bundle.playstyle.empty else 0,'role_rows':len(bundle.role_usage),'set_piece_rows':len(bundle.set_pieces),'status':bundle.status})
    coverage=pd.DataFrame(rows);out=ROOT/'data/quality/season_2627/historical_advanced_ui_coverage_2627.csv';atomic_csv(coverage,out)
    supplemental=load_historical_advanced_frame(data,'supplemental_player_match');profile=load_historical_advanced_frame(data,'player_advanced_profile');roles=load_historical_advanced_frame(data,'player_role_usage');pieces=load_historical_advanced_frame(data,'player_set_piece_usage');pitch=load_historical_advanced_frame(data,'player_pitch_events')
    player=supplemental.groupby(['fantrax_player_id','canonical_player_id','player_name'],dropna=False).agg(advanced_match_rows=('canonical_match_id','size'),rating_rows=('rating','count')).reset_index();player['profile_rows']=player.canonical_player_id.map(profile.canonical_player_id.value_counts()).fillna(0).astype(int);player['role_rows']=player.canonical_player_id.map(roles.canonical_player_id.value_counts()).fillna(0).astype(int);player['set_piece_rows']=player.canonical_player_id.map(pieces.canonical_player_id.value_counts()).fillna(0).astype(int);player['pitch_event_rows']=player.canonical_player_id.map(pitch.canonical_player_id.value_counts()).fillna(0).astype(int);player['status']=player.apply(lambda r:'AVAILABLE' if r.advanced_match_rows and r.profile_rows and r.pitch_event_rows else 'PARTIAL',axis=1);atomic_csv(player,ROOT/'data/quality/season_2627/historical_player_ui_coverage_2627.csv')
    b=coverage[coverage.canonical_club_id.eq('afc_bournemouth')].iloc[0].to_dict();b.update({'current_directory_id':'afc_bournemouth','historical_advanced_id':historical_club_id('afc_bournemouth'),'routing_namespace':'working','historical_model_root':'data/models/season_2526/advanced','seconds':round(time.perf_counter()-started,3)});atomic_json(b,ROOT/'data/quality/season_2627/bournemouth_historical_advanced_trace_2627.json')
    print(json.dumps({'clubs':len(coverage),'available':int(coverage.status.eq('AVAILABLE').sum()),'no_history':int(coverage.status.eq('NO_HISTORICAL_EPL_DATA').sum()),'failed':int(coverage.status.eq('HISTORICAL_LOOKUP_FAILED').sum()),'players':len(player),'seconds':round(time.perf_counter()-started,3)},indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
