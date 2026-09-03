import json
import pandas as pd
import pytest
from pathlib import Path
from analytics.advanced_match_poc import (
    safe_write_raw, normalize_match, normalize_lineups, normalize_events,
    map_provider_players, standardize_role, attach_manager,
    aggregate_event_metrics, build_advanced_player_match,
)

@pytest.fixture
def payload():
    return {"score":"1 : 0","home":{"teamId":1,"formations":[{"formationName":"4231","playerIds":[10],"formationSlots":[7],"captainPlayerId":10}],"players":[{"playerId":10,"position":"AMC","isFirstEleven":True,"stats":{"ratings":{"90":7.4}}}]},
      "away":{"teamId":2,"formations":[{"formationName":"433","playerIds":[20],"formationSlots":[0]}],"players":[{"playerId":20,"position":"Mystery","isFirstEleven":False}]},
      "events":[
       {"id":1,"teamId":1,"playerId":10,"minute":4,"type":{"displayName":"Pass"},"outcomeType":{"displayName":"Successful"},"x":40,"y":50,"endX":70,"endY":40,"isKeyPass":True,"qualifiers":[{"type":{"displayName":"Cross"},"value":"x"}]},
       {"id":2,"teamId":1,"playerId":10,"minute":5,"type":{"displayName":"TakeOn"},"outcomeType":{"displayName":"Successful"},"qualifiers":[]},
       {"id":3,"teamId":1,"playerId":10,"minute":6,"type":{"displayName":"Aerial"},"outcomeType":{"displayName":"Unsuccessful"},"qualifiers":[]},
       {"id":4,"teamId":1,"playerId":10,"minute":7,"type":{"displayName":"Tackle"},"outcomeType":{"displayName":"Successful"},"qualifiers":[]},
       {"id":5,"teamId":1,"playerId":10,"minute":8,"type":{"displayName":"Interception"},"outcomeType":{"displayName":"Successful"},"qualifiers":[]},
       {"id":6,"teamId":1,"playerId":10,"minute":9,"type":{"displayName":"Goal"},"outcomeType":{"displayName":"Successful"},"x":88,"y":50,"qualifiers":[]}]}

@pytest.fixture
def context(): return {"canonical_match_id":"understat:1","whoscored_match_id":99,"date":"2026-05-24","home_club_id":"MCI","away_club_id":"AVL","retrieved_at":"now"}

def test_raw_preservation_and_empty_cannot_overwrite(payload):
    p=Path('.test_artifacts/advanced_match_raw.json'); p.parent.mkdir(exist_ok=True)
    try:
        checksum=safe_write_raw(payload,p,force=True); original=p.read_bytes()
        with pytest.raises(ValueError): safe_write_raw({},p,force=True)
        assert p.read_bytes()==original and len(checksum)==64
    finally:
        p.unlink(missing_ok=True)

def test_match_lineup_formation_role_and_substitution(payload,context):
    match=normalize_match(payload,context); lineups=normalize_lineups(payload,context)
    assert match['home_formation']=='4231' and match['home_score']==1
    assert lineups.actual_position_raw.tolist()==['AMC','Mystery']
    assert lineups.actual_position_standardized.iloc[0]=='CAM' and pd.isna(lineups.actual_position_standardized.iloc[1])
    assert lineups.started.tolist()==[True,False] and pd.isna(lineups.sub_on_minute.iloc[0])

def test_event_outcome_qualifiers_coordinates_and_metrics(payload,context):
    events=normalize_events(payload,context,{10:'P10'}); totals=aggregate_event_metrics(events).iloc[0]
    assert json.loads(events.iloc[0].qualifiers)[0]['value']=='x'
    assert (events.iloc[0][['x','y','end_x','end_y']].tolist()==[40,50,70,40])
    assert totals.key_passes==1 and totals.crosses==1 and totals.passes_attempted==1 and totals.passes_completed==1
    assert totals.dribbles_attempted==1 and totals.dribbles_successful==1
    assert totals.aerials_attempted==1 and totals.aerials_won==0
    assert totals.tackles==1 and totals.interceptions==1 and totals.shots==1 and totals.shots_on_target==1

def test_explicit_player_identity_only(payload,context):
    lineups=normalize_lineups(payload,context); registry=pd.DataFrame({'whoscored_player_id':[10],'registry_player_id':['P10']})
    mapped=map_provider_players(lineups,registry)
    assert mapped.canonical_player_id.tolist()[0]=='P10' and pd.isna(mapped.canonical_player_id.iloc[1])
    assert mapped.player_mapping_method.tolist()==['explicit_crosswalk','unresolved']

def test_duplicate_names_cannot_cross_map(payload,context):
    lineups=normalize_lineups(payload,context); lineups['player_name']='Same'
    registry=pd.DataFrame({'whoscored_player_id':[30,40],'registry_player_id':['A','B'],'whoscored_player_name':['Same','Same']})
    assert map_provider_players(lineups,registry).canonical_player_id.isna().all()

def test_manager_tenure_boundary():
    matches=pd.DataFrame([{'date':'2026-01-01','home_club_id':'A','away_club_id':'B'}])
    tenures=pd.DataFrame([{'manager_id':'OLD','canonical_club_id':'A','tenure_start':'2025-01-01','tenure_end':'2025-12-31'}, {'manager_id':'NEW','canonical_club_id':'A','tenure_start':'2026-01-01','tenure_end':pd.NA}])
    assert attach_manager(matches,tenures).iloc[0].home_manager_id=='NEW'

def test_advanced_one_row_per_player_match_and_no_prediction(payload,context):
    lineups=map_provider_players(normalize_lineups(payload,context),pd.DataFrame({'whoscored_player_id':[10,20],'registry_player_id':['P10','P20']}))
    events=normalize_events(payload,context,{10:'P10'}); out=build_advanced_player_match(lineups,events)
    assert len(out)==2 and not out.duplicated(['canonical_match_id','canonical_player_id']).any()
    assert out.contains_prediction.eq(False).all()

def test_role_taxonomy_is_conservative():
    assert standardize_role('LCB')=='LCB' and pd.isna(standardize_role('left-ish'))

def test_real_cached_match_schema_and_semantics():
    p=Path('data/raw/whoscored/2526/poc/match_29140/raw_match.json')
    if not p.exists(): pytest.skip('real POC cache not present')
    raw=json.loads(p.read_text(encoding='utf-8')); context={"canonical_match_id":"understat:29140","whoscored_match_id":1903446,"home_club_id":"aston_villa","away_club_id":"liverpool"}
    match=normalize_match(raw,context); lineup=normalize_lineups(raw,context); events=normalize_events(raw,context,{102248:'FTX-02LZ0'})
    assert len(events)==1374 and len(lineup)==40
    assert (match['home_score'],match['away_score'],match['home_formation'],match['away_formation'])==(4,2,'4231','4231')
    assert lineup.started.sum()==22 and lineup.rating.notna().sum()==29
    assert events.qualifiers.str.contains('KeyPass').sum()==23
    assert events[['x','y']].max().max()<=100 and events[['x','y']].min().min()>=0
    assert events.loc[events.event_type.eq('ShotOnPost'),'is_shot'].all()
    assert aggregate_event_metrics(events).shots_on_target.sum()==20

def test_all_eight_real_caches_hashes_and_provider_ids():
    import hashlib
    manifest=pd.read_csv('data/reference/advanced_match_poc_sample_2526.csv')
    assert len(manifest)==8 and manifest.resolution_status.eq('RESOLVED').all()
    for row in manifest.itertuples():
        base=Path(f'data/raw/whoscored/2526/poc/match_{row.understat_match_id}')
        raw=base/'raw_match.json'; meta=json.loads((base/'metadata.json').read_text())
        assert raw.exists() and meta['whoscored_match_id']==row.whoscored_match_id
        assert hashlib.sha256(raw.read_bytes()).hexdigest()==meta['checksum']

def test_multimatch_event_identity_and_semantics():
    e=pd.read_csv('data/models/season_2526/whoscored_event_poc_2526.csv')
    assert len(e)==11890 and not e.duplicated(['whoscored_match_id','event_id']).any() and not e.duplicated().any()
    assert e.is_key_pass.sum()==172 and e.loc[e.is_key_pass,'qualifiers'].str.contains('KeyPass').all()
    assert e[e.event_type.eq('TakeOn')].outcome.value_counts().to_dict()=={'Unsuccessful':156,'Successful':114}
    assert e[e.event_type.eq('Aerial')].outcome.value_counts().to_dict()=={'Successful':181,'Unsuccessful':181}
    assert e.event_type.value_counts()[['Tackle','Interception','Clearance','BallRecovery','BlockedPass']].to_dict()=={'Tackle':257,'Interception':137,'Clearance':365,'BallRecovery':607,'BlockedPass':112}
    assert e[e.event_type.eq('Pass')].outcome.isin(['Successful','Unsuccessful']).all()
    assert e.qualifiers.str.contains('Cross',case=False).sum()>0
    assert e[e.is_shot].event_type.value_counts().to_dict()=={'SavedShot':121,'MissedShots':68,'Goal':28,'ShotOnPost':8}
    assert e[['x','y']].min().min()>=0 and e[['x','y']].max().max()<=100

def test_multimatch_lineup_formation_rating_substitution_and_roles():
    l=pd.read_csv('data/models/season_2526/whoscored_lineup_poc_2526.csv');m=pd.read_csv('data/models/season_2526/whoscored_match_poc_2526.csv')
    assert len(l)==320 and l.started.sum()==176 and ((~l.started)&l.sub_on_minute.isna()).sum()==76
    assert l.sub_on_minute.notna().sum()==68 and l.sub_off_minute.notna().sum()==68 and l.rating.notna().sum()==244
    assert set(pd.concat([m.home_formation,m.away_formation]))=={4231,352,442,3421,4222}
    assert set(l.actual_position_raw)=={'Sub','DC','DMC','FW','GK','AMC','DR','DL','AMR','AML','MC','DMR','DML','MR','ML'}
    assert l.loc[l.actual_position_raw.ne('Sub'),'actual_position_standardized'].notna().all()

def test_multimatch_team_player_and_advanced_identity_safety():
    teams=pd.read_csv('data/reference/whoscored_team_crosswalk_poc_2526.csv');players=pd.read_csv('data/reference/whoscored_player_crosswalk_poc_2526.csv');a=pd.read_csv('data/models/season_2526/advanced_player_match_poc_2526.csv')
    assert teams.whoscored_team_id.nunique()==11 and teams.mapping_status.eq('PROVEN').all()
    assert players.mapping_status.eq('PROVEN').sum()==231 and players.whoscored_player_id.is_unique
    assert players.loc[players.whoscored_player_id.eq(102248),'registry_player_id'].iloc[0]=='FTX-02LZ0'
    assert len(a)==319 and not a.duplicated(['canonical_match_id','canonical_player_id']).any() and a.contains_prediction.eq(False).all()
    assert a.fantrax_points.notna().sum()==319 and a.xg.notna().sum()==240
    assert a.loc[a.xg.isna(),'understat_alignment'].eq('UNRESOLVED').all()
    assert a[['key_passes','dribbles_attempted','aerials_attempted','tackles']].notna().all().all()

def test_multimatch_coordinate_orientation():
    c=pd.read_csv('data/quality/season_2526/whoscored_coordinate_orientation_poc.csv')
    assert len(c)==32 and c.orientation_supports_left_to_right.all()
