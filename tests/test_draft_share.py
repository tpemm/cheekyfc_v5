from pathlib import Path
from io import BytesIO
import html as html_module

import numpy as np
import pandas as pd

from analytics.draft.grading import best_legal_xi
from analytics.draft.share import SHARE_COLUMNS, build_share_summary, group_chat_text, share_csv, share_html


ROOT = Path(__file__).resolve().parents[1]


def inputs():
    return (pd.read_csv(ROOT / "data/models/draft_2627/draft_manager_grades_2627.csv"),
            pd.read_csv(ROOT / "data/models/draft_2627/draft_pick_grades_2627.csv"),
            pd.read_csv(ROOT / "data/models/draft_2627/draft_awards_2627.csv"))


def test_share_statistics_reconcile_to_authoritative_sources():
    managers, picks, _ = inputs(); summary = build_share_summary(managers, picks)
    assert len(summary) == 12
    for row in summary.itertuples():
        team = picks[picks["manager"].eq(row.manager)]
        xi, _ = best_legal_xi(team)
        assert len(xi) == 11 and xi.index.is_unique
        assert row.projected_starting_xi_points == pd.to_numeric(xi["projected_points"]).sum()
        assert row.average_player_projection == pd.to_numeric(team["projected_points"]).mean()
        assert row.average_adp == pd.to_numeric(team["adp"], errors="coerce").mean()
        assert row.average_adp != 999
        minutes = pd.to_numeric(team["minutes_2526"])
        valid = minutes.gt(0)
        assert row.fantasy_points_per_90 == np.sum(team.loc[valid, "total_fantasy_points"]) * 90 / minutes[valid].sum()
        assert row.ghost_points_per_90 == np.sum(team.loc[valid, "ghost_points"]) * 90 / minutes[valid].sum()
        opportunities = pd.to_numeric(team["weeks_available"])
        start_valid = opportunities.gt(0)
        assert row.historical_start_pct == pd.to_numeric(team.loc[start_valid, "starts_2526"]).sum() / opportunities[start_valid].sum() * 100
        assert row.projected_minutes_pct == pd.to_numeric(team["projected_minutes_share"]).mean()


def test_share_schema_plain_language_labels_and_ranking():
    managers, picks, _ = inputs(); summary = build_share_summary(managers, picks)
    assert list(summary.sort_values("rank")["manager"]) == list(managers.sort_values("overall_rank")["manager"])
    assert summary["main_strength"].str.strip().ne("").all()
    assert summary["main_concern"].str.strip().ne("").all()
    csv_frame = pd.read_csv(BytesIO(share_csv(summary)))
    assert tuple(csv_frame.columns) == SHARE_COLUMNS
    assert "raw_analytical_score" not in csv_frame
    forbidden = {"Production Score", "Floor Score", "Context Score", "Attacking Score", "Minutes Score"}
    assert forbidden.isdisjoint(csv_frame.columns)


def test_share_reports_are_complete_and_deterministic():
    managers, picks, awards = inputs(); summary = build_share_summary(managers, picks)
    assert share_csv(summary) == share_csv(build_share_summary(managers, picks))
    html = share_html(summary); chat = group_chat_text(summary, awards)
    assert html == share_html(summary)
    for manager in managers["manager"]:
        assert html_module.escape(manager) in html and manager in chat
    assert "League Awards" in chat
    assert len(pd.read_csv(ROOT / "reports/draft_grades_2627_share.csv")) == 12
    report_html = (ROOT / "reports/draft_grades_2627_share.html").read_text(encoding="utf-8")
    assert all(html_module.escape(manager) in report_html for manager in managers["manager"])


def test_strength_and_concern_retain_stat_ranks_and_percentiles():
    managers, picks, _ = inputs(); summary = build_share_summary(managers, picks)
    rank_columns = [column for column in summary if column.endswith("_league_rank")]
    percentile_columns = [column for column in summary if column.endswith("_league_percentile")]
    assert len(rank_columns) == len(percentile_columns) == 8
    assert summary[rank_columns].notna().all().all()
    assert summary[percentile_columns].apply(lambda values: values.between(0, 100).all()).all()
