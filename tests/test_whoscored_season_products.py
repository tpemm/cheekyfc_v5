"""Offline acceptance tests for the complete Sprint 9.5 historical layer."""
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];ADV=ROOT/'data/models/season_2526/advanced';QUALITY=ROOT/'data/quality/season_2526'
def read(name):return pd.read_csv(ADV/f'{name}_2526.csv')

def test_complete_raw_and_match_identity():
    raw=pd.read_csv(QUALITY/'whoscored_raw_cache_validation_2526.csv');matches=read('whoscored_match')
    assert len(raw)==380 and raw.classification.eq('VALID').all()
    assert len(matches)==380 and matches.canonical_match_id.is_unique and matches.whoscored_match_id.is_unique
    assert len(set(matches.home_club_id)|set(matches.away_club_id))==20

def test_event_identity_coordinates_and_proven_semantics():
    event=read('whoscored_event')
    assert not event.duplicated(['canonical_match_id','event_id']).any()
    assert event[['x','y']].stack().between(0,100).all() and event[['end_x','end_y']].stack().dropna().between(0,100).all()
    assert event.loc[event.is_key_pass.eq(True),'qualifiers'].str.contains('KeyPass',case=False).all()
    assert {'TakeOn','Aerial','Tackle','Interception','Clearance','BallRecovery','Pass','MissedShots','SavedShot','ShotOnPost','Goal'}-set(event.event_type)==set()
    assert event.loc[event.pass_completed.eq(True),'pass_attempted'].all()

def test_lineups_roles_ratings_formations_and_managers():
    lineup=read('whoscored_lineup');teams=read('team_formation_history');transitions=pd.read_csv(QUALITY/'whoscored_manager_transitions_2526.csv')
    assert lineup.groupby('canonical_match_id').started.sum().eq(22).mean()>=.95
    assert lineup.loc[lineup.started.eq(True),'actual_position_standardized'].notna().mean()>=.95
    assert lineup.loc[lineup.rating.notna(),'rating'].between(0,10).all()
    assert teams.formation.notna().mean()>=.95 and teams.manager_id.notna().mean()>=.95
    assert transitions.transition_observed.any()

def test_identity_and_advanced_uniqueness_authority_and_missing_semantics():
    lineup=read('whoscored_lineup');advanced=read('advanced_player_match');identity=pd.read_csv(ROOT/'data/reference/whoscored_player_identity.csv')
    meaningful=set(lineup.loc[lineup.started.eq(True)|lineup.sub_on_minute.notna(),'whoscored_player_id'].astype(int));mapped=identity[identity.whoscored_player_id.isin(meaningful)]
    assert mapped.mapping_status.eq('PROVEN').mean()>=.97 and identity.whoscored_player_id.is_unique
    assert not advanced.duplicated(['canonical_match_id','canonical_player_id']).any()
    ambiguous=advanced.fantrax_alignment.eq('AMBIGUOUS_MULTI_FIXTURE_PERIOD');assert advanced.loc[ambiguous,['fantrax_points','fantrax_ghost_points']].isna().all().all()
    exact=advanced.understat_alignment.eq('EXACT_PLAYER_MATCH');assert advanced.loc[exact,['xg','xa','xgi']].notna().all().all()
    assert advanced.loc[advanced.key_passes.eq(0),'key_passes'].notna().all()

def test_role_formation_team_and_position_products():
    roles=read('player_match_roles');profile=read('player_role_profile');formations=read('team_formation_profile');features=read('team_match_features');allowed=read('historical_position_fantasy_allowed')
    assert roles.started.all() and roles.actual_position_standardized.notna().mean()>=.95
    assert profile.role_share.between(0,1).all() and formations.formation_share.between(0,1).all()
    assert not features.duplicated(['canonical_match_id','club_id']).any() and len(features)==760
    assert set(allowed.position_group)=={'GK','DEF','MID','FWD'} and allowed.fantrax_authority.all()

def test_season_quality_gates_and_refresh_status():
    gates=pd.read_csv(QUALITY/'whoscored_season_quality_gates_2526.csv');status=pd.read_csv(QUALITY/'refresh_status_2526.csv')
    assert gates.passed.all()
    advanced=status[status.area.eq('WhoScored Advanced')].iloc[0]
    assert advanced.state=='Complete' and advanced.coverage=='380/380'
