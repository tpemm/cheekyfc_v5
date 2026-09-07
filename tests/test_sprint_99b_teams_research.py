from pathlib import Path
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from analytics.teams.research import (
    EVENT_LAYERS, PROFILE_GROUPS, filter_tactical_scope, prepare_team_events,
    prepare_team_fantasy_matchups, prepare_team_historical_comparison,
    prepare_team_match_analysis, prepare_team_overview,
    prepare_team_profile_percentiles,
)
from views.teams import CURRENT,HISTORICAL,TABS

ROOT=Path(__file__).resolve().parents[1]
read=lambda name,season="2627":pd.read_csv(ROOT/f"data/models/season_{season}/{name}_{season}.csv",low_memory=False)

def frames():
    return {"matches":read("team_match_analytics"),"profiles":read("team_season_profile"),"fantasy":read("team_fantasy_allowed_match"),"position":read("team_fantasy_allowed_position_match"),"fixtures":read("team_fixtures"),"history":read("team_match_analytics","2526"),"events":pd.read_csv(ROOT/"data/models/season_2627/advanced/whoscored_event_2627.csv",low_memory=False)}

def test_final_information_architecture_and_current_first_constants():
    assert TABS==("Overview","Match Analysis","Tactical Profile","Fantasy Matchups")
    assert CURRENT=="2026/27 Current" and HISTORICAL=="2025/26 Historical"

def test_overview_kpis_trend_fixtures_and_understat_values():
    d=frames();model=prepare_team_overview("arsenal",d["matches"],d["profiles"],d["fantasy"],d["fixtures"]);s=model["summary"]
    assert s.matches==3 and s.record=="3-0-0" and np.isclose(s.xg,6.1842) and np.isclose(s.xga,1.270769)
    assert len(model["trend"])==3 and 1<=len(model["fixtures"])<=5

def test_profiles_use_full_league_neutral_volume_percentiles():
    d=frames();panels=prepare_team_profile_percentiles(d["profiles"],"arsenal")
    assert set(panels)==set(PROFILE_GROUPS)
    assert all(len(panel)==5 for panel in panels.values())
    assert all(panel["Volume Percentile"].dropna().between(0,100).all() for panel in panels.values())
    # xGA is intentionally not inverted: the percentile means more xGA, never "better defense".
    xga=panels["Defensive Profile"].set_index("Metric").loc["xGA / Match"]
    assert xga["Volume Percentile"]==100*d["profiles"].assign(xga_per_match=lambda x:x.xga/x.matches).xga_per_match.rank(pct=True).loc[d["profiles"].club_id.eq("arsenal")].iloc[0]

def test_historical_compatibility_bournemouth_and_coventry():
    d=frames();b=prepare_team_historical_comparison("afc_bournemouth",d["history"]);c=prepare_team_historical_comparison("coventry_city",d["history"])
    assert b["available"] and b["historical_club_id"]=="bournemouth" and len(b["matches"])==38
    assert not c["available"] and c["matches"].empty
    assert b["matches"].xg.notna().all() and b["matches"].xga.notna().all()

def test_match_analysis_is_chronological_and_h_a_filterable():
    d=frames();all_rows=prepare_team_match_analysis(d["history"],"arsenal")["rows"];home=prepare_team_match_analysis(d["history"],"arsenal",venue="Home")["rows"]
    assert all_rows.match_date.tolist()==sorted(all_rows.match_date.tolist()) and len(all_rows)==38
    assert not home.empty and home.home_away.eq("H").all()

def test_tactical_scopes_manager_formation_and_venue():
    d=frames();rows=d["history"][d["history"].club_id.eq("nottingham_forest")];manager=rows.manager_name.value_counts().index[-1];formation=str(rows.formation.value_counts().index[0])
    assert len(filter_tactical_scope(d["history"],"nottingham_forest",scope="Last 5"))==5
    assert len(filter_tactical_scope(d["history"],"nottingham_forest",scope="Last 10"))==10
    assert filter_tactical_scope(d["history"],"nottingham_forest",manager=manager).manager_name.eq(manager).all()
    assert filter_tactical_scope(d["history"],"nottingham_forest",formation=formation).formation.astype(str).eq(formation).all()
    assert filter_tactical_scope(d["history"],"nottingham_forest",venue="Away").home_away.eq("A").all()

def test_team_event_layers_and_corrected_orientation():
    d=frames();matches=d["matches"][d["matches"].club_id.eq("arsenal")]
    assert set(EVENT_LAYERS)=={"Activity Density","Passes","Key Passes","Crosses","TakeOns","Shots","Defensive Actions","Recoveries","Aerials"}
    activity=prepare_team_events(d["events"],matches,"arsenal");passes=prepare_team_events(d["events"],matches,"arsenal","Passes")
    assert not activity.empty and passes.event_type.eq("Pass").all()
    sample=activity.dropna(subset=["x","y"]).iloc[0]
    assert np.isclose(sample.plot_x,100-sample.y) and np.isclose(sample.plot_y,sample.x)

def test_fantasy_positions_preserve_missing_as_missing_and_have_no_ranks():
    d=frames();models={club:prepare_team_fantasy_matchups(d["fantasy"],d["position"],club) for club in d["matches"].club_id}
    assert all(model["positions"].position_group.tolist()==["GK","DEF","MID","FWD"] for model in models.values())
    assert sum(model["positions"].matches_observed.isna().sum() for model in models.values())==0
    assert not any("rank" in c.lower() or "grade" in c.lower() for model in models.values() for c in model["positions"])

def test_no_style_classifications_predictions_network_or_browser():
    source=(ROOT/"views/teams.py").read_text(encoding="utf-8")+(ROOT/"analytics/teams/research.py").read_text(encoding="utf-8")
    for token in ("Low Block","High Press","Counterattacking","Projected xG","Win probability","selenium","requests.get","subprocess"):
        assert token not in source

def test_teams_apptest_four_tabs_and_representative_clubs():
    app=AppTest.from_file(str(ROOT/"app.py"),default_timeout=40).run();app.sidebar.radio(key="page_nav").set_value("Teams").run()
    assert not app.exception and [tab.label for tab in app.tabs]==list(TABS)
    selector=next(x for x in app.selectbox if x.label=="Club")
    for name in ("Arsenal","Manchester United","AFC Bournemouth","Coventry City"):
        selector.set_value(name).run();assert not app.exception
        assert next(x for x in app.selectbox if x.label=="Club").value==name
    selector=next(x for x in app.selectbox if x.label=="Club");selector.set_value("Coventry City").run();toggle=next(x for x in app.toggle if x.label=="Compare to 2025/26");toggle.set_value(True).run()
    assert not app.exception and any("No 2025/26 Premier League comparison available" in x.value for x in app.info)
