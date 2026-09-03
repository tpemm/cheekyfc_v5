from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

ROOT=Path(__file__).resolve().parents[1]


def page(name:str):
    app=AppTest.from_file(str(ROOT/"app.py"),default_timeout=30).run()
    app.sidebar.radio(key="page_nav").set_value(name).run()
    return app


def test_live_manager_scores_propagate_to_two_gameweek_hub():
    expected=pd.read_csv(ROOT/"data/models/season_2627/manager_week_summary_2627.csv")
    assert len(expected)==24 and set(expected.period)=={1,2} and expected.fantasy_points.notna().all()
    app=page("League Hub");assert not app.exception
    assert next(item for item in app.sidebar.selectbox if item.label=="Season").value=="2026/27"
    rendered=" ".join(item.value for item in app.markdown)
    assert "GW2 Results" in rendered and "GW2 Live Matchups" not in rendered and "GW38" not in rendered
    matchups=next(item.value for item in app.dataframe if {"Home","Home Score","Away Score","Away","Status"}.issubset(item.value.columns))
    assert len(matchups)==6 and matchups.Status.eq("completed").all()
    assert set(matchups["Home Score"])|set(matchups["Away Score"])==set(expected.query("period == 2").fantasy_points)


def test_real_current_player_defaults_and_historical_switch():
    supplemental=pd.read_csv(ROOT/"data/models/season_2627/advanced/supplemental_player_match_2627.csv",low_memory=False)
    current=pd.read_csv(ROOT/"data/models/season_2627/current_player_season_summary_2627.csv",dtype={"fantrax_player_id":str})
    eligible=supplemental.dropna(subset=["fantrax_player_id","rating","xg","xa","actual_tactical_role"])
    eligible=eligible[eligible.fantrax_player_id.astype(str).isin(set(current.fantrax_player_id.astype(str)))]
    candidate=eligible.sort_values("fantrax_points",ascending=False).iloc[0]
    display_name=current.set_index("fantrax_player_id").loc[str(candidate.fantrax_player_id),"player_name"]
    app=page("Players");app.get("button_group")[0].set_value("Player Profile").run()
    selector=next(item for item in app.selectbox if item.label=="Player");label=next(option for option in selector.options if str(display_name) in option);selector.set_value(label).run()
    assert not app.exception
    advanced=next(item for item in app.selectbox if item.label=="Advanced data season")
    assert advanced.value=="2026/27 Current"
    assert next(item for item in app.toggle if item.label=="Compare to 2025/26").value is False
    assert next(item for item in app.selectbox if item.label=="Match Analysis Season").value=="2026/27 Current"
    values={item.label for item in app.metric}
    assert {"Rating","xG","xA"}.issubset(values)
    pitch=next(item.value for item in app.caption if "recorded actions" in item.value)
    assert "opponent goal at top" in pitch and int(pitch.split()[0].replace(",",""))>0
    detail=next(item.value for item in app.dataframe if {"event_type","x","y"}.issubset(item.value.columns));assert len(detail)>0
    advanced.set_value("2025/26 Historical").run();assert not app.exception
    assert next(item for item in app.selectbox if item.label=="Advanced data season").value=="2025/26 Historical"
    assert any("2025/26 historical" in item.value.lower() for item in app.markdown)


def test_real_current_team_defaults_and_historical_switch():
    team=pd.read_csv(ROOT/"data/models/season_2627/understat_team_match_2627.csv");row=team.groupby("canonical_club_id",as_index=False)[["xg","xga"]].sum().sort_values("xg",ascending=False).iloc[0]
    clubs=pd.read_csv(ROOT/"data/models/season_2627/premier_league_clubs_2627.csv");club=clubs.set_index("canonical_club_id").loc[row.canonical_club_id,"canonical_name"]
    app=page("Teams");selector=next(item for item in app.selectbox if item.label=="Club");selector.set_value(club).run();assert not app.exception
    assert app.radio(key="team_match_season").value=="2026/27 Current"
    assert app.radio(key="team_fantasy_season").value=="2026/27 Current"
    metrics={(item.label,item.value) for item in app.metric};assert ("xG",f"{row.xg:.2f}") in metrics and ("xGA",f"{row.xga:.2f}") in metrics
    assert ("Played","2") in metrics and any("Current sample: 2 matches observed" in item.value for item in app.caption)
    app.radio(key="team_match_season").set_value("2025/26 Historical").run();assert not app.exception
    assert app.radio(key="team_match_season").value=="2025/26 Historical"


def test_propagation_report_and_missing_history_are_explicit():
    report=pd.read_csv(ROOT/"data/quality/season_2627/live_ui_propagation_2627.csv")
    assert report.status.eq("PASS").all() and report.season_context.isin(["CURRENT","HISTORICAL"]).all()
    clubs=pd.read_csv(ROOT/"data/models/season_2627/premier_league_clubs_2627.csv")
    assert {"coventry_city","hull_city","ipswich_town"}.issubset(set(clubs.canonical_club_id))


def test_refresh_cache_invalidation_and_commissioner_propagation_contract():
    from views.update_pipeline import _clear_streamlit_cache
    class Cache:
        cleared=False
        def clear(self):self.cleared=True
    class UI:cache_data=Cache()
    ui=UI();_clear_streamlit_cache(ui);assert ui.cache_data.cleared
    commissioner=(ROOT/"scripts/weekly_commissioner_refresh.py").read_text(encoding="utf-8")
    order=[commissioner.index(token) for token in ("'core_build'","'understat_products'","'whoscored_advanced'","'unified_models'","'refresh_status'")]
    assert order==sorted(order)
    core=(ROOT/"core/services/core_refresh.py").read_text(encoding="utf-8").lower()
    assert "playwright" not in core and "weekly_advanced_refresh" not in core and "weekly_commissioner_refresh" not in core
