#!/usr/bin/env python3
r"""
flatten_fantrax_api_player_lookup.py

Purpose
-------
Flatten the already-downloaded Fantrax getPlayerIds?sport=EPL JSON into a proper
one-row-per-player CSV.

This fixes the earlier issue where the flattener treated one player object like:
    {"fantraxId": "02m5b", "name": "Wood, Chris", ...}
as multiple id->value rows.

Inputs:
    C:\Users\Tommy\fantrax_data\raw_data\fantrax_api\player_lookup\getPlayerIds_EPL.json

Outputs:
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\api_player_lookup.csv
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\api_player_lookup_report.txt

Run:
    python C:\Users\Tommy\fantrax_data\scripts\flatten_fantrax_api_player_lookup.py
"""

from __future__ import annotations

import sys

import json
from pathlib import Path
from typing import Any

import pandas as pd


# Portable project configuration
_PROJECT_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT_BOOTSTRAP))
from config.project_paths import PROJECT_ROOT

RAW_JSON = PROJECT_ROOT / "raw_data" / "fantrax_api" / "player_lookup" / "getPlayerIds_EPL.json"

OUT_DIR = PROJECT_ROOT / "processed_data" / "fantrax_api"
CSV_OUT = OUT_DIR / "api_player_lookup.csv"
REPORT_OUT = OUT_DIR / "api_player_lookup_report.txt"


ID_KEYS = ["fantraxId", "fantrax_id", "id", "playerId", "player_id"]
NAME_KEYS = ["name", "playerName", "player_name", "fullName", "full_name"]


def lower_key_map(d: dict[str, Any]) -> dict[str, str]:
    return {str(k).lower(): k for k in d.keys()}


def get_by_possible_keys(d: dict[str, Any], keys: list[str]) -> Any:
    lk = lower_key_map(d)
    for key in keys:
        real_key = lk.get(key.lower())
        if real_key is not None:
            return d.get(real_key)
    return None


def is_player_object(d: dict[str, Any]) -> bool:
    return get_by_possible_keys(d, ID_KEYS) is not None and get_by_possible_keys(d, NAME_KEYS) is not None


def flatten_players(data: Any) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            # IMPORTANT: detect player object BEFORE generic dict handling.
            if is_player_object(obj):
                row = {
                    "api_player_id": get_by_possible_keys(obj, ID_KEYS),
                    "api_player_name": get_by_possible_keys(obj, NAME_KEYS),
                    "api_position": obj.get("position"),
                    "api_team_code": obj.get("team"),
                    "api_short_name": obj.get("shortName"),
                    "api_team_short_name": obj.get("teamShortName"),
                    "api_team_name": obj.get("teamName"),
                    "source_shape": "player_object",
                }

                # Keep any extra scalar fields for inspection.
                for k, v in obj.items():
                    if isinstance(v, (str, int, float, bool)) and k not in row:
                        extra_col = f"raw_{k}"
                        row[extra_col] = v

                rows.append(row)
                return

            # Handle rare shape: {"02m5b": "Wood, Chris"}
            # Only do this if the dict does NOT look like a player object.
            if obj and all(isinstance(v, str) for v in obj.values()):
                # Be conservative: only treat as id->name if there are many keys.
                # A single player object has few fields like fantraxId/name/team; don't use this path.
                if len(obj) > 20:
                    for k, v in obj.items():
                        rows.append({
                            "api_player_id": str(k),
                            "api_player_name": v,
                            "source_shape": "dict_id_to_name",
                        })
                    return

            for value in obj.values():
                walk(value)

        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data)

    df = pd.DataFrame(rows)

    if len(df):
        df["api_player_id"] = df["api_player_id"].astype(str).str.strip()
        df["api_player_name"] = df["api_player_name"].astype(str).str.strip()
        df = df[
            df["api_player_id"].notna()
            & df["api_player_name"].notna()
            & df["api_player_id"].ne("")
            & df["api_player_name"].ne("")
            & df["api_player_id"].ne("nan")
            & df["api_player_name"].ne("nan")
        ].copy()

        df = df.drop_duplicates(subset=["api_player_id"], keep="first")
        df = df.sort_values(["api_player_name", "api_player_id"]).reset_index(drop=True)

    return df


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not RAW_JSON.exists():
        raise FileNotFoundError(f"Missing raw JSON: {RAW_JSON}")

    data = json.loads(RAW_JSON.read_text(encoding="utf-8"))

    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"Raw JSON contains Fantrax API error: {data['error']}")

    df = flatten_players(data)

    df.to_csv(CSV_OUT, index=False, encoding="utf-8-sig")

    report = []
    report.append("Fantrax API Player Lookup Flatten Report")
    report.append("=" * 80)
    report.append(f"Input JSON: {RAW_JSON}")
    report.append(f"Output CSV: {CSV_OUT}")
    report.append("")
    report.append(f"Rows flattened: {len(df):,}")
    report.append("")
    if len(df):
        report.append("Columns:")
        for c in df.columns:
            report.append(f"  - {c}")
        report.append("")
        report.append("Sample:")
        report.append(df.head(25).to_string(index=False))
    else:
        report.append("No player rows found. Upload/get the raw JSON shape and we will adjust parser.")

    REPORT_OUT.write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
