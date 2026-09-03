import numpy as np
import pandas as pd

from analytics.players.comparison import radar_records
from analytics.players.comparison_display import (
    CORE_ROWS, comparison_card_html, comparison_cards, comparison_exact_table,
    comparison_table_styler, format_next_fixture,
)
from components.design_tokens import COLORS
from components.player_radar import build_player_radar


def players():
    rows=[]
    for index,name in enumerate(("Alpha","Bravo","Charlie","Delta","Echo")):
        rows.append({
            "registry_player_id":f"r{index}","fantrax_player_id":f"p{index}","historical_fantrax_player_id":f"h{index}",
            "player_name":name,"premier_league_club":f"Club {index}","fantrax_position":"M","canonical_position":"M",
            "available":index==1,"current_fantasy_team":None if index==1 else f"Team {index}","opening_opponent":"@LIV Sat 9:00AM" if index==0 else "AVL Sun 10:00AM",
            "current_fantasy_points":50-index,"current_points_per_game":10-index,"current_points_per_start":12-index,"current_points_per_90":14-index,
            "current_ghost_per_game":5-index/2,"current_ghost_per_start":6-index/2,"current_ghost_per_90":7-index/2,
            "current_goals":4-index/2,"current_assists":3-index/2,"current_xgi_per_game":.4-index/20,"current_xgi_per_start":.5-index/20,"current_xgi_per_90":.6-index/20,
            "current_key_passes_per_start":3.5-index/10,"current_key_passes_per_90":3-index/10,"projected_minutes_percentage":90-index,"next_five_fixture_ease_percentile":70-index,
            "historical_fantasy_points":250-index,"historical_points_per_appearance":11-index/2,"historical_points_per_start":13-index/2,"historical_points_per_90":15-index/2,
            "historical_ghost_per_appearance":6-index/2,"historical_ghost_per_start":7-index/2,"historical_ghost_per_90":8-index/2,"historical_xgi_per_90":.7-index/20,
            "fantrax_projected_points":300-index,"minutes_confidence":85-index,"team_strength_percentile":80-index,"draft_score":75-index,"adp":index+1,
        })
    return pd.DataFrame(rows)


def current_weekly():
    rows=[]
    for index in range(5):
        rows.extend((
            {"fantrax_player_id":f"p{index}","period":1,"period_complete":True,"opponent":"LIV","fantasy_points":10+index,"minutes":90,"start":1,"appearance":1},
            {"fantrax_player_id":f"p{index}","period":2,"period_complete":True,"opponent":"@AVL","fantasy_points":6+index,"minutes":45,"start":1,"appearance":1},
        ))
    return pd.DataFrame(rows)


def historical_weekly():
    rows=[]
    for index in range(5):
        rows.extend((
            {"fantrax_player_id":f"*h{index}*","fantrax_gw":1,"mgr_opponent":"LIV","mgr_fantasy_points":12+index,"mgr_min":90,"mgr_gs":1,"mgr_gp":1},
            {"fantrax_player_id":f"*h{index}*","fantrax_gw":2,"mgr_opponent":"@AVL","mgr_fantasy_points":8+index,"mgr_min":90,"mgr_gs":1,"mgr_gp":1},
        ))
    return pd.DataFrame(rows)


def test_two_through_five_cards_render_identity_context_and_selected_rates():
    frame=players()
    for count in range(2,6):
        cards=comparison_cards(frame.iloc[:count],"Current Season","Per Start",current_weekly(),historical_weekly())
        assert len(cards)==count
        assert [card["player_id"] for card in cards]==[f"r{i}" for i in range(count)]
    first,available=comparison_cards(frame.iloc[:2],"Current Season","Per Start",current_weekly(),historical_weekly())
    assert first["player_name"]=="Alpha" and first["club"]=="Club 0" and first["position"]=="M"
    assert first["points"]==12 and first["ghost"]==6 and first["xgi"]==.5
    assert first["minutes_outlook"]==90 and first["next_fixture"]=="LIV (A)"
    assert first["home_avg"]==10 and first["away_avg"]==6
    assert first["owner"]=="Team 0" and available["owner"]=="Available"
    html=comparison_card_html(first)
    for label in ("Points / Start","Ghost / Start","xGI / Start","Minutes Outlook","Next Fixture","Home Avg","Away Avg","Owner / Available"): assert label in html


def test_next_fixture_uses_only_supported_venue_evidence():
    assert format_next_fixture(pd.Series({"opening_opponent":"@Liverpool Sat"}))=="Liverpool (A)"
    assert format_next_fixture(pd.Series({"opening_opponent":"Aston Villa","opening_venue":"H"}))=="Aston Villa (H)"
    assert format_next_fixture(pd.Series({"opening_opponent":"Liverpool"}))=="Liverpool"
    assert format_next_fixture(pd.Series({"opening_opponent":np.nan}))=="—"


def test_radar_supports_three_and_eight_axes_two_and_five_players_without_zero_fill():
    frame=players()
    keys3=("projected_points","projected_minutes","fixture_ease")
    records=radar_records(frame,frame.iloc[:2],keys3,"Per Start","League")
    assert build_player_radar(records,minimum_metrics=3) is not None
    keys8=("projected_points","projected_minutes","minutes_confidence","club_strength","fixture_ease","draft_score","adp","draft_rank")
    frame["adp"]=[1,2,3,4,np.nan]; frame["draft_rank"]=[2,3,4,5,np.nan]
    records=radar_records(frame,frame.iloc[:5],keys8,"Per Start","Position")
    figure=build_player_radar(records,minimum_metrics=3)
    assert len(figure.data)==5 and all(trace.fill is None for trace in figure.data)
    assert all(value is None or value!=0 for trace in figure.data for value in trace.r)
    assert [metric["key"] for metric in records[0]["metrics"]]==list(keys8)


def test_exact_table_has_core_rows_dynamic_metric_no_duplicates_and_no_winner():
    frame=players().iloc[:2]
    table,directions=comparison_exact_table(frame,"Current Season","Per Start",("current_points","current_key_passes","fixture_ease"),current_weekly(),historical_weekly())
    required={label for _,label,_,_ in CORE_ROWS}
    assert required.issubset(set(table.Stat))
    assert "Current Key Passes / Start" in set(table.Stat)
    assert table.Stat.tolist().count("Next 5 Fixture Ease")==1
    assert "Winner" not in table and directions["Current Key Passes / Start"] is True


def test_best_value_styles_are_direction_aware_tie_safe_and_missing_safe():
    table=pd.DataFrame({"Stat":["High","Low","Tie","Missing"],"A":[10,1,5,np.nan],"B":[8,2,5,4]})
    styler=comparison_table_styler(table,{"High":True,"Low":False,"Tie":True,"Missing":True})._compute()
    ctx=styler.ctx
    expected=("color",COLORS["positive"])
    assert expected in ctx[(0,1)] and ("font-weight","700") in ctx[(0,1)]
    assert expected in ctx[(1,1)] and expected not in ctx[(1,2)]
    assert expected in ctx[(2,1)] and expected in ctx[(2,2)]
    assert expected not in ctx.get((3,1),[]) and expected in ctx[(3,2)]


def test_catalog_direction_is_preserved_for_dynamic_lower_is_better_rows():
    table,directions=comparison_exact_table(players().iloc[:2],"Custom","Per Start",("adp","projected_points","fixture_ease"),current_weekly(),historical_weekly())
    assert directions["ADP"] is False
    styled=comparison_table_styler(table,directions)._compute().ctx
    row=table.index[table.Stat.eq("ADP")][0]
    assert ("color",COLORS["positive"]) in styled[(row,1)]
    assert ("color",COLORS["positive"]) not in styled.get((row,2),[])
