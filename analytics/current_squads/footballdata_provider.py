"""Deprecated cached FootballData.io provider."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from analytics.current_squads.model import CURRENT_SQUAD_COLUMNS, CurrentSquadSchemaError
from analytics.current_squads.provider import CurrentSquadProvider
from analytics.draft.reliability import load_current_epl_squads


class FootballDataCurrentSquadProvider(CurrentSquadProvider):
    """Compatibility provider; Official FPL is the platform default."""

    name = "FootballData.io (deprecated)"

    def __init__(self, season_id: str, squad_root: Path, teams_path: Path) -> None:
        self.season_id = season_id
        self.squad_root = Path(squad_root)
        self.teams_path = Path(teams_path)

    def fetch_players(self) -> pd.DataFrame:
        squads, _ = load_current_epl_squads(self.squad_root, self.teams_path)
        if squads.empty:
            raise CurrentSquadSchemaError("FootballData.io cache contains no players")
        result = pd.DataFrame(
            {
                "provider_player_id": squads["footballdata_player_id"].astype(str),
                "player_name": squads["footballdata_player_name"],
                "first_name": "",
                "last_name": "",
                "team_name": squads["current_epl_team"],
                "team_code": squads["current_epl_team"],
                "position": "Unknown",
                "active_epl": True,
                "availability_status": "",
                "injury_news": "",
                "provider": self.name,
                "retrieved_at": squads.get("squad_retrieved_at", ""),
                "season_id": self.season_id,
            }
        )
        return result[list(CURRENT_SQUAD_COLUMNS)]
