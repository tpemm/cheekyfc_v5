from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from integrations.footballdata_client import FootballDataAPIError, FootballDataClient


def _records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data", [])
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for key in ("leagues", "results", "items", "matches", "teams", "seasons"):
            value = data.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def _contains_premier_league(row: dict[str, Any]) -> bool:
    text = json.dumps(row, ensure_ascii=False).lower()
    return "premier league" in text and ("england" in text or "english" in text)


def main() -> int:
    client = FootballDataClient()

    try:
        usage = client.usage()
        print("\nAPI connection: OK")
        print("Usage metadata:")
        print(json.dumps(usage.get("data", usage.get("meta", {})), indent=2))

        search_payload = client.search("English Premier League", force_refresh=True)
        candidates = [row for row in _records(search_payload) if _contains_premier_league(row)]

        if not candidates:
            leagues_payload = client.leagues(force_refresh=True)
            candidates = [row for row in _records(leagues_payload) if _contains_premier_league(row)]

        print("\nPremier League candidates:")
        if not candidates:
            print("No exact candidate found. Inspect data/raw/footballdata_io/search_english_premier_league.json")
            return 2

        for index, candidate in enumerate(candidates[:5], start=1):
            print(f"[{index}] {json.dumps(candidate, ensure_ascii=False)}")

        league = candidates[0]
        league_id = league.get("id") or league.get("league_id")
        if league_id is None and isinstance(league.get("league"), dict):
            league_id = league["league"].get("id")

        if league_id is None:
            print("\nCould not automatically locate league_id in the response.")
            return 3

        seasons_payload = client.league_seasons(int(league_id), force_refresh=True)
        seasons = _records(seasons_payload)
        print(f"\nSeasons for league {league_id}:")
        for season in seasons[:10]:
            print(json.dumps(season, ensure_ascii=False))

        print("\nSaved raw responses under data/raw/footballdata_io/")
        print("Next: identify the 2025/26 and 2026/27 season IDs, then test teams, squads, matches, and stats.")
        return 0

    except (FootballDataAPIError, ValueError) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
