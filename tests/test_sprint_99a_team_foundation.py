from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from analytics.teams.canonical import aggregate_profile,aggregate_team_events,fantasy_allowed_foundation,reciprocal_validation
from core.services.dataset_registry import DatasetRegistry
from core.services.historical_advanced import historical_club_id

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def team_match():return pd.read_csv(ROOT/"data/models/season_2627/team_match_analytics_2627.csv",low_memory=False)


def test_current_canonical_grain_and_coverage(team_match):
    assert len(team_match)==40
    assert team_match.canonical_match_id.nunique()==20
    assert team_match.club_id.nunique()==20
    assert team_match.groupby("canonical_match_id").size().eq(2).all()
    assert not team_match.duplicated(["canonical_match_id","club_id"]).any()


def test_reciprocal_opponent_score_xg_and_venue(team_match):
    validation=reciprocal_validation(team_match)
    assert len(validation)==20 and validation.validation_status.eq("PASS").all()


def test_current_context_and_provider_quality_gates(team_match):
    assert team_match.manager_id.notna().sum()==40
    assert team_match.formation.notna().sum()==40
    assert team_match.xg.notna().sum()==40 and team_match.xga.notna().sum()==40
    assert team_match.event_count.gt(0).all()
    assert team_match.match_completed.all()


def test_event_aggregation_semantics_and_unique_attribution():
    events=pd.DataFrame([
        {"canonical_match_id":"m","event_id":"1","club_id":"a","event_type":"Pass","outcome":"Successful","qualifiers":"[]","is_key_pass":True,"x":50,"y":70,"end_x":80,"end_y":70},
        {"canonical_match_id":"m","event_id":"2","club_id":"a","event_type":"Pass","outcome":"Successful","qualifiers":"[\"Cross\"]","is_key_pass":False,"x":80,"y":70,"end_x":90,"end_y":50},
        {"canonical_match_id":"m","event_id":"3","club_id":"b","event_type":"TakeOn","outcome":"Successful","qualifiers":"[]","is_key_pass":False,"x":70,"y":20,"end_x":None,"end_y":None},
        {"canonical_match_id":"m","event_id":"4","club_id":"b","event_type":"SavedShot","outcome":"Successful","qualifiers":"[\"Blocked\"]","is_key_pass":False,"x":90,"y":50,"end_x":None,"end_y":None},
    ])
    out=aggregate_team_events(events).set_index("club_id")
    assert out.loc["a","passes"]==2 and out.loc["a","successful_passes"]==2 and out.loc["a","key_passes"]==1
    assert out.loc["a","crosses"]==1 and out.loc["a","successful_crosses"]==1 and out.loc["a","final_third_entries"]==1
    assert out.loc["b","take_ons"]==out.loc["b","successful_take_ons"]==1
    assert out.loc["b","shots"]==1 and out.loc["b","shots_on_target"]==0
    assert out.event_count.sum()==events.event_id.nunique()


def test_real_event_metrics_and_spatial_shares(team_match):
    for field in ("passes","successful_passes","pass_completion_pct","key_passes","crosses","successful_crosses","take_ons","successful_take_ons","shots","shots_on_target","tackles","successful_tackles","interceptions","clearances","recoveries","aerials","aerial_wins","final_third_event_share","box_event_count"):
        assert field in team_match and team_match[field].notna().all()
    shares=team_match[["defensive_third_event_share","middle_third_event_share","final_third_event_share"]].sum(axis=1)
    assert np.allclose(shares,100)
    assert team_match.event_activity_center_x.between(0,100).all() and team_match.event_activity_center_y.between(0,100).all()


def test_profiles_manager_formation_home_away_and_neutral_context(team_match):
    season=pd.read_csv(ROOT/"data/models/season_2627/team_season_profile_2627.csv")
    manager=pd.read_csv(ROOT/"data/models/season_2627/team_manager_profile_2627.csv")
    formation=pd.read_csv(ROOT/"data/models/season_2627/team_formation_analytics_2627.csv")
    venue=pd.read_csv(ROOT/"data/models/season_2627/team_home_away_profile_2627.csv")
    assert len(season)==len(manager)==20
    assert len(formation)==21 and len(venue)==40
    assert np.allclose(formation.groupby("club_id").formation_share.sum(),1)
    assert any(c.endswith("_volume_rank") for c in season) and not any("best_rank" in c for c in season)
    assert not any(frame.contains_prediction.any() for frame in (season,manager,formation,venue))


def test_fantasy_allowed_match_and_position_foundations():
    total=pd.read_csv(ROOT/"data/models/season_2627/team_fantasy_allowed_match_2627.csv")
    position=pd.read_csv(ROOT/"data/models/season_2627/team_fantasy_allowed_position_match_2627.csv")
    assert len(total)==40 and total.canonical_match_id.nunique()==20
    assert len(position)==158 and set(position.position_group)<=set(["GK","DEF","MID","FWD"])
    assert total.fantasy_points_allowed.notna().all() and position.fantasy_points_allowed.notna().all()
    assert not total.contains_prediction.any() and not position.contains_prediction.any()


def test_historical_reference_and_bournemouth_bridge():
    history=pd.read_csv(ROOT/"data/models/season_2526/team_match_analytics_2526.csv",low_memory=False)
    assert len(history)==760 and history.canonical_match_id.nunique()==380 and history.club_id.nunique()==20
    assert historical_club_id("afc_bournemouth")=="bournemouth" and len(history[history.club_id.eq("bournemouth")])==38
    assert history.xg.notna().all() and history.xga.notna().all()  # restored from matched historical Understat schedule


def test_promoted_club_has_honest_no_history():
    history=pd.read_csv(ROOT/"data/models/season_2526/team_match_analytics_2526.csv",low_memory=False)
    assert "coventry_city" not in set(history.club_id)


def test_registry_and_commissioner_refresh_integration():
    registry=DatasetRegistry();keys={item.key for item in registry.list_all()}
    assert {"team_match_analytics","team_season_profile","team_manager_profile","team_formation_analytics","team_home_away_profile","team_fantasy_allowed_match","team_fantasy_allowed_position_match"}<=keys
    source=(ROOT/"scripts/weekly_commissioner_refresh.py").read_text(encoding="utf-8")
    assert "build_team_analytics_2627.py" in source and "'team_models':team_status" in source


def test_no_predictions_or_unvalidated_style_labels(team_match):
    assert not team_match.contains_prediction.any()
    forbidden={"attack_score","pressing_score","possession_score","directness_score","style_score","predicted_goals","win_probability"}
    assert forbidden.isdisjoint(team_match.columns)


def test_player_tactical_join_hook(team_match):
    player=pd.read_csv(ROOT/"data/models/season_2627/current_player_match_log_2627.csv",low_memory=False).iloc[0]
    joined=team_match[(team_match.canonical_match_id==player.canonical_match_id)&(team_match.club_id==player.opponent_id)]
    assert len(joined)==1
