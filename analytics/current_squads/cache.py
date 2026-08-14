"""Deterministic snapshot persistence for current squads."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from analytics.current_squads.model import CURRENT_SQUAD_COLUMNS, CurrentSquadSchemaError


def write_snapshot(frame: pd.DataFrame, path: Path, metadata_path: Path) -> None:
    missing = set(CURRENT_SQUAD_COLUMNS) - set(frame.columns)
    if missing:
        raise CurrentSquadSchemaError("Snapshot missing columns: " + ", ".join(sorted(missing)))
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = frame[list(CURRENT_SQUAD_COLUMNS)].sort_values(
        ["team_code", "player_name", "provider_player_id"]
    )
    ordered.to_csv(path, index=False, encoding="utf-8-sig")
    metadata = {
        "provider": str(ordered["provider"].iloc[0]) if not ordered.empty else "",
        "retrieved_at": str(ordered["retrieved_at"].iloc[0]) if not ordered.empty else "",
        "season": str(ordered["season_id"].iloc[0]) if not ordered.empty else "",
        "player_count": int(len(ordered)),
        "team_count": int(ordered["team_code"].nunique()),
        "api_version": "bootstrap-static",
        "snapshot_file": path.name,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def read_snapshot(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig", dtype={"provider_player_id": str})
    missing = set(CURRENT_SQUAD_COLUMNS) - set(frame.columns)
    if missing:
        raise CurrentSquadSchemaError("Cached snapshot missing columns: " + ", ".join(sorted(missing)))
    if frame.empty:
        raise CurrentSquadSchemaError("Cached current-squad snapshot is empty")
    return frame
