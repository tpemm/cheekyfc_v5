import numpy as np
import pandas as pd
import pytest

from analytics.draft.presentation import add_advanced_context_metrics
from analytics.draft.team import (
    assign_roster_slots,
    best_available_fits,
    draft_strategy_priorities,
    draft_turn_context,
    league_roster_slots,
    minute_weighted_rate,
    next_pick_availability_score,
    positional_coverage,
    position_scarcity,
    snake_pick_sequence,
    team_floor,
    team_strengths_and_risks,
    team_summary,
)


def player_frame(positions):
    return pd.DataFrame({"Player": [f"P{i}" for i in range(len(positions))], "Position": positions})


def test_authoritative_xg_xa_create_xgi_and_safe_rates():
    frame = pd.DataFrame({
        "Team": ["A", "B"], "understat_xg_2526": [3.0, 2.0],
        "understat_xa_2526": [2.0, 1.0], "understat_minutes_2526": [900, 0],
        "team_strength_rating": [80, 60], "fixture_ease_next_5": [40, 70],
    })
    result = add_advanced_context_metrics(frame)
    assert result.loc[0, "xgi_2526"] == 5
    assert result.loc[0, "xgi90_2526"] == pytest.approx(.5)
    assert np.isnan(result.loc[1, "xgi90_2526"])


def test_context_percentile_directions_are_higher_better():
    result = add_advanced_context_metrics(pd.DataFrame({
        "Team": ["Strong", "Weak"], "team_strength_rating": [90, 30],
        "fixture_ease_next_5": [75, 25],
    }))
    assert result.loc[0, "team_strength_percentile"] > result.loc[1, "team_strength_percentile"]
    assert result.loc[0, "fixture_ease_percentile"] > result.loc[1, "fixture_ease_percentile"]


@pytest.mark.parametrize("positions", [
    ["G"], ["D", "M", "F"], ["D/M", "M/F", "D/F"],
    ["G", "D", "D", "D", "M", "M", "F"],
])
def test_slot_assignment_never_double_counts_players(positions):
    result = assign_roster_slots(player_frame(positions))
    assert result["player_index"].is_unique
    assert result["Slot"].dropna().is_unique


def test_multi_position_players_are_preserved_for_competing_slots():
    result = assign_roster_slots(player_frame(["D", "D/M", "M", "F"]))
    assigned = result.set_index("Player")["Slot Group"]
    assert assigned["P0"] == "D"
    assert assigned["P2"] == "M"
    assert assigned.notna().all()


def test_flex_and_bench_fill_without_exceeding_roster_size():
    positions = ["G"] + ["D"] * 5 + ["M"] * 5 + ["F"] * 5
    result = assign_roster_slots(player_frame(positions))
    assert result["Slot"].notna().sum() == 16
    assert result["Slot Group"].eq("Flex").sum() == 4
    assert result["Slot Group"].isin(["Bench", "IR"]).sum() == 5


def test_full_roster_has_no_false_required_position_need():
    coverage = positional_coverage(player_frame(["G"] + ["D"] * 5 + ["M"] * 5 + ["F"] * 5))
    required = coverage[coverage["Position"].isin(["G", "D", "M", "F"])]
    assert required["Unfilled"].sum() == 0
    assert set(required["Need"]) == {"Complete"}


def test_weighted_team_rate_and_totals_reconcile():
    team = pd.DataFrame({
        "ghost_points_2526": [100, 50], "minutes_2526": [900, 450],
        "fantrax_projected_points": [250, 300], "Draft Score": [80, 90],
    })
    assert minute_weighted_rate(team, "ghost_points_2526", "minutes_2526") == 10
    summary = team_summary(team)
    assert summary["Total Fantrax Projected Points"] == 550
    assert summary["Average Draft Score"] == 85


def test_team_floor_score_reconciles_documented_weights():
    result = team_floor(pd.DataFrame({
        "ghost_score": [80, 60], "minutes_score": [90, 70],
        "minutes_confidence": [100, 80],
    }))
    assert result["Team Floor Score"] == pytest.approx(.4 * 70 + .35 * 80 + .25 * 90)


def fit_frame():
    return pd.DataFrame({
        "Player": ["Need", "Star", "Drafted"], "Position": ["G", "M", "F"],
        "Team": ["A", "B", "C"], "Draft Status": ["Available", "Available", "Drafted by Other"],
        "Draft Score": [65, 95, 100], "Value vs ADP": [5, 0, 20],
        "ghost_score": [70, 80, 100], "attacking_score": [50, 95, 100],
        "fixture_ease_percentile": [60, 70, 100], "team_strength_percentile": [50, 90, 100],
    })


def test_best_fits_excludes_drafted_and_strategy_changes_fit_not_draft_score():
    frame = fit_frame()
    team = player_frame(["D", "D", "D", "M", "M", "F"])
    balanced = best_available_fits(frame, team, "Balanced")
    needs = best_available_fits(frame, team, "Fill Positional Needs")
    assert "Drafted" not in balanced["Player"].tolist()
    assert balanced.set_index("Player").at["Need", "Fit Score"] != needs.set_index("Player").at["Need", "Fit Score"]
    assert frame.set_index("Player").at["Need", "Draft Score"] == 65


def test_concentration_warning_is_deterministic():
    team = pd.DataFrame({
        "Player": list("ABCD"), "Position": ["D", "M", "F", "G"],
        "Team": ["ARS"] * 4, "projected_minutes_share": [80] * 4,
        "Value vs ADP": [0] * 4, "fixture_ease_percentile": [50] * 4,
    })
    _, risks = team_strengths_and_risks(team)
    assert "Heavy exposure to one club" in risks


def test_registered_league_slots_total_sixteen():
    slots = league_roster_slots()
    assert len(slots) == 16
    assert len({slot.name for slot in slots}) == 16


def strategy_pool():
    rows = []
    for position, count, tier in (("G", 8, "Tier 2"), ("D", 12, "Tier 2"), ("M", 16, "Tier 3"), ("F", 3, "Tier 2")):
        for index in range(count):
            rows.append({"Player": f"{position}{index}", "Position": position, "tier": tier, "Draft Score": 80-index, "Draft Status": "Available", "Value vs ADP": 0})
    return pd.DataFrame(rows)


def test_multi_position_scarcity_uses_fractional_counts():
    pool = pd.DataFrame({"Player": ["Flex"], "Position": ["M/F"], "tier": ["Tier 2"], "Draft Score": [80]})
    result = position_scarcity(pool).set_index("Position")
    assert result.at["M", "Available Depth"] == .5
    assert result.at["F", "Available Depth"] == .5


def test_scarcity_rises_as_available_players_are_drafted():
    pool = strategy_pool()
    before = position_scarcity(pool).set_index("Position").at["F", "Scarcity Score"]
    after = position_scarcity(pool[~pool["Player"].isin(["F0", "F1"])]).set_index("Position").at["F", "Scarcity Score"]
    assert after > before


def test_early_priority_favors_outfield_and_defers_goalkeeper():
    priorities = draft_strategy_priorities(player_frame(["D"]), strategy_pool()).set_index("Position")
    assert priorities.at["F", "Baseline"] > priorities.at["M", "Baseline"] > priorities.at["D", "Baseline"] > priorities.at["G", "Baseline"]
    assert priorities.at["G", "Strategy Priority"] < priorities.at["F", "Strategy Priority"]
    assert "deferred" in priorities.at["G", "Goalkeeper Timing"]


def test_goalkeeper_priority_rises_in_final_slot():
    team = player_frame(["D"] * 5 + ["M"] * 5 + ["F"] * 5)
    priorities = draft_strategy_priorities(team, strategy_pool()).set_index("Position")
    assert priorities.at["G", "Baseline"] == 100
    assert "required" in priorities.at["G", "Goalkeeper Timing"]


def test_scarcity_aware_fit_changes_score_not_draft_score():
    pool = strategy_pool()
    team = player_frame(["D"])
    balanced = best_available_fits(pool, team, "Balanced", limit=50).set_index("Player")
    scarcity = best_available_fits(pool, team, "Scarcity Aware", limit=50).set_index("Player")
    assert balanced.at["F0", "Fit Score"] != scarcity.at["F0", "Fit Score"]
    assert pool.set_index("Player").at["F0", "Draft Score"] == 80


def test_pick_two_twelve_team_snake_sequence_and_gap():
    assert snake_pick_sequence(12, 2, 8) == [2, 23, 26, 47, 50, 71, 74, 95]
    turn = draft_turn_context(1, 12, 2, 16)
    assert turn["Current Pick"] == 2
    assert turn["Next User Pick"] == 2
    assert turn["Following User Pick"] == 23
    assert turn["Picks Until Next Turn"] == 20


def test_next_pick_survival_signal_is_directionally_transparent():
    low, low_label = next_pick_availability_score(pd.Series({"ADP": 10, "Rank": 8}), 2, 23, 70)
    high, high_label = next_pick_availability_score(pd.Series({"ADP": 40, "Rank": 35}), 2, 23, 10)
    assert low < high
    assert low_label in {"Unlikely to survive", "At risk before next pick"}
    assert high_label in {"Could survive", "Likely to survive"}


def test_goalkeeper_legal_need_is_suppressed_in_early_fit_recommendations():
    pool = strategy_pool()
    fits = best_available_fits(pool, player_frame(["D"]), "Fill Positional Needs", limit=50, current_pick=2, next_pick=23)
    goalkeeper = fits[fits["Position"].eq("G")]
    if not goalkeeper.empty:
        assert goalkeeper["Reasons"].str.contains("deferred").all()
