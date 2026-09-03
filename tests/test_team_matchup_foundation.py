import pandas as pd
import numpy as np
from analytics.teams.matchup import assign_position_groups,build_player_matchup_features,build_position_fantasy_allowed,build_team_match_observations,build_team_matchup_features,build_team_profiles,primary_position,window_periods
from analytics.teams.fixtures import build_team_fixtures

def clubs():
    return pd.DataFrame({"canonical_club_id":["a","b"],"canonical_name":["Alpha","Beta"],"fantrax_code":["AAA","BBB"]})
def fixtures():
    rows=[]
    for period,date,home,away in [(1,"2026-08-22T12:00Z","a","b"),(2,"2026-08-29T12:00Z","b","a"),(3,"2026-09-05T12:00Z","a","b")]:
        rows.extend([{"match_id":f"m{period}","date":date[:10],"kickoff_time":date,"competition":"Premier League","competition_type":"league","status":"completed","fantrax_period":period,"completed":True,"club_id":home,"club":"Alpha" if home=="a" else "Beta","opponent_id":away,"opponent":"Beta" if away=="b" else "Alpha","home_away":"H","venue":"Home","goals_for":1,"goals_against":0},
                     {"match_id":f"m{period}","date":date[:10],"kickoff_time":date,"competition":"Premier League","competition_type":"league","status":"completed","fantrax_period":period,"completed":True,"club_id":away,"club":"Alpha" if away=="a" else "Beta","opponent_id":home,"opponent":"Beta" if home=="b" else "Alpha","home_away":"A","venue":"Away","goals_for":0,"goals_against":1}])
    return pd.DataFrame(rows)
def weekly():
    rows=[]
    for period in (1,2,3):
        for club,opponent in (("AAA","BBB"),("BBB","AAA")):
            for i,(pos,points) in enumerate((("G",4),("D,M",8),("M",10),("F",12))):
                rows.append({"season_id":"2627","period":period,"period_complete":True,"fantrax_player_id":f"{club}{i}","club":club,"opponent":opponent,"canonical_position":np.nan,"fantrax_position":pos,"fantasy_points":points,"ghost_points":points-2,"appearance":1,"start":1,"minutes":90,"goals":int(pos=="F"),"assists":0,"key_passes":1,"shots":2,"shots_on_target":1,"tackles_won":1,"interceptions":1,"clearances":1,"aerials_won":1,"xg":.2,"xa":.1,"xgi":.3})
    return pd.DataFrame(rows)

def test_primary_position_and_no_multi_position_duplication():
    assert [primary_position(x) for x in ("G","D,M","M/F","F",None)]==["GK","DEF","MID","FWD",None]
    assigned=assign_position_groups(weekly()); assert len(assigned)==len(weekly()) and set(assigned.position_group)=={"GK","DEF","MID","FWD"}

def test_windows_use_completed_periods_and_partial_labels():
    frame=weekly(); frame.loc[frame.period.eq(3),"period_complete"]=False
    complete=frame[frame.period_complete]; assert window_periods(complete,"Last 5")==([1,2],"Last 5 (2 available)")
    assert window_periods(complete,"Season")==([1,2],"Season")

def test_position_allowed_attribution_windows_venue_zeros_and_ranks():
    result=build_position_fantasy_allowed(weekly(),fixtures(),clubs())
    row=result[(result.club_id.eq("b"))&(result.position_group.eq("DEF"))&(result.window.eq("Season"))&(result.venue_split.eq("All"))].iloc[0]
    assert row.matches_observed==3 and row.fantrax_points_allowed==24 and row.points_allowed_per_match==8
    assert row.player_starts==3 and row.minutes==270 and row.points_allowed_per_90==8
    assert set(result.window)=={"Season","Last 3","Last 5","Last 10"} and {"Home","Away","All"}.issubset(result.venue_split.unique())

def test_incomplete_periods_are_excluded_and_missing_remains_missing():
    frame=weekly(); frame.loc[frame.period.eq(3),"period_complete"]=False; frame.loc[frame.index[0],"ghost_points"]=np.nan
    result=build_position_fantasy_allowed(frame,fixtures(),clubs()); assert result[result.window.eq("Season")].matches_observed.max()==2

def test_team_match_observations_attribute_opponents_and_provenance():
    result=build_team_match_observations(fixtures(),weekly(),clubs())
    assert len(result)==6 and set(result.feature_class)=={"observed"}; assert result.opponent_id.notna().all()
    assert result.fantasy_points_for.notna().all() and result.fantasy_points_allowed.notna().all()

def test_profiles_are_transparent_rates_not_scores():
    observations=build_team_match_observations(fixtures(),weekly(),clubs()); attack,defense=build_team_profiles(observations)
    assert len(attack)==2 and len(defense)==2 and "attack_score" not in attack and "defense_score" not in defense
    assert set(attack.feature_class)=={"derived"}

def test_matchup_frames_have_future_context_and_no_predictions():
    future=fixtures().copy(); future["completed"]=False; future["status"]="scheduled"
    team=build_team_matchup_features(future,pd.DataFrame(),pd.DataFrame(),now="2026-08-19T00:00Z")
    assert len(team)==6 and {"club_id","opponent_id","fantrax_period","congestion_scope","feature_class"}.issubset(team)
    players=pd.DataFrame({"fantrax_player_id":["p1","p2"],"premier_league_club":["AAA","BBB"],"canonical_position":["M",np.nan],"fantrax_position":["M","D,F"],"current_manager_name":["Owner",np.nan]})
    allowed=build_position_fantasy_allowed(weekly(),fixtures(),clubs())
    frame=build_player_matchup_features(players,future,allowed,clubs(),weekly(),now="2026-08-19T00:00Z")
    assert len(frame)==2 and frame.contains_prediction.eq(False).all(); assert frame.fixture_opponent_id.notna().all()
    assert set(frame.position_group)=={"MID","DEF"}

def test_preseason_inputs_create_honest_empty_observations():
    assert build_team_match_observations(fixtures(),pd.DataFrame(),clubs()).empty
    assert build_position_fantasy_allowed(pd.DataFrame(),fixtures(),clubs()).empty
