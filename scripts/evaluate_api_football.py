#!/usr/bin/env python3
"""
Read-only API-Football evaluation for the Fantrax Data project.

What it tests:
- Account/API access and quota headers
- Current Premier League season
- EPL teams
- Current squad for every EPL team
- EPL injuries
- Upcoming EPL fixtures
- Recent EPL fixtures
- Transfers for a small sample of EPL teams
- Lineups for a recent fixture, when available
- Predictions for an upcoming fixture, when available

Expected request use:
About 27-31 requests, depending on available fixtures.

Setup in PowerShell:
    $env:API_FOOTBALL_KEY="YOUR_API_KEY"
    python evaluate_api_football.py

Optional:
    python evaluate_api_football.py --output data/api_football_test
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


BASE_URL = "https://v3.football.api-sports.io"
EPL_LEAGUE_ID = 39


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ApiFootballClient:
    def __init__(self, api_key: str, output_dir: Path) -> None:
        self.session = requests.Session()
        self.session.headers.update({"x-apisports-key": api_key})
        self.output_dir = output_dir
        self.request_count = 0
        self.last_quota: dict[str, str | None] = {}

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.request_count += 1
        url = f"{BASE_URL}/{endpoint.lstrip('/')}"
        print(f"[{self.request_count:02d}] GET /{endpoint}  params={params or {}}")

        response = self.session.get(url, params=params or {}, timeout=45)
        self.last_quota = {
            "daily_limit": response.headers.get("x-ratelimit-requests-limit"),
            "daily_remaining": response.headers.get("x-ratelimit-requests-remaining"),
            "minute_limit": response.headers.get("x-ratelimit-limit"),
            "minute_remaining": response.headers.get("x-ratelimit-remaining"),
        }

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"API returned non-JSON response ({response.status_code}): "
                f"{response.text[:500]}"
            ) from exc

        if response.status_code >= 400:
            raise RuntimeError(
                f"HTTP {response.status_code} for /{endpoint}: "
                f"{json.dumps(payload, indent=2)[:1500]}"
            )

        errors = payload.get("errors")
        if errors:
            raise RuntimeError(
                f"API error for /{endpoint}: {json.dumps(errors, indent=2)}"
            )

        # Stay comfortably below the free plan's per-minute limit.
        time.sleep(0.35)
        return payload


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)

    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def extract_current_epl_season(leagues_payload: dict[str, Any]) -> int:
    responses = leagues_payload.get("response", [])
    if not responses:
        raise RuntimeError("No Premier League record was returned.")

    seasons = responses[0].get("seasons", [])
    current = [s for s in seasons if s.get("current") is True]
    if current:
        return int(current[-1]["year"])

    # Fallback to the newest available season if the API has not marked one current.
    if seasons:
        return int(max(s["year"] for s in seasons if s.get("year") is not None))

    raise RuntimeError("No season data was returned for the Premier League.")


def flatten_teams(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in payload.get("response", []):
        team = item.get("team", {})
        venue = item.get("venue", {})
        rows.append(
            {
                "team_id": team.get("id"),
                "team_name": team.get("name"),
                "team_code": team.get("code"),
                "country": team.get("country"),
                "founded": team.get("founded"),
                "national": team.get("national"),
                "logo": team.get("logo"),
                "venue_id": venue.get("id"),
                "venue_name": venue.get("name"),
                "venue_city": venue.get("city"),
            }
        )
    return rows


def flatten_squad(payload: dict[str, Any], retrieved_at: str) -> list[dict[str, Any]]:
    rows = []
    for team_block in payload.get("response", []):
        team = team_block.get("team", {})
        for player in team_block.get("players", []):
            rows.append(
                {
                    "api_player_id": player.get("id"),
                    "player_name": player.get("name"),
                    "age": player.get("age"),
                    "shirt_number": player.get("number"),
                    "position": player.get("position"),
                    "photo": player.get("photo"),
                    "api_team_id": team.get("id"),
                    "current_team": team.get("name"),
                    "team_logo": team.get("logo"),
                    "retrieved_at_utc": retrieved_at,
                }
            )
    return rows


def flatten_injuries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in payload.get("response", []):
        player = item.get("player", {})
        team = item.get("team", {})
        fixture = item.get("fixture", {})
        league = item.get("league", {})
        rows.append(
            {
                "player_id": player.get("id"),
                "player_name": player.get("name"),
                "player_type": player.get("type"),
                "injury_reason": player.get("reason"),
                "team_id": team.get("id"),
                "team_name": team.get("name"),
                "fixture_id": fixture.get("id"),
                "fixture_date": fixture.get("date"),
                "fixture_timezone": fixture.get("timezone"),
                "league_id": league.get("id"),
                "season": league.get("season"),
            }
        )
    return rows


def flatten_fixtures(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in payload.get("response", []):
        fixture = item.get("fixture", {})
        league = item.get("league", {})
        teams = item.get("teams", {})
        goals = item.get("goals", {})
        status = fixture.get("status", {})
        rows.append(
            {
                "fixture_id": fixture.get("id"),
                "date": fixture.get("date"),
                "timestamp": fixture.get("timestamp"),
                "timezone": fixture.get("timezone"),
                "status_short": status.get("short"),
                "status_long": status.get("long"),
                "league_id": league.get("id"),
                "league_name": league.get("name"),
                "season": league.get("season"),
                "round": league.get("round"),
                "home_team_id": teams.get("home", {}).get("id"),
                "home_team": teams.get("home", {}).get("name"),
                "away_team_id": teams.get("away", {}).get("id"),
                "away_team": teams.get("away", {}).get("name"),
                "home_goals": goals.get("home"),
                "away_goals": goals.get("away"),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate API-Football for Fantrax Data.")
    parser.add_argument(
        "--output",
        default="api_football_evaluation",
        help="Folder for raw JSON, CSV files, and summary.",
    )
    parser.add_argument(
        "--transfer-teams",
        type=int,
        default=3,
        help="Number of EPL clubs to sample for transfer testing (default: 3).",
    )
    args = parser.parse_args()

    api_key = os.getenv("API_FOOTBALL_KEY", "").strip()
    if not api_key:
        print(
            "\nERROR: API_FOOTBALL_KEY is not set.\n\n"
            "In PowerShell run:\n"
            '  $env:API_FOOTBALL_KEY="YOUR_API_KEY"\n'
            "Then run this script again.\n",
            file=sys.stderr,
        )
        return 2

    output_dir = Path(args.output).resolve()
    raw_dir = output_dir / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    client = ApiFootballClient(api_key, output_dir)
    started_at = utc_now()

    summary: dict[str, Any] = {
        "started_at_utc": started_at,
        "league_id": EPL_LEAGUE_ID,
        "tests": {},
        "warnings": [],
    }

    try:
        # 1. Account/API status
        status = client.get("status")
        save_json(raw_dir / "01_status.json", status)
        summary["tests"]["status"] = {
            "ok": True,
            "response_count": status.get("results"),
            "account": status.get("response"),
        }

        # 2. Determine the current EPL season automatically
        leagues = client.get("leagues", {"id": EPL_LEAGUE_ID, "current": "true"})
        save_json(raw_dir / "02_league_current.json", leagues)

        if not leagues.get("response"):
            leagues = client.get("leagues", {"id": EPL_LEAGUE_ID})
            save_json(raw_dir / "02b_league_all_seasons.json", leagues)

        season = extract_current_epl_season(leagues)
        summary["season"] = season
        print(f"\nDetected Premier League season parameter: {season}\n")

        # 3. EPL teams
        teams_payload = client.get(
            "teams", {"league": EPL_LEAGUE_ID, "season": season}
        )
        save_json(raw_dir / "03_teams.json", teams_payload)
        team_rows = flatten_teams(teams_payload)
        write_csv(output_dir / "api_football_epl_teams.csv", team_rows)
        summary["tests"]["teams"] = {
            "ok": bool(team_rows),
            "team_count": len(team_rows),
        }

        if not team_rows:
            raise RuntimeError(
                "No EPL teams were returned. The free plan may not expose this season."
            )

        # 4. Current squad for every EPL team
        retrieved_at = utc_now()
        squad_rows: list[dict[str, Any]] = []
        squad_counts: dict[str, int] = {}

        for index, team in enumerate(team_rows, start=1):
            team_id = team["team_id"]
            team_name = team["team_name"]
            payload = client.get("players/squads", {"team": team_id})
            save_json(raw_dir / f"04_squad_{team_id}.json", payload)
            rows = flatten_squad(payload, retrieved_at)
            squad_rows.extend(rows)
            squad_counts[str(team_name)] = len(rows)
            print(f"     {team_name}: {len(rows)} players")

        write_csv(output_dir / "api_football_epl_squads.csv", squad_rows)
        summary["tests"]["squads"] = {
            "ok": bool(squad_rows),
            "total_players": len(squad_rows),
            "unique_player_ids": len(
                {row["api_player_id"] for row in squad_rows if row["api_player_id"]}
            ),
            "teams_with_squads": sum(1 for value in squad_counts.values() if value > 0),
            "players_per_team": squad_counts,
        }

        empty_squads = [team for team, count in squad_counts.items() if count == 0]
        if empty_squads:
            summary["warnings"].append(
                f"Teams with empty squad responses: {', '.join(empty_squads)}"
            )

        # 5. EPL injuries
        try:
            injuries_payload = client.get(
                "injuries", {"league": EPL_LEAGUE_ID, "season": season}
            )
            save_json(raw_dir / "05_injuries.json", injuries_payload)
            injury_rows = flatten_injuries(injuries_payload)
            write_csv(output_dir / "api_football_epl_injuries.csv", injury_rows)
            summary["tests"]["injuries"] = {
                "ok": True,
                "record_count": len(injury_rows),
            }
        except Exception as exc:
            summary["tests"]["injuries"] = {"ok": False, "error": str(exc)}
            summary["warnings"].append(f"Injury test failed: {exc}")

        # 6. Upcoming fixtures
        upcoming_payload = client.get(
            "fixtures",
            {"league": EPL_LEAGUE_ID, "season": season, "next": 10},
        )
        save_json(raw_dir / "06_upcoming_fixtures.json", upcoming_payload)
        upcoming_rows = flatten_fixtures(upcoming_payload)
        write_csv(output_dir / "api_football_epl_upcoming_fixtures.csv", upcoming_rows)
        summary["tests"]["upcoming_fixtures"] = {
            "ok": True,
            "fixture_count": len(upcoming_rows),
        }

        # 7. Recent fixtures
        recent_payload = client.get(
            "fixtures",
            {"league": EPL_LEAGUE_ID, "season": season, "last": 10},
        )
        save_json(raw_dir / "07_recent_fixtures.json", recent_payload)
        recent_rows = flatten_fixtures(recent_payload)
        write_csv(output_dir / "api_football_epl_recent_fixtures.csv", recent_rows)
        summary["tests"]["recent_fixtures"] = {
            "ok": True,
            "fixture_count": len(recent_rows),
        }

        # 8. Transfers for a small team sample
        transfer_summary: dict[str, Any] = {}
        transfer_sample = team_rows[: max(0, args.transfer_teams)]
        for team in transfer_sample:
            try:
                payload = client.get("transfers", {"team": team["team_id"]})
                save_json(
                    raw_dir / f"08_transfers_{team['team_id']}.json",
                    payload,
                )
                transfer_summary[str(team["team_name"])] = {
                    "ok": True,
                    "response_count": len(payload.get("response", [])),
                }
            except Exception as exc:
                transfer_summary[str(team["team_name"])] = {
                    "ok": False,
                    "error": str(exc),
                }
        summary["tests"]["transfers"] = transfer_summary

        # 9. Actual lineups for the most recent fixture available
        if recent_rows:
            fixture_id = recent_rows[0]["fixture_id"]
            try:
                lineups = client.get("fixtures/lineups", {"fixture": fixture_id})
                save_json(raw_dir / f"09_lineups_{fixture_id}.json", lineups)
                summary["tests"]["lineups"] = {
                    "ok": True,
                    "fixture_id": fixture_id,
                    "team_lineup_count": len(lineups.get("response", [])),
                    "has_lineup_data": bool(lineups.get("response")),
                }
            except Exception as exc:
                summary["tests"]["lineups"] = {
                    "ok": False,
                    "fixture_id": fixture_id,
                    "error": str(exc),
                }
        else:
            summary["tests"]["lineups"] = {
                "ok": False,
                "skipped": True,
                "reason": "No recent fixture was available for the detected season.",
            }

        # 10. Match prediction for the next fixture available
        if upcoming_rows:
            fixture_id = upcoming_rows[0]["fixture_id"]
            try:
                predictions = client.get("predictions", {"fixture": fixture_id})
                save_json(raw_dir / f"10_prediction_{fixture_id}.json", predictions)
                summary["tests"]["predictions"] = {
                    "ok": True,
                    "fixture_id": fixture_id,
                    "response_count": len(predictions.get("response", [])),
                    "has_prediction_data": bool(predictions.get("response")),
                }
            except Exception as exc:
                summary["tests"]["predictions"] = {
                    "ok": False,
                    "fixture_id": fixture_id,
                    "error": str(exc),
                }
        else:
            summary["tests"]["predictions"] = {
                "ok": False,
                "skipped": True,
                "reason": "No upcoming fixture was available for the detected season.",
            }

        summary["completed_at_utc"] = utc_now()
        summary["requests_made_by_script"] = client.request_count
        summary["last_seen_quota_headers"] = client.last_quota

        # Basic fitness verdict
        teams_ok = summary["tests"]["teams"].get("team_count") == 20
        squads_ok = (
            summary["tests"]["squads"].get("teams_with_squads") == 20
            and summary["tests"]["squads"].get("total_players", 0) >= 400
        )
        summary["initial_verdict"] = {
            "suitable_as_current_epl_roster_source": bool(teams_ok and squads_ok),
            "reason": (
                "All 20 EPL teams and substantial squad data were returned."
                if teams_ok and squads_ok
                else "Team or squad completeness needs manual review."
            ),
        }

        save_json(output_dir / "evaluation_summary.json", summary)

        print("\n" + "=" * 68)
        print("API-FOOTBALL EVALUATION COMPLETE")
        print("=" * 68)
        print(f"Season parameter:       {season}")
        print(f"EPL teams returned:     {len(team_rows)}")
        print(f"Squad players returned: {len(squad_rows)}")
        print(f"Requests used:          {client.request_count}")
        print(
            "Daily requests left:   "
            f"{client.last_quota.get('daily_remaining') or 'not reported'}"
        )
        print(f"Output folder:          {output_dir}")
        print("=" * 68)
        print("\nPlease send back:")
        print("  1. The console output")
        print("  2. evaluation_summary.json")
        print("  3. api_football_epl_squads.csv\n")
        return 0

    except Exception as exc:
        summary["completed_at_utc"] = utc_now()
        summary["requests_made_by_script"] = client.request_count
        summary["last_seen_quota_headers"] = client.last_quota
        summary["fatal_error"] = str(exc)
        save_json(output_dir / "evaluation_summary.json", summary)

        print(f"\nFATAL ERROR: {exc}", file=sys.stderr)
        print(
            f"A partial summary was saved to: "
            f"{output_dir / 'evaluation_summary.json'}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
