import numpy as np
import pandas as pd
import pytest

from analytics.draft.presentation import (
    AVAILABLE,
    DRAFTED_BY_ME,
    DRAFTED_BY_OTHER,
    add_draft_percentiles,
    add_explicit_rate_metrics,
    apply_board_action,
    apply_draft_statuses,
    build_tier_board,
    comparison_table,
    comparison_winner_data,
    draft_score_explanation,
    explanation_reconciles,
    format_detail_value,
    model_visualization_data,
    normalize_fantrax_positions,
    position_matches,
    percentile_context,
    player_strengths_and_risks,
    reset_draft_session,
    set_draft_status,
    stable_player_key,
    sort_draft_board,
    update_queue,
)


def test_adp_sort_always_places_missing_values_last():
    frame = pd.DataFrame(
        {
            "Player": ["None", "Late", "Early", "NaN", "NA", "Blank", "Middle"],
            "ADP": [None, 250.0, 1.0, np.nan, pd.NA, "", "3.0"],
            "Rank": [3, 2, 1, 4, 5, 6, 7],
            "Draft Score": [70, 80, 90, 60, 50, 40, 30],
        }
    )
    assert sort_draft_board(frame, "ADP", True)["Player"].tolist() == [
        "Early", "Middle", "Late", "None", "NaN", "NA", "Blank"
    ]
    assert sort_draft_board(frame, "ADP", False)["Player"].tolist() == [
        "Late", "Middle", "Early", "None", "NaN", "NA", "Blank"
    ]
    result = sort_draft_board(frame, "ADP", False)
    assert result.loc[result["Player"].eq("Blank"), "ADP"].iat[0] == ""
    assert result.loc[result["Player"].eq("None"), "ADP"].iat[0] is None


def test_tier_board_uses_numeric_tier_and_draft_rank_order():
    frame = pd.DataFrame(
        {
            "Player": ["C", "B", "A"],
            "tier": ["Tier 10", "Tier 2", "Tier 1"],
            "Rank": [30, 3, 1],
        }
    )
    groups = build_tier_board(frame)
    assert [name for name, _ in groups] == ["Tier 1", "Tier 2", "Tier 10"]
    assert groups[0][1]["Rank"].tolist() == [1]


def test_explicit_rates_share_denominators_and_blank_zero_denominators():
    frame = pd.DataFrame(
        {
            "fantasy_points_2526": [60.0, 10.0],
            "ghost_points_2526": [30.0, 5.0],
            "minutes_2526": [900.0, 0.0],
            "starts_2526": [5.0, 0.0],
            "appearances_2526": [10.0, 0.0],
        }
    )
    result = add_explicit_rate_metrics(frame)
    assert result.loc[0, "fantasy_per_appearance_2526"] == 6.0
    assert result.loc[0, "ghost_per_appearance_2526"] == 3.0
    assert result.loc[0, "fantasy_per_start_2526"] == 12.0
    assert result.loc[0, "ghost_per90_2526"] == 3.0
    assert pd.isna(result.loc[1, "fantasy_per_appearance_2526"])
    assert pd.isna(result.loc[1, "ghost_per90_2526"])


def test_draft_score_explanation_reconciles_official_components():
    row = pd.Series(
        {
            "Draft Score": 72.5,
            "production_score": 80.0,
            "minutes_score": 75.0,
            "ghost_score": 70.0,
            "attacking_score": 60.0,
            "team_context_score": 80.0,
            "fixture_score": 60.0,
        }
    )
    explanation = draft_score_explanation(row)
    assert explanation["Weighted contribution"].sum() == 72.5
    assert explanation_reconciles(row)


def test_missing_explanation_component_does_not_claim_reconciliation():
    row = pd.Series({"Draft Score": 50.0, "production_score": 50.0})
    assert not explanation_reconciles(row)


def test_queue_add_remove_and_reorder():
    queue = update_queue([], "A", "add")
    queue = update_queue(queue, "B", "add")
    queue = update_queue(queue, "B", "up")
    assert queue == ["B", "A"]
    assert update_queue(queue, "B", "remove") == ["A"]


def test_player_comparison_is_side_by_side_without_new_calculations():
    frame = add_explicit_rate_metrics(
        pd.DataFrame(
            {
                "Player": ["A", "B"],
                "Team": ["ARS", "LIV"],
                "Position": ["M", "F"],
                "tier": ["Tier 1", "Tier 2"],
                "Rank": [1, 2],
                "Draft Score": [90, 80],
                "ADP": [2, 4],
                "fantasy_points_2526": [60, 40],
                "ghost_points_2526": [30, 20],
                "minutes_2526": [900, 450],
                "starts_2526": [10, 5],
                "appearances_2526": [10, 5],
            }
        )
    )
    result = comparison_table(frame, ["A", "B"])
    assert result.columns.tolist() == ["Metric", "A", "B"]
    row = result[result["Metric"].eq("Points / Appearance")].iloc[0]
    assert (row["A"], row["B"]) == (6.0, 8.0)


def test_premium_comparison_identifies_winners_by_metric_direction():
    frame = pd.DataFrame({
        "Player": ["A", "B"],
        "Draft Score": [90, 85],
        "Rank": [1, 2],
        "ADP": [5, 3],
        "Value vs ADP": [4, 8],
        "fantrax_projected_points": [300, 280],
        "fantasy_per90_2526": [11, 12],
        "ghost_per90_2526": [7, 6],
    })
    result = comparison_winner_data(frame, "A", "B").set_index("Metric")
    assert result.at["Draft Score", "Winner"] == "A"
    assert result.at["Draft Rank", "Winner"] == "A"
    assert result.at["ADP", "Winner"] == "B"
    assert result.at["ADP Value", "Winner"] == "B"
    assert result.at["Points / 90", "Winner"] == "B"


def test_fantrax_multi_position_display_and_filtering():
    assert normalize_fantrax_positions(" D, M / F ") == "D/M/F"
    assert position_matches("D/M", ["M"])
    assert not position_matches("D/M", ["F"])


def test_draft_status_workflow_uses_stable_id_and_restores_available():
    frame = pd.DataFrame(
        {"registry_player_id": ["r1"], "fantrax_player_id": ["f1"], "Player": ["A"]}
    )
    key = stable_player_key(frame.iloc[0])
    statuses = set_draft_status({}, key, DRAFTED_BY_ME)
    assert apply_draft_statuses(frame, statuses).iloc[0]["Draft Status"] == DRAFTED_BY_ME
    statuses = set_draft_status(statuses, key, DRAFTED_BY_OTHER)
    assert apply_draft_statuses(frame, statuses).iloc[0]["Draft Status"] == DRAFTED_BY_OTHER
    statuses = set_draft_status(statuses, key, AVAILABLE)
    assert statuses == {}
    assert apply_draft_statuses(frame, statuses).iloc[0]["Draft Status"] == AVAILABLE


def test_reset_draft_session_clears_only_draft_session_values():
    state = {
        "draft_player_statuses": {"x": DRAFTED_BY_ME},
        "draft_queue": ["A"],
        "draft_sequence": ["x"],
        "unrelated": "preserved",
    }
    reset_draft_session(state)
    assert state == {
        "draft_player_statuses": {},
        "draft_queue": [],
        "draft_sequence": [],
        "unrelated": "preserved",
    }


@pytest.mark.parametrize("status", [DRAFTED_BY_ME, DRAFTED_BY_OTHER])
def test_one_click_board_action_uses_stable_key_and_removes_queue(status):
    statuses, queue, sequence = apply_board_action(
        {}, ["registry_player_id:r1", "registry_player_id:r2"], [],
        "registry_player_id:r1", status,
    )
    assert statuses == {"registry_player_id:r1": status}
    assert queue == ["registry_player_id:r2"]
    assert sequence == ["registry_player_id:r1"]


def test_draft_percentiles_use_league_and_canonical_position_peers():
    frame = pd.DataFrame({
        "Canonical Position": ["M", "M", "F"],
        "Draft Score": [90.0, 70.0, 80.0],
        "fantrax_projected_points": [300.0, 200.0, 250.0],
        "fantasy_per90_2526": [12.0, 8.0, 10.0],
        "ghost_per90_2526": [7.0, 5.0, 6.0],
        "projected_minutes_share": [95.0, 70.0, 80.0],
    })
    result = add_draft_percentiles(frame)
    assert result.loc[0, "draft_score_league_percentile"] == 100.0
    assert result.loc[0, "draft_score_position_percentile"] == 100.0
    assert result.loc[1, "draft_score_league_percentile"] == pytest.approx(100 / 3)
    position, league = percentile_context(result.loc[0], "draft_score")
    assert position == "Top 1% among Midfielders"
    assert league == "100th percentile league-wide"


def test_detail_values_are_consistently_formatted():
    assert format_detail_value(13.921052631578947) == "13.9"
    assert format_detail_value(2950.0, integer=True) == "2950"
    assert format_detail_value(pd.NA) == "—"


def test_strengths_and_risks_use_deterministic_thresholds():
    strengths, risks = player_strengths_and_risks(pd.Series({
        "projected_minutes_position_percentile": 95,
        "points_per90_position_percentile": 90,
        "ghost_per90_position_percentile": 30,
        "attacking_score": 80,
        "draft_score_league_percentile": 95,
        "Value vs ADP": -8,
        "data_confidence": 50,
    }))
    assert strengths == [
        "Elite projected minutes",
        "Excellent fantasy production",
        "Strong attacking contribution",
    ]
    assert risks == [
        "Reach versus current ADP",
        "Lower ghost floor than positional peers",
        "Lower underlying data confidence",
    ]


def test_model_visualization_data_is_bounded_and_one_decimal():
    result = model_visualization_data(pd.Series({
        "production_score": 82.349,
        "minutes_score": 101,
        "ghost_score": -3,
    }))
    assert result.to_dict("records") == [
        {"Component": "Historical Fantasy Production", "Score": 82.3},
        {"Component": "Playing-Time Reliability", "Score": 100.0},
        {"Component": "Ghost-Point Floor", "Score": 0.0},
    ]
