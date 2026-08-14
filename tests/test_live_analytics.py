import numpy as np
import pandas as pd

from core.services.data_manager import DataManager
from fantrax.live.analytics import build_live_manager_analytics, build_live_player_analytics, build_live_position_strength
from views.players import comparison_table, filter_players, sort_players


def fixtures():
    pool=pd.DataFrame([
        {"fantrax_player_id":"p1","fantrax_player_name":"Álvaro One","fantrax_current_team":"AAA","fantrax_position":"M,F","fantrax_adp":"10","fantrax_projected_points":"200"},
        {"fantrax_player_id":"p2","fantrax_player_name":"Blank ADP","fantrax_current_team":"BBB","fantrax_position":"D","fantrax_adp":"-","fantrax_projected_points":""},
    ])
    ownership=pd.DataFrame([
        {"fantrax_player_id":"p1","ownership_status":"Rostered","current_manager_id":"m1","current_manager_name":"Manager","available":False,"still_with_drafting_manager":True},
        {"fantrax_player_id":"p2","ownership_status":"Free Agent","available":True},
        {"fantrax_player_id":"roster-only","ownership_status":"Unresolved","current_manager_id":"m1","available":False},
    ])
    rankings=pd.DataFrame([{"fantrax_player_id":"p1","overall_rank":5,"draft_score":80,"fantrax_adp":10,"fantasy_points_2526":300,"minutes_2526":1800,"ghost_points_2526_authoritative":120,"understat_xg_2526":5,"understat_xa_2526":5,"understat_minutes_2526":1800,"projected_minutes_share":90}])
    draft=pd.DataFrame([{"fantrax_player_id":"p1","manager":"Manager","round":1,"overall_pick":1}])
    return pool,ownership,rankings,draft


def test_player_frame_preserves_identity_ownership_draft_and_missing_values():
    pool,ownership,rankings,draft=fixtures()
    result=build_live_player_analytics(pool,ownership,pd.DataFrame(),rankings,draft,pd.DataFrame())
    assert set(result.fantrax_player_id)=={"p1","p2","roster-only"}
    one=result.set_index("fantrax_player_id").loc["p1"]
    assert one.current_manager_id=="m1" and one.drafted_manager=="Manager" and one.fantrax_position=="M,F"
    assert result.set_index("fantrax_player_id").loc["p2","available"]
    assert pd.isna(result.set_index("fantrax_player_id").loc["p2","adp"])
    assert pd.isna(one.current_fantasy_points)


def test_filters_multi_position_free_agents_and_missing_last_sort():
    pool,ownership,rankings,draft=fixtures(); frame=build_live_player_analytics(pool,ownership,pd.DataFrame(),rankings,draft,pd.DataFrame())
    assert filter_players(frame,position="F").fantrax_player_id.tolist()==["p1"]
    assert filter_players(frame,ownership="Free Agent").fantrax_player_id.tolist()==["p2"]
    assert sort_players(frame,"adp",True).fantrax_player_id.iloc[-1] != "p1"
    assert sort_players(frame,"adp",False).fantrax_player_id.iloc[0] == "p1"


def test_manager_rates_are_weighted_missing_values_excluded_and_positions_unique():
    pool,ownership,rankings,draft=fixtures(); players=build_live_player_analytics(pool,ownership,pd.DataFrame(),rankings,draft,pd.DataFrame())
    teams=pd.DataFrame([{"season_id":"2627","manager_id":"m1","manager_name":"Manager","fantasy_team_id":"m1","fantasy_team_name":"Team"}])
    managers=build_live_manager_analytics(players,teams,pd.DataFrame(),pd.DataFrame(),draft)
    row=managers.iloc[0]
    assert row.roster_count==2 and row.average_adp==10 and row.draft_retention_percentage==100
    assert row.historical_points_per_90==15
    strength=build_live_position_strength(players,managers)
    assert strength.player_count.sum()==2


def test_comparison_has_exact_players_and_no_winner_column():
    pool,ownership,rankings,draft=fixtures(); frame=build_live_player_analytics(pool,ownership,pd.DataFrame(),rankings,draft,pd.DataFrame())
    result=comparison_table(frame,["p1","p2"])
    assert len(result.columns)==3 and "Winner" not in result.columns


def test_registered_live_presentation_datasets_resolve():
    manager=DataManager()
    for key in ("live_player_analytics","live_manager_analytics","live_position_strength","available_players"):
        assert manager.resolve_path(key,"2627").name.endswith("_2627.csv")
