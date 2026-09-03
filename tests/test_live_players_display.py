import numpy as np
import pandas as pd

from views.players import (
    LIVE_RATE_BASES,
    SORT_OPTIONS,
    historical_comparison_frame,
    live_database_frame,
    live_sort_field,
    radar_diagnostics,
    season_radar_records,
    shared_radar_records,
)
from views.players import sort_players
from components.player_radar import build_player_radar


def players():
    rows=[]
    for index in range(6):
        rows.append({
            "registry_player_id":f"registry-{index}", "fantrax_player_id":f"fantrax-{index}",
            "player_name":"Duplicate Name" if index<2 else f"Player {index}",
            "premier_league_club":"AAA", "fantrax_position":"M,F", "canonical_position":"M",
            "available":index%2==0, "current_manager_name":None if index%2==0 else "Manager",
            "current_points_per_game":10+index, "current_points_per_start":12+index, "current_points_per_90":14+index,
            "current_ghost_per_game":5+index, "current_ghost_per_start":6+index, "current_ghost_per_90":7+index,
            "current_xgi_per_game":.2+index/10, "current_xgi_per_start":.3+index/10, "current_xgi_per_90":.4+index/10,
            "current_start_percentage":60+index, "current_minutes_per_game":50+index,
            "historical_points_per_appearance":9+index, "historical_points_per_start":11+index, "historical_points_per_90":13+index,
            "historical_ghost_per_appearance":4+index, "historical_ghost_per_start":5+index, "historical_ghost_per_90":6+index,
            "historical_xgi_per_game":.15+index/10, "historical_xgi_per_start":.25+index/10, "historical_xgi_per_90":.35+index/10,
            "historical_start_percentage":55+index, "historical_minutes_per_game":48+index,
            "projected_minutes_percentage":80+index, "next_five_fixture_ease_percentile":65-index,
            "fantrax_projected_points":200-index,
            "adp":index+1, "draft_rank":index+1, "draft_score":90-index,
        })
    return pd.DataFrame(rows)


def test_live_database_is_compact_rate_driven_and_draft_free():
    frame=players()
    assert LIVE_RATE_BASES==("Per Game","Per Start","Per 90")
    for basis,labels in (("Per Game",("Pts / Game","Ghost / Game","xGI / Game")),("Per Start",("Pts / Start","Ghost / Start","xGI / Start")),("Per 90",("Pts / 90","Ghost / 90","xGI / 90"))):
        result=live_database_frame(frame,basis)
        assert list(result.columns)==["Player","Club","Position","Fantasy Manager / Available","Ownership %","FPts","FPts/Game","FPts/Start","Ghost/Start","GP","Starts","Minutes","Goals","Assists","KP","TkW","Interceptions","Aerial Wins","Accurate Crosses","Clean Sheets","xG","xA","xG/90","xA/90"]
        assert not {"ADP","Draft Rank","Draft Score"}&set(result)
    assert live_database_frame(frame,"Per Start").iloc[0]["Fantasy Manager / Available"]=="Available"
    assert live_database_frame(frame,"Per Start").iloc[1]["Fantasy Manager / Available"]=="Manager"


def test_preseason_values_stay_missing_while_context_remains():
    frame=players()
    for column in ("current_points_per_start","current_ghost_per_start","current_xgi_per_start"): frame[column]=np.nan
    result=live_database_frame(frame,"Per Start")
    assert result[["FPts/Start","Ghost/Start"]].isna().all().all()


def test_historical_comparison_uses_existing_finalized_fields():
    row=players().iloc[0]
    result=historical_comparison_frame(row,"Per Start").set_index("Metric")
    assert result.loc["Points / Start","2025/26"]==row.historical_points_per_start
    assert result.loc["Points / Start","2026/27"]==row.current_points_per_start


def test_overlay_has_identical_axes_separate_peer_percentiles_and_no_zero_fill():
    frame=players(); frame.loc[0,"current_xgi_per_90"]=np.nan
    records=season_radar_records(frame,frame.iloc[0],"Per 90","League")
    assert [m["label"] for m in records[0]["metrics"]]==[m["label"] for m in records[1]["metrics"]]
    assert pd.isna(records[0]["metrics"][2]["percentile"])
    assert records[0]["metrics"][2]["formatted"]=="—"
    assert records[1]["metrics"][2]["percentile"]>0
    positional=season_radar_records(frame,frame.iloc[0],"Per Start","Position")
    assert all(metric["peer_group"]=="Position" for record in positional for metric in record["metrics"])


def test_duplicate_names_retain_distinct_stable_registry_identity():
    frame=players()
    assert frame.iloc[0].registry_player_id!=frame.iloc[1].registry_player_id
    assert frame.iloc[0].player_name==frame.iloc[1].player_name


def test_preseason_defaults_to_projection_and_live_defaults_to_selected_points_rate():
    frame=players(); frame["fantrax_projected_points"]=[100,np.nan,300,200,50,25]
    for basis in LIVE_RATE_BASES:
        field=live_sort_field(frame,basis)
        assert field.startswith("current_points_")
    for field in [field for field in frame if field.startswith("current_points_")]: frame[field]=np.nan
    assert live_sort_field(frame,"Per Start")=="fantrax_projected_points"
    result=sort_players(frame,live_sort_field(frame,"Per Start"),False)
    assert result.iloc[0].fantrax_player_id=="fantrax-2"
    assert pd.isna(result.iloc[-1].fantrax_projected_points)


def test_every_sort_option_maps_to_a_supported_field_and_keeps_missing_last():
    frame=players()
    assert SORT_OPTIONS==("Points","Ghost","xGI","Minutes Outlook","Next 5 Fixture Ease","Projected Points")
    for option in SORT_OPTIONS:
        frame=players()
        field=live_sort_field(frame,"Per Start",option)
        frame.loc[0,field]=np.nan
        assert sort_players(frame,field,False).iloc[-1].fantrax_player_id=="fantrax-0"


def test_three_metric_radar_and_shared_overlay_rules():
    frame=players(); records=season_radar_records(frame,frame.iloc[0],"Per Start","League",("points","ghost","start_rate"))
    assert build_player_radar(records,minimum_metrics=3) is not None
    frame.loc[0,"current_xgi_per_start"]=np.nan
    frame.loc[0,"current_start_percentage"]=np.nan
    shared=shared_radar_records(season_radar_records(frame,frame.iloc[0],"Per Start","League",("points","ghost","start_rate")))
    assert [metric["key"] for metric in shared[0]["metrics"]]==["Points","Ghost"]
    assert build_player_radar(shared,minimum_metrics=3) is None


def test_players_header_and_profile_navigation_are_not_duplicated_in_database_source():
    source=__import__("inspect").getsource(__import__("views.players",fromlist=["render"]))
    assert 'page_header(ui,"Players",badge="2026/27 · Live")' in source
    assert "Player Database\",\"Search ownership" not in source
    database_block=source.split("with tabs[0]:",1)[1].split("with tabs[1]:",1)[0]
    assert "_profile(" not in database_block
    assert 'st.session_state["players_subview"]="Player Profile"' in source


def test_shared_shell_css_has_no_negative_header_offset():
    from components.styles import global_css
    css=global_css()
    assert ".block-container { max-width:var(--ft-page-max-width); padding:3.75rem" in css
    assert ".ft-shell-header { margin:0 0 1.25rem" in css
    assert "margin:-1rem" not in css


def test_profile_navigation_sets_stable_identity_and_profile_subview(monkeypatch):
    import types
    import views.players as module
    state={"click":{"row":1}}
    monkeypatch.setattr(module,"st",types.SimpleNamespace(session_state=state))
    module._open_player("click",["stable-a","stable-b"])
    assert state["live_player_id"]=="stable-b"
    assert state["players_subview"]=="Player Profile"


def test_radar_diagnostics_and_compact_profile_tab_order():
    frame=players(); records=season_radar_records(frame,frame.iloc[0],"Per Start","League",("points","ghost","start_rate"))
    diagnostics=radar_diagnostics(records)
    assert diagnostics["selected_metrics"]==["Points","Ghost","Start %"]
    assert diagnostics["shared_metric_count"]==3
    assert all(size==len(frame) for sizes in diagnostics["peer_group_sizes"].values() for size in sizes)
    source=__import__("inspect").getsource(__import__("views.players",fromlist=["render"]))
    assert '["Overview","Match Analysis","Role & Tactical","Advanced"]' in source
    headline=source.split("def _compact_profile",1)[1].split("tabs=ui.tabs",1)[0]
    assert "Draft Score" not in headline and "ADP" not in headline
