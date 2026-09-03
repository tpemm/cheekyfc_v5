#!/usr/bin/env python3
"""Build season-separated current WhoScored products from validated caches."""
from __future__ import annotations
import argparse,hashlib,json,re,sys,unicodedata
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from analytics.advanced_match_poc import normalize_match,normalize_lineups,normalize_events,build_advanced_player_match
from analytics.advanced_descriptive import add_plot_coordinates,canonical_venue
from integrations.whoscored.workflows import atomic_csv,atomic_json
from scripts.build_advanced_descriptive_products import player_profiles,set_piece_products
from fantrax.live.current_identity import normalized_name

def norm(value):return normalized_name(value)
def manager_id(name):return 'mgr:'+hashlib.sha1(norm(name).encode()).hexdigest()[:12]

def player_map(lineups:pd.DataFrame,season:str)->tuple[dict[int,str],pd.DataFrame]:
    identity_path=ROOT/'data/reference/whoscored_player_identity.csv';identity=pd.read_csv(identity_path)
    proven=identity.dropna(subset=['whoscored_player_id','canonical_player_id']).copy();pmap=dict(zip(pd.to_numeric(proven.whoscored_player_id).astype(int),proven.canonical_player_id.astype(str)))
    model=ROOT/f'data/models/season_{season}';clubs=pd.read_csv(model/f'premier_league_clubs_{season}.csv')
    current=pd.read_csv(model/f'current_player_weekly_{season}.csv',low_memory=False)
    current=current.merge(clubs[['canonical_club_id','fantrax_code']],left_on='club',right_on='fantrax_code',how='left');current['_name']=current.player_name.map(norm)
    current=current.drop_duplicates('fantrax_player_id',keep='last')
    additions=[]
    for row in lineups.drop_duplicates('whoscored_player_id').itertuples():
        pid=int(row.whoscored_player_id)
        if pid in pmap:continue
        hit=current[current['_name'].eq(norm(row.whoscored_player_name))&current.canonical_club_id.eq(row.club_id)]
        if len(hit)!=1:continue
        player=hit.iloc[0];canonical=str(player.get('registry_player_id') or '').strip()
        if not canonical or canonical.lower()=='nan':canonical='FTX-'+str(player.fantrax_player_id).upper()
        pmap[pid]=canonical;additions.append({'whoscored_player_id':pid,'whoscored_player_name':row.whoscored_player_name,'canonical_player_id':canonical,'fantrax_player_id':player.fantrax_player_id,'understat_player_id':player.get('understat_player_id'),'canonical_club_id':row.club_id,'season':season,'mapping_method':'exact normalized name + current canonical club','mapping_status':'PROVEN','mapping_confidence':'HIGH','unresolved_reason':pd.NA,'provenance':'current WhoScored lineup + current Fantrax identity'})
    if additions:
        identity=pd.concat([identity,pd.DataFrame(additions)],ignore_index=True).drop_duplicates('whoscored_player_id',keep='last');atomic_csv(identity,identity_path)
    return pmap,pd.DataFrame(additions)

def main(season:str='2627')->int:
    manifest=pd.read_csv(ROOT/f'data/reference/whoscored_season_manifest_{season}.csv');payloads=[]
    for row in manifest.dropna(subset=['whoscored_match_id']).itertuples():
        wsid=int(row.whoscored_match_id);raw=ROOT/f'data/raw/whoscored/{season}/poc/match_{wsid}/raw_match.json'
        if raw.exists():payloads.append((row,json.loads(raw.read_text(encoding='utf-8'))))
    if not payloads:raise SystemExit('no validated current-season cache')
    raw_lineups=[]
    for row,payload in payloads:
        c={'canonical_match_id':row.canonical_match_id,'whoscored_match_id':int(row.whoscored_match_id),'date':row.date,'home_club_id':row.home_club_id,'away_club_id':row.away_club_id};raw_lineups.append(normalize_lineups(payload,c))
    pmap,additions=player_map(pd.concat(raw_lineups,ignore_index=True),season)
    matches=[];lineups=[];events=[];team_rows=[];manager_rows=[]
    for row,payload in payloads:
        meta=json.loads((ROOT/f'data/raw/whoscored/{season}/poc/match_{int(row.whoscored_match_id)}/metadata.json').read_text(encoding='utf-8'));c={'canonical_match_id':row.canonical_match_id,'whoscored_match_id':int(row.whoscored_match_id),'date':row.date,'home_club_id':row.home_club_id,'away_club_id':row.away_club_id,'retrieved_at':meta.get('retrieved_at')}
        match=normalize_match(payload,c);matches.append(match);lineup=normalize_lineups(payload,c);lineup['canonical_player_id']=pd.to_numeric(lineup.whoscored_player_id).map(pmap);lineups.append(lineup);events.append(normalize_events(payload,c,pmap))
        for side,opp,venue in [('home','away','H'),('away','home','A')]:
            name=payload[side].get('managerName');manager=manager_id(name);formation=match.get(f'{side}_formation');team_rows.append({'canonical_match_id':row.canonical_match_id,'date':row.date,'club_id':getattr(row,f'{side}_club_id'),'opponent_id':getattr(row,f'{opp}_club_id'),'venue':venue,'manager_id':manager,'manager_name':name,'formation':formation,'matches':1,'formation_share':1.0});manager_rows.append({'manager_id':manager,'manager_name':name,'club_id':getattr(row,f'{side}_club_id'),'canonical_match_id':row.canonical_match_id,'date':row.date,'source':'WhoScored observed match payload'})
    match=pd.DataFrame(matches);lineup=pd.concat(lineups,ignore_index=True);event=pd.concat(events,ignore_index=True);team=pd.DataFrame(team_rows);managers=pd.DataFrame(manager_rows)
    fixtures=pd.read_csv(ROOT/f'data/models/season_{season}/team_matches_{season}.csv')
    period_column=next((column for column in ('fantrax_period','gameweek','period','gw') if column in fixtures),None)
    fixture_id_column=next((column for column in ('canonical_match_id','match_id') if column in fixtures),None)
    period_by_match=dict(zip(fixtures[fixture_id_column].astype(str),pd.to_numeric(fixtures[period_column],errors='coerce'))) if period_column and fixture_id_column else {}
    advanced=build_advanced_player_match(lineup[lineup.canonical_player_id.notna()],event[event.canonical_player_id.notna()]);advanced=canonical_venue(advanced,match);advanced=advanced.merge(match[['canonical_match_id','date']],on='canonical_match_id',how='left').merge(team[['canonical_match_id','club_id','manager_id','manager_name']],on=['canonical_match_id','club_id'],how='left');advanced['fantrax_period']=advanced.canonical_match_id.astype(str).map(period_by_match).astype('Int64');advanced['fantrax_alignment']='CURRENT_FANTRAX_MATCH_STATS_UNAVAILABLE';advanced['understat_alignment']='CURRENT_UNDERSTAT_MATCH_STATS_UNAVAILABLE';advanced['fantrax_points']=pd.NA;advanced['ghost_points']=pd.NA;advanced['xg']=pd.NA;advanced['xa']=pd.NA;advanced['xgi']=pd.NA
    supplemental=advanced.rename(columns={'actual_position_standardized':'actual_tactical_role','aerials_attempted':'aerial_attempts','aerials_won':'aerial_wins','crosses':'raw_crosses'}).copy();supplemental['assists']=event[event.is_assist.fillna(False)].groupby(['canonical_match_id','canonical_player_id']).size().reindex(pd.MultiIndex.from_frame(supplemental[['canonical_match_id','canonical_player_id']])).to_numpy();supplemental['assists']=supplemental.assists.fillna(0)
    # Provider-supported B1 semantics. These remain separate from raw attempts
    # and Fantrax fantasy assists.
    eq=event.qualifiers.astype('string');semantic=event.assign(
        cross_attempt=event.event_type.eq('Pass')&eq.str.contains('"Cross"',na=False),
        cross_successful=event.event_type.eq('Pass')&eq.str.contains('"Cross"',na=False)&event.outcome.eq('Successful'),
        tackle_attempt=event.event_type.eq('Tackle'),tackle_successful=event.event_type.eq('Tackle')&event.outcome.eq('Successful'),
        official_assist=eq.str.contains('"IntentionalGoalAssist"',na=False),
    ).groupby(['canonical_match_id','canonical_player_id'],as_index=False).agg(cross_attempts=('cross_attempt','sum'),accurate_crosses_derived=('cross_successful','sum'),tackle_attempts=('tackle_attempt','sum'),tackles_won_derived=('tackle_successful','sum'),official_assists=('official_assist','sum'))
    supplemental=supplemental.merge(semantic,on=['canonical_match_id','canonical_player_id'],how='left',validate='one_to_one')
    for column in ('cross_attempts','accurate_crosses_derived','tackle_attempts','tackles_won_derived','official_assists'):supplemental[column]=supplemental[column].fillna(0);supplemental[f'{column}_source']='WHOSCORED_DERIVED_VALIDATED' if column not in ('cross_attempts','tackle_attempts','official_assists') else 'WHOSCORED_SOURCE_SPECIFIC'
    identity=pd.read_csv(ROOT/'data/reference/whoscored_player_identity.csv');fan=dict(zip(identity.canonical_player_id.astype(str),identity.fantrax_player_id.astype(str)));supplemental['fantrax_player_id']=supplemental.canonical_player_id.astype(str).map(fan)
    current_path=ROOT/f'data/models/season_{season}/current_player_weekly_{season}.csv';current=pd.read_csv(current_path,low_memory=False) if current_path.exists() else pd.DataFrame()
    if not current.empty:
        current['fantrax_player_id']=current.fantrax_player_id.astype(str);current['fantrax_period']=pd.to_numeric(current.period,errors='coerce')
        keep=['fantrax_player_id','fantrax_period','fantasy_points','ghost_points','key_passes','aerials_won','interceptions','current_manager_id'];facts=current.reindex(columns=keep).drop_duplicates(['fantrax_player_id','fantrax_period'],keep='last').rename(columns={x:f'fantrax_{x}' for x in ('fantasy_points','ghost_points','key_passes','aerials_won','interceptions')})
        supplemental=supplemental.merge(facts,on=['fantrax_player_id','fantrax_period'],how='left',validate='many_to_one')
        detailed=supplemental.current_manager_id.notna()
        supplemental['fantrax_points']=pd.to_numeric(supplemental.fantrax_fantasy_points,errors='coerce');supplemental['ghost_points']=pd.to_numeric(supplemental.fantrax_ghost_points,errors='coerce')
        for metric in ('key_passes','aerial_wins','interceptions'):
            fantrax_column={'key_passes':'fantrax_key_passes','aerial_wins':'fantrax_aerials_won','interceptions':'fantrax_interceptions'}[metric];fantrax_values=pd.to_numeric(supplemental[fantrax_column],errors='coerce').where(detailed);ws_values=pd.to_numeric(supplemental.get(metric),errors='coerce')
            supplemental[metric]=fantrax_values.combine_first(ws_values);supplemental[f'{metric}_source']=fantrax_values.notna().map({True:'FANTRAX',False:'WHOSCORED_CURRENT_OBSERVED'})
        supplemental['fantrax_alignment']=detailed.map({True:'EXACT_PLAYER_PERIOD_DETAILED',False:'NO_DETAILED_FANTRAX_ROW'})
    else:
        for metric in ('key_passes','aerial_wins','interceptions'):supplemental[f'{metric}_source']='WHOSCORED_CURRENT_OBSERVED'
    understat_path=ROOT/f'data/models/season_{season}/understat_player_match_{season}.csv';understat=pd.read_csv(understat_path,low_memory=False) if understat_path.exists() else pd.DataFrame()
    if not understat.empty:
        us=understat[understat.fantrax_player_id.notna()][['canonical_match_id','fantrax_player_id','xg','xa','xgi']].copy();us.fantrax_player_id=us.fantrax_player_id.astype(str)
        supplemental=supplemental.drop(columns=['xg','xa','xgi'],errors='ignore').merge(us,on=['canonical_match_id','fantrax_player_id'],how='left',validate='one_to_one');supplemental['understat_alignment']=supplemental.xg.notna().map({True:'EXACT_PLAYER_MATCH',False:'UNRESOLVED'})
    event['dataset_label']='EVENT_ACTIVITY_NOT_TRACKING'
    profile,roles=player_profiles(supplemental);sp_usage,sp_hierarchy,corner=set_piece_products(event,team)
    starts=roles.copy();formation_usage=starts.groupby(['club_id','manager_id','formation','actual_tactical_role','canonical_player_id'],dropna=False).role_starts.sum().reset_index();formation_usage['role_rank']=formation_usage.groupby(['club_id','manager_id','formation','actual_tactical_role'],dropna=False).role_starts.rank(method='dense',ascending=False).astype('Int64')
    e=event.copy();typ=e.event_type.astype(str);e['cross']=e.qualifiers.str.contains('Cross',case=False,na=False);e['through_ball']=e.qualifiers.str.contains('Throughball',case=False,na=False);e['take_on']=typ.eq('TakeOn');e['aerial_event']=typ.eq('Aerial');e['tackle_event']=typ.eq('Tackle');e['interception_event']=typ.eq('Interception');e['clearance_event']=typ.eq('Clearance');e['recovery_event']=typ.eq('BallRecovery');e['shot_on_target']=typ.isin(['SavedShot','Goal']);e['progressive_pass_distance_proxy']=(pd.to_numeric(e.end_x,errors='coerce')-pd.to_numeric(e.x,errors='coerce')).clip(lower=0).where(e.pass_attempted,0);e['final_third_entry']=e.pass_attempted&pd.to_numeric(e.x,errors='coerce').lt(66.67)&pd.to_numeric(e.end_x,errors='coerce').ge(66.67);e['box_entry']=e.pass_attempted&pd.to_numeric(e.end_x,errors='coerce').ge(83)&pd.to_numeric(e.end_y,errors='coerce').between(21.1,78.9)
    features=e.groupby(['canonical_match_id','club_id'],as_index=False).agg(passes_attempted=('pass_attempted','sum'),passes_completed=('pass_completed','sum'),progressive_pass_distance_proxy=('progressive_pass_distance_proxy','sum'),final_third_entries=('final_third_entry','sum'),box_entries=('box_entry','sum'),crosses=('cross','sum'),through_balls=('through_ball','sum'),shots=('is_shot','sum'),shots_on_target=('shot_on_target','sum'),key_passes=('is_key_pass','sum'),take_ons=('take_on','sum'),aerial_player_events=('aerial_event','sum'),tackles=('tackle_event','sum'),interceptions=('interception_event','sum'),clearances=('clearance_event','sum'),recoveries=('recovery_event','sum'));features=features.merge(team,on=['canonical_match_id','club_id'],how='left');features['feature_class']='observed_or_transparently_derived';features['contains_prediction']=False
    metrics=['passes_attempted','passes_completed','progressive_pass_distance_proxy','final_third_entries','box_entries','crosses','through_balls','shots','shots_on_target','key_passes','take_ons','aerial_player_events','tackles','interceptions','clearances','recoveries'];playstyle=features.groupby(['club_id','manager_id','manager_name','formation'],dropna=False).agg(matches=('canonical_match_id','nunique'),**{f'{x}_per_match':(x,'mean') for x in metrics}).reset_index();playstyle['scope']='OBSERVED_MANAGER_FORMATION'
    names=lineup.dropna(subset=['canonical_player_id']).drop_duplicates('canonical_player_id')[['canonical_player_id','whoscored_player_name']].rename(columns={'whoscored_player_name':'player_name'})
    for frame in (supplemental,profile,roles,sp_usage,sp_hierarchy,formation_usage):
        if 'canonical_player_id' in frame and 'player_name' not in frame:frame[names.columns[1]]=frame.canonical_player_id.map(dict(zip(names.canonical_player_id,names.player_name)))
    pitch=add_plot_coordinates(event);out=ROOT/f'data/models/season_{season}/advanced';quality=ROOT/f'data/quality/season_{season}';out.mkdir(parents=True,exist_ok=True);quality.mkdir(parents=True,exist_ok=True)
    advanced=supplemental.copy()
    products={'whoscored_match':match,'whoscored_lineup':lineup,'whoscored_event':event,'player_event_data':event,'advanced_player_match':advanced,'supplemental_player_match':supplemental,'player_advanced_profile':profile,'player_role_usage':roles,'player_set_piece_usage':sp_usage,'team_set_piece_hierarchy':sp_hierarchy,'team_formation_history':team,'team_formation_profile':team,'formation_player_usage':formation_usage,'team_match_features':features,'team_playstyle_profile':playstyle}
    for key,frame in products.items():atomic_csv(frame,out/f'{key}_{season}.csv')
    temp=out/f'player_pitch_events_{season}.parquet.tmp';pitch.to_parquet(temp,index=False,compression='zstd');temp.replace(out/f'player_pitch_events_{season}.parquet')
    atomic_csv(managers,ROOT/f'data/reference/manager_observations_{season}.csv');coverage=float(lineup.canonical_player_id.notna().mean());report={'matches':len(match),'lineups':len(lineup),'events':len(event),'advanced_player_match_rows':len(advanced),'pitch_rows':len(pitch),'mapped_lineup_rows':int(lineup.canonical_player_id.notna().sum()),'lineup_rows':len(lineup),'player_identity_coverage':coverage,'new_player_mappings':len(additions),'formation_coverage':float(team.formation.notna().mean()),'rating_coverage':float(pd.to_numeric(lineup.rating,errors='coerce').notna().mean()),'coordinate_coverage':float(event[['x','y']].notna().all(axis=1).mean()),'set_piece_rows':len(sp_usage),'team_match_feature_rows':len(features),'playstyle_rows':len(playstyle),'fantasy_allowed_status':'UNAVAILABLE_NO_CURRENT_MATCH_ATTRIBUTABLE_FANTRAX_POINTS','playstyle_status':'CURRENT_OBSERVED'};atomic_json(report,quality/f'whoscored_live_quality_{season}.json');atomic_json(corner,quality/f'corner_side_validation_{season}.json');print(json.dumps(report,indent=2));return 0
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--season',default='2627');a=p.parse_args();raise SystemExit(main(a.season))
