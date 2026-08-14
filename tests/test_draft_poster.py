import hashlib
from io import BytesIO
from pathlib import Path

import pandas as pd
from PIL import Image

from analytics.draft.poster import (
    POSITION_ORDER, POSITION_WEIGHTS, POSTER_SIZE, RADAR_AXES, RADAR_FIELDS,
    _pick_callouts, build_poster_audit, build_poster_profiles, poster_output_bytes,
)
from analytics.draft.grading import best_legal_xi

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_HASH = "1cb42077c845c567f2149e78ef1674f9df3a8fd993a6b8ed43427f4c5014e7f1"
PICK_HASH = "4242032df9c47d6f0398fc997e598abae09e8dc0caecd46aa0c89d99b144fcf5"


def inputs():
    return (pd.read_csv(ROOT / "data/models/draft_2627/draft_manager_grades_2627.csv"),
            pd.read_csv(ROOT / "data/models/draft_2627/draft_pick_grades_2627.csv"))


def test_radar_has_six_relative_axes_and_raw_values():
    managers, picks = inputs(); profiles, _ = build_poster_profiles(managers, picks)
    assert RADAR_AXES == ("Projected XI", "Draft Value", "Fantasy / 90", "Ghost / 90", "xGI / 90", "Starting XI Minutes")
    assert len(RADAR_FIELDS) == 6 and len(profiles) == 12
    for field in RADAR_FIELDS:
        assert profiles[field].notna().all()
        assert profiles[f"{field}_percentile"].between(0, 100).all()
        assert profiles.sort_values(field, ascending=False)[f"{field}_percentile"].is_monotonic_decreasing
        assert profiles[f"{field}_rank"].notna().all()
    assert not profiles["draft_value"].eq(999).any()
    assert "projected_minutes_pct" not in RADAR_FIELDS


def test_starting_xi_minutes_exclude_bench_and_missing_without_rescaling():
    managers, picks = inputs(); target = managers.sort_values("overall_rank").iloc[[0]].copy()
    manager = target.iloc[0]["manager"]; team = picks[picks["manager"].eq(manager)].copy()
    xi, bench = best_legal_xi(team)
    team.loc[xi.index, "projected_minutes_share"] = range(70, 81)
    team.loc[xi.index[0], "projected_minutes_share"] = pd.NA
    team.loc[bench.index, "projected_minutes_share"] = 0
    profiles, _ = build_poster_profiles(target, team)
    expected = pd.Series(range(71, 81), dtype=float).mean()
    assert profiles.iloc[0]["starting_xi_minutes_pct"] == expected
    assert profiles.iloc[0]["starting_xi_minutes_coverage"] == 10
    assert 0 <= profiles.iloc[0]["starting_xi_minutes_pct"] <= 100
    assert set(profiles.iloc[0]["xi_indices"]) == set(xi.index)
    assert set(profiles.iloc[0]["bench_indices"]) == set(bench.index)


def test_real_starting_xi_minutes_are_plausible_and_coverage_is_retained():
    managers, picks = inputs(); profiles, _ = build_poster_profiles(managers, picks)
    assert profiles["starting_xi_minutes_pct"].between(0, 100).all()
    assert profiles["starting_xi_minutes_pct"].max() > 70
    assert profiles["starting_xi_minutes_coverage"].between(0, 11).all()
    assert (profiles["locked_starters"] + profiles["likely_starters"] + profiles["rotation_unknown_starters"]).eq(11).all()


def test_position_groups_reuse_unique_xi_and_weights_reconcile():
    managers, picks = inputs(); profiles, groups = build_poster_profiles(managers, picks)
    assert set(groups["group"]) == set(POSITION_ORDER)
    assert groups.groupby("group")["manager"].nunique().eq(12).all()
    assert all(abs(sum(weights.values()) - 1) < 1e-12 for weights in POSITION_WEIGHTS.values())
    for row in profiles.itertuples():
        manager_groups = groups[groups["manager"].eq(row.manager)]
        starters = list(manager_groups[manager_groups["group"].eq("Starting XI")]["player_indices"].iat[0])
        bench = list(manager_groups[manager_groups["group"].eq("Bench")]["player_indices"].iat[0])
        assert len(starters) == len(set(starters)) == 11
        assert len(bench) == len(set(bench)) == 4
        assert set(starters) == set(row.xi_indices)
        assert set(bench) == set(row.bench_indices)
        assert set(starters).isdisjoint(bench)
        assert manager_groups["league_rank"].between(1, 12).all()
        defense_gk = list(manager_groups[manager_groups["group"].eq("Defense + GK")]["player_indices"].iat[0])
        expected = picks.loc[starters]
        expected = expected[expected["canonical_position"].isin(["G", "D"])]
        assert len(defense_gk) == len(set(defense_gk))
        assert set(defense_gk) == set(expected.index)
    assert POSITION_ORDER == ("Defense + GK", "Midfield", "Forwards", "Bench", "Starting XI")
    assert "Goalkeeper" not in POSITION_ORDER


def test_poster_callouts_use_value_guardrails_and_adp_rank_fallback():
    rows = pd.DataFrame([
        {"manager":"A","player":"Quality Value","round":5,"pick_in_round":2,"overall_pick":50,"adp":80,"fantrax_overall_rank":75,"pick_vs_adp":30,"pick_vs_draft_rank":25,"draft_score":85,"match_method":"Exact"},
        {"manager":"A","player":"Trivial Late","round":15,"pick_in_round":1,"overall_pick":169,"adp":300,"fantrax_overall_rank":300,"pick_vs_adp":131,"pick_vs_draft_rank":131,"draft_score":1,"match_method":"Exact"},
        {"manager":"A","player":"Rank Fallback Reach","round":2,"pick_in_round":4,"overall_pick":16,"adp":pd.NA,"fantrax_overall_rank":70,"pick_vs_adp":pd.NA,"pick_vs_draft_rank":-54,"draft_score":70,"match_method":"Exact"},
        {"manager":"A","player":"ADP Reach","round":3,"pick_in_round":1,"overall_pick":25,"adp":100,"fantrax_overall_rank":40,"pick_vs_adp":-75,"pick_vs_draft_rank":-15,"draft_score":75,"match_method":"Exact"},
    ])
    best, reach = _pick_callouts(rows, rows)
    assert best["player"] == "Quality Value" and best["reason"] == "+30 picks versus ADP"
    assert reach["player"] == "ADP Reach" and reach["difference"] == -75
    assert reach["reason"] == "75 picks before ADP"
    assert _pick_callouts(rows, rows) == (best, reach)
    altered = rows.copy(); altered["pick_grade"] = [0, 100, 100, 100]
    assert _pick_callouts(altered, altered)[1]["player"] == "ADP Reach"


def test_audit_contains_required_manager_metrics_and_group_ranks():
    managers, picks = inputs(); audit = build_poster_audit(managers, picks)
    required = {"manager", "projected_xi_points", "starting_xi_minutes_pct", "starting_xi_minutes_coverage", "locked_starters", "likely_starters", "best_pick", "best_pick_adp_value", "best_pick_rank_value", "biggest_reach", "biggest_reach_adp_difference", "defense_gk_rank", "midfield_rank", "forward_rank", "bench_rank", "starting_xi_rank"}
    assert required.issubset(audit.columns) and len(audit) == 12


def test_tags_are_deterministic_limited_and_noncontradictory():
    managers, picks = inputs(); first, groups = build_poster_profiles(managers, picks); second, _ = build_poster_profiles(managers, picks)
    assert first["team_tags"].tolist() == second["team_tags"].tolist()
    for row in first.itertuples():
        tags = row.team_tags.split(" | ")
        assert 1 <= len(tags) <= 4
        assert not {"Minutes Secure", "Rotation Risk"}.issubset(tags)
        assert not {"Strong Bench", "Thin Bench"}.issubset(tags)
        bench_rank = int(groups[(groups["manager"].eq(row.manager)) & groups["group"].eq("Bench")]["league_rank"].iat[0])
        assert ("Thin Bench" in tags) == (bench_rank >= 10)


def test_poster_png_pdf_dimensions_order_and_protected_hashes():
    managers, picks = inputs(); png, pdf = poster_output_bytes(managers, picks)
    image = Image.open(BytesIO(png))
    assert image.size == POSTER_SIZE and image.format == "PNG"
    assert len(png) > 100_000 and pdf.startswith(b"%PDF") and len(pdf) > 100_000
    profiles, groups = build_poster_profiles(managers, picks)
    assert profiles["rank"].tolist() == list(range(1, 13))
    assert profiles["manager"].tolist() == managers.sort_values("overall_rank")["manager"].tolist()
    assert len(profiles) == 12 and len(groups) == 60
    assert hashlib.sha256((ROOT / "data/snapshots/draft_2627/draft_rankings_draft_day_2627.csv").read_bytes()).hexdigest() == SNAPSHOT_HASH
    assert hashlib.sha256((ROOT / "data/models/draft_2627/draft_pick_grades_2627.csv").read_bytes()).hexdigest() == PICK_HASH


def test_static_poster_outputs_exist_and_are_nonempty():
    png = ROOT / "reports/draft_grades_2627_poster.png"; pdf = ROOT / "reports/draft_grades_2627_poster.pdf"; audit = ROOT / "reports/draft_grades_2627_poster_audit.csv"
    assert Image.open(png).size == POSTER_SIZE
    assert png.stat().st_size > 100_000 and pdf.stat().st_size > 100_000
    assert len(pd.read_csv(audit)) == 12
