import inspect

import numpy as np
import pandas as pd

from analytics.players.profile_overview import DEFAULT_RADAR_KEYS, overview_radar_records
from analytics.players.ranking import metric_ranking
from components.player_radar import build_player_radar
from views.players import sort_players


def players():
    return pd.DataFrame(
        {
            "registry_player_id": ["top", "tie", "forward", "missing"],
            "player_name": ["Known Top", "Known Tie", "Forward", "Missing"],
            "canonical_position": ["M", "M", "F", "M"],
            "fantrax_position": ["M", "M", "F", "M"],
            "current_points_per_start": [18.4, 18.4, 20.0, np.nan],
            "current_ghost_per_start": [10.0, 8.0, 9.0, np.nan],
            "current_fantasy_points": [50.0, 40.0, 60.0, np.nan],
            "current_starts": [3.0, 3.0, 4.0, np.nan],
            "historical_points_per_start": [15.0, 14.0, 16.0, np.nan],
            "historical_ghost_per_start": [9.0, 8.0, 7.0, np.nan],
            "historical_fantasy_points": [300.0, 280.0, 320.0, np.nan],
            "historical_starts": [20.0, 20.0, 21.0, np.nan],
        }
    )


def metric(records, key):
    return next(item for item in records[0]["metrics"] if item["key"] == key)


def test_database_and_overview_share_points_and_ghost_league_ranks():
    frame = players()
    for field, key in (("current_points_per_start", "points_start"), ("current_ghost_per_start", "ghost_start")):
        ordered = sort_players(frame, field, False)
        prepared = metric_ranking(frame, field)
        top = ordered.iloc[0]
        radar = metric(overview_radar_records(frame, top, DEFAULT_RADAR_KEYS, "League"), key)
        assert radar["rank"] == prepared.loc[top.name, "rank"] == 1
        assert radar["peer_count"] == prepared.loc[top.name, "peer_count"] == 3


def test_position_basis_uses_the_identical_position_universe():
    frame = players(); selected = frame.iloc[0]
    prepared = metric_ranking(frame, "current_points_per_start", peer_basis="Position")
    radar = metric(overview_radar_records(frame, selected, DEFAULT_RADAR_KEYS, "Position"), "points_start")
    assert radar["rank"] == prepared.loc[selected.name, "rank"] == 1
    assert radar["peer_count"] == prepared.loc[selected.name, "peer_count"] == 2


def test_ties_and_missing_values_are_identical_and_missing_sort_last():
    frame = players(); prepared = metric_ranking(frame, "current_points_per_start")
    assert prepared.loc[0, "rank"] == prepared.loc[1, "rank"] == 2
    assert pd.isna(prepared.loc[3, "rank"])
    assert sort_players(frame, "current_points_per_start", False).iloc[-1].registry_player_id == "missing"
    tied = frame.iloc[0]
    radar = metric(overview_radar_records(frame, tied, DEFAULT_RADAR_KEYS, "League"), "points_start")
    assert radar["rank"] == prepared.loc[tied.name, "rank"]


def test_overview_hover_contains_only_raw_value_and_rank():
    frame = players(); records = overview_radar_records(frame, frame.iloc[2], DEFAULT_RADAR_KEYS, "League")[:1]
    figure = build_player_radar(records, minimum_metrics=3, simple_hover=True)
    hover = " ".join(figure.data[0].text)
    assert "Points / Start: 20.0" in hover
    assert "Rank: #1 of 3" in hover
    assert "percentile" not in hover.lower()
    assert "Fantasy Production" not in hover and "League" not in hover


def test_overview_uses_fixed_profiles_and_history_control_but_no_legacy_bars():
    import views.players as module
    source = inspect.getsource(module._compact_profile)
    for label in ("Compare to 2025/26", "Fantasy Profile", "Attacking Profile", "Defensive Profile"):
        assert label in source
    assert "overview_bars" not in source
    assert "percentile_bar" not in source
