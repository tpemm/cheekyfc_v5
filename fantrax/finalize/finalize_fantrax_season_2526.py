#!/usr/bin/env python3
r"""
finalize_fantrax_season_2526.py

Freeze the completed 2025/26 Fantrax season into:
    C:\Users\Tommy\fantrax_data\data\seasons\2526

This script does not call the live Fantrax API.
"""

from __future__ import annotations

import sys

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd


# Portable project configuration
_PROJECT_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT_BOOTSTRAP))
from config.project_paths import PROJECT_ROOT
SEASON_ID = "2526"
SEASON_LABEL = "2025/26"

DATA_DIR = PROJECT_ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"
ANALYTICS_DIR = DATA_DIR / "analytics_views"
REFERENCE_DIR = DATA_DIR / "reference"
RAW_DIR = DATA_DIR / "raw"

SEASON_ROOT = DATA_DIR / "seasons" / SEASON_ID
SEASON_PROCESSED = SEASON_ROOT / "processed"
SEASON_ANALYTICS = SEASON_ROOT / "analytics_views"
SEASON_REFERENCE = SEASON_ROOT / "reference"
SEASON_RAW_INDEX = SEASON_ROOT / "raw_index"
SEASON_REPORTS = SEASON_ROOT / "reports"

MANIFEST_PATH = SEASON_ROOT / "season_manifest.json"
VALIDATION_REPORT_PATH = SEASON_REPORTS / "finalization_validation_report.txt"
README_PATH = SEASON_ROOT / "README.txt"

REQUIRED_PROCESSED = [
    PROCESSED_DIR / f"master_player_weekly_{SEASON_ID}.csv",
    PROCESSED_DIR / f"fantrax_available_weekly_all_{SEASON_ID}.csv",
    PROCESSED_DIR / f"fantrax_rostered_weekly_all_{SEASON_ID}.csv",
    PROCESSED_DIR / f"understat_weekly_by_fantrax_gw_{SEASON_ID}.csv",
    PROCESSED_DIR / f"understat_match_to_fantrax_gw_{SEASON_ID}.csv",
    PROCESSED_DIR / f"manager_player_weekly_{SEASON_ID}.csv",
    PROCESSED_DIR / f"manager_week_summary_{SEASON_ID}.csv",
    PROCESSED_DIR / f"manager_season_summary_{SEASON_ID}.csv",
    PROCESSED_DIR / f"lineup_quality_summary_{SEASON_ID}.csv",
    PROCESSED_DIR / f"matchup_week_summary_{SEASON_ID}.csv",
]

OPTIONAL_PROCESSED = [
    PROCESSED_DIR / f"api_merge_validation_report_{SEASON_ID}.txt",
    PROCESSED_DIR / f"unmapped_fantrax_players_{SEASON_ID}.csv",
    PROCESSED_DIR / f"unmapped_understat_players_{SEASON_ID}.csv",
]

REQUIRED_ANALYTICS = [
    ANALYTICS_DIR / "league_table.csv",
    ANALYTICS_DIR / "weekly_awards.csv",
    ANALYTICS_DIR / "award_leaderboards.csv",
    ANALYTICS_DIR / "manager_streaks.csv",
    ANALYTICS_DIR / "lineup_changes.csv",
    ANALYTICS_DIR / "closest_games.csv",
    ANALYTICS_DIR / "biggest_blowouts.csv",
    ANALYTICS_DIR / "league_hub_cards.csv",
    ANALYTICS_DIR / "manager_efficiency_weekly.csv",
    ANALYTICS_DIR / "manager_efficiency_season.csv",
    ANALYTICS_DIR / "lineup_decision_details.csv",
    ANALYTICS_DIR / "ghost_points_player_weekly.csv",
    ANALYTICS_DIR / "ghost_points_player_leaders.csv",
    ANALYTICS_DIR / "ghost_points_manager_weekly.csv",
    ANALYTICS_DIR / "ghost_points_manager_season.csv",
    ANALYTICS_DIR / "position_points_manager_weekly.csv",
    ANALYTICS_DIR / "position_points_manager_season.csv",
    ANALYTICS_DIR / "roster_adds_weekly.csv",
    ANALYTICS_DIR / "roster_adds_leaders.csv",
    ANALYTICS_DIR / "manager_awards_dynamic.csv",
    ANALYTICS_DIR / "manager_profile_summary.csv",
]

OPTIONAL_ANALYTICS = [
    ANALYTICS_DIR / "manager_behavior_weekly.csv",
    ANALYTICS_DIR / "manager_behavior_season.csv",
    ANALYTICS_DIR / "formation_weekly.csv",
    ANALYTICS_DIR / "formation_manager_summary.csv",
    ANALYTICS_DIR / "formation_league_summary.csv",
    ANALYTICS_DIR / "league_awards_report.txt",
    ANALYTICS_DIR / "efficiency_ghost_awards_report.txt",
    ANALYTICS_DIR / "formation_report.txt",
]

REQUIRED_REFERENCE = [
    REFERENCE_DIR / "understat_fantrax_player_id_map.csv",
]

OPTIONAL_REFERENCE = [
    REFERENCE_DIR / f"api_to_master_player_id_bridge_{SEASON_ID}.csv",
    REFERENCE_DIR / f"api_to_master_player_id_bridge_candidates_{SEASON_ID}.csv",
    REFERENCE_DIR / f"api_to_master_player_id_bridge_unresolved_{SEASON_ID}.csv",
]

RAW_INDEX_FILES = [
    RAW_DIR / "understat" / f"understat_schedule_{SEASON_ID}_ENG-Premier_League.csv",
    RAW_DIR / "understat" / f"understat_player_match_stats_{SEASON_ID}_ENG-Premier_League.csv",
    RAW_DIR / "understat" / f"understat_players_season_{SEASON_ID}_ENG-Premier_League.csv",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(source: Path, frozen: Path | None = None) -> dict:
    stat = source.stat()
    record = {
        "source_path": str(source),
        "filename": source.name,
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "sha256": sha256_file(source),
    }
    if frozen is not None:
        record["frozen_path"] = str(frozen)
    return record


def require_files(paths: Iterable[Path]) -> None:
    missing = [path for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Required files are missing:\n" + "\n".join(f"  - {p}" for p in missing)
        )


def copy_file(source: Path, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source.name
    shutil.copy2(source, destination)
    return destination


def validate_historical_data() -> tuple[list[str], dict]:
    report: list[str] = []
    metrics: dict = {}

    master = pd.read_csv(
        PROCESSED_DIR / f"master_player_weekly_{SEASON_ID}.csv",
        encoding="utf-8-sig",
        low_memory=False,
    )
    manager_player = pd.read_csv(
        PROCESSED_DIR / f"manager_player_weekly_{SEASON_ID}.csv",
        encoding="utf-8-sig",
        low_memory=False,
    )
    manager_week = pd.read_csv(
        PROCESSED_DIR / f"manager_week_summary_{SEASON_ID}.csv",
        encoding="utf-8-sig",
        low_memory=False,
    )
    manager_season = pd.read_csv(
        PROCESSED_DIR / f"manager_season_summary_{SEASON_ID}.csv",
        encoding="utf-8-sig",
        low_memory=False,
    )
    matchup_week = pd.read_csv(
        PROCESSED_DIR / f"matchup_week_summary_{SEASON_ID}.csv",
        encoding="utf-8-sig",
        low_memory=False,
    )

    master_gw = pd.to_numeric(master["fantrax_gw"], errors="coerce")
    manager_week_gw = pd.to_numeric(manager_week["fantrax_gw"], errors="coerce")

    metrics.update({
        "master_rows": int(len(master)),
        "master_min_gw": int(master_gw.min()) if master_gw.notna().any() else None,
        "master_max_gw": int(master_gw.max()) if master_gw.notna().any() else None,
        "master_unique_gws": int(master_gw.nunique()),
        "manager_player_rows": int(len(manager_player)),
        "manager_week_rows": int(len(manager_week)),
        "manager_week_unique_gws": int(manager_week_gw.nunique()),
        "manager_season_rows": int(len(manager_season)),
        "matchup_week_rows": int(len(matchup_week)),
    })

    errors: list[str] = []
    warnings: list[str] = []

    if metrics["master_min_gw"] != 1 or metrics["master_max_gw"] != 38:
        errors.append("Master does not cover GW1 through GW38.")
    if metrics["master_unique_gws"] != 38:
        errors.append("Master does not contain exactly 38 unique gameweeks.")
    if metrics["manager_week_unique_gws"] != 38:
        errors.append("Manager-week summary does not contain exactly 38 unique gameweeks.")
    if metrics["manager_season_rows"] != 12:
        errors.append(f"Expected 12 manager-season rows, found {metrics['manager_season_rows']}.")
    if metrics["manager_player_rows"] != metrics["master_rows"]:
        errors.append("manager_player_weekly row count does not match master_player_weekly.")

    if {"fantrax_gw", "api_team_id"}.issubset(manager_week.columns):
        duplicate_count = int(
            manager_week.duplicated(["fantrax_gw", "api_team_id"], keep=False).sum()
        )
        metrics["duplicate_manager_week_rows"] = duplicate_count
        if duplicate_count:
            errors.append(f"manager_week_summary has {duplicate_count} duplicate manager/GW rows.")

    if {"fantrax_gw", "fantrax_player_id"}.issubset(master.columns):
        valid = master[
            master["fantrax_player_id"].notna()
            & master["fantrax_player_id"].astype(str).str.strip().ne("")
        ]
        duplicate_count = int(
            valid.duplicated(["fantrax_gw", "fantrax_player_id"], keep=False).sum()
        )
        metrics["duplicate_master_player_week_rows"] = duplicate_count
        if duplicate_count:
            errors.append(f"Master has {duplicate_count} duplicate player/GW rows.")

    if "is_rostered_api" in manager_player.columns:
        rostered = manager_player["is_rostered_api"].astype(str).str.lower().isin(
            ["true", "1", "yes"]
        )
        metrics["historical_rostered_rows"] = int(rostered.sum())
        if metrics["historical_rostered_rows"] < 7000:
            warnings.append("Historical rostered-row count is below the expected ~7,165.")
    else:
        warnings.append("manager_player_weekly has no is_rostered_api column.")

    metrics["errors"] = errors
    metrics["warnings"] = warnings

    report.extend([
        f"Season: {SEASON_LABEL} ({SEASON_ID})",
        f"Master rows: {metrics['master_rows']:,}",
        f"Master gameweeks: {metrics['master_min_gw']}–{metrics['master_max_gw']} "
        f"({metrics['master_unique_gws']} unique)",
        f"Manager-player rows: {metrics['manager_player_rows']:,}",
        f"Manager-week rows: {metrics['manager_week_rows']:,}",
        f"Manager-season rows: {metrics['manager_season_rows']:,}",
        f"Matchup-week rows: {metrics['matchup_week_rows']:,}",
    ])

    if "historical_rostered_rows" in metrics:
        report.append(
            f"Historical rostered rows in gold table: "
            f"{metrics['historical_rostered_rows']:,}"
        )

    report.append("")
    report.append(
        "PASS: No blocking historical-data validation errors."
        if not errors
        else "ERRORS:"
    )
    if errors:
        report.extend(f"- {message}" for message in errors)

    if warnings:
        report.append("")
        report.append("WARNINGS:")
        report.extend(f"- {message}" for message in warnings)

    return report, metrics


def main() -> None:
    print("=" * 90)
    print(f"Finalize Fantrax Season {SEASON_LABEL}")
    print("=" * 90)

    require_files(REQUIRED_PROCESSED)
    require_files(REQUIRED_ANALYTICS)
    require_files(REQUIRED_REFERENCE)

    validation_lines, metrics = validate_historical_data()
    print("\n".join(validation_lines))

    if metrics["errors"]:
        raise RuntimeError("Historical validation failed. Nothing was frozen.")

    for folder in [
        SEASON_PROCESSED,
        SEASON_ANALYTICS,
        SEASON_REFERENCE,
        SEASON_RAW_INDEX,
        SEASON_REPORTS,
    ]:
        folder.mkdir(parents=True, exist_ok=True)

    manifest_files: list[dict] = []

    for source in REQUIRED_PROCESSED + OPTIONAL_PROCESSED:
        if source.exists():
            frozen = copy_file(source, SEASON_PROCESSED)
            manifest_files.append(file_record(source, frozen))

    for source in REQUIRED_ANALYTICS + OPTIONAL_ANALYTICS:
        if source.exists():
            frozen = copy_file(source, SEASON_ANALYTICS)
            manifest_files.append(file_record(source, frozen))

    for source in REQUIRED_REFERENCE + OPTIONAL_REFERENCE:
        if source.exists():
            frozen = copy_file(source, SEASON_REFERENCE)
            record = file_record(source, frozen)
            if source.name.startswith("api_to_master_player_id_bridge"):
                record["authoritative"] = False
                record["note"] = (
                    "Audit-only copy. The live offseason API refresh may have changed this file."
                )
            else:
                record["authoritative"] = True
            manifest_files.append(record)

    for source in RAW_INDEX_FILES:
        if source.exists():
            frozen = copy_file(source, SEASON_RAW_INDEX)
            manifest_files.append(file_record(source, frozen))

    finalized_at = datetime.now().isoformat(timespec="seconds")

    validation_text = [
        "Fantrax Historical Season Finalization Validation",
        "=" * 90,
        f"Finalized at: {finalized_at}",
        "",
        *validation_lines,
        "",
        "Important:",
        "- Live Fantrax API files were not used to rebuild the frozen season.",
        "- Frozen gold/analytics files are the authoritative 2025/26 historical layer.",
        "- Any copied live API bridge files are audit-only and non-authoritative.",
    ]
    VALIDATION_REPORT_PATH.write_text("\n".join(validation_text), encoding="utf-8")

    manifest = {
        "season_id": SEASON_ID,
        "season_label": SEASON_LABEL,
        "finalized_at": finalized_at,
        "status": "finalized",
        "season_root": str(SEASON_ROOT),
        "live_api_used": False,
        "validation_metrics": metrics,
        "files": manifest_files,
        "notes": [
            "Historical gold tables are authoritative.",
            "Use a separate 2627 season folder/config for the next season.",
        ],
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    README_PATH.write_text(
        f"""Fantrax Historical Season: {SEASON_LABEL}

Status
------
FINALIZED

Processed:
{SEASON_PROCESSED}

Analytics:
{SEASON_ANALYTICS}

Reference:
{SEASON_REFERENCE}

Manifest:
{MANIFEST_PATH}

Validation report:
{VALIDATION_REPORT_PATH}

Do not run live Fantrax API refreshes against this frozen season.
""",
        encoding="utf-8",
    )

    print()
    print("=" * 90)
    print("FINALIZATION COMPLETE")
    print("=" * 90)
    print(f"Frozen season folder: {SEASON_ROOT}")
    print(f"Manifest:             {MANIFEST_PATH}")
    print(f"Validation report:    {VALIDATION_REPORT_PATH}")


if __name__ == "__main__":
    main()
