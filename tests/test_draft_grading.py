import json
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from analytics.draft.grading import (
    DraftValidationError, LETTER_THRESHOLDS, ROUND_WEIGHTS, build_all,
    best_legal_xi, calibrate_league_scores, calibration_audit, position_analysis,
    freeze_snapshot, grade_picks, match_draft_players, require_valid_draft,
    validate_draft_results,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def production_inputs():
    return (pd.read_csv(ROOT / "data/imports/draft/draft_results_2627.csv"),
            pd.read_csv(ROOT / "data/snapshots/draft_2627/draft_rankings_draft_day_2627.csv"))


def test_valid_completed_draft_and_structural_failures(production_inputs):
    draft, _ = production_inputs
    assert validate_draft_results(draft)["passed"].all()
    mutations = [draft.iloc[:-1], pd.concat([draft.iloc[:-1], draft.iloc[[0]]], ignore_index=True),
                 draft.assign(**{"Draft Slot": 1}), draft.assign(Player=draft["Player"].mask(draft.index == 0, ""))]
    for invalid in mutations:
        with pytest.raises(DraftValidationError): require_valid_draft(invalid)


def test_all_180_players_match_once_with_stable_ids(production_inputs):
    draft, rankings = production_inputs
    report, _ = match_draft_players(draft, rankings)
    assert len(report) == 180
    assert report["Match Status"].eq("Matched").all()
    identities = report["Registry ID"].fillna("")
    identities = identities.mask(identities.eq(""), report["Fantrax ID"].fillna(""))
    assert identities.astype(str).str.strip().ne("").all()
    assert identities.nunique() == 180
    assert report["Match Method"].eq("Approved draft-results alias").sum() == 2


def test_pick_grade_missing_adp_renormalizes_without_999_and_preserves_draft_score():
    row = pd.DataFrame([{"overall_pick": 20, "round": 2, "manager": "A", "player": "Player", "fantrax_position": "M",
        "adp": np.nan, "pick_vs_adp": np.nan, "pick_vs_draft_rank": 5, "tier": "Tier 2", "draft_score": 88.0,
        "minutes_score": 80.0, "projected_minutes_share": 85.0, "minutes_confidence": 90.0, "data_confidence": 95.0}])
    result = grade_picks(row); components = json.loads(result.iloc[0]["pick_grade_components"])
    assert "market_value" not in components
    assert result.iloc[0]["draft_score"] == 88.0
    assert 0 <= result.iloc[0]["pick_grade"] <= 100
    assert 999 not in result.select_dtypes(include="number").to_numpy()
    assert sum(components.values()) == pytest.approx(result.iloc[0]["pick_grade"], abs=.02)


def test_round_weights_and_letter_thresholds_are_centralized():
    assert [ROUND_WEIGHTS[r] for r in (1, 4, 7, 11, 14)] == [1.5, 1.25, 1.0, .8, .65]
    assert LETTER_THRESHOLDS[0] == (97, "A+") and LETTER_THRESHOLDS[-1] == (0, "F")


def test_production_build_reconciles_and_awards_are_deterministic(production_inputs):
    result = build_all(*production_inputs)
    assert len(result.picks) == 180 and len(result.managers) == 12
    contributions = result.categories.groupby("manager")["contribution"].sum().sort_index().round(2)
    scores = result.managers.set_index("manager")["overall_score"].sort_index().round(2)
    assert contributions.equals(scores)
    assert result.awards["award"].is_unique
    assert {"Biggest Steal", "Biggest Reach", "Best Late-Round Pick"}.issubset(result.awards["award"])


def test_snapshot_creation_is_immutable_and_reused():
    artifact = ROOT / ".test_artifacts" / f"draft_grading_{uuid4().hex}"
    artifact.mkdir(parents=True)
    source = artifact / "source.csv"; snapshot = artifact / "snapshot.csv"; metadata = artifact / "snapshot.metadata.json"
    source.write_text("a\n1\n", encoding="utf-8")
    first = freeze_snapshot(source, snapshot, metadata)
    source.write_text("a\n2\n", encoding="utf-8")
    second = freeze_snapshot(source, snapshot, metadata)
    assert snapshot.read_text(encoding="utf-8") == "a\n1\n"
    assert first == second


def test_standard_calibration_maps_mean_and_standard_deviations():
    values = pd.Series([60.0, 70.0, 80.0])
    calibrated = calibrate_league_scores(values)
    expected = (80 + 10 * ((values - values.mean()) / values.std(ddof=0))).clip(55, 98)
    assert calibrated["calibrated_score"].tolist() == pytest.approx(expected.tolist())
    assert 80 + 10 * -1 == 70 and 80 + 10 * 0 == 80 and 80 + 10 * 1 == 90
    assert calibrated["calibrated_score"].between(55, 98).all()


def test_calibration_preserves_ties_order_bounds_and_zero_variance():
    values = pd.Series([1000.0, 2.0, 2.0, -1000.0])
    result = calibrate_league_scores(values)
    assert result.loc[1, "calibrated_score"] == result.loc[2, "calibrated_score"]
    assert result["calibrated_score"].between(55, 98).all()
    assert result["calibrated_score"].rank(method="min").equals(values.rank(method="min"))
    flat = calibrate_league_scores(pd.Series([63.0, 63.0]))
    assert flat["calibrated_score"].tolist() == [80.0, 80.0]


def test_category_calibration_and_audit_report_distribution(production_inputs):
    result = build_all(*production_inputs)
    audit = calibration_audit(result.managers, result.categories)
    assert len(audit) == 12 * 7
    assert {"category_min", "category_median", "category_max", "standard_calibrated_score"}.issubset(audit)
    for _, group in result.categories.groupby("category"):
        leader = group.sort_values(["score", "manager"], ascending=[False, True]).iloc[0]
        assert leader["calibrated_category_score"] == group["calibrated_category_score"].max()
        assert leader["league_rank"] == 1
        assert leader["category_letter_grade"] == "A+" or leader["calibrated_category_score"] < 97


def test_production_calibration_preserves_raw_scores_and_ranking(production_inputs):
    result = build_all(*production_inputs)
    managers = result.managers.sort_values("overall_rank")
    assert managers["raw_analytical_score"].equals(managers["overall_score"])
    assert managers["league_relative_score"].mean() == pytest.approx(80, abs=.5)
    assert managers["league_relative_score"].is_monotonic_decreasing
    assert managers["overall_grade"].equals(managers["letter_grade"])


def test_next_generation_categories_are_fantasy_facing(production_inputs):
    result = build_all(*production_inputs)
    assert set(result.categories["category"]) == {
        "projected_production", "historical_production", "floor",
        "playing_time_security", "draft_value", "attacking_upside",
        "roster_construction",
    }
    assert result.categories.groupby("manager")["weight"].sum().eq(1).all()
    assert np.allclose(
        result.categories.groupby("manager")["contribution"].sum(),
        result.managers.set_index("manager")["raw_analytical_score"].sort_index(),
    )
    assert result.managers["roster_construction_score"].nunique() > 1


def test_best_legal_xi_has_eleven_unique_players_and_separate_bench(production_inputs):
    result = build_all(*production_inputs)
    for _, team in result.picks.groupby("manager"):
        xi, bench = best_legal_xi(team)
        assert len(xi) == 11 and len(bench) == 4
        assert set(xi.index).isdisjoint(bench.index)
        assert xi.index.is_unique
        assert xi["starting_slot"].nunique() == 11


def test_minute_weighted_rates_and_position_grades_are_available(production_inputs):
    result = build_all(*production_inputs)
    managers = result.managers
    assert managers[["fantasy_per_90", "ghost_per_90", "xgi_per_90"]].notna().all().all()
    positions = position_analysis(result.picks)
    assert {"G", "D", "M", "F"}.issubset(set(positions["position"]))
    assert positions["position_letter_grade"].notna().all()
    assert positions.groupby("position")["position_score"].max().eq(100).all()


def test_expanded_awards_use_redesigned_team_categories(production_inputs):
    result = build_all(*production_inputs)
    assert {"Highest Ceiling", "Safest Team", "Strongest Bench", "Best Midfield",
            "Best Forward Group", "Best Defender Group", "Best Goalkeeper",
            "Most Boom-or-Bust", "Most Balanced Draft"}.issubset(set(result.awards["award"]))
