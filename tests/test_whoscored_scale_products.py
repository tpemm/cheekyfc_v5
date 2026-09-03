from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]; MODEL=ROOT/'data/models/season_2526'

def read(name): return pd.read_csv(MODEL/name)

def test_scale_manifest_and_normalized_uniqueness():
    manifest=pd.read_csv(ROOT/'data/quality/season_2526/whoscored_acquisition_manifest_2526.csv')
    events=read('whoscored_event_scale_2526.csv'); advanced=read('advanced_player_match_scale_2526.csv')
    assert len(manifest)==30 and manifest.cache_valid.all()
    assert not events.duplicated(['canonical_match_id','event_id']).any()
    assert not advanced.duplicated(['canonical_match_id','canonical_player_id']).any()

def test_identity_persistence_and_meaningful_gate():
    identity=pd.read_csv(ROOT/'data/reference/whoscored_player_identity.csv'); lineup=read('whoscored_lineup_scale_2526.csv')
    meaningful=set(lineup.loc[lineup.started|lineup.sub_on_minute.notna(),'whoscored_player_id'].astype(int))
    assert identity.whoscored_player_id.is_unique
    assert identity[identity.whoscored_player_id.isin(meaningful)].mapping_status.eq('PROVEN').mean() >= .97

def test_manager_identity_tenures_and_context():
    managers=pd.read_csv(ROOT/'data/reference/manager_registry.csv'); tenures=pd.read_csv(ROOT/'data/reference/team_manager_tenures.csv'); team=read('whoscored_team_match_scale_2526.csv')
    assert managers.manager_id.is_unique and managers.normalized_name.is_unique
    assert team.manager_id.notna().all() and set(team.manager_id)<=set(managers.manager_id)
    assert tenures.confidence_status.eq('OBSERVED_RANGE_NOT_EXACT_TENURE_BOUNDARY').all()

def test_positions_formations_coordinates_and_missing_semantics():
    lineup=read('whoscored_lineup_scale_2526.csv'); team=read('whoscored_team_match_scale_2526.csv'); events=read('whoscored_event_scale_2526.csv'); advanced=read('advanced_player_match_scale_2526.csv')
    assert lineup.loc[lineup.started,'actual_position_standardized'].notna().mean() >= .95
    assert team.formation.notna().mean() >= .95
    assert events[['x','y']].stack().between(0,100).all() and events[['end_x','end_y']].stack().dropna().between(0,100).all()
    assert advanced.loc[advanced.fantrax_alignment.eq('AMBIGUOUS_MULTI_FIXTURE_PERIOD'),'fantrax_points'].isna().all()
    assert advanced.loc[advanced.understat_alignment.eq('EXACT_PLAYER_MATCH'),['xg','xa']].notna().all().all()

def test_quality_gates_pass():
    gates=pd.read_csv(ROOT/'data/quality/season_2526/whoscored_scale_readiness_gates_2526.csv')
    assert gates.passed.all()
