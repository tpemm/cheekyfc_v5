import math
import pandas as pd
from streamlit.testing.v1 import AppTest

from analytics.players.comparison import radar_records
from analytics.players.historical import RATE_FIELDS, build_historical_player_frame
from components.player_radar import build_player_radar
from views.historical_players import HISTORICAL_PRESETS, filter_historical_players, historical_comparison_table, historical_database_columns


def source_frames():
    master=pd.DataFrame([
        {"fantrax_player_id":"*p1*","fantrax_player_name":"Alpha","fantrax_team_name":"AAA","mgr_eligible":"M,F","fantrax_gw":1,"avail_fpts":10,"mgr_min":90,"mgr_gs":1,"mgr_g":1,"mgr_at":0,"minutes":90,"xg":.5,"xa":.1},
        {"fantrax_player_id":"*p1*","fantrax_player_name":"Alpha","fantrax_team_name":"AAA","mgr_eligible":"M,F","fantrax_gw":2,"avail_fpts":20,"mgr_min":90,"mgr_gs":1,"mgr_g":0,"mgr_at":1,"minutes":90,"xg":.2,"xa":.4},
        {"fantrax_player_id":"*p2*","fantrax_player_name":"Beta","fantrax_team_name":"BBB","mgr_eligible":"D","fantrax_gw":1,"avail_fpts":5,"mgr_min":0,"mgr_gs":0},
    ])
    frozen=pd.DataFrame([{"fantrax_player_id":"p1","historical_fantrax_player_id":"p1","registry_player_id":"r1","minutes_2526":180,"starts_2526":2,"fantasy_points_2526":30,"ghost_points_2526_authoritative":18,"ghost_appearances_2526":2,"understat_xg_2526":.7,"understat_xa_2526":.5,"understat_minutes_2526":180,"goals_2526":1,"assists_2526":1}])
    return master,frozen


def test_historical_model_uses_finalized_facts_and_valid_denominators():
    master,frozen=source_frames(); frame=build_historical_player_frame(master,frozen).set_index("fantrax_player_id")
    alpha=frame.loc["p1"]
    assert alpha.historical_fantasy_points==30 and alpha.historical_points_per_start==15
    assert alpha.historical_ghost_per_start==9 and alpha.historical_xgi_per_90==.6
    assert pd.isna(frame.loc["p2","historical_points_per_start"])
    assert not math.isinf(frame.loc["p2","historical_points_per_90"])


def test_search_club_and_multi_position_filters():
    master,frozen=source_frames(); frame=build_historical_player_frame(master,frozen)
    assert filter_historical_players(frame,search="alp").player_name.tolist()==["Alpha"]
    assert filter_historical_players(frame,club="BBB").player_name.tolist()==["Beta"]
    assert filter_historical_players(frame,position="F").player_name.tolist()==["Alpha"]


def test_rate_basis_changes_database_fields_without_fabricating_values():
    assert "historical_fantasy_points" in historical_database_columns("Total")
    assert "historical_points_per_start" in historical_database_columns("Per Start")
    assert "historical_points_per_90" in historical_database_columns("Per 90")
    assert set(RATE_FIELDS)=={"Total","Per Game","Per Start","Per 90"}


def test_historical_radar_supports_league_position_custom_and_insufficient_data():
    master,frozen=source_frames(); frame=build_historical_player_frame(master,frozen)
    metrics=HISTORICAL_PRESETS["Balanced Profile"]
    for basis in ("League","Position"):
        records=radar_records(frame,frame.iloc[[0]],metrics,"Per 90",basis)
        assert records[0]["metrics"][0]["peer_group"] in {"League","M"}
    assert build_player_radar(radar_records(frame,frame.iloc[[1]],metrics,"Per 90","League")) is None


def test_two_three_and_five_player_comparison_has_raw_values_and_no_winner():
    master,frozen=source_frames(); frame=build_historical_player_frame(master,frozen)
    copies=[frame.assign(fantrax_player_id=frame.fantrax_player_id+str(i),registry_player_id=pd.NA,player_name=frame.player_name+str(i)) for i in range(3)]
    population=pd.concat(copies,ignore_index=True)
    ids=population.fantrax_player_id.tolist()
    for count in (2,3,5):
        table=historical_comparison_table(population,ids[:count])
        assert len(table.columns)==count+1 and "Winner" not in table.columns
        assert table.iloc[0,1]==population.iloc[0].historical_fantasy_points


def test_historical_model_never_substitutes_999_adp():
    master,frozen=source_frames(); frame=build_historical_player_frame(master,frozen)
    assert "adp" not in frame or not pd.to_numeric(frame["adp"],errors="coerce").eq(999).any()


def test_historical_players_apptest_renders_finalized_archive():
    app=AppTest.from_file("app.py",default_timeout=45).run()
    app.sidebar.selectbox[0].set_value("2025/26").run()
    app.sidebar.radio[0].set_value("Players").run()
    assert not app.exception
    assert [tab.label for tab in app.tabs]==["Player Database","Player Profile","Compare Players"]
    assert any("2025/26 · Finalized Historical Data" in item.value for item in app.markdown)
