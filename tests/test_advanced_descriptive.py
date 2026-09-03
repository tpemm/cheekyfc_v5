"""Sprint 9.6 descriptive analytics and authority-boundary tests."""
from pathlib import Path
import pandas as pd
import pytest

from analytics.advanced_descriptive import reconcile_safe_metric,filter_pitch_events,apply_event_window,SUPPLEMENT_POLICY,canonical_venue,add_plot_coordinates

ROOT=Path(__file__).resolve().parents[1];ADV=ROOT/'data/models/season_2526/advanced';QUALITY=ROOT/'data/quality/season_2526'
def read(name):return pd.read_csv(ADV/f'{name}_2526.csv',low_memory=False)


def test_fantrax_non_null_and_zero_are_authoritative():
    d=pd.DataFrame({'mgr_kp':[4,0],'key_passes':[9,8],'fantrax_alignment':['EXACT_SINGLE_CLUB_MATCH_IN_PERIOD']*2})
    out=reconcile_safe_metric(d,'key_passes')
    assert out.key_passes.tolist()==[4,0] and out.key_passes_source.eq('FANTRAX').all()


def test_whoscored_only_fills_genuine_missing_and_keeps_provenance():
    d=pd.DataFrame({'mgr_kp':[pd.NA,7],'key_passes':[2,9],'fantrax_alignment':['EXACT_SINGLE_CLUB_MATCH_IN_PERIOD','AMBIGUOUS_MULTI_FIXTURE_PERIOD']})
    out=reconcile_safe_metric(d,'key_passes')
    assert out.key_passes.tolist()==[2,9] and out.key_passes_source.eq('WHOSCORED_SUPPLEMENT').all()


def test_unsafe_metrics_have_no_silent_reconciliation_policy():
    assert set(k for k,v in SUPPLEMENT_POLICY.items() if v['classification']=='SAFE_SUPPLEMENT')=={'key_passes','aerial_wins','interceptions'}
    assert SUPPLEMENT_POLICY['tackles']['classification']=='SOURCE_SPECIFIC_ONLY'
    assert SUPPLEMENT_POLICY['crosses']['classification']=='SOURCE_SPECIFIC_ONLY'


def test_supplemental_dataset_is_unique_and_role_is_not_fantrax_position():
    d=read('supplemental_player_match')
    assert len(d)==14677 and not d.duplicated(['canonical_match_id','canonical_player_id']).any()
    assert 'actual_tactical_role' in d and 'fantrax_position' not in d
    for metric in ('key_passes','aerial_wins','interceptions'):assert set(d[f'{metric}_source'])=={'FANTRAX','WHOSCORED_SUPPLEMENT'}


def test_profiles_use_transparent_denominators_and_missing_per90_stays_missing():
    p=read('player_advanced_profile')
    valid=p.minutes.gt(0)
    assert (p.loc[valid,'key_passes_per90'].round(8)==(p.loc[valid,'key_passes']*90/p.loc[valid,'minutes']).round(8)).all()
    assert p.loc[~valid,'key_passes_per90'].isna().all()


@pytest.mark.parametrize('layer,types',[('TakeOns',{'TakeOn'}),('Shots',{'MissedShots','SavedShot','ShotOnPost','Goal'}),('Defensive Actions',{'Tackle','Interception','Clearance','BlockedPass'}),('Recoveries',{'BallRecovery'}),('Aerials',{'Aerial'})])
def test_pitch_event_layer_filters(layer,types):
    e=pd.DataFrame({'event_type':['TakeOn','Goal','Tackle','BallRecovery','Aerial'],'qualifiers':['[]']*5,'is_key_pass':[False]*5})
    assert set(filter_pitch_events(e,layer).event_type)<=types


def test_pitch_pass_endpoints_and_windows_are_safe():
    e=pd.DataFrame({'canonical_match_id':['a','b'],'event_type':['Pass','Pass'],'qualifiers':['[]','[]'],'is_key_pass':[False,False],'x':[10,20],'y':[20,30],'end_x':[pd.NA,60],'end_y':[pd.NA,50]})
    m=pd.DataFrame({'canonical_match_id':['a','b'],'date':['2025-01-01','2025-01-02']})
    assert len(apply_event_window(filter_pitch_events(e,'Passes'),m,'Last 5'))==2
    assert e.loc[0,['end_x','end_y']].isna().all()


def test_canonical_venue_requires_match_orientation_and_preserves_unresolved():
    frame=pd.DataFrame({'canonical_match_id':['m1','m1','m2'],'club_id':['home','away','unknown'],'venue':['AWAY','HOME','HOME']})
    matches=pd.DataFrame({'canonical_match_id':['m1','m2'],'home_club_id':['home','home2'],'away_club_id':['away','away2']})
    out=canonical_venue(frame,matches)
    assert out.venue.tolist()==['HOME','AWAY',pd.NA]


def test_vertical_pitch_coordinates_preserve_raw_values_and_pass_geometry():
    events=pd.DataFrame({'x':[10.0],'y':[25.0],'end_x':[80.0],'end_y':[40.0]})
    out=add_plot_coordinates(events)
    assert out.loc[0,['x','y','end_x','end_y']].tolist()==[10.0,25.0,80.0,40.0]
    assert out.loc[0,['plot_x','plot_y','plot_end_x','plot_end_y']].tolist()==[75.0,10.0,60.0,80.0]


def test_historical_products_include_goals_and_assists():
    supplemental=read('supplemental_player_match'); profile=read('player_advanced_profile')
    assert {'goals','assists'}<=set(supplemental.columns)
    assert {'goals','assists','goals_per_match','assists_per_match'}<=set(profile.columns)
    assert supplemental.goals.notna().any() and supplemental.assists.notna().any()


def test_set_piece_semantics_windows_shares_ranks_and_ties():
    u=read('player_set_piece_usage')
    assert set(u.set_piece_type)=={'ALL_CORNERS','DIRECT_FREE_KICKS','SHORT_INDIRECT_FREE_KICKS','PENALTIES','SET_PIECE_KEY_PASSES','SET_PIECE_CROSSES'}
    assert {'SEASON','LAST_10','LAST_5','CURRENT_MANAGER_REGIME'}<=set(u.window)
    sums=u.groupby(['club_id','set_piece_type','window','manager_id'],dropna=False).player_share.sum()
    assert sums.between(.999999,1.000001).all()
    tied=u.groupby(['club_id','set_piece_type','window','manager_id','attempts'],dropna=False)['rank'].nunique();assert tied.eq(1).all()


def test_corner_side_is_not_claimed_without_orientation_evidence():
    import json
    result=json.loads((QUALITY/'corner_side_validation_2526.json').read_text())
    assert result['corners']==3785 and result['left_right_status']=='NOT_APPROVED'
    assert not read('player_set_piece_usage').set_piece_type.str.contains('LEFT|RIGHT').any()


def test_team_formation_fantasy_allowed_and_playstyle_products():
    roles=read('formation_player_usage');allowed=read('historical_fantasy_allowed_ranked');style=read('team_playstyle_profile')
    assert {'GK','DEF','MID','FWD'}==set(allowed.position_group) and len(allowed)==80
    assert allowed.matches.gt(0).all() and allowed.filter(like='_ease_rank').stack().between(1,20).all()
    assert roles.role_rank.ge(1).all() and style.matches.gt(0).all()
    assert not any('score' in c.casefold() for c in style.columns)


def test_build_is_cache_only():
    source=(ROOT/'scripts/build_advanced_descriptive_products.py').read_text(encoding='utf-8')
    assert 'requests' not in source and 'selenium' not in source and 'read_events(' not in source
