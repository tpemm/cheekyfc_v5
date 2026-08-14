"""Frozen Draft Score, ordering, tier, and ADP calculations."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd


def percentile(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    ranked = numeric.rank(pct=True, method="average")
    if not higher_is_better:
        ranked = 1 - ranked
    return ranked.fillna(0.0) * 100


def _stable_id(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def build_rankings(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply the approved formula plus a non-semantic stable final tie-break."""
    out = frame.copy()
    production = (
        0.60 * percentile(out["fantasy_ppg_2526"])
        + 0.40 * percentile(out["fantasy_fp90_2526"])
    )
    ghost = percentile(out["ghost_ppg_2526"])
    attacking = percentile(out["xgi90_2526"])
    minutes = out["projected_minutes_share"].fillna(0)
    team = (
        0.65 * percentile(out["team_attack_rating"])
        + 0.35 * percentile(out["team_strength_rating"])
    )
    fixtures = percentile(out["fixture_ease_next_5"])

    out["production_score"] = production.round(1)
    out["ghost_score"] = ghost.round(1)
    out["attacking_score"] = attacking.round(1)
    out["minutes_score"] = minutes.round(1)
    out["team_context_score"] = team.round(1)
    out["fixture_score"] = fixtures.round(1)
    out["draft_score"] = (
        0.30 * production
        + 0.20 * minutes
        + 0.15 * ghost
        + 0.15 * attacking
        + 0.10 * team
        + 0.10 * fixtures
    ).round(2)

    history_flag = out.get(
        "has_historical_data",
        out["fantasy_points_2526"].notna(),
    ).fillna(False).astype(bool)
    out["data_confidence"] = (
        0.45 * out["minutes_confidence"].fillna(0)
        + 25 * history_flag.astype(int)
        + 20 * out["understat_player_id"].replace("", np.nan).notna().astype(int)
        + 10 * out["team_strength_rating"].notna().astype(int)
    ).clip(0, 100).round(1)

    out["_stable_player_id"] = out["fantrax_player_id"].map(_stable_id)
    out = out.sort_values(
        [
            "is_draft_eligible",
            "draft_score",
            "data_confidence",
            "fantasy_ppg_2526",
            "_stable_player_id",
        ],
        ascending=[False, False, False, False, True],
        na_position="last",
    ).drop(columns="_stable_player_id").reset_index(drop=True)

    eligible = out["is_draft_eligible"].fillna(False)
    out["overall_rank"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
    out.loc[eligible, "overall_rank"] = np.arange(1, int(eligible.sum()) + 1)
    out["tier"] = pd.Series(pd.NA, index=out.index, dtype="object")
    out.loc[eligible, "tier"] = pd.cut(
        pd.to_numeric(out.loc[eligible, "overall_rank"], errors="coerce"),
        bins=[0, 12, 36, 72, 120, 180, 300, np.inf],
        labels=["Tier 1", "Tier 2", "Tier 3", "Tier 4", "Tier 5", "Tier 6", "Deep"],
    ).astype(str).values

    out["value_vs_adp"] = np.where(
        eligible & out["fantrax_adp"].notna(),
        out["fantrax_adp"] - pd.to_numeric(out["overall_rank"], errors="coerce"),
        np.nan,
    )
    out["adp_status"] = np.select(
        [
            ~eligible,
            out["fantrax_adp"].isna(),
            out["value_vs_adp"] >= 20,
            out["value_vs_adp"] >= 8,
            out["value_vs_adp"] <= -20,
            out["value_vs_adp"] <= -8,
        ],
        ["Not draft eligible", "ADP unavailable", "Strong value", "Value", "Major reach", "Reach"],
        default="Near market",
    )
    return out
