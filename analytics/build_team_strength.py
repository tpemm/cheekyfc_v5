from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from integrations.footballdata_normalizer import (
    combine_json_normalizations,
    discover_json_files,
    normalize_team_stats,
)


HIGHER_BETTER_WEIGHTS = {
    "attack_rating": {
        "xg_for_per_match": 0.35,
        "goals_for_per_match": 0.25,
        "shots_per_match": 0.15,
        "shots_on_target_per_match": 0.15,
        "possession_average": 0.10,
    },
    "control_rating": {
        "possession_average": 0.45,
        "corners_for_per_match": 0.25,
        "fouls_drawn_per_match": 0.15,
        "points_per_game": 0.15,
    },
}

DEFENSE_WEIGHTS = {
    "xg_against_per_match": 0.40,
    "goals_against_per_match": 0.30,
    "clean_sheet_percentage": 0.20,
    "loss_percentage": 0.10,
}


def percentile_score(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")

    if numeric.notna().sum() <= 1:
        return pd.Series(50.0, index=series.index)

    rank = numeric.rank(method="average", pct=True)
    score = rank * 100

    if not higher_is_better:
        score = 100 - score + (100 / numeric.notna().sum())

    return score.clip(0, 100).fillna(50.0)


def weighted_rating(
    frame: pd.DataFrame,
    weights: dict[str, float],
    inverse_fields: set[str] | None = None,
) -> pd.Series:
    inverse_fields = inverse_fields or set()
    parts: list[pd.Series] = []
    applied_weights: list[float] = []

    for field, weight in weights.items():
        if field not in frame.columns:
            continue

        parts.append(
            percentile_score(
                frame[field],
                higher_is_better=field not in inverse_fields,
            )
            * weight
        )
        applied_weights.append(weight)

    if not parts or sum(applied_weights) == 0:
        return pd.Series(50.0, index=frame.index)

    return sum(parts) / sum(applied_weights)


def build_team_strength(
    raw_folder: str | Path,
    output_path: str | Path,
) -> pd.DataFrame:
    raw_folder = Path(raw_folder)
    files = discover_json_files(
        raw_folder,
        [
            "team_*_stats_2526.json",
            "team_*_stats*.json",
            "**/team_*_stats_2526.json",
            "**/team_*_stats*.json",
        ],
    )

    stats = combine_json_normalizations(files, normalize_team_stats)

    if stats.empty:
        raise FileNotFoundError(
            f"No team-stat JSON files found under {raw_folder}"
        )

    stats = stats.drop_duplicates(
        subset=["team_id", "season_id"],
        keep="last",
    ).reset_index(drop=True)

    stats["attack_rating"] = weighted_rating(
        stats,
        HIGHER_BETTER_WEIGHTS["attack_rating"],
    )

    stats["defense_rating"] = weighted_rating(
        stats,
        DEFENSE_WEIGHTS,
        inverse_fields={
            "xg_against_per_match",
            "goals_against_per_match",
            "loss_percentage",
        },
    )

    stats["control_rating"] = weighted_rating(
        stats,
        HIGHER_BETTER_WEIGHTS["control_rating"],
    )

    stats["overall_team_rating"] = (
        stats["attack_rating"] * 0.45
        + stats["defense_rating"] * 0.40
        + stats["control_rating"] * 0.15
    )

    stats["model_confidence"] = np.where(
        len(stats) >= 18,
        "full-league",
        np.where(len(stats) >= 10, "partial-league", "prototype"),
    )

    stats["team_strength_rank"] = (
        stats["overall_team_rating"]
        .rank(method="min", ascending=False)
        .astype(int)
    )

    keep = [
        "team_strength_rank",
        "team_id",
        "team_name",
        "season_id",
        "season_year",
        "matches_played",
        "attack_rating",
        "defense_rating",
        "control_rating",
        "overall_team_rating",
        "xg_for_per_match",
        "xg_against_per_match",
        "goals_for_per_match",
        "goals_against_per_match",
        "shots_per_match",
        "shots_on_target_per_match",
        "clean_sheet_percentage",
        "possession_average",
        "points_per_game",
        "model_confidence",
        "last_updated",
    ]

    result = stats[[column for column in keep if column in stats.columns]].copy()

    rating_columns = [
        "attack_rating",
        "defense_rating",
        "control_rating",
        "overall_team_rating",
    ]
    result[rating_columns] = result[rating_columns].round(1)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)

    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--raw-folder",
        default="data/raw/footballdata_io",
    )
    parser.add_argument(
        "--output",
        default="data/analytics/draft/team_strength_2526.csv",
    )
    args = parser.parse_args()

    result = build_team_strength(args.raw_folder, args.output)

    print(f"Built {len(result)} team-strength rows.")
    print(f"Saved: {args.output}")

    if len(result) < 18:
        print(
            "WARNING: Fewer than 18 teams were found. Ratings are prototype "
            "scores until the full league's team-stat files are downloaded."
        )


if __name__ == "__main__":
    main()
