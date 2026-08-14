from __future__ import annotations

import pandas as pd

from views.live_league_hub import build_live_hub_model


def test_live_hub_model_uses_latest_registered_period_and_builds_stories():
    standings = pd.DataFrame([
        {"period": 1, "rank": 2, "manager": "Ada", "wins": 0, "draws": 0, "losses": 1, "fantasy_points_for": 40, "fantasy_points_against": 50},
        {"period": 2, "rank": 1, "manager": "Ada", "wins": 1, "draws": 0, "losses": 1, "fantasy_points_for": 100, "fantasy_points_against": 90},
        {"period": 2, "rank": 2, "manager": "René", "wins": 1, "draws": 0, "losses": 1, "fantasy_points_for": 90, "fantasy_points_against": 100},
    ])
    weeks = pd.DataFrame([
        {"period": 1, "manager": "Ada", "total_score": 40, "result": "L", "rank_after_week": 2},
        {"period": 2, "manager": "Ada", "total_score": 60, "result": "W", "rank_after_week": 1},
        {"period": 2, "manager": "René", "total_score": 55, "result": "L", "rank_after_week": 2},
    ])
    matchups = pd.DataFrame([{"status": "completed", "home_manager": "Ada", "away_manager": "René", "margin": 5}])

    model = build_live_hub_model(pd.DataFrame(), standings, matchups, weeks)

    assert model["standings"]["period"].unique().tolist() == [2]
    assert model["managers"].iloc[0]["manager"] == "Ada"
    assert model["managers"].iloc[0]["average_score_numeric"] == 50
    assert {item[0] for item in model["highlights"]} >= {"Highest Score", "Closest Match"}
    assert list(model["position_history"].index) == [1, 2]


def test_live_hub_model_handles_preseason_rows_without_period_or_scores():
    teams = pd.DataFrame([{"manager_name": "Zoë", "fantasy_team_name": "Café XI"}])
    model = build_live_hub_model(teams, pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    assert model["managers"].iloc[0]["manager"] == "Zoë"
    assert model["highlights"] == []
