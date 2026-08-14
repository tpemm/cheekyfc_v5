from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from integrations.footballdata_normalizer import (
    combine_json_normalizations,
    discover_json_files,
    normalize_matches,
)


def clamp(value: pd.Series, low: float = 0, high: float = 100) -> pd.Series:
    return value.clip(lower=low, upper=high)


def build_team_perspective(matches: pd.DataFrame) -> pd.DataFrame:
    home = pd.DataFrame(
        {
            "match_id": matches["match_id"],
            "match_date": matches["match_date"],
            "game_week": matches["game_week"],
            "game_week_is_estimated": matches["game_week_is_estimated"],
            "team_id": matches["home_team_id"],
            "team_name": matches["home_team"],
            "opponent_id": matches["away_team_id"],
            "opponent": matches["away_team"],
            "venue": "Home",
            "team_win_probability": matches["home_win_probability"],
            "draw_probability": matches["draw_probability"],
            "opponent_win_probability": matches["away_win_probability"],
            "status": matches["status"],
        }
    )

    away = pd.DataFrame(
        {
            "match_id": matches["match_id"],
            "match_date": matches["match_date"],
            "game_week": matches["game_week"],
            "game_week_is_estimated": matches["game_week_is_estimated"],
            "team_id": matches["away_team_id"],
            "team_name": matches["away_team"],
            "opponent_id": matches["home_team_id"],
            "opponent": matches["home_team"],
            "venue": "Away",
            "team_win_probability": matches["away_win_probability"],
            "draw_probability": matches["draw_probability"],
            "opponent_win_probability": matches["home_win_probability"],
            "status": matches["status"],
        }
    )

    return pd.concat([home, away], ignore_index=True)


def build_fixture_strength(
    raw_folder: str | Path,
    team_strength_path: str | Path,
    output_path: str | Path,
) -> pd.DataFrame:
    raw_folder = Path(raw_folder)

    fixture_files = discover_json_files(
        raw_folder,
        [
            "matches_2627*.json",
            "**/matches_2627*.json",
        ],
    )

    matches = combine_json_normalizations(fixture_files, normalize_matches)

    if matches.empty:
        raise FileNotFoundError(
            f"No 2026/27 match JSON files found under {raw_folder}"
        )

    matches = matches.drop_duplicates(subset=["match_id"], keep="last")
    perspective = build_team_perspective(matches)

    team_strength_path = Path(team_strength_path)

    if team_strength_path.exists():
        strength = pd.read_csv(team_strength_path)

        opponent_strength = strength[
            [
                "team_id",
                "attack_rating",
                "defense_rating",
                "overall_team_rating",
            ]
        ].rename(
            columns={
                "team_id": "opponent_id",
                "attack_rating": "opponent_attack_rating",
                "defense_rating": "opponent_defense_rating",
                "overall_team_rating": "opponent_overall_rating",
            }
        )

        perspective = perspective.merge(
            opponent_strength,
            how="left",
            on="opponent_id",
        )
    else:
        perspective["opponent_attack_rating"] = np.nan
        perspective["opponent_defense_rating"] = np.nan
        perspective["opponent_overall_rating"] = np.nan

    for column in [
        "opponent_attack_rating",
        "opponent_defense_rating",
        "opponent_overall_rating",
    ]:
        perspective[column] = perspective[column].fillna(50.0)

    win_component = perspective["team_win_probability"].fillna(50.0)

    # Higher ease scores mean a better fantasy fixture.
    perspective["attacker_fixture_ease"] = clamp(
        win_component * 0.55
        + (100 - perspective["opponent_defense_rating"]) * 0.45
    )

    perspective["defender_fixture_ease"] = clamp(
        win_component * 0.55
        + (100 - perspective["opponent_attack_rating"]) * 0.45
    )

    perspective["overall_fixture_ease"] = clamp(
        win_component * 0.50
        + (100 - perspective["opponent_overall_rating"]) * 0.50
    )

    perspective["fixture_difficulty"] = 100 - perspective["overall_fixture_ease"]

    perspective["fixture_band"] = pd.cut(
        perspective["overall_fixture_ease"],
        bins=[-1, 35, 45, 55, 65, 101],
        labels=[
            "Very difficult",
            "Difficult",
            "Neutral",
            "Favorable",
            "Very favorable",
        ],
    )

    perspective["fixture_confidence"] = np.where(
        perspective["opponent_overall_rating"].eq(50.0),
        "probability-only",
        "team-strength-adjusted",
    )

    rating_columns = [
        "attacker_fixture_ease",
        "defender_fixture_ease",
        "overall_fixture_ease",
        "fixture_difficulty",
    ]
    perspective[rating_columns] = perspective[rating_columns].round(1)

    perspective = perspective.sort_values(
        ["match_date", "team_name"],
    ).reset_index(drop=True)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    perspective.to_csv(output_path, index=False)

    return perspective


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--raw-folder",
        default="data/raw/footballdata_io",
    )
    parser.add_argument(
        "--team-strength",
        default="data/analytics/draft/team_strength_2526.csv",
    )
    parser.add_argument(
        "--output",
        default="data/analytics/draft/fixture_difficulty_2627.csv",
    )
    args = parser.parse_args()

    result = build_fixture_strength(
        args.raw_folder,
        args.team_strength,
        args.output,
    )

    print(f"Built {len(result)} team-fixture rows.")
    print(f"Saved: {args.output}")

    estimated = int(result["game_week_is_estimated"].sum())
    if estimated:
        print(
            f"NOTE: {estimated} rows use estimated gameweeks because the API "
            "returned null game_week values."
        )


if __name__ == "__main__":
    main()
