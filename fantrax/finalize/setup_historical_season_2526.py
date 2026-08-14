#!/usr/bin/env python3
r"""
setup_historical_season_2526.py

Purpose
-------
Finish the frozen 2025/26 historical season by:

1. Rebuilding manager behavior analytics.
2. Rebuilding formation analytics.
3. Copying those new analytics into data\seasons\2526\analytics_views.
4. Creating season_results.csv from the playoff finishing order.
5. Creating season_metadata.json with champion and season format.

Run:
    python C:\Users\Tommy\fantrax_data\scripts\setup_historical_season_2526.py

The script will display the 12 teams and ask you to enter their final playoff order
using the displayed numbers, for example:

    1,4,2,3,5,6,7,8,9,10,11,12
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


# Portable project configuration
_PROJECT_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT_BOOTSTRAP))
from config.project_paths import PROJECT_ROOT
ANALYTICS_SCRIPTS_DIR = PROJECT_ROOT / "fantrax" / "analytics"
ACTIVE_ANALYTICS = PROJECT_ROOT / "data" / "analytics_views"
SEASON_ROOT = PROJECT_ROOT / "data" / "seasons" / "2526"
SEASON_ANALYTICS = SEASON_ROOT / "analytics_views"

PYTHON_EXE = Path(sys.executable)

BEHAVIOR_SCRIPT = ANALYTICS_SCRIPTS_DIR / "build_manager_behavior_views.py"
FORMATION_SCRIPT = ANALYTICS_SCRIPTS_DIR / "build_formation_views.py"

LEAGUE_TABLE_FILE = SEASON_ANALYTICS / "league_table.csv"
RESULTS_FILE = SEASON_ROOT / "season_results.csv"
METADATA_FILE = SEASON_ROOT / "season_metadata.json"

EXTRA_ANALYTICS = [
    "manager_behavior_weekly.csv",
    "manager_behavior_season.csv",
    "formation_weekly.csv",
    "formation_manager_summary.csv",
    "formation_league_summary.csv",
    "formation_report.txt",
]


def run_script(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing script: {path}")

    print()
    print("=" * 88)
    print(f"Running {path.name}")
    print("=" * 88)

    proc = subprocess.run(
        [str(PYTHON_EXE), str(path)],
        cwd=str(PROJECT_ROOT),
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{path.name} failed with exit code {proc.returncode}")


def clean_name(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).replace("â€™", "’").replace("ðŸ¤¡", "").replace("🤡", "")
    return " ".join(text.split()).strip()


def main() -> None:
    print("=" * 88)
    print("Set Up Historical Fantrax Season 2025/26")
    print("=" * 88)

    run_script(BEHAVIOR_SCRIPT)
    run_script(FORMATION_SCRIPT)

    SEASON_ANALYTICS.mkdir(parents=True, exist_ok=True)

    print()
    print("Copying new analytics into the frozen season...")
    for name in EXTRA_ANALYTICS:
        source = ACTIVE_ANALYTICS / name
        if source.exists():
            destination = SEASON_ANALYTICS / name
            shutil.copy2(source, destination)
            print(f"  copied {name}")
        else:
            print(f"  missing optional output: {source}")

    if not LEAGUE_TABLE_FILE.exists():
        raise FileNotFoundError(f"Missing frozen league table: {LEAGUE_TABLE_FILE}")

    league = pd.read_csv(LEAGUE_TABLE_FILE, encoding="utf-8-sig")
    league["api_team_name"] = league["api_team_name"].map(clean_name)
    league["_regular_rank"] = pd.to_numeric(
        league.get("official_rank"),
        errors="coerce",
    )

    league = league.sort_values(["_regular_rank", "api_team_name"]).reset_index(drop=True)

    print()
    print("Teams by regular-season rank:")
    for idx, row in league.iterrows():
        regular_rank = row.get("_regular_rank")
        rank_text = int(regular_rank) if pd.notna(regular_rank) else "?"
        print(f"  {idx + 1:>2}. {row['api_team_name']}  (regular-season rank {rank_text})")

    print()
    print("Enter the FINAL playoff finishing order using each team's number.")
    print("Use every number exactly once, separated by commas.")
    print("Example: 1,4,2,3,5,6,7,8,9,10,11,12")
    raw_order = input("Final order: ").strip()

    try:
        order = [int(x.strip()) for x in raw_order.split(",") if x.strip()]
    except ValueError as exc:
        raise ValueError("Final order must contain only comma-separated numbers.") from exc

    expected = list(range(1, len(league) + 1))
    if sorted(order) != expected:
        raise ValueError(
            f"Final order must use every number from 1 to {len(league)} exactly once."
        )

    playoff_labels = {
        1: "Champion",
        2: "Runner-up",
        3: "Third place",
        4: "Fourth place",
    }

    rows = []
    for final_rank, selected_number in enumerate(order, start=1):
        team = league.iloc[selected_number - 1]

        rows.append({
            "season_id": "2526",
            "season_label": "2025/26",
            "final_rank": final_rank,
            "api_team_id": team.get("api_team_id"),
            "api_team_name": team.get("api_team_name"),
            "playoff_result": playoff_labels.get(final_rank, f"{final_rank}th place"),
            "regular_season_rank": int(team["_regular_rank"]) if pd.notna(team["_regular_rank"]) else None,
            "official_record": team.get("official_record"),
            "official_total_points_for": team.get("official_total_points_for"),
            "total_starter_points": team.get("total_starter_points"),
        })

    results = pd.DataFrame(rows)
    results.to_csv(RESULTS_FILE, index=False, encoding="utf-8-sig")

    champion = results.iloc[0]
    runner_up = results.iloc[1]

    metadata = {
        "season_id": "2526",
        "season_label": "2025/26",
        "league_name": "Cheeky FC",
        "format": "Regular season plus knockout playoffs",
        "regular_season_end_gw": 35,
        "playoff_gameweeks": [36, 37, 38],
        "champion_team_id": champion["api_team_id"],
        "champion_team_name": champion["api_team_name"],
        "runner_up_team_id": runner_up["api_team_id"],
        "runner_up_team_name": runner_up["api_team_name"],
        "finalized": True,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "notes": [
            "Final standings are based on playoff finishing order.",
            "Regular-season table remains available separately.",
            "Future seasons use league-table placement without playoffs.",
        ],
    }
    METADATA_FILE.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print("=" * 88)
    print("HISTORICAL SEASON SETUP COMPLETE")
    print("=" * 88)
    print(f"Season results:  {RESULTS_FILE}")
    print(f"Season metadata: {METADATA_FILE}")
    print()
    print("Champion:", champion["api_team_name"])
    print("Runner-up:", runner_up["api_team_name"])


if __name__ == "__main__":
    main()
