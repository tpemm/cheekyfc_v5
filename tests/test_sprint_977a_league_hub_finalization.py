from pathlib import Path
import time

import pandas as pd
from streamlit.testing.v1 import AppTest

from fantrax.live.league_analytics import build_live_league_summary,completed_matchups,jester_history,league_highlights,player_leaderboards,scoring_frames
from fantrax.live.league_lineups import ACTIVE_STATUSES,active_player_weekly,optimal_legal_xi
from views.live_league_hub import build_live_hub_model


ROOT=Path(__file__).parents[1];MODELS=ROOT/"data"/"models"/"season_2627"


def _read(name):return pd.read_csv(MODELS/name,dtype={"fantrax_player_id":str})


def test_real_gw1_results_records_awards_and_trends():
    games=_read("weekly_matchups_2627.csv");weeks=_read("manager_week_summary_2627.csv");gw=games.query("period == 1")
    assert len(gw)==6 and gw.status.eq("completed").all() and len(completed_matchups(gw))==6
    periods=weeks.period.nunique()
    assert weeks.result.value_counts().to_dict()=={"W":6*periods,"L":6*periods}
    assert weeks.cumulative_wins.sum()==weeks.cumulative_losses.sum()==6*sum(range(1,periods+1))
    assert weeks.query("period == 1").lineup_changes.isna().all()
    assert weeks.query("period == 2").lineup_changes.notna().all() and weeks.lineup_efficiency_pct.notna().sum()==24
    jester=jester_history(weeks).iloc[0];assert (jester.manager_name.split()[0],jester.weekly_score,int(jester.period))==("wmuck1",68.0,1)
    highlights={row["label"]:row for row in league_highlights(weeks,games)}
    latest=weeks[weeks.period.eq(weeks.period.max())]
    high=latest.loc[latest.fantasy_points.idxmax()];low=latest.loc[latest.fantasy_points.idxmin()]
    assert highlights["Highest Score"]["value"]==high.manager_name and f"{high.fantasy_points:.1f} pts" in highlights["Highest Score"]["detail"]
    assert highlights["Lowest Score"]["value"]==low.manager_name and f"{low.fantasy_points:.1f} pts" in highlights["Lowest Score"]["detail"]
    assert "Berkshire’s Club 91.5 (W)" in highlights["Closest Match"]["value"] and "epatel3 91.0" in highlights["Closest Match"]["detail"]
    assert "tpem 167.5 (W)" in highlights["Biggest Blowout"]["value"] and "Berkshire’s Club 110.5" in highlights["Biggest Blowout"]["detail"]
    scoring,history=scoring_frames(weeks);assert scoring.shape==(periods,13) and history.shape[0]==periods
    assert sorted(history.iloc[-1].dropna().astype(int))==list(range(1,13))


def test_real_active_lineup_exact_132_and_excludes_bench_and_waivers():
    active=_read("league_active_player_weekly_2627.csv");weekly=_read("current_player_weekly_2627.csv")
    assert len(active)==132*active.period.nunique() and active.groupby(["period","manager_id"]).size().eq(11).all()
    assert not active.duplicated(["period","fantrax_player_id"]).any() and active.active_start.astype(str).str.lower().eq("true").all()
    for period,rows in active.groupby("period"):
        same=weekly[pd.to_numeric(weekly.period,errors="coerce").eq(period)]
        bench=set(same.loc[same.lineup_status.eq("RESERVE"),"fantrax_player_id"]);waivers=set(same.loc[same.current_manager_id.isna(),"fantrax_player_id"])
        assert set(rows.fantrax_player_id).isdisjoint(bench|waivers)
    boards=player_leaderboards(active);assert all(not board.empty for board in boards.values())
    assert all("Manager" in board for board in boards.values())


def test_leaderboards_include_active_but_exclude_bench_and_waiver_stats():
    rows=pd.DataFrame([
        {"period":1,"period_complete":True,"player_name":"Active","fantasy_team_name":"Ours","fantrax_points":10,"goals":1,"assists":1,"clean_sheets":1},
        {"period":1,"period_complete":True,"player_name":"Bench","fantasy_team_name":pd.NA,"fantrax_points":99,"goals":9,"assists":9,"clean_sheets":9},
    ])
    active=rows.iloc[[0]];boards=player_leaderboards(active)
    assert all("Active" in board.Player.tolist() for board in boards.values())
    assert all("Bench" not in board.Player.tolist() for board in boards.values())


def test_optimal_xi_is_legal_deterministic_and_handles_negative_multi_position():
    players=[]
    for pos,count in (("G",2),("D",6),("M",6),("F",3)):
        players.extend({"fantrax_player_id":f"{pos}{i}","fantrax_position":pos,"fantasy_points":20-i} for i in range(count))
    players.append({"fantrax_player_id":"multi","fantrax_position":"D,M","fantasy_points":30})
    players.append({"fantrax_player_id":"negative","fantrax_position":"F","fantasy_points":-5})
    score,ids=optimal_legal_xi(pd.DataFrame(players));again=optimal_legal_xi(pd.DataFrame(players).sample(frac=1,random_state=7))
    assert len(ids)==11 and again==(score,ids) and "multi" in ids and pd.notna(score)


def test_active_future_week_remains_provisional_and_awards_withheld():
    live_games=pd.DataFrame([{"period":2,"status":"live","home_manager":"A","away_manager":"B","home_score":10,"away_score":5,"margin":5}])
    live_weeks=pd.DataFrame([{"period":2,"manager_id":"a","manager_name":"A","fantasy_points":10,"result":pd.NA,"source_coverage":"live active-lineup score"}])
    assert completed_matchups(live_games).empty and jester_history(live_weeks).empty and league_highlights(live_weeks,live_games)==[]


def test_real_league_hub_apptest_is_finalized_and_fast():
    started=time.perf_counter();app=AppTest.from_file(str(ROOT/"app.py"),default_timeout=45).run();app.sidebar.radio(key="page_nav").set_value("League Hub").run();elapsed=time.perf_counter()-started
    assert not app.exception and elapsed<20
    rendered=" ".join(str(x.value) for x in app.markdown);assert "2026/27" in rendered and "Latest Jester" in rendered and "wmuck1" in rendered
    weeks=_read("manager_week_summary_2627.csv");latest=int(weeks.period.max());high=weeks.query("period == @latest").fantasy_points.max()
    assert "Highest Score" in rendered and f"{high:.1f} pts" in rendered and "Closest Match" in rendered and "Biggest Blowout" in rendered
    assert "Weekly Scoring" in rendered and "League Position History" in rendered and "Manager Awards" in rendered
    assert "Player Leaderboards" not in rendered and "Ghost King" in rendered
    assert f"GW{latest} Results" in rendered and f"GW{latest} Live Matchups" not in rendered
    tables=[x.value for x in app.dataframe];assert any(len(table)==12 and "Record" in table for table in tables)
