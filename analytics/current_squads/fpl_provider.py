"""Official Fantasy Premier League current-squad provider."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Callable
from urllib.request import Request, urlopen

import pandas as pd

from analytics.current_squads.model import (
    CURRENT_SQUAD_COLUMNS,
    CurrentSquadError,
    CurrentSquadSchemaError,
)
from analytics.current_squads.normalization import FPL_POSITION, normalize_team
from analytics.current_squads.provider import CurrentSquadProvider

FPL_BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"


def _download(url: str, timeout: float) -> bytes:
    request = Request(url, headers={"User-Agent": "FantraxAnalytics/5 player-registry"})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


class FPLCurrentSquadProvider(CurrentSquadProvider):
    name = "Official FPL API"

    def __init__(
        self,
        season_id: str,
        *,
        timeout: float = 20,
        downloader: Callable[[str, float], bytes] = _download,
        retrieved_at: datetime | None = None,
    ) -> None:
        self.season_id = season_id
        self.timeout = timeout
        self.downloader = downloader
        self.retrieved_at = retrieved_at

    def fetch_players(self) -> pd.DataFrame:
        try:
            payload = json.loads(
                self.downloader(FPL_BOOTSTRAP_URL, self.timeout).decode("utf-8")
            )
        except CurrentSquadError:
            raise
        except Exception as exc:
            raise CurrentSquadError(f"FPL bootstrap download failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise CurrentSquadSchemaError("FPL bootstrap root must be an object")
        elements = payload.get("elements")
        teams = payload.get("teams")
        if not isinstance(elements, list) or not isinstance(teams, list):
            raise CurrentSquadSchemaError("FPL bootstrap requires elements and teams arrays")
        if not elements:
            raise CurrentSquadSchemaError("FPL bootstrap returned no players")
        team_lookup = {
            item.get("id"): item
            for item in teams
            if isinstance(item, dict) and item.get("id") is not None
        }
        retrieved = (self.retrieved_at or datetime.now(timezone.utc)).isoformat()
        rows = []
        for player in elements:
            if not isinstance(player, dict):
                raise CurrentSquadSchemaError("FPL elements must contain objects")
            missing = {"id", "first_name", "second_name", "team", "element_type"} - set(player)
            if missing:
                raise CurrentSquadSchemaError(
                    "FPL player is missing fields: " + ", ".join(sorted(missing))
                )
            team = team_lookup.get(player["team"])
            if team is None:
                raise CurrentSquadSchemaError(
                    f"FPL player {player['id']} references unknown team {player['team']}"
                )
            first = str(player["first_name"]).strip()
            last = str(player["second_name"]).strip()
            rows.append(
                {
                    "provider_player_id": str(player["id"]),
                    "player_name": f"{first} {last}".strip(),
                    "first_name": first,
                    "last_name": last,
                    "team_name": str(team.get("name", "")).strip(),
                    "team_code": normalize_team(team.get("short_name") or team.get("name")),
                    "position": FPL_POSITION.get(player["element_type"], "Unknown"),
                    "active_epl": True,
                    "availability_status": str(player.get("status", "")).strip(),
                    "injury_news": str(player.get("news", "")).strip(),
                    "provider": self.name,
                    "retrieved_at": retrieved,
                    "season_id": self.season_id,
                }
            )
        result = pd.DataFrame(rows, columns=CURRENT_SQUAD_COLUMNS)
        if result["provider_player_id"].duplicated().any():
            raise CurrentSquadSchemaError("FPL response contains duplicate player IDs")
        if result["team_code"].nunique() != 20:
            raise CurrentSquadSchemaError(
                f"FPL response contains {result['team_code'].nunique()} teams; expected 20"
            )
        return result.sort_values(
            ["team_code", "player_name", "provider_player_id"]
        ).reset_index(drop=True)
