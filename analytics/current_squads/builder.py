"""Refresh current squads independently from downstream registry builds."""

from __future__ import annotations

import argparse
from pathlib import Path

from analytics.current_squads.cache import write_snapshot
from analytics.current_squads.fpl_provider import FPLCurrentSquadProvider

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def refresh_current_squad(season_id: str = "2627") -> Path:
    frame = FPLCurrentSquadProvider(season_id).fetch_players()
    folder = PROJECT_ROOT / "data" / "reference" / "current_squads"
    path = folder / f"fpl_players_{season_id}.csv"
    write_snapshot(frame, path, folder / f"fpl_players_{season_id}.metadata.json")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season-id", default="2627")
    args = parser.parse_args()
    path = refresh_current_squad(args.season_id)
    print(f"Saved current-squad snapshot: {path}")


if __name__ == "__main__":
    main()
