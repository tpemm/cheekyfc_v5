import pandas as pd

from core.services.data_manager import DataManager
from fantrax.live.analytics import expected_record
from fantrax.live.league_analytics import (
    build_live_league_summary, completed_manager_weeks, completed_matchups,
    compact_league_table, format_movement, jester_history, latest_manager_of_month,
    league_highlights, LIVE_TABLE_COLUMNS, scoring_frames,
)


def teams():
    return pd.DataFrame([
        {"season_id":"2627","manager_id":"m1","manager_name":"Alpha","fantasy_team_id":"t1","fantasy_team_name":"Alpha FC"},
        {"season_id":"2627","manager_id":"m2","manager_name":"Beta","fantasy_team_id":"t2","fantasy_team_name":"Beta FC"},
    ])


def managers():
    return pd.DataFrame([
        {"season_id":"2627","manager_id":"m1","manager_name":"Alpha","fantasy_team_id":"t1","fantasy_team_name":"Alpha FC","current_rank":1,"wins":2,"draws":0,"losses":1,"points_for":300,"points_against":250,"current_roster_projection":4000,"draft_retention_pct":90,"current_roster_points_per_90":11,"current_roster_ghost_per_90":8},
        {"season_id":"2627","manager_id":"m2","manager_name":"Beta","fantasy_team_id":"t2","fantasy_team_name":"Beta FC","current_rank":2,"wins":1,"draws":0,"losses":2,"points_for":250,"points_against":300,"current_roster_projection":3900,"draft_retention_pct":80,"current_roster_points_per_90":10,"current_roster_ghost_per_90":7},
    ])


def weeks():
    return pd.DataFrame([
        {"period":1,"manager_id":"m1","manager_name":"Alpha","fantasy_points":90,"result":"L","rank_after_week":2},
        {"period":1,"manager_id":"m2","manager_name":"Beta","fantasy_points":100,"result":"W","rank_after_week":1},
        {"period":2,"manager_id":"m1","manager_name":"Alpha","fantasy_points":110,"result":"W","rank_after_week":1},
        {"period":2,"manager_id":"m2","manager_name":"Beta","fantasy_points":80,"result":"L","rank_after_week":2},
        {"period":3,"manager_id":"m1","manager_name":"Alpha","fantasy_points":100,"result":"W","rank_after_week":1},
        {"period":3,"manager_id":"m2","manager_name":"Beta","fantasy_points":70,"result":"L","rank_after_week":2},
        {"period":4,"manager_id":"m1","manager_name":"Alpha","fantasy_points":pd.NA,"result":pd.NA,"rank_after_week":pd.NA},
    ])


def matchups():
    return pd.DataFrame([
        {"period":2,"status":"completed","home_manager":"Alpha","away_manager":"Beta","home_score":110,"away_score":80},
        {"period":3,"status":"completed","home_manager":"Alpha","away_manager":"Beta","home_score":100,"away_score":99},
        {"period":4,"status":"scheduled","home_manager":"Alpha","away_manager":"Beta","home_score":0,"away_score":0},
    ])


def test_league_summary_uses_stable_identity_and_completed_rank_movement():
    result=build_live_league_summary(teams(),pd.DataFrame(),weeks(),managers()).set_index("manager_id")
    assert result.loc["m1","movement"]=="\u2014"
    assert result.loc["m2","movement"]=="\u2014"
    assert result.loc["m1","current_form"]=="L W W"
    assert result.loc["m1","average_weekly_score"]==100
    assert result.loc["m1","current_roster_points_per_90"]==11


def test_movement_up_down_same_and_preseason():
    assert format_movement(1,3)=="\u25b22"
    assert format_movement(3,1)=="\u25bc2"
    assert format_movement(2,2)=="\u2014"
    assert format_movement(pd.NA,pd.NA)=="\u2014"


def test_completed_period_filters_exclude_future_and_incomplete_rows():
    assert completed_manager_weeks(weeks()).period.max()==3
    assert completed_matchups(matchups()).period.tolist()==[2,3]


def test_latest_highlights_jester_closest_and_blowout_use_completed_results():
    highlights={item["label"]:item for item in league_highlights(weeks(),matchups())}
    assert highlights["Manager of the Week"]["value"]=="Alpha"
    assert highlights["Weekly Jester"]["value"]=="Beta"
    assert "1.0-point" in highlights["Closest Match"]["detail"]
    assert "30.0-point" in highlights["Biggest Blowout"]["detail"]


def test_scoring_includes_correct_league_average_and_rank_history():
    scoring,history=scoring_frames(weeks())
    assert scoring.loc[1,"League Average"]==95
    assert 4 not in scoring.index and history.loc[1,"Beta"]==1


def test_expected_wins_and_luck_reuse_manager_methodology():
    result=expected_record(completed_manager_weeks(weeks())).set_index("manager_id")
    assert result.loc["m1","expected_wins"]==2
    assert result.loc["m1","luck_wins"]==0


def test_registered_live_league_summary_resolves():
    assert DataManager().resolve_path("live_league_summary","2627").name=="live_league_summary_2627.csv"


def test_hub_uses_data_manager_and_performs_no_http_or_direct_csv_reads():
    source=open("views/live_league_hub.py",encoding="utf-8").read()
    assert "data.load_frame" in source
    assert "pd.read_csv" not in source and "requests." not in source and "httpx." not in source
    assert "Manager Awards" in source and "Weekly Scoring" in source


def test_manager_moves_are_not_called_trades_without_confirmation():
    source=open("fantrax/live/roster_tracking.py",encoding="utf-8").read()
    assert "not classified as a trade without confirmation" in source


def test_jester_history_latest_and_leader_are_deterministic():
    history=jester_history(weeks())
    assert history.iloc[-1].manager_name=="Beta" and history.iloc[-1].period==3
    assert history.groupby("manager_name").size().to_dict()=={"Alpha":1,"Beta":2}


def test_manager_of_month_uses_record_then_points_and_excludes_current_month():
    frame=weeks().dropna(subset=["fantasy_points"]).copy();frame["period_completed_at"]=["2026-08-03","2026-08-03","2026-08-10","2026-08-10","2026-09-02","2026-09-02"]
    award=latest_manager_of_month(frame,as_of="2026-09-15T00:00:00Z")
    assert award["month"]=="2026-08" and award["leaders"][0]["manager_id"]=="m1"


def test_compact_table_has_exact_columns_and_blanks_unproven_fields():
    summary=build_live_league_summary(teams(),pd.DataFrame(),weeks(),managers());table=compact_league_table(summary,weeks())
    assert tuple(table.columns)==LIVE_TABLE_COLUMNS
    assert not {"W","D","L","Points For","Points Against"}.intersection(table.columns)
    assert table.loc[0,"Record"]=="2-0-1" and table.loc[0,"Pts / GW"]==100
    assert table["Ghost / GW"].isna().all() and table["Efficiency"].isna().all() and table["Lineup Changes"].isna().all()


def test_preseason_compact_table_uses_neutral_live_fields():
    summary=build_live_league_summary(teams(),pd.DataFrame(),pd.DataFrame(),managers());table=compact_league_table(summary,pd.DataFrame())
    assert table["Movement"].eq("\u2014").all()
    assert table[["Form","Pts / GW","Ghost / GW","Efficiency","Lineup Changes"]].isna().all().all()


def test_hub_cards_and_manager_grid_refinement_are_present_in_source():
    source=open("views/live_league_hub.py",encoding="utf-8").read()
    for label in ("Latest Jester","Jester Leader","Manager of the Month","Cup Status"):assert label in source
    assert 'section_header(ui,"Manager Cards"' not in source
    assert "Recent Roster Activity" not in source and "Available Players" not in source
