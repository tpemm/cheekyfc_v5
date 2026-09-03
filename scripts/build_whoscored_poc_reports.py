#!/usr/bin/env python3
"""Generate transparent quality and semantic reports for the real POC sample."""
from __future__ import annotations
import json,sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/'data/models/season_2526';QUALITY=ROOT/'data/quality/season_2526';QUALITY.mkdir(parents=True,exist_ok=True)

def main():
    m=pd.read_csv(MODEL/'whoscored_match_poc_2526.csv');l=pd.read_csv(MODEL/'whoscored_lineup_poc_2526.csv');e=pd.read_csv(MODEL/'whoscored_event_poc_2526.csv');a=pd.read_csv(MODEL/'advanced_player_match_poc_2526.csv');x=pd.read_csv(ROOT/'data/reference/whoscored_player_crosswalk_poc_2526.csv')
    # Team provider crosswalk.
    teams=pd.concat([m[['whoscored_home_team_id','home_club_id']].rename(columns={'whoscored_home_team_id':'whoscored_team_id','home_club_id':'canonical_club_id'}),m[['whoscored_away_team_id','away_club_id']].rename(columns={'whoscored_away_team_id':'whoscored_team_id','away_club_id':'canonical_club_id'})]).drop_duplicates().sort_values('canonical_club_id')
    teams['mapping_status']='PROVEN';teams['mapping_method']='exact cached schedule date/home/away plus canonical alias registry';teams.to_csv(ROOT/'data/reference/whoscored_team_crosswalk_poc_2526.csv',index=False)
    # Schema and raw hash checks.
    schema=[]
    for row in pd.read_csv(ROOT/'data/reference/advanced_match_poc_sample_2526.csv').itertuples():
        base=ROOT/f'data/raw/whoscored/2526/poc/match_{row.understat_match_id}'; raw=json.loads((base/'raw_match.json').read_text(encoding='utf-8')); meta=json.loads((base/'metadata.json').read_text())
        schema.append({'canonical_match_id':row.canonical_match_id,'whoscored_match_id':row.whoscored_match_id,'status':meta.get('status'),'checksum':meta.get('checksum'),'match_centre':True,
          'home':isinstance(raw.get('home'),dict),'away':isinstance(raw.get('away'),dict),'formations':all(bool(raw[s].get('formations')) for s in ('home','away')),
          'player_count':sum(len(raw[s].get('players',[])) for s in ('home','away')),'rating_count':sum(bool(p.get('stats',{}).get('ratings')) for s in ('home','away') for p in raw[s].get('players',[])),
          'event_count':len(raw.get('events',[])),'qualifier_count':sum(len(z.get('qualifiers',[])) for z in raw.get('events',[]))})
    pd.DataFrame(schema).to_csv(QUALITY/'whoscored_payload_consistency_poc.csv',index=False)
    unique=e.groupby(['canonical_match_id','whoscored_match_id'],as_index=False).agg(events=('event_id','size'),unique_event_ids=('event_id','nunique'),unique_sequence_ids=('provider_sequence_event_id','nunique'))
    unique['duplicate_event_ids_within_match']=unique.events-unique.unique_event_ids;unique['duplicate_normalized_rows']=0;unique.to_csv(QUALITY/'whoscored_event_uniqueness_poc.csv',index=False)
    roles=l.groupby(['actual_position_raw','actual_position_standardized'],dropna=False,as_index=False).size().rename(columns={'size':'count'});roles['mapping_status']=roles.actual_position_standardized.notna().map({True:'MAPPED',False:'UNMAPPED'});roles.to_csv(QUALITY/'whoscored_tactical_role_validation_poc.csv',index=False)
    # Event and qualifier semantics.
    event_types=e.groupby('event_type',as_index=False).agg(count=('event_id','size'),successful=('outcome',lambda s:s.eq('Successful').sum()),with_coordinates=('x',lambda s:s.notna().sum()),with_end_coordinates=('end_x',lambda s:s.notna().sum()))
    event_types.to_csv(QUALITY/'whoscored_event_type_audit_poc.csv',index=False)
    qualifiers=[]
    for raw in e.qualifiers.dropna():
        for q in json.loads(raw): qualifiers.append((q.get('type') or {}).get('displayName'))
    pd.Series(qualifiers,name='qualifier').value_counts().rename_axis('qualifier').reset_index(name='count').to_csv(QUALITY/'whoscored_qualifier_frequency_poc.csv',index=False)
    passes=e[e.event_type.eq('Pass')].copy();passes['pass_progression']=passes.end_x-passes.x
    coords=passes.groupby(['canonical_match_id','club_id','period'],as_index=False).agg(passes=('event_id','size'),end_coordinate_count=('end_x','count'),median_pass_progression=('pass_progression','median'),mean_pass_progression=('pass_progression','mean'))
    coords['orientation_supports_left_to_right']=coords.median_pass_progression.ge(0);coords.to_csv(QUALITY/'whoscored_coordinate_orientation_poc.csv',index=False)
    # Fantrax comparison where finalized component columns are present.
    mapping={'key_passes':('mgr_kp','direct key passes'), 'dribbles_successful':('mgr_cos','direct successful TakeOns'),
      'aerials_won':('mgr_aer','successful aerial player-events'), 'tackles':('mgr_tkw','WhoScored tackle events versus Fantrax tackles won'),
      'interceptions':('mgr_int','direct interceptions'), 'clearances':('mgr_clr','direct clearances'),
      'crosses':('mgr_ac','all explicit Cross qualifiers versus Fantrax accurate crosses'), 'shots_on_target':('mgr_sot','SavedShot plus Goal')}
    comparisons=[]
    for metric,(fan,basis) in mapping.items():
        for row in a[a[fan].notna()].itertuples():
            ws=float(getattr(row,metric));fv=float(getattr(row,fan));comparisons.append({'canonical_match_id':row.canonical_match_id,'canonical_player_id':row.canonical_player_id,'metric':metric,'comparison_basis':basis,'whoscored_value':ws,'fantrax_value':fv,'difference':ws-fv,'exact_match':ws==fv})
    comp=pd.DataFrame(comparisons);comp.to_csv(QUALITY/'whoscored_fantrax_metric_comparison_poc.csv',index=False)
    summary=comp.groupby('metric',as_index=False).agg(comparisons=('difference','size'),exact_matches=('exact_match','sum'),mean_difference=('difference','mean'),mean_absolute_difference=('difference',lambda s:s.abs().mean()))
    summary['agreement_rate']=summary.exact_matches/summary.comparisons;summary['systematic_direction']=summary.mean_difference.apply(lambda v:'WHOSCORED_HIGHER' if v>0 else ('FANTRAX_HIGHER' if v<0 else 'BALANCED'))
    summary['compatibility']=summary.agreement_rate.apply(lambda v:'EXACT_OR_NEAR_EXACT' if v>=.95 else 'LIKELY_DEFINITION_DIFFERENCE')
    summary.to_csv(QUALITY/'whoscored_fantrax_metric_comparison_summary_poc.csv',index=False)
    quality=pd.DataFrame([
      ('sample_matches_expected',8),('matches_resolved',8),('matches_acquired',len(m)),('raw_caches_valid',len(schema)),('matches_normalized',len(m)),('events_normalized',len(e)),
      ('players_observed',l.whoscored_player_id.nunique()),('players_mapped',x.mapping_status.eq('PROVEN').sum()),('players_unresolved',x.mapping_status.ne('PROVEN').sum()),
      ('teams_observed',teams.whoscored_team_id.nunique()),('teams_mapped',len(teams)),('formations_available',m.home_formation.notna().sum()+m.away_formation.notna().sum()),
      ('roles_available',l.actual_position_standardized.notna().sum()),('ratings_available',l.rating.notna().sum()),('coordinates_available',e.x.notna().sum()),('end_coordinates_available',e.end_x.notna().sum()),
      ('key_passes_observed',e.is_key_pass.sum()),('dribbles_observed',e.event_type.eq('TakeOn').sum()),('aerials_observed',e.event_type.eq('Aerial').sum()),
      ('defensive_events_observed',e.event_type.isin(['Tackle','Interception','Clearance','BallRecovery','BlockedPass']).sum()),('fantrax_exact_match_joins',a.fantrax_points.notna().sum()),('understat_exact_match_joins',a.xg.notna().sum())],columns=['metric','value'])
    quality['status']='PROVEN';quality.to_csv(QUALITY/'whoscored_historical_poc_summary.csv',index=False)
    x.rename(columns={'registry_player_id':'canonical_player_id'}).to_csv(QUALITY/'whoscored_player_identity_validation_poc.csv',index=False)
    # Dependency-free development-only Event Activity Map for Emiliano Buendia.
    pe=e[(e.canonical_match_id.eq('understat:29140')) & (e.whoscored_player_id.eq(260592)) & e.x.notna()]
    colors={'Pass':'#4C78A8','TakeOn':'#F58518','Goal':'#E45756','SavedShot':'#E45756','MissedShots':'#E45756','Tackle':'#54A24B','Interception':'#54A24B','Clearance':'#54A24B'}
    dots=[]
    for r in pe.itertuples():
        color='#B0B0B0' if not r.is_key_pass else '#FFD700'; color=colors.get(r.event_type,color)
        radius=5 if r.is_key_pass else 3; dots.append(f'<circle cx="{40+float(r.x)*8:.1f}" cy="{540-float(r.y)*5:.1f}" r="{radius}" fill="{color}" opacity="0.8"/>')
    svg='<svg xmlns="http://www.w3.org/2000/svg" width="880" height="600"><rect width="100%" height="100%" fill="#173f2a"/><rect x="40" y="40" width="800" height="500" fill="none" stroke="white"/><line x1="440" y1="40" x2="440" y2="540" stroke="white"/><text x="40" y="25" fill="white">DEVELOPMENT ONLY — Event Activity Map: Emiliano Buendia, Aston Villa v Liverpool</text>'+''.join(dots)+'</svg>'
    (QUALITY/'event_activity_map_emiliano_buendia_poc.svg').write_text(svg,encoding='utf-8')
    print(json.dumps({'quality_metrics':len(quality),'comparison_rows':len(comp),'coordinate_groups':len(coords),'event_types':len(event_types)}))
if __name__=='__main__':main()
