from pathlib import Path
import time

import pandas as pd
from streamlit.testing.v1 import AppTest

from fantrax.live.league_analytics import manager_active_season_totals,manager_award_leaderboards


ROOT=Path(__file__).parents[1]


def real_active():return pd.read_csv(ROOT/"data/models/season_2627/league_active_player_weekly_2627.csv",dtype={"fantrax_player_id":str})


def test_real_manager_totals_reconcile_all_132_active_rows():
    active=real_active();totals=manager_active_season_totals(active)
    assert len(active)==132*active.period.nunique() and len(totals)==12 and totals.season_id.astype(str).eq("2627").all()
    active=active[active.period_complete.fillna(False)]
    assert totals.active_starts.eq(11*active.period.nunique()).all() and totals.periods_counted.eq(active.period.nunique()).all()
    for metric in ("goals","assists","clean_sheets"):
        expected=pd.to_numeric(active[metric],errors="coerce").sum(min_count=1);actual=pd.to_numeric(totals[metric],errors="coerce").sum(min_count=1);assert actual==expected
    complete_ghost=active.groupby("manager_id").filter(lambda rows: rows.ghost_points.notna().all())
    assert totals.ghost_points.sum(min_count=1)==complete_ghost.ghost_points.sum(min_count=1)


def test_real_award_leaders_are_managers_with_competition_ranks():
    boards=manager_award_leaderboards(manager_active_season_totals(real_active()))
    assert set(boards)=={"Golden Boot","Playmaker","Golden Glove","Ghost King"}
    assert boards["Golden Boot"].iloc[0][["Manager","Goals"]].tolist()==["tpem",6.0]
    assert boards["Playmaker"].iloc[0][["Manager","Assists"]].tolist()==["epatel3",6.0]
    assert boards["Golden Glove"].Rank.tolist()[:2]==[1,1]
    assert boards["Ghost King"].iloc[0][["Manager","Ghost Points"]].tolist()==["The Facerockers",174.0]


def test_bench_ir_and_waiver_rows_never_enter_manager_totals():
    frame=pd.DataFrame([
        {"season_id":"2627","period":1,"period_complete":True,"manager_id":"a","manager_name":"A","fantrax_player_id":"active","active_start":True,"goals":1,"assists":1,"clean_sheets":1,"ghost_points":5},
        {"season_id":"2627","period":1,"period_complete":True,"manager_id":"a","manager_name":"A","fantrax_player_id":"bench","active_start":False,"goals":9,"assists":9,"clean_sheets":9,"ghost_points":90},
        {"season_id":"2627","period":1,"period_complete":True,"manager_id":pd.NA,"manager_name":pd.NA,"fantrax_player_id":"waiver","active_start":False,"goals":8,"assists":8,"clean_sheets":8,"ghost_points":80},
    ])
    row=manager_active_season_totals(frame).iloc[0];assert row[["goals","assists","clean_sheets","ghost_points"]].tolist()==[1,1,1,5]


def test_trade_history_and_multiweek_accumulation_stay_with_period_manager():
    frame=pd.DataFrame([
        {"season_id":"2627","period":1,"period_complete":True,"manager_id":"a","manager_name":"A","fantrax_player_id":"p","active_start":True,"goals":2,"assists":1,"clean_sheets":0,"ghost_points":4},
        {"season_id":"2627","period":2,"period_complete":True,"manager_id":"b","manager_name":"B","fantrax_player_id":"p","active_start":True,"goals":1,"assists":2,"clean_sheets":1,"ghost_points":6},
        {"season_id":"2627","period":2,"period_complete":True,"manager_id":"a","manager_name":"A","fantrax_player_id":"q","active_start":True,"goals":3,"assists":2,"clean_sheets":1,"ghost_points":5},
    ])
    totals=manager_active_season_totals(frame).set_index("manager_id")
    assert totals.loc["a",["goals","assists","ghost_points"]].tolist()==[5,3,9]
    assert totals.loc["b",["goals","assists","ghost_points"]].tolist()==[1,2,6]


def test_provisional_period_and_missing_ghost_are_not_fabricated():
    frame=pd.DataFrame([{"season_id":"2627","period":1,"period_complete":True,"manager_id":"a","manager_name":"A","fantrax_player_id":"p","active_start":True,"goals":1,"assists":0,"clean_sheets":0,"ghost_points":pd.NA},{"season_id":"2627","period":2,"period_complete":False,"manager_id":"a","manager_name":"A","fantrax_player_id":"q","active_start":True,"goals":9,"assists":9,"clean_sheets":9,"ghost_points":99}])
    row=manager_active_season_totals(frame).iloc[0];assert row.goals==1 and pd.isna(row.ghost_points)


def test_real_hub_renders_manager_awards_not_players():
    started=time.perf_counter();app=AppTest.from_file(str(ROOT/"app.py"),default_timeout=45).run();app.sidebar.radio(key="page_nav").set_value("League Hub").run();elapsed=time.perf_counter()-started
    assert not app.exception and elapsed<20
    rendered=" ".join(str(item.value) for item in app.markdown)
    assert "Manager Awards" in rendered and "Player Leaderboards" not in rendered
    assert all(label in rendered for label in ("Golden Boot","Playmaker","Golden Glove","Ghost King"))
    assert "The Facerockers" in rendered and "KindComet" in rendered and "epatel3" in rendered
    assert "Maxim De Cuyper" not in rendered and rendered.count("Highest Score")==1
