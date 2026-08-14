import math
import pandas as pd
import pytest

from analytics.players.comparison_catalog import CATALOG, MODE_DEFAULTS, PRESETS, validate_metrics
from analytics.players.comparison import COMPARE_KEY, add_compare, clear_compare, prepare_percentiles, primary_position, radar_records, remove_compare
from components.player_radar import build_player_radar, comparison_values_frame, raw_values_frame

METRICS=("projected_points","projected_minutes","minutes_confidence","club_strength","fixture_ease","draft_score")

def players():
    return pd.DataFrame({
        "fantrax_player_id":["a","b","c","d","e"],"player_name":["A","B","C","D","E"],
        "canonical_position":["F","F","M","M",None],"fantrax_position":["F","F","M","M","D,M"],
        "fantrax_projected_points":[100,80,60,40,None],"projected_minutes_percentage":[90,80,70,60,50],
        "minutes_confidence":[95,85,75,65,55],"team_strength_percentile":[90,80,70,60,50],
        "next_five_fixture_ease_percentile":[70,60,50,40,30],"draft_score":[90,80,70,60,50],
        "adp":[1,2,3,4,None],"historical_fantasy_points":[200,150,100,50,None],
        "historical_points_per_appearance":[10,8,6,4,None],"historical_points_per_start":[12,10,8,6,None],
        "historical_points_per_90":[14,12,10,8,None],
    })

def test_catalog_is_complete_and_controlled():
    assert PRESETS and MODE_DEFAULTS
    for key,metric in CATALOG.items():
        assert key and metric.label and metric.family and metric.higher_is_better is not None
        assert metric.rate_bases and metric.modes and metric.source and metric.missing
    with pytest.raises(ValueError): validate_metrics(("arbitrary_column",)*4)
    with pytest.raises(ValueError): validate_metrics(("draft_score",)*4)
    with pytest.raises(ValueError): validate_metrics(METRICS[:3])
    with pytest.raises(ValueError): validate_metrics(tuple(CATALOG)[:9])

def test_league_percentiles_direction_ties_and_missing_values():
    frame=players(); frame.loc[1,"fantrax_projected_points"]=100
    output=prepare_percentiles(frame,("projected_points","adp","projected_minutes","club_strength"),"Total")
    assert output.loc[0,"projected_points__league_pct"] == output.loc[1,"projected_points__league_pct"]
    assert output.loc[0,"adp__league_pct"] > output.loc[3,"adp__league_pct"]
    assert math.isnan(output.loc[4,"projected_points__league_pct"])

def test_position_percentiles_use_one_primary_peer_group():
    frame=players(); output=prepare_percentiles(frame,METRICS[:4],"Per 90")
    assert output.loc[0,"peer_position"]=="F" and output.loc[2,"peer_position"]=="M"
    assert output.loc[4,"peer_position"]=="D"
    assert output.loc[0,"projected_points__position_pct"] > output.loc[1,"projected_points__position_pct"]

def test_rate_basis_changes_capable_metric_but_not_natural_percentages():
    frame=players(); total=prepare_percentiles(frame,("fantasy_production","projected_minutes","draft_score","fixture_ease"),"Total")
    per90=prepare_percentiles(frame,("fantasy_production","projected_minutes","draft_score","fixture_ease"),"Per 90")
    assert total.loc[0,"fantasy_production__raw"]==200 and per90.loc[0,"fantasy_production__raw"]==14
    assert total.loc[0,"projected_minutes__raw"]==per90.loc[0,"projected_minutes__raw"]==90

def test_radar_preserves_raw_values_hover_order_and_missing():
    frame=players(); selected=frame.iloc[:2]; records=radar_records(frame,selected,METRICS,"Per 90","League")
    figure=build_player_radar(records); assert figure is not None
    assert all((value is None or 0<=value<=100) for trace in figure.data for value in trace.r)
    assert "100.0" in figure.data[0].text[0] and "percentile" in figure.data[0].text[0]
    assert raw_values_frame(records).iloc[0]["Raw Value"]=="100.0"
    assert [m["key"] for m in records[0]["metrics"]]==list(METRICS)

def test_fewer_than_four_valid_metrics_does_not_draw_polygon():
    frame=players()
    for column in ("fantrax_projected_points","projected_minutes_percentage","minutes_confidence"): frame[column]=float("nan")
    records=radar_records(frame,frame.iloc[[0]],METRICS,"Total","League")
    assert build_player_radar(records) is None

def test_compare_state_prevents_duplicates_caps_at_five_and_clears():
    state={}
    for pid in "abcde": assert add_compare(state,pid)[0]
    assert not add_compare(state,"a")[0] and not add_compare(state,"f")[0]
    remove_compare(state,"c"); assert state[COMPARE_KEY]==["a","b","d","e"]
    clear_compare(state); assert state[COMPARE_KEY]==[]

def test_direction_aware_best_highlight_has_no_winner_column_and_skips_missing():
    frame=players(); records=radar_records(frame,frame.iloc[[0,4]],METRICS,"Total","League")
    table=comparison_values_frame(records)
    assert "Winner" not in table.columns and table.iloc[0]["A"].startswith("●")
    assert table.iloc[0]["E"]=="—"
