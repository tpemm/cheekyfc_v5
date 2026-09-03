from pathlib import Path
from uuid import uuid4
import pandas as pd
import pytest
from fantrax.live.unified_weekly import build_unified_weekly,current_fantasy_allowed,source_coverage
from fantrax.live.weekly_acquisition import all_player_url,commit_period,roster_url,validate_csv_response

def frames():
    fan=pd.DataFrame([
      {'fantrax_player_id':'p1','period':1,'player_name':'Rostered','club':'ARS','canonical_position':'M','current_manager_id':'t1','fantasy_points':0,'key_passes':0},
      {'fantrax_player_id':'p2','period':1,'player_name':'Waiver','club':'COV','canonical_position':'F','current_manager_id':pd.NA,'fantasy_points':8,'key_passes':pd.NA},
      {'fantrax_player_id':'p3','period':1,'player_name':'Unplayed','club':'CHE','canonical_position':'D','current_manager_id':pd.NA,'fantasy_points':pd.NA,'key_passes':pd.NA},])
    identity=pd.DataFrame([{'canonical_player_id':'c1','fantrax_player_id':'p1'},{'canonical_player_id':'c2','fantrax_player_id':'p2'}])
    advanced=pd.DataFrame([
      {'canonical_player_id':'c1','canonical_match_id':'m1','fantrax_period':1,'club_id':'arsenal','opponent_id':'coventry_city','key_passes':4,'aerials_won':2,'interceptions':1,'rating':7,'actual_position_standardized':'CM','formation':'4231','manager_name':'Arteta'},
      {'canonical_player_id':'c2','canonical_match_id':'m1','fantrax_period':1,'club_id':'coventry_city','opponent_id':'arsenal','key_passes':2,'aerials_won':1,'interceptions':0,'rating':6,'actual_position_standardized':'ST','formation':'4141','manager_name':'Lampard'}])
    understat=pd.DataFrame([{'fantrax_player_id':'p2','period':1,'xg':.4,'xa':.1,'xgi':.5,'understat_minutes':90}])
    clubs=pd.DataFrame([{'fantrax_code':'ARS','canonical_club_id':'arsenal'},{'fantrax_code':'COV','canonical_club_id':'coventry_city'},{'fantrax_code':'CHE','canonical_club_id':'chelsea'}])
    return fan,advanced,understat,identity,pd.DataFrame(),clubs

def test_fantrax_zero_wins_and_waiver_all_player_row_is_retained():
    result=build_unified_weekly(*frames()).set_index('fantrax_player_id')
    assert result.loc['p1','fantasy_points']==0 and result.loc['p1','key_passes']==0 and result.loc['p1','key_passes_source']=='FANTRAX_DETAILED'
    assert result.loc['p2','fantrax_detail_source']=='FANTRAX_ALL_PLAYER_ONLY' and result.loc['p2','fantasy_points']==8 and result.loc['p2','xgi']==.5
    assert pd.isna(result.loc['p3','fantasy_points'])

def test_exact_match_attribution_builds_fantasy_allowed_with_sample():
    result=build_unified_weekly(*frames());allowed=current_fantasy_allowed(result)
    waiver=allowed[(allowed.opponent_id=='arsenal')&(allowed.position_group=='FWD')].iloc[0]
    assert waiver.points_allowed==8 and waiver.matches==1 and waiver.sample_status=='1 observed match'

def test_dgw_ambiguity_is_excluded_not_split():
    values=list(frames());extra=values[1].iloc[[1]].copy();extra['canonical_match_id']='m2';values[1]=pd.concat([values[1],extra],ignore_index=True)
    result=build_unified_weekly(*values);row=result.set_index('fantrax_player_id').loc['p2']
    assert row.fantrax_match_attribution=='AMBIGUOUS_MULTI_FIXTURE_PERIOD'
    assert current_fantasy_allowed(result).query("opponent_id == 'arsenal' and position_group == 'FWD'").empty

def test_source_coverage_reports_combinations():
    coverage=source_coverage(build_unified_weekly(*frames()))
    assert coverage.players.sum()==3 and coverage.source_coverage.str.contains('FANTRAX_ALL_PLAYER_ONLY').any()

def test_html_login_response_is_rejected():
    with pytest.raises(ValueError,match='HTML/login'):validate_csv_response(b'<!doctype html><form>Login</form>',required={'ID'},label='all-player')

def test_partial_manager_commit_preserves_all_player_and_reports_coverage():
    root=Path('.test_artifacts')/f'unified-weekly-{uuid4().hex}';all_players=b'ID,Player,Team,Position,FPts\n*p1*,One,ARS,M,5\n';team=b'"","Outfielder"\nID,Pos,Player,Team,Fantasy Points\n*p1*,M,One,ARS,5\n'
    meta=commit_period(root,1,all_players,{'t1':('One',team)},finalized=False,expected_team_ids={'t1','t2'},team_failures={'t2':'timeout'},retrieved_at='2026-08-24T12:00:00Z')
    assert meta['status']=='PARTIAL_MANAGER_COVERAGE' and meta['maturity']=='LIVE' and meta['manager_exports_acquired']==1 and meta['all_player_rows']==1
    assert (root/'player_stats/period_01/snapshots/20260824T120000Z/all_players.csv').exists()

def test_current_period_urls_are_deterministic_and_team_id_driven():
    players=all_player_url('league',1,start_date='2026-08-21',end_date='2026-08-24');roster=roster_url('league',1,'registered-team')
    assert 'SEASON_926_BY_PERIOD' in players and 'transactionPeriod=1' in players and 'statusOrTeamFilter=ALL' in players
    assert 'period=1' in roster and 'statsType=1' in roster and 'teamId=registered-team' in roster

def test_current_league_has_twelve_unique_registered_team_ids():
    import json
    payload=json.loads(Path('data/raw/fantrax/2627/league/league_metadata_2627_latest.json').read_text(encoding='utf-8'))
    ids=[str(item.get('id') or key) for key,item in payload['teamInfo'].items()]
    assert len(ids)==12 and len(set(ids))==12 and all(ids)

def test_browser_locator_uses_stable_current_icon_attribute():
    source=Path('fantrax/live/weekly_acquisition.py').read_text(encoding='utf-8')
    assert 'button[mattooltip="Download all as CSV"]' in source and 'downloads_path' in source
