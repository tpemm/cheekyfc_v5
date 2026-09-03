from pathlib import Path
import pandas as pd
from streamlit.testing.v1 import AppTest
from fantrax.live.manager_name_history import update_manager_name_history,resolve_current_manager_names
from fantrax.live.pipeline import authoritative_current_roster,_manager_week_summary
from fantrax.live.league_analytics import configured_manager_of_month,build_live_league_summary

ROOT=Path(__file__).parents[1]

def test_latest_weekly_roster_includes_ir_bench_and_waiver():
    weekly=pd.DataFrame([
        {"season_id":"2627","period":2,"fantrax_player_id":"ir","current_manager_id":"x","current_manager_name":"X","lineup_status":"IR","player_name":"IR"},
        {"season_id":"2627","period":2,"fantrax_player_id":"bench","current_manager_id":"x","current_manager_name":"X","lineup_status":"Res","player_name":"Bench"},
        {"season_id":"2627","period":2,"fantrax_player_id":"free","current_manager_id":pd.NA,"player_name":"Free"},
    ]);teams=pd.DataFrame([{"season_id":"2627","manager_id":"x","manager_name":"X","fantasy_team_id":"x","fantasy_team_name":"X"}])
    roster=authoritative_current_roster(weekly,teams,"now").set_index("fantrax_player_id")
    assert set(roster.index)=={"ir","bench"};assert roster.loc["ir","injured_reserve"] and roster.loc["bench","reserve"]

def test_multiple_renames_remain_one_stable_identity():
    history=pd.DataFrame()
    for period,name in ((1,"Count Doku"),(2,"GVand35"),(3,"Another Name")):
        current=pd.DataFrame([{"season_id":"2627","manager_id":"XYZ","manager_name":name,"fantasy_team_name":name}]);history=update_manager_name_history(history,current,period=period,observed_at=f"t{period}")
    assert history.manager_id.nunique()==1 and history.display_name.tolist()==["Count Doku","GVand35","Another Name"] and history.is_current.sum()==1
    facts=pd.DataFrame([{"manager_id":"XYZ","manager_name":"Count Doku","fantasy_team_name":"Count Doku","period":1},{"manager_id":"XYZ","manager_name":"GVand35","fantasy_team_name":"GVand35","period":2}])
    assert resolve_current_manager_names(facts,current).manager_name.eq("Another Name").all()

def test_august_september_award_is_in_progress_without_winner():
    weeks=pd.DataFrame([{"period":1,"manager_id":"a","manager_name":"A","fantasy_points":100,"result":"W","period_completed_at":"2026-08-25"},{"period":2,"manager_id":"a","manager_name":"A","fantasy_points":110,"result":"W","period_completed_at":"2026-08-31"}])
    result=configured_manager_of_month(weeks,as_of="2026-09-01")
    assert result["label"]=="August / September" and result["completion_state"]=="in progress" and result["winner"] is None and result["current_leaders"][0]["manager_name"]=="A"

def test_stale_upstream_rank_cannot_override_derived_cumulative_rank():
    teams=pd.DataFrame([{"season_id":"2627","manager_id":"a","manager_name":"A","fantasy_team_id":"a","fantasy_team_name":"A"},{"season_id":"2627","manager_id":"b","manager_name":"B","fantasy_team_id":"b","fantasy_team_name":"B"}])
    matchups=pd.DataFrame([{"season_id":"2627","period":1,"home_team_id":"a","away_team_id":"b","home_manager":"A","away_manager":"B","home_score":90,"away_score":100,"status":"completed"},{"season_id":"2627","period":2,"home_team_id":"a","away_team_id":"b","home_manager":"A","away_manager":"B","home_score":120,"away_score":80,"status":"completed"}])
    stale=pd.DataFrame([{"manager_id":"b","manager":"B","rank":1},{"manager_id":"a","manager":"A","rank":2}]);weeks=_manager_week_summary(matchups,stale,teams,"now")
    summary=build_live_league_summary(teams,stale,weeks,pd.DataFrame())
    assert weeks.query("period==2").sort_values("rank_after_week").manager_id.tolist()==["a","b"] and summary.sort_values("current_rank").manager_id.tolist()==["a","b"]

def test_repaired_player_database_and_league_hub_apptest():
    app=AppTest.from_file(str(ROOT/"app.py"),default_timeout=40).run();app.sidebar.radio(key="page_nav").set_value("Players").run();assert not app.exception
    from views.players import live_database_frame
    database=live_database_frame(pd.read_csv(ROOT/"data/models/season_2627/live_player_analytics_2627.csv"),"Per Start")
    for name in ("Jack Hinshelwood","Vitaly Janelt"):
        row=database[database.Player.eq(name)].iloc[0];assert row["Fantasy Manager / Available"]=="tpem"
    app.sidebar.radio(key="page_nav").set_value("League Hub").run();assert not app.exception
    table=next(x.value for x in app.dataframe if {"Rank","Team","Movement","Record"}.issubset(getattr(x.value,"columns",set())))
    assert table.Rank.tolist()==list(range(1,13)) and table.iloc[0].Team=="tpem" and "GVand35" in set(table.Team) and "Count Doku" not in set(table.Team)
    rendered=" ".join(x.value for x in app.markdown);assert "August / September Manager of the Month" in rendered and "In Progress" in rendered and "Current Leader: tpem" in rendered
