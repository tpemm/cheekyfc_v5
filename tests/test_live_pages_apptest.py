import re
from streamlit.testing.v1 import AppTest


def run_page(page):
    app=AppTest.from_file("app.py",default_timeout=30).run()
    app.sidebar.radio(key="page_nav").set_value(page).run()
    return app


def test_update_pipeline_apptest():
    app=run_page("Operations Center")
    assert not app.exception
    assert any("Refresh League" in item.value for item in app.markdown)
    rendered=" ".join(item.value for item in app.markdown)
    assert "Current Period" in rendered and re.search(r"Current Period.*?GW\d+",rendered) and "GW38" not in rendered
    assert any({"Status","Area","Last Update","Rows","Version"}.issubset(item.value.columns) for item in app.dataframe)


def test_players_apptest():
    app=run_page("Players")
    assert not app.exception
    assert app.selectbox


def test_teams_apptest():
    app=run_page("Teams")
    assert not app.exception
    assert any(item.label=="Club" for item in app.selectbox)
    assert any("Team Directory" in item.value for item in app.markdown)


def test_players_comparison_apptest():
    app=run_page("Players")
    app.get("button_group")[0].set_value("Player Comparison").run()
    selector=next(item for item in app.multiselect if item.label.startswith("Compare 2"))
    selector.set_value(selector.options[:2]).run()
    assert not app.exception
    rendered=" ".join(item.value for item in app.markdown)
    assert "Compare Players" in rendered and "ft-compare-card" in rendered
    assert any(item.label=="Edit Metrics (3–8)" for item in app.multiselect)
    assert app.get("plotly_chart")
    exact=[item.value for item in app.dataframe if "Stat" in getattr(item.value,"columns",[])]
    assert exact and "Winner" not in exact[-1].columns


def legacy_players_historical_profile_radar_apptest():
    app=run_page("Players")
    navigation=app.get("button_group")[0]
    navigation.set_value("Player Profile").run()
    assert [tab.label for tab in app.tabs]==["Overview","Performance","Playing Time","Advanced","Pitch","Fixtures","History","Ownership / Draft"]
    selector=next(item for item in app.selectbox if item.label=="Player")
    historical=next(option for option in selector.options if option.startswith("Abdukodir Khusanov"))
    selector.set_value(historical).run()
    assert not app.exception
    assert app.get("plotly_chart")
    mode=next(item for item in app.selectbox if item.label=="Mode")
    assert mode.value=="Current Season"
    mode.set_value("2025/26 Historical").run()
    assert next(item for item in app.selectbox if item.label=="Mode").value=="2025/26 Historical"
    assert not any(item.label=="Preset" for item in app.selectbox)
    assert any(item.label=="Edit Metrics (3–8)" for item in app.multiselect)
    exact=[item.value for item in app.dataframe if {"Stat","2025/26"}.issubset(item.value.columns)]
    assert exact and exact[0].Stat.tolist()==["Points / Start","Ghost / Start","Season Points","Games Started","xGI / 90","Minutes Outlook"]
    percentile_html="".join(item.value for item in app.markdown if "ft-percentile" in item.value)
    assert 'class="ft-percentile"' not in percentile_html
    rendered=" ".join(item.value for item in app.markdown)
    for section in ("Points by Gameweek","Last 5 Gameweeks","Home vs Away Average","Points Breakdown","Full Gameweek Stats"):
        assert section in rendered
    gameweek_tables=[item.value for item in app.dataframe if {"GW","Opponent","H/A","FDR","Minutes","Started","Points","Ghost Points","Goals","Assists"}.issubset(item.value.columns)]
    assert gameweek_tables


def test_managers_apptest():
    app=run_page("Managers")
    assert not app.exception
    assert app.selectbox


def test_players_research_profile_and_historical_overlay_apptest():
    app=run_page("Players");app.get("button_group")[0].set_value("Player Profile").run()
    assert [tab.label for tab in app.tabs]==["Overview","Match Analysis","Role & Tactical","Advanced"]
    selector=next(item for item in app.selectbox if item.label=="Player");waiver=next(option for option in selector.options if option.startswith("Vitaly Janelt"));selector.set_value(waiver).run()
    assert not app.exception
    rendered=" ".join(item.value for item in app.markdown)
    for section in ("Fantasy Profile","Attacking Profile","Defensive Profile","Season Trend","Next Fixtures","Full Gameweek Stats"):assert section in rendered
    comparison=next(item for item in app.toggle if item.label=="Compare to 2025/26");assert comparison.value is False;comparison.set_value(True).run();assert not app.exception
    assert next(item for item in app.toggle if item.label=="Compare to 2025/26").value is True
    gameweek=[item.value for item in app.dataframe if {"GW","Opponent","H/A","FDR","Pts","Ghost","GP","GS","Min"}.issubset(getattr(item.value,"columns",[]))]
    assert gameweek and gameweek[0].iloc[0][["GP","GS","Min"]].tolist()==[1,1,90]

def test_maxim_and_no_history_overview_comparison_apptest():
    app=run_page("Players");app.get("button_group")[0].set_value("Player Profile").run()
    selector=next(item for item in app.selectbox if item.label=="Player")
    maxim=next(option for option in selector.options if option.startswith("Maxim De Cuyper"));selector.set_value(maxim).run()
    toggle=next(item for item in app.toggle if item.label=="Compare to 2025/26");assert not toggle.disabled
    current_metrics=[item.value for item in app.metric];toggle.set_value(True).run();assert not app.exception
    assert len(app.get("plotly_chart"))>=3 and [item.value for item in app.metric]==current_metrics
    assert any({"Metric","2026/27","2025/26"}.issubset(getattr(item.value,"columns",set())) for item in app.dataframe)
    toggle=next(item for item in app.toggle if item.label=="Compare to 2025/26");toggle.set_value(False).run();assert not app.exception
    selector=next(item for item in app.selectbox if item.label=="Player")
    no_history=next(option for option in selector.options if option.startswith("Mamadou Sangare"));selector.set_value(no_history).run()
    toggle=next(item for item in app.toggle if item.label=="Compare to 2025/26");assert toggle.disabled or not toggle.value

def test_player_overview_representative_visual_states_apptest():
    app=run_page("Players");app.get("button_group")[0].set_value("Player Profile").run()
    for name in ("Vitaly Janelt","Mamadou Sangare","Piero Hincapi","Carl Rushworth","Jordan Henderson","Alisson Becker","Alexander Isak"):
        selector=next(item for item in app.selectbox if item.label=="Player");choice=next(option for option in selector.options if option.startswith(name));selector.set_value(choice).run()
        assert not app.exception
        rendered=" ".join(item.value for item in app.markdown).lower()
        assert "fantasy profile" in rendered and "season trend" in rendered and ">none<" not in rendered and ">nan<" not in rendered

def test_match_analysis_current_and_historical_research_apptest():
    app=run_page("Players");app.get("button_group")[0].set_value("Player Profile").run();selector=next(x for x in app.selectbox if x.label=="Player");selector.set_value(next(x for x in selector.options if x.startswith("Maxim De Cuyper"))).run()
    season=next(x for x in app.selectbox if x.label=="Match Analysis Season");assert season.value=="2026/27 Current"
    rendered=" ".join(x.value for x in app.markdown);assert "Production Distribution" in rendered and "Match Performance" in rendered and "Match History" in rendered
    assert any({"GW","Date","Opp","Position","Formation","Rating","FPts","Ghost","xG","xA"}.issubset(getattr(x.value,"columns",set())) for x in app.dataframe)
    season.set_value("2025/26 Historical").run();assert not app.exception
    table=next(x.value for x in app.dataframe if {"GW","Date","Opp","Rating","FPts"}.issubset(getattr(x.value,"columns",set())))
    assert len(table)==36 and table.Rating.notna().mean()>.8

def test_jack_hinshelwood_corrected_ghost_propagates_apptest():
    app=run_page("Players");app.get("button_group")[0].set_value("Player Profile").run();selector=next(x for x in app.selectbox if x.label=="Player");selector.set_value(next(x for x in selector.options if x.startswith("Jack Hinshelwood"))).run();assert not app.exception
    ghost_metrics=[x.value for x in app.metric if x.label in {"GHOST PTS/START","Ghost / Start"}]
    assert ghost_metrics and all(float(value.replace(",",""))==9.5 for value in ghost_metrics)
    tables=[x.value for x in app.dataframe if {"GW","FPts","Ghost"}.issubset(getattr(x.value,"columns",set()))]
    assert any(len(table)==1 and table.iloc[0].FPts==28.5 and table.iloc[0].Ghost==9.5 for table in tables)


def test_live_league_hub_apptest():
    app=run_page("League Hub")
    assert not app.exception
    assert any("League Table" in item.value for item in app.markdown)
    assert any("Manager Awards" in item.value for item in app.markdown)
