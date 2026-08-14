from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


BASE_URL = "https://footballdata.io/api/v1"

LEAGUE_ID = 15
SEASON_2526_ID = 189
SEASON_2627_ID = 103535

OUTPUT_DIR = Path("data/raw/footballdata_io/coverage_test")


def api_get(
    path: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send a GET request to Footballdata.io and return JSON data."""
    api_key = os.getenv("FOOTBALLDATA_IO_API_KEY")

    if not api_key:
        raise RuntimeError(
            "FOOTBALLDATA_IO_API_KEY was not found. "
            "Check that your .env file exists in the project root."
        )

    response = requests.get(
        f"{BASE_URL}/{path.lstrip('/')}",
        headers={"Authorization": f"Bearer {api_key}"},
        params=params,
        timeout=30,
    )

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"API returned non-JSON content for {path}. "
            f"HTTP status: {response.status_code}"
        ) from exc

    if response.status_code >= 400:
        raise RuntimeError(
            f"API request failed for {path}\n"
            f"HTTP {response.status_code}\n"
            f"{json.dumps(payload, indent=2)}"
        )

    if isinstance(payload, dict) and payload.get("success") is False:
        raise RuntimeError(
            f"API reported a failed request for {path}\n"
            f"{json.dumps(payload, indent=2)}"
        )

    return payload


def save_json(
    filename: str,
    payload: dict[str, Any],
) -> None:
    """Save an API response as formatted JSON."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    path = OUTPUT_DIR / filename

    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Saved: {path}")


def get_data(payload: dict[str, Any]) -> Any:
    """Return the response's data field when present."""
    return payload.get("data", payload)


def find_first_list(value: Any) -> list[dict[str, Any]]:
    """
    Recursively find the first list containing dictionary records.

    This is useful because different Footballdata.io endpoints may
    nest records under fields such as teams, players, or matches.
    """
    if isinstance(value, list):
        return [
            item
            for item in value
            if isinstance(item, dict)
        ]

    if isinstance(value, dict):
        for item in value.values():
            result = find_first_list(item)

            if result:
                return result

    return []


def get_identifier(
    record: dict[str, Any],
    possible_names: list[str],
) -> Any:
    """Return the first matching identifier field from a record."""
    for name in possible_names:
        value = record.get(name)

        if value is not None:
            return value

    return None


def get_nested_identifier(
    record: dict[str, Any],
    nested_field: str,
    possible_names: list[str],
) -> Any:
    """Look for an identifier inside a nested dictionary."""
    nested_record = record.get(nested_field, {})

    if not isinstance(nested_record, dict):
        return None

    return get_identifier(
        nested_record,
        possible_names,
    )


def summarize_response(
    label: str,
    payload: dict[str, Any],
) -> None:
    """Print a basic summary of an API response."""
    data = get_data(payload)

    print(f"\n--- {label} ---")

    if isinstance(data, dict):
        print("Top-level data fields:")
        print(", ".join(sorted(data.keys())) or "(none)")

        records = find_first_list(data)

        print(f"First discovered record count: {len(records)}")

        if records:
            print("Example record fields:")
            print(", ".join(sorted(records[0].keys())))

            print("Example record:")
            print(
                json.dumps(
                    records[0],
                    indent=2,
                    ensure_ascii=False,
                )
            )

    elif isinstance(data, list):
        print(f"Record count: {len(data)}")

        if data and isinstance(data[0], dict):
            print("Example record fields:")
            print(", ".join(sorted(data[0].keys())))

            print("Example record:")
            print(
                json.dumps(
                    data[0],
                    indent=2,
                    ensure_ascii=False,
                )
            )

    else:
        print(f"Data type: {type(data).__name__}")


def main() -> None:
    load_dotenv()

    print("Testing Footballdata.io Premier League coverage...")
    print(f"Premier League league ID: {LEAGUE_ID}")
    print(f"2025/26 season ID: {SEASON_2526_ID}")
    print(f"2026/27 season ID: {SEASON_2627_ID}")

    # ---------------------------------------------------------
    # 1. Current 2026/27 teams
    # ---------------------------------------------------------

    try:
        teams_2627 = api_get(
            f"seasons/{SEASON_2627_ID}/teams"
        )
    except RuntimeError as exc:
        print("\nUnable to retrieve 2026/27 teams:")
        print(exc)
        return

    save_json(
        "teams_2627.json",
        teams_2627,
    )

    summarize_response(
        "2026/27 teams",
        teams_2627,
    )

    team_records = find_first_list(
        get_data(teams_2627)
    )

    if not team_records:
        print("\nNo 2026/27 team records were found.")
        return

    first_team = team_records[0]

    team_details = first_team.get("team", {})

    if not isinstance(team_details, dict):
        team_details = {}

    team_id = (
        team_details.get("team_id")
        or first_team.get("team_id")
        or first_team.get("id")
        or first_team.get("teamId")
    )

    season_team_id = (
        first_team.get("season_team_id")
        or first_team.get("seasonTeamId")
    )

    team_name = (
        team_details.get("team_name")
        or first_team.get("team_name")
        or first_team.get("name")
        or "Unknown team"
    )

    print(
        f"\nFirst team selected for testing: {team_name}"
    )
    print(f"Detected team ID: {team_id}")
    print(f"Detected season-team ID: {season_team_id}")

    if team_id is None:
        print("Could not identify the team ID field.")
        return

    # ---------------------------------------------------------
    # 2. Current team squad
    # ---------------------------------------------------------

    player_records: list[dict[str, Any]] = []

    try:
        team_players = api_get(
            f"teams/{team_id}/players"
        )

        save_json(
            f"team_{team_id}_players.json",
            team_players,
        )

        summarize_response(
            "Team players",
            team_players,
        )

        player_records = find_first_list(
            get_data(team_players)
        )

    except RuntimeError as exc:
        print("\nTeam-player endpoint unavailable or restricted:")
        print(exc)

    # ---------------------------------------------------------
    # 3. Team statistics
    # ---------------------------------------------------------

    try:
        team_stats = api_get(
            f"teams/{team_id}/stats",
            params={
                "season_id": SEASON_2526_ID,
            },
        )

        save_json(
            f"team_{team_id}_stats_2526.json",
            team_stats,
        )

        summarize_response(
            "2025/26 team statistics",
            team_stats,
        )

    except RuntimeError as exc:
        print("\nTeam stats unavailable or restricted:")
        print(exc)

    # ---------------------------------------------------------
    # 4. Player statistics
    # ---------------------------------------------------------

    if player_records:
        first_player = player_records[0]

        player_details = first_player.get("player", {})

        if not isinstance(player_details, dict):
            player_details = {}

        player_id = (
            player_details.get("player_id")
            or first_player.get("player_id")
            or first_player.get("id")
            or first_player.get("playerId")
        )

        player_name = (
            player_details.get("player_name")
            or player_details.get("name")
            or first_player.get("player_name")
            or first_player.get("name")
            or "Unknown player"
        )

        print(
            f"\nFirst player selected for testing: "
            f"{player_name}"
        )
        print(f"Detected player ID: {player_id}")

        if player_id is not None:
            try:
                player_stats = api_get(
                    f"players/{player_id}/stats",
                    params={
                        "season_id": SEASON_2526_ID,
                    },
                )

                save_json(
                    f"player_{player_id}_stats_2526.json",
                    player_stats,
                )

                summarize_response(
                    "2025/26 player statistics",
                    player_stats,
                )

            except RuntimeError as exc:
                print(
                    "\nPlayer stats unavailable or restricted:"
                )
                print(exc)

        else:
            print(
                "Could not identify a player ID "
                "from the team-player response."
            )

    else:
        print(
            "\nNo player records were available, "
            "so the player-statistics test was skipped."
        )

    # ---------------------------------------------------------
    # 5. Completed 2025/26 matches
    # ---------------------------------------------------------

    match_records: list[dict[str, Any]] = []

    try:
        matches_2526 = api_get(
            f"seasons/{SEASON_2526_ID}/matches",
            params={
                "page": 1,
                "limit": 100,
            },
        )

        save_json(
            "matches_2526_page_1.json",
            matches_2526,
        )

        summarize_response(
            "2025/26 matches",
            matches_2526,
        )

        match_records = find_first_list(
            get_data(matches_2526)
        )

    except RuntimeError as exc:
        print("\n2025/26 matches unavailable or restricted:")
        print(exc)

    completed_match = None

    for match in match_records:
        status_value = (
            match.get("status")
            or match.get("state")
            or match.get("match_status")
            or match.get("status_name")
            or ""
        )

        if isinstance(status_value, dict):
            status_text = " ".join(
                str(value)
                for value in status_value.values()
            ).lower()
        else:
            status_text = str(status_value).lower()

        if any(
            status_word in status_text
            for status_word in [
                "finished",
                "complete",
                "completed",
                "full time",
                "full-time",
                "ft",
            ]
        ):
            completed_match = match
            break

    if completed_match is None and match_records:
        completed_match = match_records[0]

    if completed_match:
        match_details = completed_match.get("match", {})

        if not isinstance(match_details, dict):
            match_details = {}

        match_id = (
            match_details.get("match_id")
            or completed_match.get("match_id")
            or completed_match.get("id")
            or completed_match.get("fixture_id")
            or completed_match.get("matchId")
        )

        print("\nMatch selected for stats test:")
        print(
            json.dumps(
                completed_match,
                indent=2,
                ensure_ascii=False,
            )
        )
        print(f"Detected match ID: {match_id}")

        if match_id is not None:
            try:
                match_stats = api_get(
                    f"matches/{match_id}/stats"
                )

                save_json(
                    f"match_{match_id}_stats.json",
                    match_stats,
                )

                summarize_response(
                    "Match statistics",
                    match_stats,
                )

            except RuntimeError as exc:
                print(
                    "\nMatch stats unavailable or restricted:"
                )
                print(exc)

            try:
                match_events = api_get(
                    f"matches/{match_id}/events"
                )

                save_json(
                    f"match_{match_id}_events.json",
                    match_events,
                )

                summarize_response(
                    "Match events",
                    match_events,
                )

            except RuntimeError as exc:
                print(
                    "\nMatch events unavailable or restricted:"
                )
                print(exc)

        else:
            print(
                "Could not identify a match ID, "
                "so match stats and events were skipped."
            )

    else:
        print(
            "\nNo 2025/26 matches were found, "
            "so match stats and events were skipped."
        )

    # ---------------------------------------------------------
    # 6. Available 2026/27 fixtures
    # ---------------------------------------------------------

    try:
        matches_2627 = api_get(
            f"seasons/{SEASON_2627_ID}/matches",
            params={
                "page": 1,
                "limit": 100,
            },
        )

        save_json(
            "matches_2627_page_1.json",
            matches_2627,
        )

        summarize_response(
            "2026/27 matches",
            matches_2627,
        )

    except RuntimeError as exc:
        print("\n2026/27 matches unavailable or restricted:")
        print(exc)

    print("\nCoverage test finished.")
    print(f"Review the JSON files in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()