import numpy as np
import pandas as pd

from fantrax.live.analytics import build_live_manager_analytics, expected_record
from fantrax.live.pipeline import _manager_week_summary
from views.live_managers import WINDOWS, manager_squad, manager_week_window


def teams():
    return pd.DataFrame([
        {"season_id":"2627","manager_id":"m1","manager_name":"Alpha","fantasy_team_id":"t1","fantasy_team_name":"Alpha FC","draft_slot":1},
        {"season_id":"2627","manager_id":"m2","manager_name":"Beta","fantasy_team_id":"t2","fantasy_team_name":"Beta FC","draft_slot":2},
    ])


def players():
    return pd.DataFrame([
        {"season_id":"2627","fantrax_player_id":"p1","current_manager_id":"m1","still_with_drafting_manager":True,"historical_fantasy_points":100,"historical_ghost_points":50,"historical_xgi":5,"historical_minutes":900,"understat_minutes_2526":900,"current_fantasy_points":20,"current_ghost_points":10,"current_xgi":1,"current_minutes":180,"current_starts":2,"current_appearances":2,"fantrax_projected_points":200,"lineup_status":"ACTIVE","roster_status":"ACTIVE"},
        {"season_id":"2627","fantrax_player_id":"p2","current_manager_id":"m1","still_with_drafting_manager":False,"historical_fantasy_points":999,"historical_ghost_points":999,"historical_xgi":999,"historical_minutes":np.nan,"understat_minutes_2526":np.nan,"current_fantasy_points":10,"current_ghost_points":4,"current_xgi":.5,"current_minutes":90,"current_starts":1,"current_appearances":1,"fantrax_projected_points":100,"lineup_status":"RESERVE","roster_status":"ACTIVE"},
    ])


def standings():
    return pd.DataFrame([{"period":1,"manager_id":"m1","rank":2,"wins":1,"draws":0,"losses":0,"points":3,"fantasy_points_for":100,"fantasy_points_against":90,"games_played":1,"streak":"W1"}])


def weekly():
    return pd.DataFrame([
        {"period":1,"manager_id":"m1","fantasy_points":100,"result":"W"},{"period":1,"manager_id":"m2","fantasy_points":90,"result":"L"},
        {"period":2,"manager_id":"m1","fantasy_points":80,"result":"L"},{"period":2,"manager_id":"m2","fantasy_points":85,"result":"W"},
        {"period":3,"manager_id":"m1","fantasy_points":95,"result":"W"},{"period":3,"manager_id":"m2","fantasy_points":70,"result":"L"},
    ])


def test_manager_model_reconciles_identity_standings_roster_and_weighted_rates():
    draft=pd.DataFrame([{"manager":"Alpha"},{"manager":"Alpha"}])
    result=build_live_manager_analytics(players(),teams(),standings(),pd.DataFrame(),draft,weekly()).set_index("manager_id")
    row=result.loc["m1"]
    assert row.current_rank==2 and row.wins==1 and row.points_for==100 and row.points_against==90
    assert row.roster_count==2 and row.active_count==1 and row.reserve_count==1
    assert row.historical_points_per_90==10 and row.historical_ghost_per_90==5 and row.historical_xgi_per_90==.5
    assert row.current_roster_points_per_90==10 and row.current_roster_ghost_per_90==pytest.approx(14*90/270)
    assert row.drafted_players_retained==1 and row.draft_retention_pct==50


def test_preseason_weekly_values_and_form_remain_missing():
    result=build_live_manager_analytics(players(),teams(),standings(),pd.DataFrame(),pd.DataFrame())
    assert "average_weekly_score" not in result or result["average_weekly_score"].isna().all()
    assert "form" not in result or result["form"].isna().all()


def test_expected_record_is_established_all_play_with_half_credit_for_ties():
    frame=weekly(); frame.loc[len(frame)]={"period":3,"manager_id":"m3","fantasy_points":95,"result":"D"}
    result=expected_record(frame).set_index("manager_id")
    assert result.loc["m1","expected_wins"]==1.75
    assert result.loc["m1","luck_wins"]==.25


def test_windows_use_completed_periods_and_label_partial_coverage():
    frame=pd.concat([weekly(),pd.DataFrame([{"period":4,"manager_id":"m1","fantasy_points":pd.NA}])],ignore_index=True)
    last3,label=manager_week_window(frame,"m1","Last 3")
    assert last3.period.tolist()==[1,2,3] and label=="Last 3"
    last10,label=manager_week_window(frame,"m1","Last 10")
    assert len(last10)==3 and label=="Last 10 (3 completed)"
    assert set(WINDOWS)=={"Season","Last 3","Last 5","Last 10"}


def test_current_squad_has_one_row_per_player_and_excludes_historical_owner():
    frame=pd.concat([players(),players().iloc[[0]]],ignore_index=True)
    frame.loc[len(frame)]={"season_id":"2627","fantrax_player_id":"old","current_manager_id":"m2"}
    result=manager_squad(frame,"m1")
    assert set(result.fantrax_player_id)=={"p1","p2"}


def test_manager_week_contract_has_stable_ids_and_cumulative_results():
    matchups=pd.DataFrame([{"season_id":"2627","period":1,"home_manager":"Alpha","away_manager":"Beta","home_score":100,"away_score":90}])
    result=_manager_week_summary(matchups,standings(),teams(),"now")
    alpha=result[result.manager_id.eq("m1")].iloc[0]
    assert alpha.fantasy_points==100 and alpha.opponent_manager_id=="m2"
    assert alpha.cumulative_wins==1 and alpha.points_for_after_week==100


def test_live_manager_view_has_five_tabs_and_no_http_or_file_reads():
    source=open("views/live_managers.py",encoding="utf-8").read()
    assert '["Overview","Performance","Squad","Decisions","Explorer"]' in source
    assert "pd.read_" not in source and "requests." not in source and "httpx." not in source
    assert "Lineup-decision analytics will begin" in source


import pytest
