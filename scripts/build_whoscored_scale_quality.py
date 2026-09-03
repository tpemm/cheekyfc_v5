#!/usr/bin/env python3
"""Build offline, reproducible Sprint 9.3 scale-readiness quality evidence."""
from pathlib import Path
import json
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]; MODEL=ROOT/'data/models/season_2526'; QUALITY=ROOT/'data/quality/season_2526'

def main():
    acq=pd.read_csv(QUALITY/'whoscored_acquisition_manifest_2526.csv'); cross=pd.read_csv(ROOT/'data/reference/whoscored_player_crosswalk_scale_2526.csv')
    match=pd.read_csv(MODEL/'whoscored_match_scale_2526.csv'); team=pd.read_csv(MODEL/'whoscored_team_match_scale_2526.csv'); lineup=pd.read_csv(MODEL/'whoscored_lineup_scale_2526.csv'); event=pd.read_csv(MODEL/'whoscored_event_scale_2526.csv'); adv=pd.read_csv(MODEL/'advanced_player_match_scale_2526.csv')
    meaningful=set(lineup.loc[lineup.started.eq(True)|lineup.sub_on_minute.notna(),'whoscored_player_id'].astype(int)); cm=cross[cross.whoscored_player_id.isin(meaningful)]
    coords=event[['x','y']].stack().between(0,100).all() and event[['end_x','end_y']].stack().dropna().between(0,100).all()
    rated=lineup.rating.notna(); comparable=adv.fantrax_alignment.eq('EXACT_SINGLE_CLUB_MATCH_IN_PERIOD')
    gates=[
      ('match_acquisition',acq.cache_valid.eq(True).mean(),.95),('team_mapping',team.club_id.notna().mean(),1),('meaningful_player_mapping',cm.mapping_status.eq('PROVEN').mean(),.97),
      ('event_id_uniqueness',1-event.duplicated(['canonical_match_id','event_id']).mean(),1),('formation_parsing',team.formation.notna().mean(),.95),
      ('starting_role_parsing',lineup.loc[lineup.started,'actual_position_standardized'].notna().mean(),.95),('rating_extraction',lineup.loc[rated,'rating'].between(0,10).mean(),1),
      ('coordinate_validity',float(coords),1),('fantrax_match_alignment',adv.loc[comparable,'fantrax_points'].notna().mean(),.95)]
    report=pd.DataFrame([{'gate':n,'observed':v,'threshold':t,'passed':bool(v>=t)} for n,v,t in gates])
    report.to_csv(QUALITY/'whoscored_scale_readiness_gates_2526.csv',index=False)
    summary={'matches':len(match),'teams':team.club_id.nunique(),'players':lineup.whoscored_player_id.nunique(),'meaningful_players':len(meaningful),'mapped_meaningful':int(cm.mapping_status.eq('PROVEN').sum()),'understat_exact':int(adv.understat_alignment.eq('EXACT_PLAYER_MATCH').sum()),'understat_rate':float(adv.understat_alignment.eq('EXACT_PLAYER_MATCH').mean()),'fantrax_comparable':int(comparable.sum()),'fantrax_exact_points':int(adv.loc[comparable,'fantrax_points'].notna().sum()),'all_gates_passed':bool(report.passed.all())}
    (QUALITY/'whoscored_scale_readiness_summary_2526.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary))
if __name__=='__main__':main()
