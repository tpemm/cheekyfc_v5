import pandas as pd
import pytest
from pathlib import Path

from analytics.draft.model import build_rankings, percentile
from analytics.draft.reliability import (
    apply_current_squad_eligibility,
    apply_eligibility_overrides,
    load_current_epl_squads,
    normalize_team,
)
import analytics.draft.reliability as reliability
import scripts.build_draft_tool_v1_2_2_2627 as draft_script
from scripts.build_draft_tool_v1_2_2_2627 import (
    build_historical_player_summary,
    build_minutes_outlook,
    load_current_fantrax,
)


def test_current_fantrax_loader_preserves_multi_position_eligibility(monkeypatch):
    source = pd.DataFrame(
        {
            "ID": ["a", "b"], "Player": ["Dual", "Triple"],
            "Team": ["ARS", "LIV"], "Position": ["D,M", "D,M,F"],
            "FPts": [100, 120], "ADP": [10, 20],
        }
    )
    monkeypatch.setattr(draft_script, "read_csv", lambda _path: source)
    result = load_current_fantrax(Path("isolated.csv"))
    assert result["fantrax_position_eligibility"].tolist() == ["D,M", "D,M,F"]


def ranking_frame(size=4):
    values = list(range(1, size + 1))
    return pd.DataFrame(
        {
            "fantrax_player_id": [f"id{i:03}" for i in values],
            "player_name": [f"Player {i}" for i in values],
            "team_2627": ["ARS"] * size,
            "is_draft_eligible": [True] * size,
            "fantasy_ppg_2526": values,
            "fantasy_fp90_2526": values,
            "ghost_ppg_2526": values,
            "xgi90_2526": values,
            "projected_minutes_share": values,
            "team_attack_rating": values,
            "team_strength_rating": values,
            "fixture_ease_next_5": values,
            "minutes_confidence": [50] * size,
            "fantasy_points_2526": values,
            "has_historical_data": [True] * size,
            "understat_player_id": [f"u{i}" for i in values],
            "fantrax_adp": [float(i + 10) for i in values],
        }
    )


def test_percentile_average_ties_and_missing_zero():
    result = percentile(pd.Series([1.0, 1.0, 3.0, None]))
    assert result.tolist() == [50.0, 50.0, 100.0, 0.0]


def test_exact_frozen_score_subweights_and_rounding():
    frame = ranking_frame(2)
    frame.loc[0, ["fantasy_ppg_2526", "ghost_ppg_2526", "xgi90_2526"]] = 10
    result = build_rankings(frame).set_index("fantrax_player_id")
    row = result.loc["id001"]
    production = 0.60 * 100 + 0.40 * 50
    team = 0.65 * 50 + 0.35 * 50
    expected = round(
        0.30 * production + 0.20 * 1 + 0.15 * 100
        + 0.15 * 100 + 0.10 * team + 0.10 * 50,
        2,
    )
    assert row["draft_score"] == expected


def test_adp_and_confidence_do_not_change_draft_score():
    frame = pd.concat([ranking_frame(1), ranking_frame(1)], ignore_index=True)
    frame["fantrax_player_id"] = ["a", "b"]
    frame["fantrax_adp"] = [1.5, 300.0]
    frame["minutes_confidence"] = [0, 100]
    result = build_rankings(frame)
    assert result["draft_score"].nunique() == 1


@pytest.mark.parametrize(
    ("rank", "tier"),
    [
        (12, "Tier 1"), (13, "Tier 2"), (36, "Tier 2"), (37, "Tier 3"),
        (72, "Tier 3"), (73, "Tier 4"), (120, "Tier 4"), (121, "Tier 5"),
        (180, "Tier 5"), (181, "Tier 6"), (300, "Tier 6"), (301, "Deep"),
    ],
)
def test_fixed_tier_boundaries(rank, tier):
    result = build_rankings(ranking_frame(301))
    assert result.loc[result["overall_rank"].eq(rank), "tier"].iloc[0] == tier


def test_ineligible_player_has_no_rank_tier_or_adp_value():
    frame = ranking_frame(2)
    frame.loc[1, "is_draft_eligible"] = False
    result = build_rankings(frame).set_index("fantrax_player_id")
    row = result.loc["id002"]
    assert pd.isna(row["overall_rank"])
    assert pd.isna(row["tier"])
    assert pd.isna(row["value_vs_adp"])
    assert row["adp_status"] == "Not draft eligible"


@pytest.mark.parametrize(
    ("adp", "expected"),
    [(21.0, "Strong value"), (9.0, "Value"), (-7.0, "Reach"), (-19.0, "Major reach")],
)
def test_adp_thresholds_include_decimal_pick_values(adp, expected):
    frame = ranking_frame(1)
    frame.loc[0, "fantrax_adp"] = adp
    assert build_rankings(frame).iloc[0]["adp_status"] == expected


def test_missing_adp_status_and_alias_is_not_used():
    frame = ranking_frame(1)
    frame["fantrax_adp"] = pd.NA
    frame["fantrax_adp_rank"] = 99.9
    result = build_rankings(frame).iloc[0]
    assert result["adp_status"] == "ADP unavailable"
    assert pd.isna(result["value_vs_adp"])


def test_ranking_keys_and_stable_id_are_deterministic():
    frame = pd.concat([ranking_frame(1)] * 3, ignore_index=True)
    frame["fantrax_player_id"] = ["c", "a", "b"]
    first = build_rankings(frame.sample(frac=1, random_state=1))
    second = build_rankings(frame.sample(frac=1, random_state=2))
    assert first["fantrax_player_id"].tolist() == ["a", "b", "c"]
    assert first["fantrax_player_id"].tolist() == second["fantrax_player_id"].tolist()


def test_override_id_precedence_conflict_and_unique_name_rules():
    frame = pd.DataFrame(
        {
            "fantrax_player_id": ["a", "b", "c"],
            "player_name": ["Same", "Same", "Unique"],
            "team_2627": ["ARS"] * 3,
            "current_epl_team": ["ARS"] * 3,
            "is_draft_eligible": [True] * 3,
            "is_free_agent": [False] * 3,
        }
    )
    overrides = pd.DataFrame(
        [
            {"fantrax_player_id": "a", "player_name": "Unique", "is_draft_eligible": False},
            {"player_name": "Same", "is_draft_eligible": False},
            {
                "fantrax_player_id": "c", "player_name": "Unique",
                "is_draft_eligible": False, "current_team": "CHE", "reason": "Left EPL",
            },
        ]
    )
    result, report = apply_eligibility_overrides(frame, overrides)
    assert result.set_index("fantrax_player_id").loc["c", "team_2627"] == "CHE"
    assert not result.set_index("fantrax_player_id").loc["c", "is_draft_eligible"]
    assert report["status"].tolist() == ["not applied", "not applied", "applied"]


def test_incomplete_squad_source_reports_every_player():
    frame = pd.DataFrame(
        {
            "fantrax_player_id": ["a"],
            "player_name": ["Player"],
            "team_2627": ["ARS"],
            "is_draft_eligible": [True],
            "is_free_agent": [False],
        }
    )
    result, report, coverage = apply_current_squad_eligibility(
        frame, Path("data/does_not_exist")
    )
    assert result.iloc[0]["draft_eligibility_status"].startswith("Unresolved")
    assert len(report) == 1
    assert coverage.empty


def test_complete_squad_source_exact_match_and_confirmed_non_epl(monkeypatch):
    squads = pd.DataFrame(
        {
            "footballdata_player_id": [1],
            "current_epl_team": ["ARS"],
            "footballdata_player_name": ["Exact Player"],
            "alias_keys": [("exact player",)],
        }
    )
    coverage = pd.DataFrame(
        {
            "team_code": [f"T{i:02}" for i in range(19)] + ["ARS"],
            "coverage_complete": [True] * 20,
        }
    )
    monkeypatch.setattr(
        reliability, "load_current_epl_squads", lambda *_: (squads, coverage)
    )
    frame = pd.DataFrame(
        {
            "fantrax_player_id": ["a", "b"],
            "player_name": ["Exact Player", "Departed Player"],
            "team_2627": ["ARS", "ARS"],
            "is_draft_eligible": [True, True],
            "is_free_agent": [False, False],
        }
    )
    result, report, _ = apply_current_squad_eligibility(frame, Path("data"))
    statuses = result.set_index("fantrax_player_id")["draft_eligibility_status"]
    assert statuses["a"] == "Matched eligible"
    assert statuses["b"] == "Confirmed no longer EPL eligible"
    assert len(report) == 2


def test_fuzzy_within_club_match(monkeypatch):
    squads = pd.DataFrame(
        {
            "footballdata_player_id": [1],
            "current_epl_team": ["ARS"],
            "footballdata_player_name": ["Gabriel Martinelli"],
            "alias_keys": [("gabriel martinelli",)],
        }
    )
    coverage = pd.DataFrame(
        {"team_code": ["ARS"], "coverage_complete": [True]}
    )
    monkeypatch.setattr(
        reliability, "load_current_epl_squads", lambda *_: (squads, coverage)
    )
    frame = pd.DataFrame(
        {
            "fantrax_player_id": ["a"],
            "player_name": ["Gabriel Martineli"],
            "team_2627": ["ARS"],
            "is_draft_eligible": [True],
            "is_free_agent": [False],
        }
    )
    result, _, _ = apply_current_squad_eligibility(frame, Path("data"))
    assert result.iloc[0]["squad_match_method"] == "fuzzy within listed club"


def test_team_normalization_covers_current_codes():
    assert normalize_team("Brentford FC") == "BRF"
    assert normalize_team("Nottingham Forest FC") == "NOT"
    assert normalize_team("Fulham FC") == "FUL"
    assert normalize_team("Ipswich Town FC") == "IPS"


def test_historical_latest_team_position_duplicate_week_and_transfer_detection():
    master = pd.DataFrame(
        {
            "fantrax_player_id": ["*a*", "*a*", "*a*"],
            "fantrax_player_name": ["Player", "Player", "Player"],
            "fantrax_gw": [1, 2, 2],
            "avail_team": ["ARS", "AVL", "CHE"],
            "avail_position": ["M", "M,F", "F"],
            "mgr_min": [90, 10, 80],
            "official_fantasy_points": [5, 1, 7],
        }
    )
    summary = build_historical_player_summary(master)
    assert summary.iloc[0]["team_2526"] == "CHE"
    assert summary.iloc[0]["position_2526"] == "F"
    assert summary.iloc[0]["minutes_2526"] == 170
    outlook = build_minutes_outlook(
        summary.assign(team_2627="ARS")
    )
    assert bool(outlook.iloc[0]["team_changed"])


def test_no_historical_record_is_not_zero_history():
    history = build_historical_player_summary(
        pd.DataFrame(
            {
                "fantrax_player_id": ["a"],
                "fantrax_player_name": ["Known"],
                "fantrax_gw": [1],
                "avail_team": ["ARS"],
                "avail_position": ["M"],
                "mgr_min": [0],
                "official_fantasy_points": [0],
            }
        )
    )
    merged = pd.DataFrame({"historical_fantrax_player_id": ["missing"]}).merge(
        history, left_on="historical_fantrax_player_id", right_on="fantrax_player_id", how="left"
    )
    assert pd.isna(merged.iloc[0]["fantasy_points_2526"])
    assert pd.isna(merged.iloc[0]["historical_name"])


def test_draft_main_consumes_registry_without_internal_identity_or_squad_matching():
    source = Path("scripts/build_draft_tool_v1_2_2_2627.py").read_text(encoding="utf-8")
    main = source.split("def main() -> None:", 1)[1]
    assert "player_registry_2627.csv" in main
    assert "attach_bridge(current" not in main
    assert "apply_current_squad_eligibility(" not in main
    assert "apply_eligibility_overrides(" not in main


@pytest.mark.parametrize(
    ("fantrax_name", "fpl_id"),
    [("Bruno Fernandes", "426"), ("Bruno Guimaraes", "452")],
)
def test_rebuilt_draft_contains_expanded_name_matches_as_eligible(
    fantrax_name, fpl_id
):
    rankings = pd.read_csv(
        "data/models/draft_2627/draft_rankings_2627.csv",
        dtype={"fpl_player_id": str},
        low_memory=False,
    )
    row = rankings[rankings["player_name"].eq(fantrax_name)].iloc[0]
    assert bool(row["is_draft_eligible"])
    assert row["registry_status"] == "Confirmed"
    assert row["match_method"] == "Ordered Token Expanded Name"
    assert str(row["fpl_player_id"]).removesuffix(".0") == fpl_id


@pytest.mark.parametrize(
    "fantrax_name",
    [
        "Ehor Yarmolyuk",
        "Valentino Livramento",
        "Djordje Petrovic",
        "Danny Ballard",
        "Eli Kroupi",
        "Mateus Fernandes",
        "Reinildo",
        "Alisson Becker",
        "Richarlison",
    ],
)
def test_rebuilt_draft_ranks_explicit_player_aliases(fantrax_name):
    rankings = pd.read_csv(
        "data/models/draft_2627/draft_rankings_2627.csv",
        low_memory=False,
    )
    rows = rankings[rankings["player_name"].eq(fantrax_name)]
    assert len(rows) == 1
    row = rows.iloc[0]
    assert bool(row["is_draft_eligible"])
    assert row["eligibility_source"] == "Player Registry"
    assert row["match_method"] == "Explicit Player Alias"
    assert pd.notna(row["overall_rank"])
    assert pd.notna(row["tier"])
    assert pd.notna(row["adp_status"])
