import numpy as np
import pandas as pd

from analytics.players.match_analysis import (
    DEFAULT_COLUMNS,
    calculate_home_away_split,
    calculate_points_breakdown,
    prepare_gameweek_table,
    prepare_last_n_periods,
    prepare_player_gameweek_frame,
    supported_optional_columns,
)


def current_weekly():
    rows=[]
    for period in range(1,8):
        rows.append({"fantrax_player_id":"p1","period":period,"period_complete":period<7,"fantasy_points":-2 if period==2 else period*2,"ghost_points":period,"minutes":90 if period!=3 else 20,"appearance":1,"start":0 if period==3 else 1,"opponent":("@AWY" if period%2==0 else "HOM")+" Sat","roster_status":"ACTIVE","goals":0,"assists":0,"shots":period,"xg":period/10})
    rows.append({"fantrax_player_id":"other","period":1,"period_complete":True,"fantasy_points":99})
    return pd.DataFrame(rows)


def historical_weekly():
    return pd.DataFrame([
        {"fantrax_player_id":"*old*","fantrax_gw":1,"mgr_fantasy_points":10,"mgr_min":90,"mgr_gp":1,"mgr_gs":1,"mgr_opponent":"AAA","mgr_status":"ACTIVE","mgr_g":1,"mgr_at":0,"mgr_kp":2,"xg":.5,"xa":.1},
        {"fantrax_player_id":"*old*","fantrax_gw":2,"mgr_fantasy_points":-3,"mgr_min":30,"mgr_gp":1,"mgr_gs":0,"mgr_opponent":"@BBB","mgr_status":"RESERVE","mgr_g":0,"mgr_at":0,"mgr_kp":0,"xg":0,"xa":0},
    ])


def test_current_periods_use_only_completed_rows_and_preserve_negatives_and_gaps():
    result=prepare_player_gameweek_frame(current_weekly(),"p1",season="2026/27")
    assert result.period.tolist()==[1,2,3,4,5,6]
    assert result.loc[result.period.eq(2),"fantasy_points"].iat[0]==-2
    assert 7 not in result.period.tolist()
    missing=current_weekly()[~current_weekly().period.eq(4)]
    assert prepare_player_gameweek_frame(missing,"p1",season="2026/27").period.tolist()==[1,2,3,5,6]


def test_last_five_uses_latest_available_periods_in_order_without_padding():
    frame=prepare_player_gameweek_frame(current_weekly(),"p1",season="2026/27")
    assert prepare_last_n_periods(frame).period.tolist()==[2,3,4,5,6]
    assert prepare_last_n_periods(frame.head(3)).period.tolist()==[1,2,3]


def test_historical_gameweeks_work_without_current_data():
    result=prepare_player_gameweek_frame(historical_weekly(),"old",season="2025/26")
    assert result.period.tolist()==[1,2] and result.fantasy_points.tolist()==[10,-3]
    assert result.venue.tolist()==["H","A"] and result.opponent.tolist()==["AAA","BBB"]
    assert result.ghost_points.isna().all()


def test_gameweek_table_defaults_filters_and_supported_optional_columns():
    frame=prepare_player_gameweek_frame(current_weekly(),"p1",season="2026/27")
    assert tuple(prepare_gameweek_table(frame).columns)==DEFAULT_COLUMNS
    assert prepare_gameweek_table(frame,home_away="Home")["H/A"].eq("H").all()
    assert prepare_gameweek_table(frame,home_away="Away")["H/A"].eq("A").all()
    assert prepare_gameweek_table(frame,appearance="Started")["Started"].eq("Yes").all()
    assert len(prepare_gameweek_table(frame,appearance="Sub"))==1
    assert "Shots" in supported_optional_columns(frame) and "Blocks" not in supported_optional_columns(frame)
    table=prepare_gameweek_table(frame,extra_columns=("Shots","xG")); assert {"Shots","xG"}.issubset(table)


def test_dnp_is_only_classified_with_proven_roster_context():
    base=pd.DataFrame([{"fantrax_player_id":"p","period":1,"period_complete":True,"minutes":0,"appearance":0,"start":0,"fantasy_points":0},{"fantrax_player_id":"p","period":2,"period_complete":True,"minutes":0,"appearance":0,"start":0,"fantasy_points":0,"roster_status":"ACTIVE"}])
    result=prepare_player_gameweek_frame(base,"p",season="2026/27")
    assert pd.isna(result.iloc[0].appearance_type) and result.iloc[1].appearance_type=="DNP"
    assert prepare_gameweek_table(result).Points.tolist()==[0,0]


def test_fdr_filter_applies_only_when_supported():
    frame=prepare_player_gameweek_frame(current_weekly(),"p1",season="2026/27"); frame["fdr"]=[1,2,3,4,5,1]
    assert prepare_gameweek_table(frame,fdr_range=(2,4)).GW.tolist()==[2,3,4]
    frame["fdr"]=np.nan; assert len(prepare_gameweek_table(frame,fdr_range=(2,4)))==len(frame)


def test_home_away_rates_and_invalid_denominators():
    frame=prepare_player_gameweek_frame(current_weekly(),"p1",season="2026/27")
    split=calculate_home_away_split(frame,"Per Game").set_index("Venue")
    assert split.loc["Home","Sample"]==3 and split.loc["Away","Sample"]==3
    assert split.loc["Home","Average"]==6 and split.loc["Away","Average"]==6
    only_home=frame[frame.venue.eq("H")]; away=calculate_home_away_split(only_home,"Per Start").set_index("Venue").loc["Away"]
    assert away.Sample==0 and pd.isna(away.Average)


def test_points_breakdown_reconciles_and_negative_geometry_is_safe():
    frame=pd.DataFrame({"fantasy_points":[10,-2,0],"ghost_points":[4,1,0]})
    result=calculate_points_breakdown(frame)
    assert result["total"]==8 and result["ghost"]==5 and result["non_ghost"]==3 and result["pie_safe"]
    negative=calculate_points_breakdown(pd.DataFrame({"fantasy_points":[-2],"ghost_points":[1]}))
    assert negative["non_ghost"]==-3 and not negative["pie_safe"]
    unavailable=calculate_points_breakdown(pd.DataFrame({"fantasy_points":[10],"ghost_points":[np.nan]})); assert pd.isna(unavailable["non_ghost"])


def test_double_gameweek_rows_remain_deterministic_match_detail():
    frame=current_weekly(); duplicate=frame.iloc[[0]].copy(); duplicate["opponent"]="@SECOND"; frame=pd.concat([frame,duplicate],ignore_index=True)
    result=prepare_player_gameweek_frame(frame,"p1",season="2026/27")
    assert result[result.period.eq(1)].opponent.tolist()==["HOM","SECOND"]
