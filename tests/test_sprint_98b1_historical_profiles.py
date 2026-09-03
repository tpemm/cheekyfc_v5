from pathlib import Path
import inspect
import pandas as pd

from analytics.players.research_overview import (
    ATTACKING_AXES, DEFENSIVE_AXES, fixed_radar_records,
    historical_profile_availability, overlay_historical_advanced,
)
from components.player_radar import build_player_radar

ROOT=Path(__file__).resolve().parents[1]

def _real():
    frame=pd.read_csv(ROOT/"data/models/season_2627/live_player_analytics_2627.csv",low_memory=False)
    profile=pd.read_csv(ROOT/"data/models/season_2526/advanced/player_advanced_profile_2526.csv")
    return overlay_historical_advanced(frame,profile)

def test_historical_identity_bridge_and_maxim_canary():
    frame=_real();row=frame[frame.fantrax_player_id.astype(str).eq("06y9m")].iloc[0]
    availability=historical_profile_availability(row)
    assert len(availability["attacking"]["available_axes"])==5
    assert len(availability["defensive"]["available_axes"])>=4
    assert build_player_radar(fixed_radar_records(frame,row,ATTACKING_AXES,True)[0],minimum_metrics=3) is not None
    assert build_player_radar(fixed_radar_records(frame,row,DEFENSIVE_AXES,True)[0],minimum_metrics=3) is not None

def test_explicit_zero_and_missing_axis_are_distinct():
    row=_real().query("fantrax_player_id == '06y9m'").iloc[0]
    assert row.historical_goals_per_start==0
    assert pd.isna(row.get("historical_clean_sheets_per_start"))

def test_historical_percentiles_use_historical_distribution():
    frame=_real();row=frame.query("fantrax_player_id == '06y9m'").iloc[0]
    records,_=fixed_radar_records(frame,row,ATTACKING_AXES,True)
    metric=records[1]["metrics"][0]
    expected=pd.to_numeric(frame.loc[frame.fantrax_position.astype(str).str.startswith("D"),"historical_goals_per_start"],errors="coerce")
    assert metric["peer_count"]<=expected.count() and metric["source"]=="2025/26"

def test_overview_has_one_toggle_and_no_eager_historical_events():
    import views.players as players
    compact=inspect.getsource(players._compact_profile);render=inspect.getsource(players.render)
    assert compact.count('toggle("Compare to 2025/26"')==1
    assert "Historical Comparison" not in compact and "Advanced data season" not in render
    assert render.count("get_historical_player_advanced")==1
