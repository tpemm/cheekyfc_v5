import numpy as np
import pandas as pd

from analytics.players.profile_overview import DEFAULT_RADAR_KEYS, EXACT_STATS, OVERVIEW_METRICS, exact_stats_frame, overview_bars, overview_radar_records, qualitative_label, valid_radar_records
from components.player_radar import build_player_radar


def players():
    rows=[]
    for i in range(6):
        rows.append({"fantrax_player_id":f"p{i}","historical_fantrax_player_id":f"h{i}","registry_player_id":f"r{i}","player_name":f"Player {i}","fantrax_position":"M","canonical_position":"M",
            "current_ghost_per_start":5+i,"historical_ghost_per_start":4+i,"current_points_per_start":10+i,"historical_points_per_start":9+i,"current_fantasy_points":20+i,"historical_fantasy_points":200+i,"current_starts":2+i,"historical_starts":20+i,
            "current_xgi_per_90":.2+i/10,"historical_xgi_per_90":.3+i/10,"current_start_percentage":60+i,"historical_start_percentage":70+i,"current_minutes":180+i,"historical_minutes":1800+i,"projected_minutes_percentage":80+i,"next_five_fixture_ease_percentile":50+i})
    return pd.DataFrame(rows)


def weekly():
    return pd.DataFrame([{"fantrax_player_id":f"p{i}","fantasy_points":10+i,"period_complete":True} for i in range(6)])


def historical_weekly():
    return pd.DataFrame([{"fantrax_player_id":f"*h{i}*","mgr_fantasy_points":15+i,"avail_fpts":np.nan} for i in range(6)])


def test_default_radar_fields_are_exactly_the_approved_four():
    assert DEFAULT_RADAR_KEYS==("ghost_start","points_start","season_points","games_started")
    assert [OVERVIEW_METRICS[key][0] for key in DEFAULT_RADAR_KEYS]==["Ghost / Start","Points / Start","Season Points","Games Started"]


def test_edit_metric_catalog_supports_three_through_eight_in_stable_order():
    frame=players(); keys=tuple(OVERVIEW_METRICS)
    assert len(keys)>=8
    assert len(overview_radar_records(frame,frame.iloc[0],keys[:3],"League")[0]["metrics"])==3
    assert [metric["key"] for metric in overview_radar_records(frame,frame.iloc[0],keys[:8],"League")[0]["metrics"]]==list(keys[:8])


def test_single_mode_omits_missing_axes_and_overlay_keeps_identical_shared_axes():
    frame=players(); frame.loc[0,"current_fantasy_points"]=np.nan
    records=overview_radar_records(frame,frame.iloc[0],DEFAULT_RADAR_KEYS,"League")
    current=valid_radar_records(records,"Current Season"); overlay=valid_radar_records(records,"Overlay Both")
    assert "season_points" not in [metric["key"] for metric in current[0]["metrics"]]
    assert [metric["key"] for metric in overlay[0]["metrics"]]==[metric["key"] for metric in overlay[1]["metrics"]]
    assert all(metric["raw"]!=0 for record in overlay for metric in record["metrics"])


def test_radar_polygon_explicitly_closes_for_three_through_eight_axes():
    for count in range(3,9):
        metrics=[{"key":str(i),"label":f"Metric {i}","raw":i,"formatted":str(i),"percentile":50+i,"rank":i+1,"peer_count":20,"peer_group":"League","source":"test","low_peers":False} for i in range(count)]
        figure=build_player_radar([{"player_id":"p","player_name":"Player","metrics":metrics}],minimum_metrics=3)
        trace=figure.data[0]
        assert len(trace.r)==count+1 and trace.r[0]==trace.r[-1]
        assert len(trace.theta)==count+1 and trace.theta[0]==trace.theta[-1]


def test_exact_stats_modes_use_only_established_season_fields():
    row=players().iloc[0]
    assert tuple(EXACT_STATS)==("points_start","ghost_start","season_points","games_started","xgi_90","minutes_outlook")
    current=exact_stats_frame(row,"Current Season"); historical=exact_stats_frame(row,"2025/26 Historical"); overlay=exact_stats_frame(row,"Overlay Both")
    assert list(current)==["Stat","2026/27"] and list(historical)==["Stat","2025/26"]
    assert list(overlay)==["Stat","2026/27","2025/26"]
    assert pd.isna(overlay.loc[overlay.Stat.eq("Minutes Outlook"),"2025/26"]).all()
    assert overlay.loc[overlay.Stat.eq("xGI / 90"),"2025/26"].iat[0]==row.historical_xgi_per_90


def test_exactly_five_transparent_bars_and_historical_fixture_is_current_context():
    frame=players(); row=frame.iloc[0]
    current=overview_bars(frame,row,"Current Season","League",weekly(),historical_weekly())
    historical=overview_bars(frame,row,"2025/26 Historical","Position",weekly(),historical_weekly())
    assert [item["label"] for item in current]==["Fantasy Production","Points Floor","Points Ceiling","Playing Time","Next 5 Fixture Outlook"]
    assert len(historical)==5
    assert current[0]["basis"]=="Points / Start" and current[1]["basis"]=="Ghost / Start"
    assert current[2]["basis"]=="Highest completed weekly score"
    assert current[3]["basis"]=="Minutes Outlook" and historical[3]["basis"]=="Start %"
    assert historical[4]["basis"].startswith("Current Context")


def test_missing_bar_inputs_remain_unavailable_and_labels_are_deterministic():
    frame=players(); frame.loc[0,["current_points_per_start","current_ghost_per_start","projected_minutes_percentage"]]=np.nan
    bars=overview_bars(frame,frame.iloc[0],"Current Season","League",pd.DataFrame(),pd.DataFrame())
    assert all(pd.isna(bars[index]["percentile"]) for index in (0,1,2,3))
    assert [qualitative_label(value) for value in (95,80,50,25,10,np.nan)]==["Elite","Strong","League Average","Below Average","Weak","Unavailable"]


def test_league_and_position_peer_counts_are_respected():
    frame=players(); frame.loc[4:,"canonical_position"]="F"
    league=overview_radar_records(frame,frame.iloc[0],DEFAULT_RADAR_KEYS,"League")[0]
    position=overview_radar_records(frame,frame.iloc[0],DEFAULT_RADAR_KEYS,"Position")[0]
    assert league["metrics"][0]["peer_count"]==6 and position["metrics"][0]["peer_count"]==4
