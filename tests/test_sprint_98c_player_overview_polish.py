import inspect
import pandas as pd

from analytics.players.research_overview import fixture_cards_html,format_overview_value,set_piece_chips
from components.player_radar import build_player_radar

def test_kpi_formatting_contract():
    assert format_overview_value("current_fantasy_points",35)=="35.0"
    assert format_overview_value("current_points_per_start",12.1764705)=="12.18"
    assert format_overview_value("current_xg_per_90",.094086)=="0.09"

def test_missing_values_never_display_as_text_nan():
    for value in (None,pd.NA,float("nan"),"nan","None"):assert format_overview_value("x",value)=="—"

def test_set_piece_labels_are_compact():
    frame=pd.DataFrame([{"set_piece_type":"direct_free_kick","rank":1},{"set_piece_type":"corner","rank":2}])
    assert set_piece_chips(frame)==["Corners #2","Direct FK #1"]

def test_fixture_cards_escape_and_preserve_fdr():
    html=fixture_cards_html(pd.DataFrame([{"GW":2,"Opponent":"A&B","H/A":"A","FDR":4}]))
    assert "GW 2" in html and "A&amp;B" in html and "A · FDR 4" in html

def test_radar_current_dominant_and_historical_secondary():
    metrics=lambda values:[{"label":str(i),"formatted":str(v),"percentile":v,"rank":1,"peer_count":10} for i,v in enumerate(values)]
    figure=build_player_radar([{"player_name":"2026/27 Current","metrics":metrics([10,20,30])},{"player_name":"2025/26","metrics":metrics([20,30,40])}],minimum_metrics=3,simple_hover=True)
    assert figure.data[0].line.width>figure.data[1].line.width and figure.data[1].line.dash=="dot" and not figure.data[0].connectgaps

def test_four_card_and_responsive_contracts_present():
    import views.players as players
    from components.styles import global_css
    source=inspect.getsource(players._compact_profile);css=global_css()
    assert "ui.columns(4)" in source and "profile_columns[3]" in source
    assert "@media(max-width:1100px)" in css and "@media(max-width:640px)" in css

def test_single_toggle_tooltips_and_no_network_render():
    import views.players as players
    source=inspect.getsource(players._compact_profile);render=inspect.getsource(players.render).lower()
    assert source.count('toggle("Compare to 2025/26"')==1 and "partial derived estimate" in source
    assert "requests." not in render and "playwright" not in render

def test_research_table_abbreviations_and_contextual_advanced_control():
    import views.players as players
    source=inspect.getsource(players._compact_profile)
    for label in ('"Pts"','"GS"','"Min"','"AC"','"TkW"','"AER"'):assert label in source
    assert 'selectbox("Advanced data season"' in source
