#!/usr/bin/env python3
r"""
diagnose_rostered_duplicates.py

Purpose
-------
Find exactly where duplicate rostered rows are coming from when build_master_weekly.py fails with:

    same player appears multiple times in same GW

Run:
    python C:\Users\Tommy\fantrax_data\scripts\diagnose_rostered_duplicates.py

Outputs:
    C:\Users\Tommy\fantrax_data\data\processed\duplicate_rostered_player_debug.csv
    C:\Users\Tommy\fantrax_data\data\processed\duplicate_rostered_player_file_debug.csv
"""

from __future__ import annotations

import sys

from pathlib import Path
import re
import pandas as pd


# Portable project configuration
_PROJECT_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT_BOOTSTRAP))
from config.project_paths import PROJECT_ROOT
ROSTER_DIR = PROJECT_ROOT / "data" / "raw" / "fantrax" / "team_rosters_weekly"
OUT_DUPES = PROJECT_ROOT / "data" / "processed" / "duplicate_rostered_player_debug.csv"
OUT_FILES = PROJECT_ROOT / "data" / "processed" / "duplicate_rostered_player_file_debug.csv"


def extract_gw(path: Path) -> int | None:
    m = re.search(r"GW(\d+)", path.name, flags=re.IGNORECASE)
    return int(m.group(1)) if m else None


def extract_manager(path: Path) -> str:
    m = re.search(r"weeklystats_(.*?)_GW\d+", path.name, flags=re.IGNORECASE)
    return m.group(1) if m else ""


def find_player_id_col(df: pd.DataFrame) -> str | None:
    candidates = ["fantrax_player_id", "Player ID", "player_id", "ID", "id"]
    for c in candidates:
        if c in df.columns:
            return c

    for c in df.columns:
        if "id" in c.lower():
            return c

    return None


def find_player_name_col(df: pd.DataFrame) -> str | None:
    candidates = ["mgr_player", "Player", "player", "Name", "name"]
    for c in candidates:
        if c in df.columns:
            return c

    for c in df.columns:
        if "player" in c.lower() or "name" in c.lower():
            return c

    return None


def clean_id(x: object) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip().replace("*", "")


def main() -> None:
    files = sorted(ROSTER_DIR.rglob("*.csv"))
    print(f"Roster dir: {ROSTER_DIR}")
    print(f"CSV files found: {len(files):,}")

    rows = []
    file_rows = []

    for path in files:
        gw = extract_gw(path)
        manager = extract_manager(path)

        try:
            df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(path, dtype=str, encoding="latin1")
        except Exception as exc:
            print(f"FAILED reading {path}: {exc}")
            continue

        id_col = find_player_id_col(df)
        name_col = find_player_name_col(df)

        file_rows.append({
            "file": str(path),
            "filename": path.name,
            "gw": gw,
            "manager": manager,
            "rows": len(df),
            "id_col": id_col,
            "name_col": name_col,
            "columns": "|".join(df.columns.astype(str)),
        })

        if not id_col:
            continue

        for idx, row in df.iterrows():
            rows.append({
                "file": str(path),
                "filename": path.name,
                "gw": gw,
                "manager": manager,
                "row_number": idx + 2,
                "fantrax_player_id_clean": clean_id(row.get(id_col)),
                "raw_player_id": row.get(id_col),
                "player_name": row.get(name_col) if name_col else "",
            })

    all_rows = pd.DataFrame(rows)
    file_debug = pd.DataFrame(file_rows)

    OUT_DUPES.parent.mkdir(parents=True, exist_ok=True)
    file_debug.to_csv(OUT_FILES, index=False, encoding="utf-8-sig")

    if all_rows.empty:
        print("No roster rows parsed.")
        return

    counts = (
        all_rows
        .groupby(["gw", "fantrax_player_id_clean"], dropna=False)
        .size()
        .reset_index(name="dupe_count")
    )

    dupes = counts[counts["dupe_count"] > 1].copy()

    debug = all_rows.merge(dupes, on=["gw", "fantrax_player_id_clean"], how="inner")
    debug = debug.sort_values(["gw", "fantrax_player_id_clean", "manager", "filename"])

    debug.to_csv(OUT_DUPES, index=False, encoding="utf-8-sig")

    print()
    print(f"Duplicate player/GW groups: {len(dupes):,}")
    if len(debug):
        print(debug.head(50).to_string(index=False))

    print()
    print(f"Saved duplicate debug: {OUT_DUPES}")
    print(f"Saved file debug:      {OUT_FILES}")
    print()
    print("Next step:")
    print("Open duplicate_rostered_player_debug.csv and check which manager files contain:")
    print("  GW37 player IDs 06clz and 06ezb")
    print("Then either delete/re-download the bad manager CSV(s), or send me what the rows show.")


if __name__ == "__main__":
    main()
