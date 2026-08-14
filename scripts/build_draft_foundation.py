from __future__ import annotations

import argparse
import sys
from pathlib import Path


# Ensure the fantrax_data_v4 project root is importable when this file is run
# directly with:
#     python scripts\build_draft_foundation.py
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from analytics.build_fixture_strength import build_fixture_strength
from analytics.build_team_strength import build_team_strength
from integrations.footballdata_normalizer import (
    combine_json_normalizations,
    discover_json_files,
    normalize_matches,
    normalize_players,
    normalize_teams,
)


def save_frame(frame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    print(f"Saved {len(frame)} rows: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the first cached Footballdata.io draft datasets."
    )
    parser.add_argument(
        "--raw-folder",
        default="data/raw/footballdata_io",
    )
    parser.add_argument(
        "--output-folder",
        default="data/analytics/draft",
    )
    args = parser.parse_args()

    raw_folder = PROJECT_ROOT / args.raw_folder
    output_folder = PROJECT_ROOT / args.output_folder

    team_files = discover_json_files(
        raw_folder,
        ["teams_2627.json", "**/teams_2627.json"],
    )
    player_files = discover_json_files(
        raw_folder,
        ["team_*_players.json", "**/team_*_players.json"],
    )
    historical_match_files = discover_json_files(
        raw_folder,
        ["matches_2526*.json", "**/matches_2526*.json"],
    )
    fixture_files = discover_json_files(
        raw_folder,
        ["matches_2627*.json", "**/matches_2627*.json"],
    )

    teams = combine_json_normalizations(team_files, normalize_teams)
    players = combine_json_normalizations(player_files, normalize_players)
    historical_matches = combine_json_normalizations(
        historical_match_files,
        normalize_matches,
    )
    fixtures = combine_json_normalizations(
        fixture_files,
        normalize_matches,
    )

    if not teams.empty:
        teams = teams.drop_duplicates(subset=["team_id"], keep="last")
        save_frame(teams, output_folder / "teams_2627.csv")

    if not players.empty:
        players = players.drop_duplicates(
            subset=["football_data_player_id", "season_id"],
            keep="last",
        )
        save_frame(players, output_folder / "football_players_2526.csv")

        invalid_minutes = int((~players["minutes_valid"]).sum())
        if invalid_minutes:
            print(
                f"WARNING: {invalid_minutes} players have invalid API minute "
                "totals. These rows are flagged and should not be used for "
                "per-90 projections until reconciled with Fantrax data."
            )

    if not historical_matches.empty:
        historical_matches = historical_matches.drop_duplicates(
            subset=["match_id"],
            keep="last",
        )
        save_frame(
            historical_matches,
            output_folder / "matches_2526_normalized.csv",
        )

        bad_scores = int((~historical_matches["score_total_valid"]).sum())
        if bad_scores:
            print(
                f"WARNING: {bad_scores} completed matches have inconsistent "
                "score.total_goals fields. The normalized calculated total is "
                "preserved separately."
            )

    if not fixtures.empty:
        fixtures = fixtures.drop_duplicates(subset=["match_id"], keep="last")
        save_frame(
            fixtures,
            output_folder / "fixtures_2627_normalized.csv",
        )

    team_strength_path = output_folder / "team_strength_2526.csv"
    fixture_strength_path = output_folder / "fixture_difficulty_2627.csv"

    team_strength = build_team_strength(raw_folder, team_strength_path)
    print(f"Saved {len(team_strength)} rows: {team_strength_path}")

    fixture_strength = build_fixture_strength(
        raw_folder,
        team_strength_path,
        fixture_strength_path,
    )
    print(f"Saved {len(fixture_strength)} rows: {fixture_strength_path}")

    print("\nFoundation build complete.")
    print("No API requests were made. Everything was built from cached JSON.")


if __name__ == "__main__":
    main()
