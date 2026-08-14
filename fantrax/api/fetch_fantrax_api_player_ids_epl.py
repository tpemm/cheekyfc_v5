#!/usr/bin/env python3
r"""
fetch_fantrax_api_player_ids_epl.py

Purpose
-------
Fetch Fantrax EPL player ID/name data using the correct Fantrax sport code.

Key finding:
    getPlayerIds requires sport=EPL

This creates the player lookup we need to bridge:
    API roster player_id -> player name -> master CSV fantrax_player_id

Outputs:
    C:\Users\Tommy\fantrax_data\raw_data\fantrax_api\player_lookup\getPlayerIds_EPL.json
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\api_player_lookup.csv
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\api_player_lookup_report.txt

Run:
    python C:\Users\Tommy\fantrax_data\scripts\fetch_fantrax_api_player_ids_epl.py
"""

from __future__ import annotations

import sys

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


# Portable project configuration
_PROJECT_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT_BOOTSTRAP))
from config.project_paths import PROJECT_ROOT
BASE_URL = "https://www.fantrax.com/fxea/general"

RAW_OUT_DIR = PROJECT_ROOT / "raw_data" / "fantrax_api" / "player_lookup"
PROCESSED_OUT_DIR = PROJECT_ROOT / "processed_data" / "fantrax_api"

RAW_JSON_OUT = RAW_OUT_DIR / "getPlayerIds_EPL.json"
CSV_OUT = PROCESSED_OUT_DIR / "api_player_lookup.csv"
REPORT_OUT = PROCESSED_OUT_DIR / "api_player_lookup_report.txt"


def fetch_json(endpoint: str, params: dict[str, Any]) -> Any:
    url = f"{BASE_URL}/{endpoint}?{urlencode(params)}"
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 FantraxAnalyticsProject/1.0",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urlopen(req, timeout=45) as response:
        raw = response.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def flatten_any_player_json(data: Any) -> pd.DataFrame:
    """
    Fantrax getPlayerIds may return either:
    - dict of {id: name}
    - list of player objects
    - dict wrapping one of the above

    This recursively finds likely player records.
    """
    rows: list[dict[str, Any]] = []

    def is_probable_player_obj(obj: dict[str, Any]) -> bool:
        keys = {str(k).lower() for k in obj.keys()}
        has_id = any(k in keys for k in ["id", "playerid", "player_id", "fantraxid", "fantrax_id"])
        has_name = any(k in keys for k in ["name", "playername", "player_name", "fullName".lower(), "full_name"])
        return has_id and has_name

    def walk(obj: Any, parent_key: str | None = None) -> None:
        if isinstance(obj, dict):
            # Case: {"04tsb": "Some Player", ...}
            scalar_values = [v for v in obj.values() if isinstance(v, (str, int, float))]
            if obj and len(scalar_values) == len(obj):
                # Treat as id -> name if keys look ID-ish and values look name-ish.
                for k, v in obj.items():
                    if isinstance(v, str):
                        rows.append({
                            "api_player_id": str(k),
                            "api_player_name": v,
                            "source_shape": "dict_id_to_name",
                        })
                return

            if is_probable_player_obj(obj):
                lower_map = {str(k).lower(): k for k in obj.keys()}

                id_key = None
                for cand in ["id", "playerid", "player_id", "fantraxid", "fantrax_id"]:
                    if cand in lower_map:
                        id_key = lower_map[cand]
                        break

                name_key = None
                for cand in ["name", "playername", "player_name", "fullname", "full_name"]:
                    if cand in lower_map:
                        name_key = lower_map[cand]
                        break

                row = {
                    "api_player_id": obj.get(id_key),
                    "api_player_name": obj.get(name_key),
                    "source_shape": "player_object",
                }

                # Preserve useful extras.
                for extra in ["team", "teamName", "team_name", "position", "pos", "status"]:
                    if extra in obj:
                        row[extra] = obj.get(extra)

                rows.append(row)
                return

            for key, value in obj.items():
                walk(value, str(key))

        elif isinstance(obj, list):
            for item in obj:
                walk(item, parent_key)

    walk(data)

    df = pd.DataFrame(rows)

    if len(df):
        df["api_player_id"] = df["api_player_id"].astype(str).str.strip()
        df["api_player_name"] = df["api_player_name"].astype(str).str.strip()
        df = df.dropna(subset=["api_player_id", "api_player_name"])
        df = df[df["api_player_id"].ne("") & df["api_player_name"].ne("")]
        df = df.drop_duplicates(subset=["api_player_id"], keep="first")
        df = df.sort_values(["api_player_name", "api_player_id"]).reset_index(drop=True)

    return df


def main() -> None:
    RAW_OUT_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching Fantrax getPlayerIds?sport=EPL")
    data = fetch_json("getPlayerIds", {"sport": "EPL"})

    RAW_JSON_OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved raw JSON: {RAW_JSON_OUT}")

    # If Fantrax returns an API error, stop clearly.
    if isinstance(data, dict) and "error" in data:
        print("Fantrax returned an error:")
        print(json.dumps(data["error"], indent=2))
        REPORT_OUT.write_text(
            "Fantrax returned an error for getPlayerIds?sport=EPL:\n"
            + json.dumps(data["error"], indent=2),
            encoding="utf-8",
        )
        return

    df = flatten_any_player_json(data)

    df.to_csv(CSV_OUT, index=False, encoding="utf-8-sig")

    report = []
    report.append("Fantrax API Player Lookup Report")
    report.append("=" * 80)
    report.append("Endpoint: getPlayerIds?sport=EPL")
    report.append(f"Raw JSON: {RAW_JSON_OUT}")
    report.append(f"CSV:      {CSV_OUT}")
    report.append("")
    report.append(f"Rows flattened: {len(df):,}")
    report.append("")
    if len(df):
        report.append("Columns:")
        for c in df.columns:
            report.append(f"  - {c}")
        report.append("")
        report.append("Sample:")
        report.append(df.head(20).to_string(index=False))
    else:
        report.append("No player rows flattened. Inspect the raw JSON shape.")

    REPORT_OUT.write_text("\n".join(report), encoding="utf-8")

    print("\n".join(report))


if __name__ == "__main__":
    main()
